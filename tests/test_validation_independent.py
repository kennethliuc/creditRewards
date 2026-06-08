"""Independent validation and monitor orchestrator tests."""

from credit_rewards.validation.independent import run_independent_validation
from credit_rewards.validation.orchestrator import build_monitor_plan
from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

import pytest

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference && import-reference",
)


def test_independent_validation_passes(twenty_card_db):
    result = run_independent_validation(
        db_path_override=twenty_card_db,
        reimport_reference=False,
    )
    assert result.ok, result.blockers
    assert all(g.status == "pass" for g in result.gates)


def test_monitor_phase1_complete(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    plan = build_monitor_plan(include_l2=False, skip_network=True)
    assert plan["independent_ok"] is True
    monitor_tasks = [t for t in plan["tasks"] if t["agent"] == "Monitor"]
    assert monitor_tasks
