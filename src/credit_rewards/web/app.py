from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from credit_rewards.client import CardDataClient, RewardsCCError
from credit_rewards.ingest.compare import (
    CardComparisonReport,
    RuleRow,
    compare_all,
    compare_card,
)
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.merchant_mapping import (
    MerchantNotFoundError,
    list_merchants,
    lookup_merchant_by_id,
    lookup_merchant_category,
    merchant_suggestions,
    resolve_merchant,
)
from credit_rewards.models import PurchaseContext
from credit_rewards.official_cpp import enrich_card_profile, fallback_program_table, resolve_card_official_cpp
from credit_rewards.recommend import recommend_best_cards
from credit_rewards.validation.dashboard import build_validation_dashboard
from credit_rewards.validation.summary_report import build_validation_summary_report
from credit_rewards.payment_ui.orchestrator import build_payment_ui_monitor_plan
from credit_rewards.wallet import load_wallet

STATIC_DIR = Path(__file__).resolve().parent / "static"
FETCH_EVIDENCE = os.getenv("CREDITREWARDS_FETCH_EVIDENCE", "1").lower() not in {
    "0",
    "false",
    "no",
}

app = FastAPI(title="CreditRewards", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class RecommendRequest(BaseModel):
    card_keys: list[str] | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1)
    mcc: str | None = Field(default=None, min_length=1)
    merchant_url: str | None = Field(default=None, min_length=1)
    merchant_name: str | None = Field(default=None, min_length=1)
    merchant_id: str | None = Field(default=None, min_length=1)
    amount_usd: float = Field(gt=0)


class MerchantResolveRequest(BaseModel):
    merchant_url: str | None = Field(default=None, min_length=1)
    merchant_name: str | None = Field(default=None, min_length=1)


def _all_registry_card_keys() -> list[str]:
    return [entry["card_key"] for entry in load_card_registry()]


def _resolve_purchase_category(body: RecommendRequest) -> tuple[str, dict[str, object] | None]:
    if body.category:
        if body.merchant_id and body.merchant_id.startswith("osm:"):
            match = lookup_merchant_category(
                merchant_id=body.merchant_id,
                category=body.category,
                merchant_name=body.merchant_name,
            )
            return body.category, match.to_dict()
        if body.merchant_id:
            try:
                match = lookup_merchant_by_id(body.merchant_id)
            except MerchantNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return match.spend_bonus_category_name, match.to_dict()
        return body.category, None

    if body.merchant_id:
        try:
            match = lookup_merchant_by_id(body.merchant_id)
        except MerchantNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return match.spend_bonus_category_name, match.to_dict()

    if body.merchant_url or body.merchant_name:
        try:
            match = lookup_merchant_category(
                merchant_url=body.merchant_url,
                merchant_name=body.merchant_name,
            )
        except MerchantNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return match.spend_bonus_category_name, match.to_dict()

    from credit_rewards.mcc_mapping import lookup_mcc_category, mcc_match_to_dict

    if body.mcc and not body.category:
        match = lookup_mcc_category(body.mcc)
        return match.spend_bonus_category_name, mcc_match_to_dict(match)
    if body.category:
        return body.category, None
    raise HTTPException(
        status_code=400,
        detail="Provide merchant_url, merchant_name, category, or mcc",
    )


def _enrich_wallet(cards):
    table = fallback_program_table()
    enriched = []
    for card in cards:
        detail = {
            "cardKey": card.card_key,
            "baseSpendEarnType": card.reward_program,
            "baseSpendEarnCurrency": card.base_earn_currency,
        }
        cpp, program = resolve_card_official_cpp(card.card_key, detail, table)
        enriched.append(enrich_card_profile(card, official_cpp=cpp, resolved_program=program))
    return enriched


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/compare")
def compare_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "compare.html")


@app.get("/validation")
def validation_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "validation.html")


@app.get("/validation-report")
def validation_report_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "validation-report.html")


@app.get("/api/payment-ui/monitor")
def api_payment_ui_monitor(skip_tests: bool = False) -> dict[str, object]:
    return build_payment_ui_monitor_plan(run_pytest=not skip_tests)


@app.get("/api/validation/monitor")
def api_validation_monitor(
    include_l2: bool = False,
    skip_network: bool = False,
) -> dict[str, object]:
    from credit_rewards.validation.orchestrator import build_monitor_plan

    return build_monitor_plan(include_l2=include_l2, skip_network=skip_network)


@app.get("/api/validation/independent")
def api_validation_independent() -> dict[str, object]:
    from credit_rewards.validation.independent import run_independent_validation

    return run_independent_validation(reimport_reference=False).to_dict()


@app.get("/api/validation")
def api_validation() -> dict[str, object]:
    return build_validation_dashboard(fetch_evidence=FETCH_EVIDENCE)


@app.get("/api/validation/report")
def api_validation_report() -> dict[str, object]:
    return build_validation_summary_report(fetch_evidence=FETCH_EVIDENCE)


def _registry_has(card_key: str) -> bool:
    return any(entry["card_key"] == card_key for entry in load_card_registry())


def _rule_to_api(rule: RuleRow) -> dict[str, Any]:
    desc = rule.spend_bonus_desc
    if len(desc) > 120:
        desc = desc[:119] + "…"
    return {
        "category_name": rule.spend_bonus_category_name,
        "multiplier": rule.earn_multiplier,
        "description": desc,
    }


def _diff_from_report(report: CardComparisonReport) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in report.matched:
        rows.append(
            {
                "category_name": match.scraped.spend_bonus_category_name,
                "status": "match",
                "scraped_multiplier": match.scraped.earn_multiplier,
                "reference_multiplier": match.reference.earn_multiplier,
            }
        )
    for mismatch in report.mismatches:
        base = {
            "note": mismatch.explanation,
            "evidence_verdict": mismatch.evidence_verdict,
            "evidence_action": mismatch.evidence_action,
            "evidence_summary": mismatch.evidence_summary,
            "evidence_scrape": mismatch.evidence_scrape,
            "evidence_reference": mismatch.evidence_reference,
        }
        if mismatch.mismatch_type == "multiplier_mismatch" and mismatch.scraped and mismatch.reference:
            status = "mismatch"
            if mismatch.evidence_verdict == "scrape_supported":
                status = "scrape_verified"
            elif mismatch.evidence_verdict == "reference_supported":
                status = "reference_verified"
            rows.append(
                {
                    "category_name": mismatch.scraped.spend_bonus_category_name,
                    "status": status,
                    "scraped_multiplier": mismatch.scraped.earn_multiplier,
                    "reference_multiplier": mismatch.reference.earn_multiplier,
                    **base,
                }
            )
        elif mismatch.mismatch_type == "missing_in_scrape" and mismatch.reference:
            status = "extra_reference"
            if mismatch.evidence_verdict == "reference_supported":
                status = "reference_verified"
            rows.append(
                {
                    "category_name": mismatch.reference.spend_bonus_category_name,
                    "status": status,
                    "reference_multiplier": mismatch.reference.earn_multiplier,
                    **base,
                }
            )
        elif mismatch.mismatch_type == "missing_in_reference" and mismatch.scraped:
            status = "extra_scrape"
            if mismatch.evidence_verdict in ("scrape_supported", "scrape_noise"):
                status = (
                    "scrape_verified"
                    if mismatch.evidence_verdict == "scrape_supported"
                    else "scrape_noise"
                )
            rows.append(
                {
                    "category_name": mismatch.scraped.spend_bonus_category_name,
                    "status": status,
                    "scraped_multiplier": mismatch.scraped.earn_multiplier,
                    **base,
                }
            )
        elif mismatch.mismatch_type == "base_rate_mismatch":
            status = "mismatch"
            if mismatch.evidence_verdict == "scrape_supported":
                status = "scrape_verified"
            rows.append(
                {
                    "category_name": "Base earn rate",
                    "status": status,
                    **base,
                }
            )
    return rows


def _report_to_api(report: CardComparisonReport) -> dict[str, Any]:
    registry_url = ""
    for entry in load_card_registry():
        if entry["card_key"] == report.card_key:
            registry_url = entry.get("url") or ""
            break
    notes = [m.explanation for m in report.mismatches if m.explanation]
    diff = _diff_from_report(report)
    return {
        "card_key": report.card_key,
        "card_name": report.card_name,
        "issuer": report.issuer,
        "issuer_url": report.source_url or registry_url,
        "last_scraped": report.scraped_at,
        "reference_synced_at": report.reference_synced_at,
        "scraped_rules": [_rule_to_api(r) for r in report.scraped_rules],
        "reference_rules": [_rule_to_api(r) for r in report.reference_rules],
        "diff": diff,
        "aligned": report.aligned,
        "scrape_verified": report.scrape_verified,
        "parser_fix_needed": report.parser_fix_needed,
        "mismatch_count": len(
            [d for d in diff if d["status"] in ("mismatch", "extra_scrape", "extra_reference", "scrape_noise")]
        ),
        "notes": notes,
        "detail": asdict(report),
    }


@app.get("/api/compare")
def api_compare_all() -> dict[str, object]:
    reports = compare_all(fetch_evidence=FETCH_EVIDENCE)
    cards = [_report_to_api(r) for r in reports]
    aligned_count = sum(1 for c in cards if c["aligned"])
    scrape_verified_count = sum(1 for c in cards if c["scrape_verified"])
    return {
        "total": len(cards),
        "aligned_count": aligned_count,
        "scrape_verified_count": scrape_verified_count,
        "parser_fix_count": sum(1 for c in cards if c["parser_fix_needed"]),
        "mismatch_count": len(cards) - aligned_count,
        "cards": cards,
    }


@app.get("/api/compare/{card_key}")
def api_compare_card(card_key: str) -> dict[str, object]:
    if not _registry_has(card_key):
        raise HTTPException(status_code=404, detail=f"Unknown card_key: {card_key}")
    return _report_to_api(compare_card(card_key, fetch_evidence=FETCH_EVIDENCE))


@app.get("/api/health")
def health() -> dict[str, object]:
    client = CardDataClient()
    return {
        "ok": True,
        "data_provider": client.provider,
        "live_api": client.is_configured,
    }


@app.get("/api/cards")
def api_cards() -> dict[str, object]:
    cards = []
    for entry in load_card_registry():
        cards.append(
            {
                "card_key": entry["card_key"],
                "issuer": entry.get("issuer") or "",
                "reward_program": entry.get("reward_program") or "",
            }
        )
    return {"total": len(cards), "cards": cards}


@app.get("/api/merchants")
def api_merchants(q: str | None = None) -> dict[str, object]:
    if q:
        return {"query": q, "suggestions": merchant_suggestions(q)}
    merchants = list_merchants()
    return {"total": len(merchants), "merchants": merchants}


@app.post("/api/merchant/resolve")
def api_merchant_resolve(body: MerchantResolveRequest) -> dict[str, object]:
    try:
        result = resolve_merchant(
            merchant_url=body.merchant_url,
            merchant_name=body.merchant_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.best:
        raise HTTPException(
            status_code=404,
            detail="No merchant match. Try another URL, store name, or pick from suggestions.",
        )
    return result.to_dict()


@app.post("/api/recommend")
def recommend(body: RecommendRequest) -> dict[str, object]:
    try:
        category, merchant_info = _resolve_purchase_category(body)
        card_keys = body.card_keys if body.card_keys else _all_registry_card_keys()
        wallet = _enrich_wallet(load_wallet(card_keys, CardDataClient()))
        purchase = PurchaseContext(category=category, amount_usd=body.amount_usd)
        results = recommend_best_cards(wallet, purchase)
    except RewardsCCError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not results:
        raise HTTPException(status_code=400, detail="No cards could be loaded.")

    top = results[0]
    return {
        "best": top.model_dump(),
        "rankings": [r.model_dump() for r in results],
        "live_api": CardDataClient().is_configured,
        "resolved_category": category,
        "merchant": merchant_info,
        "card_count": len(results),
        "full_library": body.card_keys is None,
    }
