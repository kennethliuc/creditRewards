from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from credit_rewards.ingest.compare import compare_all, summarize_reference_verification
from credit_rewards.ingest.reference_sync import REFERENCE_DIR
from credit_rewards.ingest.reference_validate import validate_all
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.mcc_mapping import lookup_mcc_category
from credit_rewards.official_cpp import load_official_cpp_config
from credit_rewards.validation.golden import run_golden_cases

GOLDEN_CASES_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "validation" / "golden_cases.yaml"
)

# Phase V3 gate — common checkout MCC codes
TOP_VALIDATION_MCCS: list[dict[str, str]] = [
    {"code": "5411", "label": "Grocery"},
    {"code": "5812", "label": "Restaurant"},
    {"code": "5814", "label": "Fast food"},
    {"code": "5541", "label": "Gas station"},
    {"code": "5542", "label": "Automated fuel"},
    {"code": "5912", "label": "Drugstore"},
    {"code": "5310", "label": "Discount store"},
    {"code": "5499", "label": "Misc food"},
    {"code": "4121", "label": "Taxicabs"},
    {"code": "4131", "label": "Bus lines"},
    {"code": "4511", "label": "Airlines"},
    {"code": "7011", "label": "Hotels"},
    {"code": "4784", "label": "Tolls"},
    {"code": "5732", "label": "Electronics"},
    {"code": "5651", "label": "Clothing"},
    {"code": "5999", "label": "Misc retail"},
    {"code": "7523", "label": "Parking"},
    {"code": "7832", "label": "Motion pictures"},
    {"code": "7997", "label": "Recreation clubs"},
    {"code": "8299", "label": "Schools"},
    {"code": "5311", "label": "Department store"},
    {"code": "5813", "label": "Bars"},
    {"code": "5977", "label": "Cosmetics"},
    {"code": "7230", "label": "Beauty shops"},
]

L1_GATE = 1.0
L2_GATE = 0.90
L3_GATE = 0.95
MCC_GATE = 1.0
MIN_SCRAPED_CARDS = 18


def _load_source_types(db_path: Path | None) -> dict[str, str]:
    from credit_rewards.datastore.db import session

    with session(db_path) as conn:
        rows = conn.execute("SELECT card_key, source_type FROM cards").fetchall()
    return {row["card_key"]: row["source_type"] or "unknown" for row in rows}


def _gate_status(actual: float, gate: float) -> str:
    return "pass" if actual >= gate else "fail"


def _summarize_cpp() -> dict[str, Any]:
    config = load_official_cpp_config()
    programs: list[dict[str, Any]] = []
    with_source = 0
    for name, cfg in config.programs.items():
        has_source = name == "Cash" or bool(
            cfg.get("valuation_program_key") or cfg.get("official_cpp") or cfg.get("manual_cpp")
        )
        if has_source:
            with_source += 1
        programs.append(
            {
                "program": name,
                "has_source": has_source,
            }
        )
    override_count = len(config.card_overrides)
    total = len(config.programs)
    return {
        "version": config.version,
        "program_count": total,
        "programs_with_source": with_source,
        "card_override_count": override_count,
        "coverage_pct": round(100.0 * with_source / total, 1) if total else 100.0,
        "gate": 1.0,
        "status": "pass" if with_source == total else "fail",
        "programs": programs,
        "overrides": [
            {"card_key": key, **value} for key, value in config.card_overrides.items()
        ],
    }


def _summarize_external(*, reports_dir: Path | None = None) -> dict[str, Any]:
    """Load latest external cross-check report, or pending if not run yet."""
    out = reports_dir or Path(__file__).resolve().parents[3] / "reports" / "validation"
    files = sorted(out.glob("external-crosscheck-*.json"), reverse=True)
    if not files:
        return {
            "ok": False,
            "status": "pending",
            "cross_verified_pct": 0.0,
            "gate_pct": 90.0,
            "scraped_count": 0,
            "blockers": ["Run: paycue-db validation-external"],
            "report_path": None,
        }
    data = json.loads(files[0].read_text())
    return {
        "ok": bool(data.get("ok")),
        "status": "pass" if data.get("ok") else "fail",
        "cross_verified_pct": data.get("cross_verified_pct", 0),
        "gate_pct": data.get("gate_pct", 90),
        "scraped_count": data.get("scraped_count", 0),
        "blockers": data.get("blockers") or [],
        "report_path": str(files[0]),
    }


def _summarize_mcc_gap(*, db_path: Path | None) -> dict[str, Any]:
    from credit_rewards.validation.mcc_gap import run_mcc_gap_analysis

    result = run_mcc_gap_analysis(db_path_override=db_path)
    return {
        **result.to_dict(),
        "status": "pass" if result.ok else "fail",
        "gap_count": sum(1 for c in result.categories if c.gap),
    }


def _summarize_mcc() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    unmapped_label = "Unmapped MCC — use card base earn rate"
    for item in TOP_VALIDATION_MCCS:
        match = lookup_mcc_category(item["code"])
        mapped = match.mcc_description != unmapped_label
        rows.append(
            {
                "mcc": item["code"],
                "label": item["label"],
                "category": match.spend_bonus_category_name,
                "description": match.mcc_description,
                "mapped": mapped,
            }
        )
    mapped_count = sum(1 for r in rows if r["mapped"])
    total = len(rows)
    coverage = mapped_count / total if total else 1.0
    return {
        "total_checked": total,
        "mapped_count": mapped_count,
        "coverage_pct": round(100.0 * coverage, 1),
        "gate": MCC_GATE,
        "status": _gate_status(coverage, MCC_GATE),
        "rows": rows,
    }


def build_validation_dashboard(
    *,
    fetch_evidence: bool = True,
    reference_dir: Path | None = None,
    db_path: Path | None = None,
    golden_path: Path | None = None,
    l1_results_override: list[Any] | None = None,
    golden_result_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate L1–L3, CPP, and MCC validation for API + visualization."""
    ref_dir = reference_dir or REFERENCE_DIR
    card_keys = [entry["card_key"] for entry in load_card_registry()]

    if l1_results_override is not None:
        l1_results = l1_results_override
    else:
        l1_results = validate_all(card_keys, reference_dir=ref_dir)
    l1_pass = sum(1 for r in l1_results if r.ok)
    l1_total = len(l1_results)
    l1_rate = l1_pass / l1_total if l1_total else 0.0

    compare_reports = compare_all(
        card_keys,
        reference_dir=ref_dir,
        db_path=db_path,
        fetch_evidence=fetch_evidence,
    )
    source_types = _load_source_types(db_path)
    l2_cards: list[dict[str, Any]] = []
    verified_sum = 0
    row_sum = 0
    scrape_card_count = 0
    for report in compare_reports:
        stats = summarize_reference_verification(report)
        src = source_types.get(report.card_key, "unknown")
        if src == "scrape":
            scrape_card_count += 1
            verified_sum += stats["verified_rows"]
            row_sum += stats["total_rows"]
        verified_pct = stats["verified_pct"]
        if stats["total_rows"] == 0 and report.aligned:
            verified_pct = 100.0
        l2_cards.append(
            {
                "card_key": report.card_key,
                "card_name": report.card_name,
                "source_type": src,
                "verified_pct": verified_pct,
                "verified_rows": stats["verified_rows"],
                "total_rows": stats["total_rows"],
                "aligned": stats["aligned"],
                "scrape_verified": stats["scrape_verified"],
                "parser_fix_needed": stats["parser_fix_needed"],
                "compare_url": f"/compare#{report.card_key}",
            }
        )
    l2_rate = verified_sum / row_sum if row_sum else 1.0

    golden = golden_result_override or run_golden_cases(path=golden_path or GOLDEN_CASES_PATH, db_path=db_path)
    l3_rate = golden["pass_rate"]

    cpp = _summarize_cpp()
    mcc = _summarize_mcc()
    external = _summarize_external()
    mcc_gap = _summarize_mcc_gap(db_path=db_path)

    layers = [
        {
            "id": "l1",
            "name": "L1 — DB ↔ Reference",
            "description": "Imported runtime data matches Rewards CC reference JSON",
            "independent": True,
            "pass_count": l1_pass,
            "total": l1_total,
            "rate": round(l1_rate * 100, 1),
            "gate_pct": L1_GATE * 100,
            "status": _gate_status(l1_rate, L1_GATE),
        },
        {
            "id": "l2",
            "name": "L2 — Reference verified",
            "description": "Reference earn rows confirmed (match or issuer-backed reference)",
            "independent": False,
            "pass_count": verified_sum,
            "total": row_sum,
            "rate": round(l2_rate * 100, 1),
            "gate_pct": L2_GATE * 100,
            "status": _gate_status(l2_rate, L2_GATE),
        },
        {
            "id": "l3",
            "name": "L3 — Golden recommend",
            "description": "Wallet scenarios pick expected best card",
            "independent": True,
            "pass_count": golden["passed"],
            "total": golden["total"],
            "rate": round(l3_rate * 100, 1),
            "gate_pct": L3_GATE * 100,
            "status": _gate_status(l3_rate, L3_GATE) if golden["total"] else "pending",
        },
        {
            "id": "cpp",
            "name": "CPP sources",
            "description": "Official cents-per-point table coverage",
            "independent": True,
            "pass_count": cpp["programs_with_source"],
            "total": cpp["program_count"],
            "rate": cpp["coverage_pct"],
            "gate_pct": 100.0,
            "status": cpp["status"],
        },
        {
            "id": "mcc",
            "name": "MCC coverage",
            "description": f"Top {mcc['total_checked']} checkout MCC codes mapped",
            "independent": True,
            "pass_count": mcc["mapped_count"],
            "total": mcc["total_checked"],
            "rate": mcc["coverage_pct"],
            "gate_pct": MCC_GATE * 100,
            "status": mcc["status"],
        },
        {
            "id": "external",
            "name": "External cross-verify",
            "description": "Raw issuer scrape vs reference (≥2 independent signals per row)",
            "independent": True,
            "pass_count": external.get("scraped_count", 0),
            "total": len(card_keys),
            "rate": external.get("cross_verified_pct", 0),
            "gate_pct": external.get("gate_pct", 90),
            "status": external.get("status", "pending"),
        },
        {
            "id": "mcc_gap",
            "name": "MCC category gap",
            "description": f"Phase-1 {mcc_gap.get('total_categories', 0)} earn categories classified + MCC path",
            "independent": True,
            "pass_count": mcc_gap.get("total_categories", 0) - mcc_gap.get("gap_count", 0),
            "total": mcc_gap.get("total_categories", 0),
            "rate": mcc_gap.get("mcc_bonus_coverage_pct", 0),
            "gate_pct": 70.0,
            "status": mcc_gap.get("status", "fail"),
        },
    ]

    independent_blockers: list[str] = []
    l2_blockers: list[str] = []
    if _gate_status(l1_rate, L1_GATE) == "fail":
        independent_blockers.append("L1: re-run sync-reference && import-reference")
    if golden["total"] and _gate_status(l3_rate, L3_GATE) == "fail":
        independent_blockers.append("L3: fix golden recommend failures")
    if not golden["total"]:
        independent_blockers.append("L3: add golden_cases.yaml scenarios")
    if cpp["status"] == "fail":
        independent_blockers.append("CPP: missing program sources in official_cpp.yaml")
    if mcc["status"] == "fail":
        independent_blockers.append("MCC: expand visa_mcc_categories.yaml")
    if not external.get("ok"):
        if external.get("status") == "pending":
            independent_blockers.append("External: run paycue-db validation-external")
        else:
            independent_blockers.extend(external.get("blockers") or ["External cross-verify failed"])
    if not mcc_gap.get("ok"):
        independent_blockers.extend(mcc_gap.get("blockers") or ["MCC gap: expand category mappings"])

    if scrape_card_count < MIN_SCRAPED_CARDS:
        l2_blockers.append(
            f"L2: only {scrape_card_count}/20 cards scraped — fix parsers "
            f"(target ≥{MIN_SCRAPED_CARDS})"
        )
    elif _gate_status(l2_rate, L2_GATE) == "fail":
        l2_blockers.append("L2: review /compare evidence for stale reference rows")

    blockers = independent_blockers + l2_blockers
    independent_ready = not independent_blockers

    core_blockers: list[str] = []
    if not external.get("ok"):
        core_blockers.extend(external.get("blockers") or ["External cross-verify not passed"])
    if not mcc_gap.get("ok"):
        core_blockers.extend(mcc_gap.get("blockers") or [])

    core_ready = independent_ready and external.get("ok") and mcc_gap.get("ok")
    ship_ready = core_ready and not l2_blockers

    matrix: list[dict[str, Any]] = []
    l1_by_key = {r.card_key: r for r in l1_results}
    l2_by_key = {c["card_key"]: c for c in l2_cards}
    for key in card_keys:
        l1 = l1_by_key.get(key)
        l2 = l2_by_key.get(key, {})
        row_blockers: list[str] = []
        if l1 and not l1.ok:
            row_blockers.append("L1 fail")
        src = l2.get("source_type", "unknown")
        if src != "scrape":
            row_blockers.append("no live scrape")
        elif l2.get("verified_pct", 0) < L2_GATE * 100:
            row_blockers.append("L2 low")
        l2_pct = l2.get("verified_pct") if src == "scrape" else None
        matrix.append(
            {
                "card_key": key,
                "card_name": l2.get("card_name") or key,
                "source_type": src,
                "l1_ok": bool(l1 and l1.ok),
                "l1_diff_count": len(l1.diffs) if l1 else 0,
                "l2_verified_pct": l2_pct,
                "l2_aligned": l2.get("aligned", False) if src == "scrape" else None,
                "blocker": "; ".join(row_blockers) if row_blockers else "",
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "independent_ready": independent_ready,
        "core_ready": core_ready,
        "independent_blockers": independent_blockers,
        "core_blockers": core_blockers,
        "l2_blockers": l2_blockers,
        "ship_ready": ship_ready,
        "blockers": blockers + core_blockers,
        "layers": layers,
        "cards": matrix,
        "l1": {
            "pass_count": l1_pass,
            "total": l1_total,
            "results": [
                {
                    "card_key": r.card_key,
                    "ok": r.ok,
                    "diff_count": len(r.diffs),
                    "notes": r.notes,
                    "diffs": [asdict(d) for d in r.diffs],
                }
                for r in l1_results
            ],
        },
        "l2": {
            "verified_pct": round(l2_rate * 100, 1),
            "scraped_card_count": scrape_card_count,
            "cards": l2_cards,
        },
        "l3": golden,
        "cpp": cpp,
        "mcc": mcc,
        "external": external,
        "mcc_gap": mcc_gap,
    }
