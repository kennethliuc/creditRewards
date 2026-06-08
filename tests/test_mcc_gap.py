"""Tests for MCC category gap analysis."""

from credit_rewards.validation.mcc_gap import (
    collect_card_categories,
    run_mcc_gap_analysis,
)

import pytest

from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference && import-reference",
)


def test_collect_card_categories(twenty_card_db):
    cats = collect_card_categories(db_path_override=twenty_card_db)
    assert len(cats) >= 20
    names = {c.category_name for c in cats}
    assert "Dining" in names
    assert "Grocery Stores" in names


def test_mcc_gap_classifies_all_categories(twenty_card_db):
    result = run_mcc_gap_analysis(db_path_override=twenty_card_db)
    assert result.total_categories == len(result.categories)
    assert result.classified_pct == 100.0
    assert all(c.strategy for c in result.categories)


def test_mcc_gap_meets_bonus_gate(twenty_card_db):
    result = run_mcc_gap_analysis(db_path_override=twenty_card_db)
    assert result.classified_pct == 100.0
    assert result.mcc_bonus_coverage_pct >= 70.0
    assert result.ok
