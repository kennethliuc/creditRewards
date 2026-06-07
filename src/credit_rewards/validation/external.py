"""External cross-validation — issuer scrape vs reference without reference overlay."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credit_rewards.ingest.compare import (
    CardComparisonReport,
    ComparisonMatch,
    ComparisonMismatch,
    compare_card_details,
    summarize_reference_verification,
)
from credit_rewards.ingest.reference_sync import load_reference_card
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.ingest.scrape.runner import ScrapeError, scrape_card_page_raw

EXTERNAL_CROSS_VERIFY_GATE = 0.90
MIN_SCRAPED_FOR_EXTERNAL = 18


@dataclass
class CrossVerifiedRow:
    card_key: str
    category_name: str
    category_id: int
    multiplier: float
    signals: list[str]
    cross_verified: bool
    evidence_verdict: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_key": self.card_key,
            "category_name": self.category_name,
            "category_id": self.category_id,
            "multiplier": self.multiplier,
            "signals": self.signals,
            "cross_verified": self.cross_verified,
            "evidence_verdict": self.evidence_verdict,
            "note": self.note,
        }


@dataclass
class ExternalCardResult:
    card_key: str
    card_name: str
    scrape_ok: bool
    scrape_error: str = ""
    raw_rule_count: int = 0
    aligned: bool = False
    cross_verified_rows: int = 0
    total_rows: int = 0
    cross_verified_pct: float = 0.0
    report: CardComparisonReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_key": self.card_key,
            "card_name": self.card_name,
            "scrape_ok": self.scrape_ok,
            "scrape_error": self.scrape_error,
            "raw_rule_count": self.raw_rule_count,
            "aligned": self.aligned,
            "cross_verified_rows": self.cross_verified_rows,
            "total_rows": self.total_rows,
            "cross_verified_pct": self.cross_verified_pct,
        }


@dataclass
class ExternalValidationResult:
    ok: bool
    cross_verified_pct: float
    gate_pct: float
    scraped_count: int
    cards: list[ExternalCardResult] = field(default_factory=list)
    rows: list[CrossVerifiedRow] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "cross_verified_pct": self.cross_verified_pct,
            "gate_pct": round(self.gate_pct * 100, 1),
            "scraped_count": self.scraped_count,
            "cards": [c.to_dict() for c in self.cards],
            "rows": [r.to_dict() for r in self.rows],
            "blockers": self.blockers,
        }


def _registry_upstream_key(card_key: str) -> str | None:
    for entry in load_card_registry():
        if entry["card_key"] == card_key:
            return entry.get("rewards_cc_card_key") or entry["card_key"]
    return None


def _signals_for_match(
    match: ComparisonMatch,
    *,
    issuer_html_fetched: bool,
) -> tuple[list[str], bool, str]:
    """≥2 independent signals required for cross-verification."""
    signals: list[str] = ["reference", "raw_scrape"]
    if issuer_html_fetched:
        signals.append("issuer_page")
    # Raw scrape matched reference — two structured sources agree.
    cross = len(signals) >= 2
    return signals, cross, "raw scrape aligned with reference"


def _signals_for_mismatch(
    mismatch: ComparisonMismatch,
    *,
    issuer_html_fetched: bool,
) -> tuple[list[str], bool, str]:
    signals: list[str] = ["reference"]
    verdict = mismatch.evidence_verdict or ""
    note = mismatch.evidence_summary or mismatch.explanation

    if mismatch.scraped:
        signals.append("raw_scrape")
    if issuer_html_fetched and verdict:
        signals.append("issuer_page")

    cross = False
    if verdict == "reference_supported" and "issuer_page" in signals:
        cross = True
        note = note or "issuer page supports reference earn rate"
    elif verdict == "scrape_supported" and "issuer_page" in signals and "raw_scrape" in signals:
        cross = True
        note = note or "issuer page supports raw scrape — reference may be stale"
    elif mismatch.mismatch_type == "missing_in_scrape" and verdict == "reference_supported":
        cross = True
        note = note or "parser missed category; issuer confirms reference"

    return signals, cross, note


def _analyze_report(
    card_key: str,
    report: CardComparisonReport,
    *,
    issuer_html_fetched: bool,
) -> tuple[list[CrossVerifiedRow], int, int]:
    """
    Cross-verify each reference earn row (not parser noise).

    A reference row is verified with ≥2 independent signals when:
    - raw scrape matches reference, or
    - issuer page evidence supports reference (reference_supported).
    """
    rows: list[CrossVerifiedRow] = []
    verified = 0
    total = len(report.reference_rules)

    matched_ref_ids = {m.reference.spend_bonus_category_id for m in report.matched}

    for match in report.matched:
        ref = match.reference
        signals, cross, note = _signals_for_match(match, issuer_html_fetched=issuer_html_fetched)
        rows.append(
            CrossVerifiedRow(
                card_key=card_key,
                category_name=ref.spend_bonus_category_name,
                category_id=ref.spend_bonus_category_id,
                multiplier=ref.earn_multiplier,
                signals=signals,
                cross_verified=cross,
                evidence_verdict="aligned",
                note=note,
            )
        )
        if cross:
            verified += 1

    for mismatch in report.mismatches:
        if mismatch.mismatch_type == "missing_in_reference":
            continue
        ref = mismatch.reference
        if not ref or ref.spend_bonus_category_id in matched_ref_ids:
            continue

        signals, cross, note = _signals_for_mismatch(
            mismatch, issuer_html_fetched=issuer_html_fetched
        )
        rows.append(
            CrossVerifiedRow(
                card_key=card_key,
                category_name=ref.spend_bonus_category_name,
                category_id=ref.spend_bonus_category_id,
                multiplier=ref.earn_multiplier,
                signals=signals,
                cross_verified=cross,
                evidence_verdict=mismatch.evidence_verdict,
                note=note,
            )
        )
        if cross:
            verified += 1

    if total == 0:
        total = 1
        base_mismatch = next(
            (m for m in report.mismatches if m.mismatch_type == "base_rate_mismatch"),
            None,
        )
        if base_mismatch is None:
            signals = ["reference", "raw_scrape"]
            if issuer_html_fetched:
                signals.append("issuer_page")
            cross = True
            verdict = "aligned"
            note = "base-only card; base rate matches reference (bonus rules empty)"
        elif base_mismatch:
            signals, cross, note = _signals_for_mismatch(
                base_mismatch, issuer_html_fetched=issuer_html_fetched
            )
            verdict = base_mismatch.evidence_verdict

        rows.append(
            CrossVerifiedRow(
                card_key=card_key,
                category_name="All Purchases (base)",
                category_id=0,
                multiplier=0.0,
                signals=signals,
                cross_verified=cross,
                evidence_verdict=verdict,
                note=note,
            )
        )
        if cross:
            verified += 1

    return rows, verified, total


def run_external_validation(
    *,
    card_keys: list[str] | None = None,
    fetch_evidence: bool = True,
    skip_network: bool = False,
) -> ExternalValidationResult:
    """
    External cross-validation track (Monitor Phase A).

    Scrapes issuer pages WITHOUT reference overlay, compares to Rewards CC reference,
    and requires ≥2 independent signals per earn row (reference + raw scrape, or
    reference + issuer evidence, etc.).
    """
    keys = card_keys or [e["card_key"] for e in load_card_registry()]
    registry = {e["card_key"]: e for e in load_card_registry()}
    card_results: list[ExternalCardResult] = []
    all_rows: list[CrossVerifiedRow] = []
    scraped_ok = 0
    total_verified = 0
    total_rows = 0

    for card_key in keys:
        entry = registry.get(card_key)
        if not entry:
            continue

        upstream = _registry_upstream_key(card_key)
        reference = load_reference_card(card_key, upstream_key=upstream)
        if not reference:
            card_results.append(
                ExternalCardResult(
                    card_key=card_key,
                    card_name=card_key,
                    scrape_ok=False,
                    scrape_error="missing reference JSON — run sync-reference",
                )
            )
            continue

        if skip_network:
            card_results.append(
                ExternalCardResult(
                    card_key=card_key,
                    card_name=reference.get("cardName", card_key),
                    scrape_ok=True,
                    raw_rule_count=len(reference.get("spendBonusCategory") or []),
                    aligned=True,
                    cross_verified_rows=0,
                    total_rows=len(reference.get("spendBonusCategory") or []),
                    cross_verified_pct=0.0,
                )
            )
            continue

        try:
            raw_detail, html = scrape_card_page_raw(entry, align_to_reference=False)
        except Exception as exc:
            card_results.append(
                ExternalCardResult(
                    card_key=card_key,
                    card_name=reference.get("cardName", card_key),
                    scrape_ok=False,
                    scrape_error=str(exc),
                )
            )
            continue

        scraped_ok += 1
        report = compare_card_details(
            card_key,
            raw_detail,
            reference,
            source_url=entry.get("url") or "",
            issuer_html=html if fetch_evidence else None,
            fetch_evidence=fetch_evidence,
        )
        row_list, verified, row_total = _analyze_report(
            card_key,
            report,
            issuer_html_fetched=bool(html or fetch_evidence),
        )
        all_rows.extend(row_list)
        total_verified += verified
        total_rows += row_total
        pct = round(100.0 * verified / row_total, 1) if row_total else 0.0
        card_results.append(
            ExternalCardResult(
                card_key=card_key,
                card_name=report.card_name,
                scrape_ok=True,
                raw_rule_count=len(raw_detail.get("spendBonusCategory") or []),
                aligned=report.aligned,
                cross_verified_rows=verified,
                total_rows=row_total,
                cross_verified_pct=pct,
                report=report,
            )
        )

    overall_pct = total_verified / total_rows if total_rows else 0.0
    blockers: list[str] = []

    if scraped_ok < MIN_SCRAPED_FOR_EXTERNAL:
        blockers.append(
            f"External/Issuer: only {scraped_ok}/{len(keys)} cards scraped raw "
            f"(need ≥{MIN_SCRAPED_FOR_EXTERNAL})"
        )
    if overall_pct < EXTERNAL_CROSS_VERIFY_GATE:
        blockers.append(
            f"External/CrossValidate: {round(overall_pct * 100, 1)}% rows cross-verified "
            f"(need ≥{EXTERNAL_CROSS_VERIFY_GATE * 100}%)"
        )

    failed_cards = [c for c in card_results if not c.scrape_ok]
    if failed_cards:
        sample = ", ".join(c.card_key for c in failed_cards[:5])
        blockers.append(f"External/Parser: raw scrape failed for {sample}")

    low_cards = [
        c for c in card_results
        if c.scrape_ok and c.total_rows and c.cross_verified_pct < EXTERNAL_CROSS_VERIFY_GATE * 100
    ]
    if low_cards and overall_pct < EXTERNAL_CROSS_VERIFY_GATE:
        sample = ", ".join(f"{c.card_key} ({c.cross_verified_pct}%)" for c in low_cards[:5])
        blockers.append(f"External/Issuer: low cross-verify cards: {sample}")

    return ExternalValidationResult(
        ok=not blockers,
        cross_verified_pct=round(overall_pct * 100, 1),
        gate_pct=EXTERNAL_CROSS_VERIFY_GATE,
        scraped_count=scraped_ok,
        cards=card_results,
        rows=all_rows,
        blockers=blockers,
    )


def write_external_report(
    result: ExternalValidationResult,
    *,
    output_dir: Path | None = None,
) -> Path:
    out = output_dir or Path(__file__).resolve().parents[3] / "reports" / "validation"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    path = out / f"external-crosscheck-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    payload = result.to_dict()
    payload["date"] = stamp
    payload["summary"] = {
        "cross_verified_rows": sum(r.cross_verified_rows for r in result.cards),
        "total_rows": sum(r.total_rows for r in result.cards),
        "legacy_reference_verification": [
            summarize_reference_verification(c.report)
            for c in result.cards
            if c.report is not None
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path
