"""Point valuation — 20 registry cards aligned with official CPP table."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from credit_rewards.card_api.app import app
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.program_valuation import points_to_dollars
from credit_rewards.valuation import compute_earn_value
from credit_rewards.models import PurchaseContext
from tests.official_cpp_fixtures import enrich_from_official_table
from tests.twenty_cards_fixtures import (
    EXPECTED_CARD_COUNT,
    REGISTRY_CARD_KEYS,
    load_reference_detail,
    reference_files_ready,
    twenty_card_db,
)

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference (all 20 cards)",
)


@pytest.fixture()
def client(twenty_card_db):
    return TestClient(app)


@pytest.mark.parametrize("card_key", REGISTRY_CARD_KEYS)
def test_card_valuation_has_single_official_cpp(client, card_key):
    res = client.get(f"/creditcard-valuation-bycard/{card_key}")
    assert res.status_code == 200
    summary = res.json()[0]
    assert "officialCpp" in summary
    assert "estimatedValueUsd" in summary["examplePurchase"]
    assert "cppDefault" not in summary
    assert "valueUsdConservative" not in summary.get("examplePurchase", {})


@pytest.mark.parametrize("card_key", REGISTRY_CARD_KEYS)
def test_official_cpp_resolves_for_card(card_key, twenty_card_db):
    from credit_rewards.datastore.db import session
    from credit_rewards.datastore.repository import CardDataRepository

    with session(twenty_card_db) as conn:
        repo = CardDataRepository(conn)
        summary = repo.get_card_valuation(card_key)
    assert summary is not None
    assert summary["officialCpp"] > 0


def test_amex_gold_grocery_dollar_value():
    ref = load_reference_detail("amex-gold")
    card = enrich_from_official_table(normalize_card_detail(ref))
    purchase = PurchaseContext(category="Grocery Stores", amount_usd=100)
    _, _, value, _, _, _, _ = compute_earn_value(card, purchase)
    assert value == pytest.approx(5.88)


def test_program_valuation_list_uses_official_cpp(client, twenty_card_db):
    res = client.get("/creditcard-valuation-programlist/")
    assert res.status_code == 200
    rows = res.json()
    assert rows
    assert "officialCpp" in rows[0]
    assert "cppDefault" not in rows[0]


def test_all_twenty_cards_have_valuation_endpoint(client):
    assert len(REGISTRY_CARD_KEYS) == EXPECTED_CARD_COUNT
    for card_key in REGISTRY_CARD_KEYS:
        res = client.get(f"/creditcard-valuation-bycard/{card_key}")
        assert res.status_code == 200, card_key
