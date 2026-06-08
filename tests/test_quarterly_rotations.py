"""Quarterly rotation schedules for Discover it Cash Back and similar cards."""

from datetime import date

from credit_rewards.ingest.quarterly_rotations import (
    _build_rotation_rules,
    enrich_with_quarterly_rotations,
    load_quarterly_rotations,
)
from credit_rewards.ingest.reference_sync import load_reference_card
from credit_rewards.models import PurchaseContext
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.valuation import best_multiplier, compute_earn_value


def test_discover_rotation_yaml_has_three_quarters():
    config = load_quarterly_rotations()["discover-it-cash-back"]
    assert len(config["quarters"]) == 3
    rules = _build_rotation_rules(config)
    assert len(rules) == 9  # 3 + 2 + 4 categories


def test_discover_cash_back_q2_dining_five_percent():
    detail = load_reference_card("discover-it-cash-back", upstream_key="discover-cashback")
    assert detail is not None
    card = normalize_card_detail([detail])
    mult, rule = best_multiplier(card, "Dining", as_of=date(2026, 5, 15))
    assert mult == 5.0
    assert rule is not None
    assert rule.limit_begin == date(2026, 4, 1)


def test_discover_cash_back_q1_grocery_five_percent():
    detail = load_reference_card("discover-it-cash-back", upstream_key="discover-cashback")
    card = normalize_card_detail([detail])
    mult, _ = best_multiplier(card, "Grocery Stores", as_of=date(2026, 2, 1))
    assert mult == 5.0


def test_discover_cash_back_q3_gas_five_percent():
    detail = load_reference_card("discover-it-cash-back", upstream_key="discover-cashback")
    card = normalize_card_detail([detail])
    mult, _ = best_multiplier(card, "Gas Stations", as_of=date(2026, 8, 1))
    assert mult == 5.0


def test_discover_cash_back_off_quarter_falls_back_to_base():
    detail = load_reference_card("discover-it-cash-back", upstream_key="discover-cashback")
    card = normalize_card_detail([detail])
    mult, _ = best_multiplier(card, "Dining", as_of=date(2026, 1, 15))
    assert mult == 1.0


def test_discover_miles_no_rotation_rules():
    detail = load_reference_card("discover-it-miles", upstream_key="discover-miles")
    assert detail is not None
    assert detail.get("spendBonusCategory") == []
    card = normalize_card_detail([detail])
    mult, _, value, _, _, _, _ = compute_earn_value(
        card,
        PurchaseContext(category="Dining", amount_usd=100),
    )
    assert mult == 1.5
    assert value == 1.5


def test_enrich_replaces_date_limited_rules_only():
    detail = {
        "cardKey": "discover-it-cash-back",
        "spendBonusCategory": [
            {
                "spendBonusCategoryName": "Dining",
                "spendBonusCategoryId": 160378660,
                "earnMultiplier": 5.0,
                "isDateLimit": 1,
                "limitBeginDate": "2020-01-01",
                "limitEndDate": "2020-03-31",
            },
            {
                "spendBonusCategoryName": "Permanent Bonus",
                "spendBonusCategoryId": 999,
                "earnMultiplier": 2.0,
                "isDateLimit": 0,
            },
        ],
    }
    enriched = enrich_with_quarterly_rotations(detail, card_key="discover-it-cash-back")
    rules = enriched["spendBonusCategory"]
    assert any(r["spendBonusCategoryName"] == "Permanent Bonus" for r in rules)
    assert sum(1 for r in rules if r.get("isDateLimit")) == 9
