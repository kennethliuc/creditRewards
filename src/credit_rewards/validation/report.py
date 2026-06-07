from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credit_rewards.datastore.db import db_path, session
from credit_rewards.ingest.compare import compare_all, summarize_reference_verification
from credit_rewards.ingest.reference_import import import_reference_to_db
from credit_rewards.ingest.reference_validate import validate_all
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.validation.dashboard import build_validation_dashboard
from credit_rewards.validation.golden import run_golden_cases

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports" / "validation"
STATUS_PATH = Path(__file__).resolve().parents[3] / "docs" / "validation" / "status.md"


def _card_source_types(db_path: Path | None = None) -> dict[str, str]:
    with session(db_path) as conn:
        rows = conn.execute("SELECT card_key, source_type FROM cards").fetchall()
    return {row["card_key"]: row["source_type"] or "unknown" for row in rows}


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _render_status_md(
    dashboard: dict[str, Any],
    *,
    l1_snapshot: dict[str, Any],
    golden_snapshot: dict[str, Any],
    scrape_summary: dict[str, Any],
) -> str:
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    ship = "✅ Ship ready" if dashboard["ship_ready"] else "⛔ Not ship ready"
    indep_line = (
        "✅ Independent OK"
        if dashboard.get("independent_ready")
        else "⛔ Independent blocked"
    )
    blockers = dashboard.get("blockers") or []
    blocker_lines = "\n".join(f"- {b}" for b in blockers) if blockers else "- (none)"

    matrix_rows = []
    for row in dashboard.get("cards") or []:
        l1 = "✓" if row.get("l1_ok") else "✗"
        l2_pct = row.get("l2_verified_pct")
        l2 = f"{l2_pct}%" if l2_pct is not None else "—"
        matrix_rows.append(
            f"| {row['card_key']} | {l1} | {l2} | "
            f"{row.get('blocker') or '—'} |"
        )

    layers = dashboard.get("layers") or []
    layer_summary = "\n".join(
        f"| {layer['name']} | {layer['rate']}% | ≥{layer['gate_pct']}% | {layer['status']} |"
        for layer in layers
    )

    golden = golden_snapshot
    golden_line = (
        f"{golden.get('passed', 0)}/{golden.get('total', 0)} "
        f"({round(golden.get('pass_rate', 0) * 100, 1)}%)"
    )
    scrape_line = (
        f"{len(scrape_summary.get('scraped') or [])}/20 scraped · "
        f"{len(scrape_summary.get('failed') or [])} parser failures"
    )

    return f"""# Validation Status

**Updated:** {date}  
**Independent:** {indep_line}  
**Overall ship:** {ship}

## Gates

| Layer | Actual | Gate | Status |
|-------|--------|------|--------|
{layer_summary}

## Blockers

{blocker_lines}

## L1 snapshot (reference import)

Pass: **{l1_snapshot.get('pass_count', 0)}/{l1_snapshot.get('total', 0)}**

## L2 issuer scrape

{scrape_line}

## L3 golden recommend

{golden_line}

## Card matrix

| card_key | L1 | L2 verified | blocker |
|----------|----|-------------|---------|
{chr(10).join(matrix_rows)}

## Commands

```bash
uvicorn credit_rewards.web.app:app --port 8000
# → http://127.0.0.1:8000/validation
```

Re-run: `credit-rewards-db validation-report`
"""


def run_validation_report(
    *,
    fetch_evidence: bool = True,
    skip_scrape: bool = False,
    restore_reference: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Execute validation phases V0–V5 and write JSON + validation-status.md.

    1. import-reference → L1 + golden on runtime DB
    2. optional refresh-all → L2 compare (issuer evidence)
    3. restore import-reference for CardData API runtime
    """
    out = output_dir or REPORTS_DIR
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    path = db_path()

    import_reference_to_db()
    from credit_rewards.ingest.official_cpp_refresh import refresh_official_cpp

    refresh_official_cpp()

    card_keys = [e["card_key"] for e in load_card_registry()]
    l1_results = validate_all(card_keys)
    l1_pass = sum(1 for r in l1_results if r.ok)
    l1_snapshot = {
        "date": stamp,
        "pass_count": l1_pass,
        "total": len(l1_results),
        "results": [
            {
                "card_key": r.card_key,
                "ok": r.ok,
                "diff_count": len(r.diffs),
                "notes": r.notes,
            }
            for r in l1_results
        ],
    }
    _write_json(out / f"reference-{stamp}.json", l1_snapshot)

    golden_l3 = run_golden_cases(db_path=path)
    _write_json(out / f"golden-{stamp}.json", golden_l3)

    scrape_summary: dict[str, Any] = {"skipped": skip_scrape, "scraped": [], "failed": []}
    if not skip_scrape:
        from credit_rewards.ingest.scrape.runner import ScrapeError, scrape_card_entry
        from credit_rewards.datastore.repository import CardDataRepository

        for entry in load_card_registry():
            key = entry["card_key"]
            try:
                with session(path) as conn:
                    detail = scrape_card_entry(CardDataRepository(conn), entry)
                scrape_summary["scraped"].append(
                    {"card_key": key, "rules": len(detail.get("spendBonusCategory") or [])}
                )
            except Exception as exc:
                scrape_summary["failed"].append({"card_key": key, "error": str(exc)})

    sources = _card_source_types(path)
    compare_reports = compare_all(fetch_evidence=fetch_evidence, db_path=path)
    l2_cards = []
    for report in compare_reports:
        stats = summarize_reference_verification(report)
        src = sources.get(report.card_key, "unknown")
        l2_cards.append(
            {
                "card_key": report.card_key,
                "source_type": src,
                "aligned": report.aligned,
                "scrape_verified": report.scrape_verified,
                "parser_fix_needed": report.parser_fix_needed,
                **stats,
            }
        )
    compare_payload = {
        "date": stamp,
        "scraped_count": sum(1 for s in sources.values() if s == "scrape"),
        "reference_only_count": sum(1 for s in sources.values() if s == "reference"),
        "scrape_attempt": scrape_summary,
        "cards": l2_cards,
    }
    _write_json(out / f"compare-summary-{stamp}.json", compare_payload)

    dashboard = build_validation_dashboard(
        fetch_evidence=False,
        db_path=path,
        l1_results_override=l1_results,
        golden_result_override=golden_l3,
    )
    dashboard["l1_snapshot"] = l1_snapshot
    dashboard["l2_scrape"] = compare_payload
    dashboard["l3_snapshot"] = golden_l3
    _write_json(out / f"dashboard-{stamp}.json", dashboard)

    cpp_section = dashboard.get("cpp") or {}
    _write_json(out / f"cpp-{stamp}.json", cpp_section)

    mcc_section = dashboard.get("mcc") or {}
    mcc_md = out / f"mcc-coverage-{stamp}.md"
    mcc_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# MCC coverage ({stamp})",
        "",
        f"Mapped: **{mcc_section.get('mapped_count', 0)}/{mcc_section.get('total_checked', 0)}**",
        "",
        "| MCC | Label | Category | Mapped |",
        "|-----|-------|----------|--------|",
    ]
    for row in mcc_section.get("rows") or []:
        lines.append(
            f"| {row['mcc']} | {row['label']} | {row['category']} | "
            f"{'yes' if row['mapped'] else 'no'} |"
        )
    mcc_md.write_text("\n".join(lines) + "\n")

    if restore_reference:
        import_reference_to_db(db_path=path)
        refresh_official_cpp(db_path=path)

    status_md = _render_status_md(
        dashboard,
        l1_snapshot=l1_snapshot,
        golden_snapshot=golden_l3,
        scrape_summary=scrape_summary,
    )
    STATUS_PATH.write_text(status_md)

    return {
        "output_dir": str(out),
        "status_path": str(STATUS_PATH),
        "independent_ok": dashboard.get("independent_ready", False),
        "ship_ready": dashboard["ship_ready"],
        "blockers": dashboard.get("blockers") or [],
        "independent_blockers": dashboard.get("independent_blockers") or [],
        "l2_blockers": dashboard.get("l2_blockers") or [],
        "l1": f"{l1_pass}/{len(l1_results)}",
        "l3": f"{golden_l3.get('passed', 0)}/{golden_l3.get('total', 0)}",
        "scraped": len(scrape_summary.get("scraped") or []),
        "scrape_failed": len(scrape_summary.get("failed") or []),
    }
