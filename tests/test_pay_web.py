"""Payment-moment homepage and merchant API."""

import pytest
from fastapi.testclient import TestClient

from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.web.app import app
from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

client = TestClient(app)


def _wallet_loader(db_path):
    def load_wallet(card_keys, client=None):
        cards = []
        with session(db_path) as conn:
            repo = CardDataRepository(conn)
            for key in card_keys:
                detail = repo.get_card_detail(key)
                if not detail:
                    raise RuntimeError(f"Missing card in test db: {key}")
                cards.append(normalize_card_detail(detail))
        return cards

    return load_wallet


def test_index_page_loads():
    res = client.get("/")
    assert res.status_code == 200
    assert "仅在本机使用" in res.text
    assert "wallet-ui.js" in res.text


def test_merchant_resolve_url():
    res = client.post("/api/merchant/resolve", json={"merchant_url": "https://chipotle.com"})
    assert res.status_code == 200
    body = res.json()
    assert body["best"]["spendBonusCategoryName"] == "Dining"
    assert body["needsConfirmation"] is True
    assert body["candidates"]


def test_merchant_resolve_long_checkout_url():
    url = (
        "https://payments.example.com/v1/checkout?"
        "success=https%3A%2F%2Fwww.amazon.com%2Fgp%2Fbuy%2Fthankyou"
    )
    res = client.post("/api/merchant/resolve", json={"merchant_url": url})
    assert res.status_code == 200
    assert res.json()["best"]["merchantName"] == "Amazon"


def test_merchant_resolve_name():
    res = client.post("/api/merchant/resolve", json={"merchant_name": "Starbucks"})
    assert res.status_code == 200
    assert res.json()["best"]["spendBonusCategoryName"] == "Dining"


def test_merchant_resolve_unknown_404(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    res = client.post("/api/merchant/resolve", json={"merchant_name": "Not A Real Store XYZ"})
    assert res.status_code == 404


def test_api_cards_lists_registry():
    res = client.get("/api/cards")
    assert res.status_code == 200
    assert res.json()["total"] == 20


def test_recommend_with_confirmed_merchant_id(twenty_card_db, monkeypatch):
    monkeypatch.setattr(
        "credit_rewards.web.app.load_wallet",
        _wallet_loader(twenty_card_db),
    )
    res = client.post(
        "/api/recommend",
        json={"merchant_id": "chipotle", "amount_usd": 100},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_category"] == "Dining"
    assert data["merchant"]["merchantId"] == "chipotle"
    assert data["card_count"] == 20


def test_recommend_with_osm_merchant(twenty_card_db, monkeypatch):
    monkeypatch.setattr(
        "credit_rewards.web.app.load_wallet",
        _wallet_loader(twenty_card_db),
    )
    res = client.post(
        "/api/recommend",
        json={
            "merchant_id": "osm:12345",
            "merchant_name": "Local Cafe",
            "category": "Dining",
            "amount_usd": 40,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_category"] == "Dining"
    assert data["merchant"]["merchantId"] == "osm:12345"
    assert data["merchant"]["source"] == "nominatim"


@pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: credit-rewards-db sync-reference && import-reference",
)
def test_recommend_full_library_via_merchant_url(twenty_card_db, monkeypatch):
    monkeypatch.setattr(
        "credit_rewards.web.app.load_wallet",
        _wallet_loader(twenty_card_db),
    )
    res = client.post(
        "/api/recommend",
        json={"merchant_url": "https://www.chipotle.com", "amount_usd": 100},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["full_library"] is True
    assert data["card_count"] == 20
    assert data["resolved_category"] == "Dining"
    assert data["merchant"]["merchantName"] == "Chipotle"
    assert data["best"]["estimated_value_usd"] > 0
    assert len(data["rankings"]) == 20


@pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: credit-rewards-db sync-reference && import-reference",
)
def test_recommend_full_library_via_merchant_name(twenty_card_db, monkeypatch):
    monkeypatch.setattr(
        "credit_rewards.web.app.load_wallet",
        _wallet_loader(twenty_card_db),
    )
    res = client.post(
        "/api/recommend",
        json={"merchant_name": "Amazon", "amount_usd": 50},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_category"] == "Online Shopping"
