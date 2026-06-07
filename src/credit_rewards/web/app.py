from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from credit_rewards.card_catalog import (
    catalog_coverage_stats,
    enrich_registry_cards,
    list_issuers,
    search_cards_by_issuer,
)
from credit_rewards.card_image import (
    apply_local_image_urls,
    fetch_card_image_url,
    fetch_card_image_urls,
    local_image_path,
    media_type_for_card_image,
    warm_card_images,
    warm_registry_card_images,
)
from credit_rewards.card_import import ensure_wallet_cards_in_db
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
from credit_rewards.web.accounts import (
    SESSION_COOKIE,
    SESSION_DAYS,
    AccountError,
    ensure_account_schema,
    get_user_wallet,
    login_user,
    logout_session,
    register_user,
    save_user_wallet,
    user_id_from_session,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
COOKIE_SECURE = os.getenv("CREDITREWARDS_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}
FETCH_EVIDENCE = os.getenv("CREDITREWARDS_FETCH_EVIDENCE", "1").lower() not in {
    "0",
    "false",
    "no",
}

app = FastAPI(title="CreditRewards", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _warm_images_async(card_keys: list[str] | None = None) -> None:
    keys = [k.strip() for k in (card_keys or []) if k and k.strip()]

    def _run() -> None:
        try:
            if keys:
                warm_card_images(keys)
            else:
                warm_registry_card_images()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


@app.on_event("startup")
def _startup_warm_registry_images() -> None:
    _warm_images_async()


class RecommendRequest(BaseModel):
    card_keys: list[str] | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1)
    mcc: str | None = Field(default=None, min_length=1)
    merchant_url: str | None = Field(default=None, min_length=1)
    merchant_name: str | None = Field(default=None, min_length=1)
    merchant_id: str | None = Field(default=None, min_length=1)
    amount_usd: float = Field(gt=0)
    purchase_channel: str | None = Field(default=None, pattern="^(online|in_store)$")


class MerchantResolveRequest(BaseModel):
    merchant_url: str | None = Field(default=None, min_length=1)
    merchant_name: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    purchase_channel: str | None = Field(default=None, pattern="^(online|in_store)$")


class WalletCardInput(BaseModel):
    card_key: str = Field(min_length=1)
    nickname: str = ""
    last4: str = ""


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    cards: list[WalletCardInput] = Field(min_length=1)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class WalletUpdateRequest(BaseModel):
    cards: list[WalletCardInput] = Field(min_length=1)


class CardImagesRequest(BaseModel):
    card_keys: list[str] = Field(min_length=1, max_length=48)


def _card_display_name(card_key: str) -> str:
    return card_key.replace("-", " ").title()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_DAYS * 86400,
        secure=COOKIE_SECURE,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, httponly=True, samesite="lax", secure=COOKIE_SECURE)


def _session_user_id(request: Request) -> int | None:
    return user_id_from_session(request.cookies.get(SESSION_COOKIE))


@app.on_event("startup")
def _startup_account_schema() -> None:
    ensure_account_schema()


def _all_registry_card_keys() -> list[str]:
    return [entry["card_key"] for entry in load_card_registry()]


def _resolve_purchase_category(body: RecommendRequest) -> tuple[str, dict[str, object] | None]:
    channel = body.purchase_channel

    if body.category and body.merchant_id:
        if body.merchant_id.startswith("osm:") or body.merchant_id.startswith("gmaps:"):
            match = lookup_merchant_category(
                merchant_id=body.merchant_id,
                category=body.category,
                merchant_name=body.merchant_name,
            )
            return body.category, match.to_dict()
        if body.merchant_id.startswith("web:"):
            match = lookup_merchant_category(
                merchant_id=body.merchant_id,
                category=body.category,
                merchant_name=body.merchant_name,
            )
            return body.category, match.to_dict()
        try:
            match = lookup_merchant_by_id(
                body.merchant_id,
                purchase_channel=channel,
            )
        except MerchantNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        confirmed = {**match.to_dict(), "spendBonusCategoryName": body.category}
        return body.category, confirmed

    if body.category:
        return body.category, None

    if body.merchant_id:
        try:
            match = lookup_merchant_by_id(body.merchant_id, purchase_channel=channel)
        except MerchantNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return match.spend_bonus_category_name, match.to_dict()

    if body.merchant_url or body.merchant_name:
        try:
            match = lookup_merchant_category(
                merchant_url=body.merchant_url,
                merchant_name=body.merchant_name,
                purchase_channel=channel,
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


@app.get("/manifest.webmanifest")
def web_manifest() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


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
    cards = apply_local_image_urls(enrich_registry_cards())
    return {"total": len(cards), "cards": cards}


@app.get("/api/cards/issuers")
def api_card_issuers() -> dict[str, object]:
    return {"issuers": list_issuers()}


@app.get("/api/cards/coverage")
def api_cards_coverage() -> dict[str, object]:
    return catalog_coverage_stats()


@app.get("/api/cards/by-issuer")
def api_cards_by_issuer(q: str, limit: int = 48) -> dict[str, object]:
    query = (q or "").strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Enter at least 2 characters for bank name")
    matches = search_cards_by_issuer(query, limit=min(limit, 40))
    return {"query": query, "matches": matches, "total": len(matches)}


@app.get("/api/cards/image")
def api_card_image(card_key: str) -> dict[str, object]:
    key = card_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="card_key required")
    url = fetch_card_image_url(key)
    return {"card_key": key, "image_url": url}


@app.get("/api/cards/image/file")
def api_card_image_file(card_key: str) -> FileResponse:
    key = card_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="card_key required")
    path = local_image_path(key)
    if not path:
        raise HTTPException(status_code=404, detail="Image not cached")
    return FileResponse(
        path,
        media_type=media_type_for_card_image(key),
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


@app.post("/api/cards/images")
def api_card_images(body: CardImagesRequest) -> dict[str, object]:
    images = fetch_card_image_urls(body.card_keys)
    return {"images": images}


@app.get("/api/merchants")
def api_merchants(
    q: str | None = None,
    purchase_channel: str | None = None,
) -> dict[str, object]:
    if q:
        return {
            "query": q,
            "purchaseChannel": purchase_channel or "in_store",
            "suggestions": merchant_suggestions(q, purchase_channel=purchase_channel),
        }
    merchants = list_merchants()
    return {"total": len(merchants), "merchants": merchants}


@app.post("/api/merchant/resolve")
def api_merchant_resolve(body: MerchantResolveRequest) -> dict[str, object]:
    try:
        result = resolve_merchant(
            merchant_url=body.merchant_url,
            merchant_name=body.merchant_name,
            latitude=body.latitude,
            longitude=body.longitude,
            purchase_channel=body.purchase_channel,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.best:
        detail = "No merchant match. Try another URL, store name, or pick from suggestions."
        channel = body.purchase_channel or (
            "online" if body.merchant_url else "in_store"
        )
        if channel == "in_store" and body.latitude is None and body.longitude is None:
            detail += " Allow location access for better nearby store matching."
        raise HTTPException(status_code=404, detail=detail)
    payload = result.to_dict()
    payload["usedLocation"] = body.latitude is not None and body.longitude is not None
    return payload


@app.get("/api/merchant/nearby")
def api_merchant_nearby(
    latitude: float,
    longitude: float,
    limit: int = 5,
) -> dict[str, object]:
    from credit_rewards.merchant_google_places import google_places_enabled, lookup_nearby_stores

    if not google_places_enabled():
        return {"places": [], "googlePlacesEnabled": False}
    capped = min(max(limit, 1), 8)
    places = lookup_nearby_stores(latitude, longitude, limit=capped)
    return {
        "places": places,
        "googlePlacesEnabled": True,
        "limit": capped,
    }


@app.get("/api/merchant/config")
def api_merchant_config() -> dict[str, object]:
    from credit_rewards.merchant_google_places import google_places_enabled
    from credit_rewards.merchant_nominatim import NOMINATIM_ENABLED

    enabled = google_places_enabled()
    return {
        "googlePlacesEnabled": enabled,
        "nominatimEnabled": NOMINATIM_ENABLED,
        "locationRecommended": enabled,
        "nearbyStoresEnabled": enabled,
    }


@app.post("/api/recommend")
def recommend(body: RecommendRequest) -> dict[str, object]:
    try:
        category, merchant_info = _resolve_purchase_category(body)
        card_keys = body.card_keys if body.card_keys else _all_registry_card_keys()
        if body.card_keys:
            ensure_wallet_cards_in_db(card_keys)
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


@app.post("/api/auth/register")
def api_auth_register(body: RegisterRequest, response: Response) -> dict[str, object]:
    try:
        result = register_user(
            body.email,
            body.password,
            [c.model_dump() for c in body.cards],
        )
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_session_cookie(response, str(result["session_token"]))
    return {
        "authenticated": True,
        "email": result["email"],
        "cards": result["cards"],
    }


@app.post("/api/auth/login")
def api_auth_login(body: LoginRequest, response: Response) -> dict[str, object]:
    try:
        result = login_user(body.email, body.password)
    except AccountError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_session_cookie(response, str(result["session_token"]))
    return {
        "authenticated": True,
        "email": result["email"],
        "cards": result["cards"],
    }


@app.post("/api/auth/logout")
def api_auth_logout(request: Request, response: Response) -> dict[str, object]:
    logout_session(request.cookies.get(SESSION_COOKIE))
    _clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def api_auth_me(request: Request) -> dict[str, object]:
    user_id = _session_user_id(request)
    if not user_id:
        return {"authenticated": False}
    try:
        wallet = get_user_wallet(user_id)
    except AccountError:
        return {"authenticated": False}
    return {"authenticated": True, "email": wallet["email"], "cards": wallet["cards"]}


@app.get("/api/wallet")
def api_get_wallet(request: Request) -> dict[str, object]:
    user_id = _session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        return get_user_wallet(user_id)
    except AccountError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/wallet")
def api_put_wallet(body: WalletUpdateRequest, request: Request) -> dict[str, object]:
    user_id = _session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        result = save_user_wallet(user_id, [c.model_dump() for c in body.cards])
        keys = [c["card_key"] for c in result["cards"]]
        missing = ensure_wallet_cards_in_db(keys)
        if missing:
            result["import_warnings"] = [
                f"Reward data not loaded for: {', '.join(missing)}. Recommend may skip these cards."
            ]
        apply_local_image_urls(result["cards"])
        _warm_images_async(keys)
        return result
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
