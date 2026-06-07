"""Monitor — re-check payment UI gates until page_ready."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from credit_rewards.payment_ui.gates import run_all_gates
from credit_rewards.payment_ui.orchestrator import build_payment_ui_monitor_plan


def run_payment_ui_monitor_cycle(*, cycle: int = 1, run_pytest: bool = True) -> dict[str, Any]:
    report = run_all_gates(run_pytest=run_pytest)
    plan = build_payment_ui_monitor_plan(run_pytest=False)
    plan["cycle"] = cycle
    plan["gates"] = report["gates"]
    plan["page_ready"] = report["page_ready"]
    plan["blockers"] = report["blockers"]
    return plan


def run_payment_ui_monitor_until_ready(
    *,
    max_cycles: int = 3,
    run_pytest: bool = True,
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None

    for cycle in range(1, max_cycles + 1):
        result = run_payment_ui_monitor_cycle(cycle=cycle, run_pytest=run_pytest)
        history.append(
            {
                "cycle": cycle,
                "page_ready": result["page_ready"],
                "phase": result["phase"],
                "blockers": result["blockers"],
            }
        )
        final = result
        if result["page_ready"]:
            break

    assert final is not None
    return {
        "finished_at": datetime.now(UTC).isoformat(),
        "page_ready": final["page_ready"],
        "cycles_run": len(history),
        "final": final,
        "history": history,
    }
