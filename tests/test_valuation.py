from datetime import date

import pytest
from credit_rewards.models import PurchaseContext
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.recommend import recommend_best_cards
from credit_rewards.valuation import compute_earn_value
from pathlib import Path
import json

from tests.official_cpp_fixtures import enrich_from_official_table

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    card = normalize_card_detail(json.loads((FIXTURES / name).read_text()))
    return enrich_from_official_table(card)


def test_amex_gold_grocery_official_valuation():
    card = _load("amex-gold.json")
    purchase = PurchaseContext(category="Grocery Stores", amount_usd=100)
    mult, points, value, _, _, _, _ = compute_earn_value(card, purchase)
    assert mult == 4.0
    assert points == 400
    assert value == 8.8  # 400 × 2.2¢ official


def test_citi_double_cash_uses_thankyou_cpp():
    card = enrich_from_official_table(normalize_card_detail(json.loads((FIXTURES / "citi-double-cash.json").read_text())))
    purchase = PurchaseContext(category="Anything", amount_usd=100)
    _, _, value, _, _, _, _ = compute_earn_value(card, purchase)
    assert value == pytest.approx(3.4)  # 200 × 1.7¢


def test_cash_back_card_literal_percent():
    card = normalize_card_detail(json.loads((FIXTURES / "citi-double-cash.json").read_text()))
    card = card.model_copy(update={"valuate_as_points": False, "official_cpp": 1.0, "resolved_program": "Cash"})
    purchase = PurchaseContext(category="Anything", amount_usd=100)
    mult, _, value, _, _, _, _ = compute_earn_value(card, purchase)
    assert mult == 2.0
    assert value == 2.0


def test_expired_quarterly_bonus_falls_back_to_base():
    card = _load("chase-freedomflex.json")
    purchase = PurchaseContext(
        category="Grocery Stores",
        amount_usd=100,
        as_of=date(2025, 6, 1),
    )
    mult, _, _, _, _, _, _ = compute_earn_value(card, purchase)
    assert mult == 1.0


def test_recommend_ranks_amex_above_citi_for_grocery():
    wallet = [_load("amex-gold.json"), _load("citi-double-cash.json")]
    purchase = PurchaseContext(category="Grocery Stores", amount_usd=100)
    results = recommend_best_cards(wallet, purchase)
    assert results[0].card_key == "amex-gold"


def test_recommend_includes_points_vs_cash_metadata():
    wallet = [_load("amex-gold.json"), _load("citi-double-cash.json")]
    purchase = PurchaseContext(category="Grocery Stores", amount_usd=100)
    results = {r.card_key: r for r in recommend_best_cards(wallet, purchase)}
    assert results["amex-gold"].valuate_as_points is True
    assert results["amex-gold"].points_earned == 400
    assert results["citi-double-cash"].valuate_as_points is True
    assert results["citi-double-cash"].resolved_program == "Citi ThankYou Rewards"
