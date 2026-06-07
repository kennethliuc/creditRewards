"""CardData API — all Rewards CC-compatible endpoints × 20 registry cards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from credit_rewards.card_api.app import app
from credit_rewards.datastore.db import session
from tests.twenty_cards_fixtures import (
    EXPECTED_CARD_COUNT,
    REGISTRY_CARD_KEYS,
    category_ids_for_cards,
    load_reference_detail,
    reference_files_ready,
    twenty_card_db,
)

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: credit-rewards-db sync-reference (all 20 cards)",
)


@pytest.fixture()
def client(twenty_card_db):
    return TestClient(app)


def test_registry_has_twenty_cards():
    assert len(REGISTRY_CARD_KEYS) == EXPECTED_CARD_COUNT


def test_card_list_lists_all_twenty(client):
    res = client.get("/creditcard-cardlist")
    assert res.status_code == 200
    keys = {card["cardKey"] for group in res.json() for card in group["card"]}
    assert keys == set(REGISTRY_CARD_KEYS)


@pytest.mark.parametrize("card_key", REGISTRY_CARD_KEYS)
def test_card_detail_by_card(client, card_key, twenty_card_db):
    res = client.get(f"/creditcard-detail-bycard/{card_key}")
    assert res.status_code == 200
    detail = res.json()[0]
    assert detail["cardKey"] == card_key
    assert detail.get("spendBonusCategory") is not None

    ref = load_reference_detail(card_key)
    assert len(detail["spendBonusCategory"]) == len(ref.get("spendBonusCategory") or [])
    ref_by_id = {
        int(r["spendBonusCategoryId"]): float(r["earnMultiplier"])
        for r in ref.get("spendBonusCategory") or []
    }
    for rule in detail["spendBonusCategory"]:
        cat_id = int(rule["spendBonusCategoryId"])
        assert cat_id in ref_by_id
        assert float(rule["earnMultiplier"]) == pytest.approx(ref_by_id[cat_id])


@pytest.mark.parametrize(
    "card_key,query",
    [
        ("amex-gold", "gold"),
        ("chase-sapphire-preferred", "sapphire"),
        ("citi-double-cash", "double"),
        ("capital-one-venture-x", "venture"),
        ("discover-it-cash-back", "discover"),
        ("apple-card", "apple"),
    ],
)
def test_name_search_finds_cards(client, card_key, query):
    res = client.get(f"/creditcard-detail-namesearch/{query}")
    assert res.status_code == 200
    keys = {row["cardKey"] for row in res.json()}
    assert card_key in keys


def test_category_list_endpoint(client):
    res = client.get("/creditcard-spendbonuscategory-categorylist/")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_category_card_for_each_registry_category(client, twenty_card_db):
    for cat_id in category_ids_for_cards(twenty_card_db):
        res = client.get(f"/creditcard-spendbonuscategory-categorycard/{cat_id}")
        assert res.status_code == 200
        rows = res.json()
        assert isinstance(rows, list)
        assert rows, f"category {cat_id} should include at least one card"
        for row in rows:
            assert row["cardKey"] in REGISTRY_CARD_KEYS
            assert int(row["spendBonusCategoryId"]) == cat_id


def test_transfer_program_list(client):
    res = client.get("/creditcard-pointtransfer-transferprogramlist/")
    assert res.status_code == 200
    programs = res.json()
    assert len(programs) >= 1
    assert "transferPartnerId" in programs[0]


def test_transfer_program_cards(client):
    partner_id = 1722165547  # Hilton Honors — seeded in data/seed/transfer_partner_cards.json
    res2 = client.get(f"/creditcard-pointtransfer-transferprogramcard/{partner_id}")
    assert res2.status_code == 200
    rows = res2.json()
    assert len(rows) >= 1
    assert rows[0]["cardKey"] in REGISTRY_CARD_KEYS


def test_api_usage_after_calls(client):
    client.get(f"/creditcard-detail-bycard/{REGISTRY_CARD_KEYS[0]}")
    res = client.get("/creditcard-apiusage/dev")
    assert res.status_code == 200
    payload = res.json()
    assert payload[0]["statusCode"][0]["apiCalls"] >= 1


def test_unknown_card_returns_404(client):
    res = client.get("/creditcard-detail-bycard/not-in-registry-xyz")
    assert res.status_code == 404


def test_unknown_category_returns_404(client):
    res = client.get("/creditcard-spendbonuscategory-categorycard/999999999")
    assert res.status_code == 404
