"""Co-brand category index and auto-matching."""

from __future__ import annotations

import pytest

from credit_rewards.co_brand_category_index import (
    load_co_brand_category_index,
    resolve_co_brand_category_names,
)
from credit_rewards.ingest.reference_sync import assemble_card_from_category_snapshots, load_reference_card
from credit_rewards.merchant_co_brand import (
    catalog_merchant_id_for_display_name,
    co_brand_bonus_categories_for_merchant,
    co_brand_bonus_categories_for_purchase,
    canonical_merchant_id_for_purchase,
)
from credit_rewards.models import PurchaseContext
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.official_cpp import enrich_card_profile, fallback_program_table, resolve_card_official_cpp
from credit_rewards.recommend import recommend_best_cards
from credit_rewards.valuation import best_multiplier, compute_earn_value


def _load_card(card_key: str):
    detail = load_reference_card(card_key) or assemble_card_from_category_snapshots(card_key)
    assert detail is not None, card_key
    card = normalize_card_detail(detail)
    table = fallback_program_table()
    cpp, program = resolve_card_official_cpp(card_key, detail, table)
    return enrich_card_profile(card, official_cpp=cpp, resolved_program=program)


def test_co_brand_index_includes_major_merchants():
    index = load_co_brand_category_index()
    labels = {name for name, _cid in index.values()}
    assert "Starbucks" in labels
    assert "American Airlines" in labels
    assert "Delta Airlines" in labels
    assert "Marriott" in labels
    assert "Amazon" in labels
    assert "United Airlines" in labels
    assert "Costco" in labels
    assert "Target" in labels
    assert "Walmart" in labels
    assert "BJ's" in labels


def test_resolve_delta_air_lines_to_delta_airlines_category():
    names = resolve_co_brand_category_names("Delta Air Lines", aliases=["delta"])
    assert "Delta Airlines" in names


def test_resolve_united_airlines_category():
    names = resolve_co_brand_category_names("United Airlines", aliases=["united"])
    assert names == ["United Airlines"]


def test_catalog_merchant_auto_match_starbucks():
    assert co_brand_bonus_categories_for_merchant("starbucks") == ["Starbucks"]


@pytest.mark.parametrize(
    ("merchant_id", "expected"),
    [
        ("american_airlines", "American Airlines"),
        ("delta", "Delta Airlines"),
        ("united", "United Airlines"),
        ("southwest", "Southwest"),
        ("marriott", "Marriott"),
        ("hilton", "Hilton Hotels & Resorts"),
        ("hyatt", "Hyatt"),
        ("jetblue", "JetBlue"),
        ("alaska_airlines", "Alaska Airlines"),
        ("amazon", "Amazon"),
        ("costco", "Costco"),
        ("sams_club", "Sam's Club"),
        ("bjs", "BJ's"),
        ("target", "Target"),
        ("walmart", "Walmart"),
    ],
)
def test_catalog_merchant_auto_match_co_brands(merchant_id, expected):
    cats = co_brand_bonus_categories_for_merchant(merchant_id)
    assert expected in cats


def test_purchase_fallback_matches_display_name_only():
    assert co_brand_bonus_categories_for_purchase(merchant_name="Marriott") == ["Marriott"]
    assert co_brand_bonus_categories_for_purchase(merchant_name="Delta Air Lines") == ["Delta Airlines"]


def test_gmaps_costco_maps_to_catalog_co_brand():
    assert catalog_merchant_id_for_display_name("Costco Wholesale · Dallas, TX") == "costco"
    assert canonical_merchant_id_for_purchase(
        merchant_id="gmaps:ChIJtest",
        merchant_name="Costco · 123 Main St",
    ) == "costco"
    assert co_brand_bonus_categories_for_purchase(
        merchant_id="gmaps:ChIJtest",
        merchant_name="Costco · 123 Main St",
    ) == ["Costco"]


@pytest.mark.parametrize(
    ("card_key", "merchant_id", "category", "bonus_cat", "min_mult"),
    [
        ("citi-costcoanywherevisa", "costco", "Wholesale Clubs", "Costco", 2.0),
        ("tdbank-targetredcard", "target", "All Purchases", "Target", 5.0),
        ("capitalone-walmartrewards", "walmart", "Grocery Stores", "Walmart", 2.0),
        ("synchrony-samsclub", "sams_club", "Wholesale Clubs", "Sam's Club", 3.0),
        ("capitalone-bjsone", "bjs", "Wholesale Clubs", "BJ's", 3.0),
    ],
)
def test_store_co_brand_cards_use_partner_bucket(card_key, merchant_id, category, bonus_cat, min_mult):
    card = _load_card(card_key)
    mult, rule = best_multiplier(card, category, bonus_categories=[bonus_cat])
    assert mult >= min_mult
    assert rule is not None
    assert rule.category_name == bonus_cat


def test_costco_cash_card_partner_bonus_flag():
    card = _load_card("citi-costcoanywherevisa")
    purchase = PurchaseContext(
        category="Wholesale Clubs",
        amount_usd=100,
        bonus_categories=["Wholesale Clubs", "Costco"],
        merchant_id="costco",
    )
    mult, _, value, _, _, _, partner_bonus = compute_earn_value(card, purchase)
    assert mult == 2.0
    assert value == pytest.approx(2.0)
    assert partner_bonus is True


def test_starbucks_card_falls_back_to_base_without_co_brand_category():
    card = _load_card("chase-starbucksrewardsvisa")
    mult, rule = best_multiplier(card, "Dining")
    assert mult == 0.25
    assert rule is None


def test_starbucks_card_uses_starbucks_bonus_not_base():
    card = _load_card("chase-starbucksrewardsvisa")
    mult, rule = best_multiplier(card, "Dining", bonus_categories=["Starbucks"])
    assert mult == 3.0
    assert rule is not None
    assert rule.category_name == "Starbucks"


def test_delta_gold_uses_delta_airlines_bonus():
    card = _load_card("amex-deltagold")
    mult, rule = best_multiplier(card, "Airfare", bonus_categories=["Delta Airlines"])
    assert mult >= 2.0
    assert rule is not None
    assert rule.category_name == "Delta Airlines"


def test_marriott_bonvoy_uses_marriott_bonus():
    card = _load_card("amex-marriottbonvoybevy")
    mult, rule = best_multiplier(card, "Hotels", bonus_categories=["Marriott"])
    assert mult >= 6.0
    assert rule is not None
    assert rule.category_name == "Marriott"


def test_amazon_store_card_uses_amazon_bonus():
    card = _load_card("amex-biz-amazon")
    mult, rule = best_multiplier(card, "Online Shopping", bonus_categories=["Amazon"])
    assert mult >= 3.0
    assert rule is not None
    assert rule.category_name == "Amazon"


def test_delta_gold_co_brand_redemption_cpp_at_delta():
    card = _load_card("amex-deltagold")
    purchase = PurchaseContext(
        category="Airfare",
        amount_usd=100,
        bonus_categories=["Delta Airlines"],
        merchant_id="delta",
    )
    mult, pts, value, _, cpp, partner_checkout, partner_bonus = compute_earn_value(card, purchase)
    assert mult == 2.0
    assert pts == 200
    assert cpp == 1.2
    assert value == pytest.approx(2.4)
    assert partner_checkout is True
    assert partner_bonus is True


def test_co_brand_cpp_not_applied_at_unrelated_merchant():
    card = _load_card("amex-deltagold")
    purchase = PurchaseContext(category="Dining", amount_usd=100, merchant_id="chipotle")
    mult, _, value, _, cpp, _, _ = compute_earn_value(card, purchase)
    assert cpp == 1.0
    assert mult == 2.0  # Delta Gold dining bonus, generic 1¢/mile
    assert value == pytest.approx(2.0)


def test_aa_mileup_earns_co_brand_bonus_on_aa_merchant():
    aa = _load_card("citi-aaadvantagemileup")
    chase = _load_card("chase-sapphire-preferred")
    purchase = PurchaseContext(
        category="Airfare",
        amount_usd=100,
        bonus_categories=["American Airlines"],
        merchant_id="american_airlines",
    )
    aa_mult, _, aa_value, _, aa_cpp, _, _ = compute_earn_value(aa, purchase)
    chase_mult, _, chase_value, _, chase_cpp, _, _ = compute_earn_value(chase, purchase)
    assert aa_mult == 2.0
    assert chase_mult == 1.0
    assert aa_cpp == 1.4
    assert chase_cpp == 2.0
    assert aa_value == pytest.approx(2.8)
    assert aa_value > chase_value


def test_aa_executive_beats_chase_sapphire_on_aa_merchant():
    executive = _load_card("citi-aaadvantageexecutive")
    chase = _load_card("chase-sapphire-preferred")
    purchase = PurchaseContext(
        category="Airfare",
        amount_usd=100,
        bonus_categories=["American Airlines"],
        merchant_id="american_airlines",
    )
    exec_mult, _, exec_value, _, _, _, _ = compute_earn_value(executive, purchase)
    chase_mult, _, chase_value, _, _, _, _ = compute_earn_value(chase, purchase)
    assert exec_mult == 4.0
    assert chase_mult == 1.0
    assert exec_value == pytest.approx(5.6)
    assert exec_value > chase_value


def test_recommend_aa_mileup_ranks_above_csp_at_aa_merchant():
    wallet = [_load_card("citi-aaadvantagemileup"), _load_card("chase-sapphire-preferred")]
    purchase = PurchaseContext(
        category="Airfare",
        amount_usd=100,
        bonus_categories=["American Airlines"],
        merchant_id="american_airlines",
    )
    results = recommend_best_cards(wallet, purchase)
    assert results[0].card_key == "citi-aaadvantagemileup"
    assert results[0].multiplier == 2.0
    assert results[0].estimated_value_usd == pytest.approx(2.8)
    assert results[1].multiplier == 1.0


def test_american_airlines_alias_does_not_match_aaa():
    cats = co_brand_bonus_categories_for_merchant("american_airlines")
    assert cats == ["American Airlines"]
    assert "AAA" not in cats
    assert "amextravel.com" not in cats


def test_recommend_delta_gold_ranks_above_csp_at_delta_merchant():
    wallet = [_load_card("amex-deltagold"), _load_card("chase-sapphire-preferred")]
    purchase = PurchaseContext(
        category="Airfare",
        amount_usd=100,
        bonus_categories=["Delta Airlines"],
        merchant_id="delta",
    )
    results = recommend_best_cards(wallet, purchase)
    delta = next(r for r in results if r.card_key == "amex-deltagold")
    csp = next(r for r in results if "sapphire" in r.card_key and "preferred" in r.card_key.replace("-", ""))
    assert delta.multiplier >= 2.0
    assert csp.multiplier == 1.0
    assert delta.estimated_value_usd > csp.estimated_value_usd
    assert delta.rank <= csp.rank


def test_recommend_starbucks_card_earns_3x_at_starbucks_merchant():
    wallet = [_load_card("chase-starbucksrewardsvisa")]
    purchase = PurchaseContext(
        category="Dining",
        amount_usd=100,
        bonus_categories=["Starbucks"],
    )
    results = recommend_best_cards(wallet, purchase)
    starbucks = results[0]
    assert starbucks.multiplier == 3.0
    assert starbucks.points_earned == 300
