from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from credit_rewards.datastore.db import session
from credit_rewards.ingest.reference_sync import REFERENCE_DIR, load_reference_card
from credit_rewards.ingest.scrape.registry import load_card_registry

MULTIPLIER_TOLERANCE = 0.01

# Category IDs that must never be paired across sources via name alias.
AIRFARE_CATEGORY_ID = 2013874334
TRAVEL_GENERIC_CATEGORY_ID = 164006704
AMEX_TRAVEL_CATEGORY_ID = 1120466653

FORBIDDEN_CROSS_ID_PAIRS: frozenset[frozenset[int]] = frozenset(
    {
        frozenset({AIRFARE_CATEGORY_ID, TRAVEL_GENERIC_CATEGORY_ID}),
        frozenset({AIRFARE_CATEGORY_ID, AMEX_TRAVEL_CATEGORY_ID}),
        frozenset({TRAVEL_GENERIC_CATEGORY_ID, AMEX_TRAVEL_CATEGORY_ID}),
    }
)

# Normalized name aliases (same canonical bucket). Travel↔Airfare is intentionally omitted.
NAME_ALIAS_GROUPS: list[frozenset[str]] = [
    frozenset({"dining", "restaurants", "restaurant"}),
    frozenset({"grocery stores", "grocery", "groceries", "u.s. supermarkets", "supermarket"}),
    frozenset({"chase travel", "travel purchased through chase"}),
    frozenset({"amextravel.com", "amex travel", "amextravel"}),
]


@dataclass
class RuleRow:
    spend_bonus_category_id: int
    spend_bonus_category_name: str
    earn_multiplier: float
    spend_bonus_desc: str = ""
    spend_bonus_category_group: str = ""


@dataclass
class ComparisonMatch:
    scraped: RuleRow
    reference: RuleRow


@dataclass
class ComparisonMismatch:
    mismatch_type: str
    explanation: str
    scraped: RuleRow | None = None
    reference: RuleRow | None = None
    evidence_scrape: list[str] = field(default_factory=list)
    evidence_reference: list[str] = field(default_factory=list)
    evidence_verdict: str = ""
    evidence_action: str = ""
    evidence_summary: str = ""


@dataclass
class CardComparisonReport:
    card_key: str
    card_name: str
    issuer: str
    source_url: str
    scraped_at: str | None
    reference_synced_at: str | None
    scraped_rules: list[RuleRow] = field(default_factory=list)
    reference_rules: list[RuleRow] = field(default_factory=list)
    matched: list[ComparisonMatch] = field(default_factory=list)
    mismatches: list[ComparisonMismatch] = field(default_factory=list)
    extra_scraped: list[RuleRow] = field(default_factory=list)
    extra_reference: list[RuleRow] = field(default_factory=list)
    aligned: bool = False
    scrape_verified: bool = False
    parser_fix_needed: bool = False


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def _canonical_name(name: str) -> str:
    normalized = _normalize_name(name)
    for group in NAME_ALIAS_GROUPS:
        if normalized in group:
            return min(group)
    return normalized


def _rule_from_dict(rule: dict[str, Any]) -> RuleRow:
    return RuleRow(
        spend_bonus_category_id=int(rule.get("spendBonusCategoryId") or 0),
        spend_bonus_category_name=(rule.get("spendBonusCategoryName") or "").strip(),
        earn_multiplier=float(rule.get("earnMultiplier") or 0),
        spend_bonus_desc=(rule.get("spendBonusDesc") or "").strip(),
        spend_bonus_category_group=(rule.get("spendBonusCategoryGroup") or "").strip(),
    )


def _rules_from_detail(detail: dict[str, Any]) -> list[RuleRow]:
    rows: list[RuleRow] = []
    for rule in detail.get("spendBonusCategory") or []:
        cat_id = rule.get("spendBonusCategoryId")
        if cat_id is None:
            continue
        rows.append(_rule_from_dict(rule))
    return rows


def _registry_upstream_key(card_key: str) -> str | None:
    for entry in load_card_registry():
        if entry["card_key"] == card_key:
            return entry.get("rewards_cc_card_key") or entry["card_key"]
    return None


def _load_reference_synced_at(reference_dir: Path) -> str | None:
    manifest_path = reference_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    return manifest.get("synced_at")


def _load_local_detail(
    card_key: str,
    db_path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    with session(db_path) as conn:
        row = conn.execute(
            "SELECT detail_json, source_url, updated_at FROM cards WHERE card_key = ?",
            (card_key,),
        ).fetchone()
        if not row:
            return None, None, None
        detail = json.loads(row["detail_json"])
        return detail, row["source_url"] or "", row["updated_at"]


def _forbidden_cross_id(id_a: int, id_b: int) -> bool:
    if id_a == id_b:
        return False
    return frozenset({id_a, id_b}) in FORBIDDEN_CROSS_ID_PAIRS


def _multiplier_matches(a: float, b: float) -> bool:
    return abs(a - b) <= MULTIPLIER_TOLERANCE


def _match_by_id(
    scraped: list[RuleRow],
    reference: list[RuleRow],
) -> tuple[list[ComparisonMatch], list[RuleRow], list[RuleRow], list[ComparisonMismatch]]:
    matched: list[ComparisonMatch] = []
    mismatches: list[ComparisonMismatch] = []
    ref_by_id = {r.spend_bonus_category_id: r for r in reference}
    unmatched_scraped: list[RuleRow] = []

    for s_rule in scraped:
        r_rule = ref_by_id.get(s_rule.spend_bonus_category_id)
        if not r_rule:
            unmatched_scraped.append(s_rule)
            continue
        if _multiplier_matches(s_rule.earn_multiplier, r_rule.earn_multiplier):
            matched.append(ComparisonMatch(scraped=s_rule, reference=r_rule))
        else:
            mismatches.append(
                ComparisonMismatch(
                    mismatch_type="multiplier_mismatch",
                    scraped=s_rule,
                    reference=r_rule,
                    explanation=(
                        f"Category {s_rule.spend_bonus_category_name!r} (id {s_rule.spend_bonus_category_id}): "
                        f"scraped {s_rule.earn_multiplier}x vs reference {r_rule.earn_multiplier}x"
                    ),
                )
            )

    matched_ids = {m.reference.spend_bonus_category_id for m in matched}
    mismatch_ids = {m.scraped.spend_bonus_category_id for m in mismatches if m.scraped}
    consumed_ref_ids = matched_ids | mismatch_ids
    unmatched_reference = [r for r in reference if r.spend_bonus_category_id not in consumed_ref_ids]

    return matched, unmatched_scraped, unmatched_reference, mismatches


def _find_name_pair(
    s_rule: RuleRow,
    candidates: list[RuleRow],
) -> RuleRow | None:
    s_canon = _canonical_name(s_rule.spend_bonus_category_name)
    for r_rule in candidates:
        if _forbidden_cross_id(s_rule.spend_bonus_category_id, r_rule.spend_bonus_category_id):
            continue
        r_canon = _canonical_name(r_rule.spend_bonus_category_name)
        if s_canon == r_canon:
            return r_rule
        if s_rule.spend_bonus_category_id == r_rule.spend_bonus_category_id:
            # Same id with different display names (e.g. Travel vs Airfare) — only when same id.
            if _normalize_name(s_rule.spend_bonus_category_name) == _normalize_name(
                r_rule.spend_bonus_category_name
            ):
                return r_rule
    return None


def _match_by_name(
    unmatched_scraped: list[RuleRow],
    unmatched_reference: list[RuleRow],
) -> tuple[list[ComparisonMatch], list[RuleRow], list[RuleRow], list[ComparisonMismatch]]:
    matched: list[ComparisonMatch] = []
    mismatches: list[ComparisonMismatch] = []
    remaining_ref = list(unmatched_reference)

    still_scraped: list[RuleRow] = []
    for s_rule in unmatched_scraped:
        r_rule = _find_name_pair(s_rule, remaining_ref)
        if not r_rule:
            still_scraped.append(s_rule)
            continue
        remaining_ref.remove(r_rule)
        if _multiplier_matches(s_rule.earn_multiplier, r_rule.earn_multiplier):
            matched.append(ComparisonMatch(scraped=s_rule, reference=r_rule))
        else:
            mismatches.append(
                ComparisonMismatch(
                    mismatch_type="multiplier_mismatch",
                    scraped=s_rule,
                    reference=r_rule,
                    explanation=(
                        f"Matched by name {s_rule.spend_bonus_category_name!r} ↔ "
                        f"{r_rule.spend_bonus_category_name!r}: scraped {s_rule.earn_multiplier}x "
                        f"vs reference {r_rule.earn_multiplier}x"
                    ),
                )
            )

    return matched, still_scraped, remaining_ref, mismatches


def _compare_base_rate(
    scraped_detail: dict[str, Any],
    reference_detail: dict[str, Any],
) -> ComparisonMismatch | None:
    scraped_base = float(scraped_detail.get("baseSpendAmount") or 1)
    reference_base = float(reference_detail.get("baseSpendAmount") or 1)
    if _multiplier_matches(scraped_base, reference_base):
        return None
    return ComparisonMismatch(
        mismatch_type="base_rate_mismatch",
        explanation=(
            f"Base earn rate: scraped {scraped_base}x vs reference {reference_base}x"
        ),
    )


def _build_comparison(
    card_key: str,
    scraped_detail: dict[str, Any],
    reference_detail: dict[str, Any],
    *,
    source_url: str = "",
    scraped_at: str | None = None,
) -> CardComparisonReport:
    scraped_rules = _rules_from_detail(scraped_detail)
    reference_rules = _rules_from_detail(reference_detail)

    id_matched, unmatched_scraped, unmatched_reference, id_mismatches = _match_by_id(
        scraped_rules, reference_rules
    )
    name_matched, extra_scraped, extra_reference, name_mismatches = _match_by_name(
        unmatched_scraped, unmatched_reference
    )

    matched = id_matched + name_matched
    mismatches = id_mismatches + name_mismatches

    for r_rule in extra_reference:
        mismatches.append(
            ComparisonMismatch(
                mismatch_type="missing_in_scrape",
                reference=r_rule,
                explanation=(
                    f"Reference category {r_rule.spend_bonus_category_name!r} "
                    f"(id {r_rule.spend_bonus_category_id}, {r_rule.earn_multiplier}x) "
                    f"not found in scrape"
                ),
            )
        )
    for s_rule in extra_scraped:
        mismatches.append(
            ComparisonMismatch(
                mismatch_type="missing_in_reference",
                scraped=s_rule,
                explanation=(
                    f"Scraped category {s_rule.spend_bonus_category_name!r} "
                    f"(id {s_rule.spend_bonus_category_id}, {s_rule.earn_multiplier}x) "
                    f"not in reference"
                ),
            )
        )

    base_mismatch = _compare_base_rate(scraped_detail, reference_detail)
    if base_mismatch:
        mismatches.append(base_mismatch)

    extra_scraped_rows = list(extra_scraped)
    extra_reference_rows = list(extra_reference)

    aligned = (
        not mismatches
        and not extra_scraped_rows
        and not extra_reference_rows
        and (bool(matched) or (not scraped_rules and not reference_rules))
    )

    return CardComparisonReport(
        card_key=card_key,
        card_name=scraped_detail.get("cardName") or reference_detail.get("cardName") or card_key,
        issuer=scraped_detail.get("cardIssuer") or reference_detail.get("cardIssuer") or "",
        source_url=source_url or scraped_detail.get("cardUrl") or reference_detail.get("cardUrl") or "",
        scraped_at=scraped_at,
        reference_synced_at=None,
        scraped_rules=scraped_rules,
        reference_rules=reference_rules,
        matched=matched,
        mismatches=mismatches,
        extra_scraped=extra_scraped_rows,
        extra_reference=extra_reference_rows,
        aligned=aligned,
    )


def compare_card_details(
    card_key: str,
    scraped_detail: dict[str, Any],
    reference_detail: dict[str, Any],
    *,
    source_url: str = "",
    scraped_at: str | None = None,
    issuer_html: str | None = None,
    fetch_evidence: bool = True,
) -> CardComparisonReport:
    """Compare in-memory scrape vs reference (external validation — no DB overlay)."""
    report = _build_comparison(
        card_key,
        scraped_detail,
        reference_detail,
        source_url=source_url or scraped_detail.get("cardUrl") or reference_detail.get("cardUrl") or "",
        scraped_at=scraped_at,
    )
    report.reference_synced_at = _load_reference_synced_at(REFERENCE_DIR)
    return enrich_report_with_website_evidence(
        report,
        scraped_detail=scraped_detail,
        reference_detail=reference_detail,
        issuer_html=issuer_html,
        fetch_if_missing=fetch_evidence,
    )


def compare_card(
    card_key: str,
    *,
    reference_dir: Path | None = None,
    db_path: Path | None = None,
    issuer_html: str | None = None,
    fetch_evidence: bool = True,
) -> CardComparisonReport:
    ref_root = reference_dir or REFERENCE_DIR
    upstream = _registry_upstream_key(card_key)
    reference = load_reference_card(card_key, ref_root, upstream_key=upstream)
    scraped_detail, source_url, scraped_at = _load_local_detail(card_key, db_path)

    synced_at = _load_reference_synced_at(ref_root)

    if not reference and not scraped_detail:
        return CardComparisonReport(
            card_key=card_key,
            card_name=card_key,
            issuer="",
            source_url="",
            scraped_at=None,
            reference_synced_at=synced_at,
            aligned=False,
            mismatches=[
                ComparisonMismatch(
                    mismatch_type="missing_in_scrape",
                    explanation="No local scrape and no reference JSON for this card",
                )
            ],
        )

    if not reference:
        return CardComparisonReport(
            card_key=card_key,
            card_name=(scraped_detail or {}).get("cardName", card_key),
            issuer=(scraped_detail or {}).get("cardIssuer", ""),
            source_url=source_url or "",
            scraped_at=scraped_at,
            reference_synced_at=synced_at,
            scraped_rules=_rules_from_detail(scraped_detail or {}),
            aligned=False,
            mismatches=[
                ComparisonMismatch(
                    mismatch_type="missing_in_reference",
                    explanation="Reference file missing — run sync-reference",
                )
            ],
        )

    if not scraped_detail:
        return CardComparisonReport(
            card_key=card_key,
            card_name=reference.get("cardName", card_key),
            issuer=reference.get("cardIssuer", ""),
            source_url=reference.get("cardUrl", ""),
            scraped_at=None,
            reference_synced_at=synced_at,
            reference_rules=_rules_from_detail(reference),
            aligned=False,
            mismatches=[
                ComparisonMismatch(
                    mismatch_type="missing_in_scrape",
                    explanation="Local DB has no card — run refresh-all",
                )
            ],
        )

    report = _build_comparison(
        card_key,
        scraped_detail,
        reference,
        source_url=source_url or "",
        scraped_at=scraped_at,
    )
    report.reference_synced_at = synced_at
    return enrich_report_with_website_evidence(
        report,
        scraped_detail=scraped_detail,
        reference_detail=reference,
        issuer_html=issuer_html,
        fetch_if_missing=fetch_evidence,
    )


def _apply_evidence_to_mismatch(
    mismatch: ComparisonMismatch,
    page_text: str,
    scraped_detail: dict[str, Any],
    reference_detail: dict[str, Any],
) -> None:
    from credit_rewards.ingest.evidence import analyze_base_rate_evidence, analyze_mismatch

    if mismatch.mismatch_type == "base_rate_mismatch":
        verdict = analyze_base_rate_evidence(
            page_text,
            float(scraped_detail.get("baseSpendAmount") or 1),
            float(reference_detail.get("baseSpendAmount") or 1),
        )
    else:
        category_name = (
            (mismatch.scraped.spend_bonus_category_name if mismatch.scraped else None)
            or (mismatch.reference.spend_bonus_category_name if mismatch.reference else "")
        )
        verdict = analyze_mismatch(
            mismatch_type=mismatch.mismatch_type,
            category_name=category_name,
            scrape_multiplier=mismatch.scraped.earn_multiplier if mismatch.scraped else None,
            reference_multiplier=mismatch.reference.earn_multiplier if mismatch.reference else None,
            scrape_description=mismatch.scraped.spend_bonus_desc if mismatch.scraped else "",
            reference_description=mismatch.reference.spend_bonus_desc if mismatch.reference else "",
            page_text=page_text,
        )

    mismatch.evidence_scrape = verdict.evidence_scrape
    mismatch.evidence_reference = verdict.evidence_reference
    mismatch.evidence_verdict = verdict.verdict
    mismatch.evidence_action = verdict.action
    mismatch.evidence_summary = verdict.summary


def _fetch_issuer_html(source_url: str) -> str:
    import httpx

    response = httpx.get(
        source_url,
        timeout=30.0,
        headers={"User-Agent": "PayCueBot/0.1 (+research; contact: local-dev)"},
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def enrich_report_with_website_evidence(
    report: CardComparisonReport,
    *,
    scraped_detail: dict[str, Any],
    reference_detail: dict[str, Any],
    issuer_html: str | None = None,
    fetch_if_missing: bool = True,
) -> CardComparisonReport:
    """Attach issuer-page snippets to mismatches; set scrape_verified / parser_fix_needed."""
    from credit_rewards.ingest.scrape.parsers import html_to_text

    if not report.mismatches:
        report.scrape_verified = report.aligned
        report.parser_fix_needed = False
        return report

    html = issuer_html
    if not html and fetch_if_missing and report.source_url:
        try:
            html = _fetch_issuer_html(report.source_url)
        except Exception:
            html = None

    if not html:
        report.scrape_verified = False
        report.parser_fix_needed = bool(report.mismatches)
        return report

    page_text = html_to_text(html)
    if "lyft" in html.lower() or "capital one travel" in html.lower() or "showcase-" in html.lower():
        page_text = f"{page_text} {html}"
    for mismatch in report.mismatches:
        _apply_evidence_to_mismatch(mismatch, page_text, scraped_detail, reference_detail)

    parser_fix = any(m.evidence_action == "fix_scrape" for m in report.mismatches)
    scrape_supported = all(
        m.evidence_action == "keep_scrape" for m in report.mismatches if m.evidence_action
    )

    report.parser_fix_needed = parser_fix
    report.scrape_verified = report.aligned or (scrape_supported and not parser_fix)
    return report


def summarize_reference_verification(report: CardComparisonReport) -> dict[str, Any]:
    """Count category rows where reference earn rules are verified for runtime use."""
    verified = len(report.matched)
    total = len(report.matched) + len(report.mismatches)
    for mismatch in report.mismatches:
        if mismatch.evidence_verdict == "reference_supported":
            verified += 1
    pct = round(100.0 * verified / total, 1) if total else 100.0
    return {
        "verified_rows": verified,
        "total_rows": total,
        "verified_pct": pct,
        "aligned": report.aligned,
        "scrape_verified": report.scrape_verified,
        "parser_fix_needed": report.parser_fix_needed,
    }


def compare_all(
    card_keys: list[str] | None = None,
    *,
    reference_dir: Path | None = None,
    db_path: Path | None = None,
    fetch_evidence: bool = True,
) -> list[CardComparisonReport]:
    keys = card_keys or [entry["card_key"] for entry in load_card_registry()]
    return [
        compare_card(
            key,
            reference_dir=reference_dir,
            db_path=db_path,
            fetch_evidence=fetch_evidence,
        )
        for key in keys
    ]


def _report_to_dict(report: CardComparisonReport) -> dict[str, Any]:
    return asdict(report)


def write_reports(
    reports: list[CardComparisonReport] | None = None,
    *,
    output_dir: Path = Path("data/reports/comparison"),
    card_keys: list[str] | None = None,
    reference_dir: Path | None = None,
    db_path: Path | None = None,
) -> list[Path]:
    if reports is None:
        reports = compare_all(
            card_keys, reference_dir=reference_dir, db_path=db_path
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for report in reports:
        path = output_dir / f"{report.card_key}.json"
        path.write_text(json.dumps(_report_to_dict(report), indent=2) + "\n")
        written.append(path)
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "card_count": len(reports),
                "aligned_count": sum(1 for r in reports if r.aligned),
                "scrape_verified_count": sum(1 for r in reports if r.scrape_verified),
                "parser_fix_count": sum(1 for r in reports if r.parser_fix_needed),
                "misaligned": [r.card_key for r in reports if not r.aligned],
                "reports": [_report_to_dict(r) for r in reports],
            },
            indent=2,
        )
        + "\n"
    )
    written.append(summary_path)
    return written
