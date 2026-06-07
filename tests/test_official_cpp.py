"""Official CPP aggregation and single-value valuation tests."""

from __future__ import annotations

import pytest

from credit_rewards.official_cpp import (
    aggregate_official_cpp,
    compute_program_official_cpp,
    load_official_cpp_config,
    resolve_card_official_cpp,
)
from credit_rewards.official_cpp import fallback_program_table
from tests.official_cpp_fixtures import EXPECTED_OFFICIAL_CPP


def test_max_aggregation_picks_highest():
    assert aggregate_official_cpp([1.6, 1.7, 2.0], sanity_cap=3.5) == 2.0


def test_sanity_cap_clamps_outliers():
    assert aggregate_official_cpp([4.0, 2.0], sanity_cap=3.5) == 3.5


def test_amex_mr_official_cpp():
    official, sources = compute_program_official_cpp(
        "American Express Membership Rewards",
        rewards_cc_values=[2.2, 2.2],
        benchmark_cpp=2.0,
    )
    assert official == pytest.approx(2.2)
    assert sources["rewards_cc_max"] == 2.2


def test_citi_typ_max_of_rc_and_benchmark():
    official, _ = compute_program_official_cpp(
        "Citi ThankYou Rewards",
        rewards_cc_values=[1.6],
        benchmark_cpp=1.7,
    )
    assert official == pytest.approx(1.7)


def test_cfu_override_uses_chase_ur_cpp():
    detail = {"baseSpendEarnType": "Cash", "baseSpendEarnValuation": 1.0}
    cpp, program = resolve_card_official_cpp(
        "chase-freedom-unlimited",
        detail,
        EXPECTED_OFFICIAL_CPP,
    )
    assert program == "Chase Ultimate Rewards"
    assert cpp == pytest.approx(2.0)


def test_double_cash_override_uses_typ():
    detail = {"baseSpendEarnType": "Cash", "baseSpendEarnValuation": 1.0}
    cpp, program = resolve_card_official_cpp(
        "citi-double-cash",
        detail,
        EXPECTED_OFFICIAL_CPP,
    )
    assert program == "Citi ThankYou Rewards"
    assert cpp == pytest.approx(1.7)


def test_fallback_table_matches_phase1_expectations():
    table = fallback_program_table()
    assert table["American Express Membership Rewards"] == pytest.approx(2.2)
    assert table["Bilt Points"] == pytest.approx(2.2)
    assert table["Cash"] == pytest.approx(1.0)
