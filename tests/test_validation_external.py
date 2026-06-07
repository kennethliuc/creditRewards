"""Tests for external cross-validation track."""

from credit_rewards.validation.external import run_external_validation
from credit_rewards.validation.orchestrator import (
    AGENT_CROSS_VALIDATE,
    AGENT_EXTERNAL,
    AGENT_MCC_COVERAGE,
    build_monitor_plan,
)

import pytest

from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: credit-rewards-db sync-reference && import-reference",
)


def test_external_validation_skip_network_structure(twenty_card_db):
    result = run_external_validation(skip_network=True)
    assert result.scraped_count == 0
    assert len(result.cards) == 20
    assert not result.ok
    assert result.blockers


def test_monitor_dispatches_external_when_internal_passes(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    plan = build_monitor_plan(skip_network=True)
    assert plan["independent_ok"] is True
    if not plan.get("external_ok"):
        assert plan["phase"] in ("external", "mcc_gap", "core_complete")
        agents = {t["agent"] for t in plan["tasks"]}
        external_agents = {AGENT_EXTERNAL, AGENT_CROSS_VALIDATE, "Issuer", "Parser", AGENT_MCC_COVERAGE}
        assert agents & external_agents or plan["phase"] == "mcc_gap"


def test_cross_verified_row_requires_two_signals():
    from credit_rewards.ingest.compare import ComparisonMatch, RuleRow
    from credit_rewards.validation.external import _signals_for_match

    match = ComparisonMatch(
        scraped=RuleRow(1, "Dining", 4.0),
        reference=RuleRow(1, "Dining", 4.0),
    )
    signals, cross, _note = _signals_for_match(match, issuer_html_fetched=False)
    assert "reference" in signals
    assert "raw_scrape" in signals
    assert cross is True

    signals2, cross2, _ = _signals_for_match(match, issuer_html_fetched=True)
    assert "issuer_page" in signals2
    assert cross2 is True
