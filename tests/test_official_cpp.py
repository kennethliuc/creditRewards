"""Official CPP aggregation and single-value valuation tests."""

from __future__ import annotations

import pytest

from credit_rewards.benchmarks import load_program_benchmarks, typical_utilization_cpp
from credit_rewards.official_cpp import (
    aggregate_official_cpp,
    compute_program_official_cpp,
    fallback_program_table,
    load_official_cpp_config,
    resolve_card_official_cpp,
)
from tests.official_cpp_fixtures import EXPECTED_OFFICIAL_CPP

TYPICAL_CPP = {
    "American Express Membership Rewards": 1.47,
    "Chase Ultimate Rewards": 1.3825,
    "Citi ThankYou Rewards": 1.185,
    "Capital One Miles": 1.215,
    "Bilt Points": 1.57,
    "Wells Fargo Go Far Rewards": 1.0,
    "Cash": 1.0,
}


def test_max_aggregation_picks_highest():
    assert aggregate_official_cpp([1.6, 1.7, 2.0], sanity_cap=3.5) == 2.0


def test_sanity_cap_clamps_outliers():
    assert aggregate_official_cpp([4.0, 2.0], sanity_cap=3.5) == 3.5


def test_typical_utilization_amex_mr():
    bench = load_program_benchmarks()["American Express Membership Rewards"]
    assert typical_utilization_cpp(bench) == pytest.approx(1.47)


def test_amex_mr_official_cpp_uses_typical_not_max():
    official, sources = compute_program_official_cpp(
        "American Express Membership Rewards",
        rewards_cc_values=[2.2, 2.2],
        benchmark_cpp=2.0,
    )
    assert official == pytest.approx(1.47)
    assert sources["typical_utilization"] == pytest.approx(1.47)
    assert sources["rewards_cc_max"] == 2.2


def test_citi_typ_typical_below_benchmark():
    official, _ = compute_program_official_cpp(
        "Citi ThankYou Rewards",
        rewards_cc_values=[1.6],
        benchmark_cpp=1.7,
    )
    assert official == pytest.approx(1.185)


def test_cfu_override_uses_chase_ur_typical_cpp():
    detail = {"baseSpendEarnType": "Cash", "baseSpendEarnValuation": 1.0}
    cpp, program = resolve_card_official_cpp(
        "chase-freedom-unlimited",
        detail,
        EXPECTED_OFFICIAL_CPP,
    )
    assert program == "Chase Ultimate Rewards"
    assert cpp == pytest.approx(1.3825)


def test_double_cash_override_uses_typ():
    detail = {"baseSpendEarnType": "Cash", "baseSpendEarnValuation": 1.0}
    cpp, program = resolve_card_official_cpp(
        "citi-double-cash",
        detail,
        EXPECTED_OFFICIAL_CPP,
    )
    assert program == "Citi ThankYou Rewards"
    assert cpp == pytest.approx(1.185)


def test_fallback_table_matches_typical_utilization():
    table = fallback_program_table()
    for program, expected in TYPICAL_CPP.items():
        assert table[program] == pytest.approx(expected)


def test_config_aggregation_mode():
    assert load_official_cpp_config().aggregation == "typical_utilization"
