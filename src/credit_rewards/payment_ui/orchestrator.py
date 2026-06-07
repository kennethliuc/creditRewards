"""Payment UI Monitor — dispatch sub-agent tasks from gate failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from credit_rewards.payment_ui.gates import run_all_gates

AGENT_MONITOR = "Monitor"
AGENT_MERCHANT = "MerchantAgent"
AGENT_FRONTEND = "FrontendAgent"
AGENT_API = "APIAgent"
AGENT_QA = "QAAgent"

TRACK_AGENTS = {
    "M": AGENT_MERCHANT,
    "P": AGENT_FRONTEND,
    "R": AGENT_API,
    "T": AGENT_QA,
    "V": AGENT_MONITOR,
}


@dataclass
class PaymentUITask:
    agent: str
    priority: int
    track: str
    scope: str
    commands: list[str] = field(default_factory=list)
    acceptance: str = ""
    requirement_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "priority": self.priority,
            "track": self.track,
            "scope": self.scope,
            "commands": self.commands,
            "acceptance": self.acceptance,
            "requirementIds": self.requirement_ids,
        }


def _tasks_from_gates(gate_report: dict[str, Any]) -> list[PaymentUITask]:
    tasks: list[PaymentUITask] = []
    seen: set[tuple[str, str]] = set()

    for gate in gate_report.get("gates") or []:
        if gate.get("status") != "fail":
            continue
        track = gate.get("track", "?")
        agent = TRACK_AGENTS.get(track, AGENT_MONITOR)
        for blocker in gate.get("blockers") or [gate.get("name", "fix gate")]:
            key = (agent, blocker)
            if key in seen:
                continue
            seen.add(key)
            req_ids = {
                "M": ["R1", "R2", "R3"],
                "P": ["R3", "R4", "R7"],
                "R": ["R5", "R6"],
                "T": ["R8"],
                "V": ["R8"],
            }.get(track, [])
            commands = {
                AGENT_MERCHANT: [
                    "pytest tests/test_merchant_mapping.py -q",
                    "# edit data/merchants/merchant_categories.yaml",
                ],
                AGENT_FRONTEND: ["# edit src/credit_rewards/web/static/index.html"],
                AGENT_API: ["# edit src/credit_rewards/web/app.py"],
                AGENT_QA: ["pytest tests/test_merchant_mapping.py tests/test_pay_web.py -q"],
                AGENT_MONITOR: ["credit-rewards-db validation-monitor-run"],
            }.get(agent, [])
            tasks.append(
                PaymentUITask(
                    agent=agent,
                    priority=0 if track == "V" else 1 if track in {"M", "R"} else 2,
                    track=track,
                    scope=blocker,
                    commands=commands,
                    acceptance=gate.get("name", ""),
                    requirement_ids=req_ids,
                )
            )

    tasks.sort(key=lambda t: (t.priority, t.track, t.agent))
    return tasks


def build_payment_ui_monitor_plan(*, run_pytest: bool = True) -> dict[str, Any]:
    """Monitor snapshot: gates, page_ready, sub-agent dispatch list."""
    report = run_all_gates(run_pytest=run_pytest)
    tasks = _tasks_from_gates(report)

    phase = "page_ready" if report["page_ready"] else "fixing"
    if any(g["track"] == "V" and g["status"] == "fail" for g in report["gates"]):
        phase = "blocked_on_validation"

    return {
        "phase": phase,
        "page_ready": report["page_ready"],
        "blockers": report["blockers"],
        "gates": report["gates"],
        "tracks": report["tracks"],
        "tasks": [t.to_dict() for t in tasks],
        "requirements_doc": "docs/payment-ui-requirements.md",
        "monitor_doc": "docs/payment-ui-agent-system.md",
        "tracker_doc": "docs/payment-ui-tracker.md",
        "commands": {
            "monitor": "credit-rewards-db payment-ui-monitor",
            "monitor_run": "credit-rewards-db payment-ui-monitor-run",
            "validation": "credit-rewards-db validation-monitor-run",
            "pytest": "pytest tests/test_merchant_mapping.py tests/test_pay_web.py -q",
            "dev_server": "uvicorn credit_rewards.web.app:app --port 8000",
        },
        "manual_smoke": [
            "Open http://127.0.0.1:8000/",
            "Paste long checkout URL with embedded chipotle.com",
            "Confirm merchant modal → see full 20-card ranking",
            "Or: bash scripts/smoke_payment_ui.sh",
        ],
    }
