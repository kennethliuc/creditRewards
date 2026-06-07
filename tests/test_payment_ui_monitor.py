"""Payment UI Monitor gates."""

from credit_rewards.payment_ui.gates import run_all_gates
from credit_rewards.payment_ui.orchestrator import build_payment_ui_monitor_plan


def test_payment_ui_gates_pass():
    report = run_all_gates(run_pytest=True)
    assert report["page_ready"], report["blockers"]


def test_monitor_plan_structure():
    plan = build_payment_ui_monitor_plan(run_pytest=False)
    assert "tasks" in plan
    assert "requirements_doc" in plan
    assert plan["phase"] in {"page_ready", "fixing", "blocked_on_validation"}
