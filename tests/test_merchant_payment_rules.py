"""Merchant payment acceptance and spend-context category rules."""

from __future__ import annotations

import pytest

from credit_rewards.ingest.reference_sync import assemble_card_from_category_snapshots, load_reference_card
from credit_rewards.merchant_payment_rules import (
    accepted_networks_for_merchant,
    infer_card_network,
    partition_wallet_by_payment,
    resolve_spend_category_for_merchant,
)
from credit_rewards.models import PurchaseContext
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.official_cpp import enrich_card_profile, fallback_program_table, resolve_card_official_cpp
from credit_rewards.valuation import best_multiplier, compute_earn_value


def _load_card(card_key: str):
    detail = load_reference_card(card_key) or assemble_card_from_category_snapshots(card_key)
    assert detail is not None, card_key
    card = normalize_card_detail(detail)
    cpp, program = resolve_card_official_cpp(card_key, detail, fallback_program_table())
    return enrich_card_profile(card, official_cpp=cpp, resolved_program=program)


def test_costco_in_store_visa_only():
    nets = accepted_networks_for_merchant(
        merchant_id="costco",
        merchant_name="Costco",
        purchase_channel="in_store",
    )
    assert nets == ["Visa"]


def test_costco_gas_resolves_gas_category():
    cat = resolve_spend_category_for_merchant(
        merchant_id="costco",
        merchant_name="Costco Gas #1234",
        purchase_channel="in_store",
        default_category="Wholesale Clubs",
    )
    assert cat == "Gas Stations"


def test_costco_food_court_resolves_dining():
    cat = resolve_spend_category_for_merchant(
        merchant_id="costco",
        merchant_name="Costco Food Court",
        purchase_channel="in_store",
        default_category="Wholesale Clubs",
    )
    assert cat == "Dining"


def test_costco_warehouse_default_category():
    cat = resolve_spend_category_for_merchant(
        merchant_id="costco",
        merchant_name="Costco",
        purchase_channel="in_store",
        default_category="Grocery Stores",
    )
    assert cat == "Wholesale Clubs"


def test_costco_visa_card_4_percent_gas():
    card = _load_card("citi-costcoanywherevisa")
    mult, rule = best_multiplier(
        card,
        "Gas Stations",
        bonus_categories=["Costco"],
    )
    assert mult == 4.0
    assert rule is not None
    assert rule.category_name == "Gas Stations"


def test_costco_visa_card_3_percent_dining():
    card = _load_card("citi-costcoanywherevisa")
    mult, rule = best_multiplier(card, "Dining", bonus_categories=["Costco"])
    assert mult == 3.0
    assert rule.category_name == "Dining"


def test_costco_visa_card_2_percent_warehouse():
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


def test_partition_excludes_amex_at_costco():
    costco_visa = _load_card("citi-costcoanywherevisa")
    amex = _load_card("amex-gold")
    eligible, excluded = partition_wallet_by_payment(
        [costco_visa, amex],
        accepted_networks=["Visa"],
    )
    assert [c.card_key for c in eligible] == ["citi-costcoanywherevisa"]
    assert len(excluded) == 1
    assert excluded[0]["card_key"] == "amex-gold"
    assert "American Express" in excluded[0]["reason"]


def test_infer_card_network_from_detail():
    card = _load_card("citi-costcoanywherevisa")
    assert infer_card_network(card) == "Visa"
