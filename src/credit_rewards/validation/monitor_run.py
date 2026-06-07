"""Monitor agent — run validation tracks until core_ready or hard stop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credit_rewards.validation.external import (
    run_external_validation,
    write_external_report,
)
from credit_rewards.validation.independent import run_independent_validation
from credit_rewards.validation.mcc_gap import run_mcc_gap_analysis, write_mcc_gap_report
from credit_rewards.validation.orchestrator import build_monitor_plan


@dataclass
class MonitorCycleResult:
    cycle: int
    core_ready: bool
    phase: str
    independent_ok: bool
    external_pct: float
    external_ok: bool
    mcc_gap_ok: bool
    blockers: list[str] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "core_ready": self.core_ready,
            "phase": self.phase,
            "independent_ok": self.independent_ok,
            "external_pct": self.external_pct,
            "external_ok": self.external_ok,
            "mcc_gap_ok": self.mcc_gap_ok,
            "blockers": self.blockers,
            "tasks": self.tasks,
        }


def run_monitor_cycle(
    *,
    cycle: int = 1,
    fetch_evidence: bool = True,
    write_reports: bool = True,
) -> MonitorCycleResult:
    """Single Monitor pass: run gates, write reports, return dispatch plan."""
    independent = run_independent_validation(reimport_reference=False)
    external = run_external_validation(fetch_evidence=fetch_evidence)
    mcc_gap = run_mcc_gap_analysis()

    if write_reports:
        write_external_report(external)
        write_mcc_gap_report(mcc_gap)

    plan = build_monitor_plan(
        include_external=False,
        include_mcc_gap=False,
        fetch_evidence=fetch_evidence,
    )
    plan["independent_ok"] = independent.ok
    plan["external_ok"] = external.ok
    plan["external"] = external.to_dict()
    plan["mcc_gap_ok"] = mcc_gap.ok
    plan["mcc_gap"] = mcc_gap.to_dict()
    plan["core_ready"] = independent.ok and external.ok and mcc_gap.ok

    blockers = []
    if not independent.ok:
        blockers.extend(independent.blockers)
    if not external.ok:
        blockers.extend(external.blockers)
    if not mcc_gap.ok:
        blockers.extend(mcc_gap.blockers)

    return MonitorCycleResult(
        cycle=cycle,
        core_ready=plan["core_ready"],
        phase=plan["phase"],
        independent_ok=independent.ok,
        external_pct=external.cross_verified_pct,
        external_ok=external.ok,
        mcc_gap_ok=mcc_gap.ok,
        blockers=blockers,
        tasks=plan.get("tasks") or [],
    )


def run_monitor_until_ready(
    *,
    max_cycles: int = 3,
    fetch_evidence: bool = True,
) -> dict[str, Any]:
    """
    Monitor supervisor loop.

    Re-runs validation gates each cycle and returns final status + task plan
    for fixer sub-agents. Does not auto-edit parsers (fixers run separately).
    """
    history: list[dict[str, Any]] = []
    final: MonitorCycleResult | None = None

    for cycle in range(1, max_cycles + 1):
        result = run_monitor_cycle(cycle=cycle, fetch_evidence=fetch_evidence)
        history.append(result.to_dict())
        final = result
        if result.core_ready:
            break

    assert final is not None
    return {
        "finished_at": datetime.now(UTC).isoformat(),
        "core_ready": final.core_ready,
        "cycles_run": len(history),
        "final": final.to_dict(),
        "history": history,
    }
