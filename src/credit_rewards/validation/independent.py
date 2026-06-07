"""Independent validation — gates that do not require live issuer scrape (L2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from credit_rewards.datastore.db import db_path
from credit_rewards.ingest.reference_import import import_reference_to_db
from credit_rewards.ingest.reference_validate import validate_all
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.validation.dashboard import (
    L1_GATE,
    L3_GATE,
    MCC_GATE,
    _gate_status,
    _summarize_cpp,
    _summarize_mcc,
)
from credit_rewards.validation.golden import run_golden_cases

INDEPENDENT_LAYER_IDS = frozenset({"l1", "l3", "cpp", "mcc"})


@dataclass
class IndependentGate:
    layer_id: str
    name: str
    rate: float
    gate_pct: float
    status: str
    detail: str = ""


@dataclass
class IndependentValidationResult:
    ok: bool
    gates: list[IndependentGate] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "gates": [
                {
                    "layer_id": g.layer_id,
                    "name": g.name,
                    "rate": g.rate,
                    "gate_pct": g.gate_pct,
                    "status": g.status,
                    "detail": g.detail,
                }
                for g in self.gates
            ],
            "blockers": self.blockers,
        }


def run_independent_validation(
    *,
    db_path_override: Path | None = None,
    reimport_reference: bool = True,
) -> IndependentValidationResult:
    """
    Run L1 + L3 + CPP + MCC on reference-imported DB.

    Does not scrape issuer pages or run L2 compare.
    """
    path = db_path_override or db_path()
    if reimport_reference:
        import_reference_to_db(db_path=path)
        from credit_rewards.ingest.official_cpp_refresh import refresh_official_cpp

        refresh_official_cpp(db_path=path)

    card_keys = [e["card_key"] for e in load_card_registry()]
    l1_results = validate_all(card_keys)
    l1_pass = sum(1 for r in l1_results if r.ok)
    l1_total = len(l1_results)
    l1_rate = l1_pass / l1_total if l1_total else 0.0

    golden = run_golden_cases(db_path=path)
    l3_rate = golden["pass_rate"]

    cpp = _summarize_cpp()
    mcc = _summarize_mcc()

    gates = [
        IndependentGate(
            "l1",
            "L1 — DB ↔ Reference",
            round(l1_rate * 100, 1),
            L1_GATE * 100,
            _gate_status(l1_rate, L1_GATE),
            f"{l1_pass}/{l1_total} cards",
        ),
        IndependentGate(
            "l3",
            "L3 — Golden recommend",
            round(l3_rate * 100, 1),
            L3_GATE * 100,
            _gate_status(l3_rate, L3_GATE) if golden["total"] else "pending",
            f"{golden.get('passed', 0)}/{golden.get('total', 0)} cases",
        ),
        IndependentGate(
            "cpp",
            "CPP sources",
            cpp["coverage_pct"],
            100.0,
            cpp["status"],
            f"{cpp['programs_with_source']}/{cpp['program_count']} programs",
        ),
        IndependentGate(
            "mcc",
            "MCC coverage",
            mcc["coverage_pct"],
            MCC_GATE * 100,
            mcc["status"],
            f"{mcc['mapped_count']}/{mcc['total_checked']} codes",
        ),
    ]

    blockers: list[str] = []
    if _gate_status(l1_rate, L1_GATE) == "fail":
        blockers.append("Agent Reference: sync-reference && import-reference")
    if not golden["total"]:
        blockers.append("Agent Benchmark: add data/validation/golden_cases.yaml")
    elif _gate_status(l3_rate, L3_GATE) == "fail":
        failed = [c["id"] for c in golden.get("cases", []) if not c.get("ok")]
        blockers.append(f"Agent Rank: fix golden cases {failed[:5]}")
    if cpp["status"] == "fail":
        blockers.append("Agent CPP: refresh-official-cpp / official_cpp.yaml")
    if mcc["status"] == "fail":
        blockers.append("Agent MCC: expand data/mcc/visa_mcc_categories.yaml")

    return IndependentValidationResult(
        ok=not blockers,
        gates=gates,
        blockers=blockers,
    )
