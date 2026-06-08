"""L3 golden recommend validation against imported reference DB."""

from __future__ import annotations

import pytest

from credit_rewards.validation.golden import run_golden_cases
from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference && import-reference",
)


def test_golden_recommend_pass_rate(twenty_card_db):
    result = run_golden_cases(db_path=twenty_card_db)
    assert result["configured"]
    assert result["total"] >= 18
    assert result["pass_rate"] >= 0.95, [
        c for c in result["cases"] if not c.get("ok")
    ]


def test_golden_headline_cases(twenty_card_db):
    result = run_golden_cases(db_path=twenty_card_db)
    headline = {
        "amex_gold_dining_100",
        "csr_travel_500",
        "cfu_base_50",
        "mcc_grocery_5411",
        "mcc_dining_5812",
    }
    by_id = {c["id"]: c for c in result["cases"]}
    for case_id in headline:
        assert by_id[case_id]["ok"], by_id[case_id]
