"""End-to-end payment UI smoke (TestClient — no live server required)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from credit_rewards.web.app import app
from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

client = TestClient(app)

LONG_CHECKOUT_URL = (
    "https://checkout.stripe.com/pay/cs_test_abc"
    "?return_url=https%3A%2F%2Fwww.chipotle.com%2Forder%2Fconfirmation"
)

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: credit-rewards-db sync-reference && import-reference",
)


def test_e2e_resolve_long_url():
    res = client.post("/api/merchant/resolve", json={"merchant_url": LONG_CHECKOUT_URL})
    assert res.status_code == 200
    data = res.json()
    assert data["best"]["merchantName"] == "Chipotle"
    assert data["best"]["spendBonusCategoryName"] == "Dining"
    assert data["needsConfirmation"] is True


def test_e2e_recommend_after_confirm(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))

    resolve = client.post("/api/merchant/resolve", json={"merchant_url": LONG_CHECKOUT_URL})
    merchant_id = resolve.json()["best"]["merchantId"]

    rec = client.post(
        "/api/recommend",
        json={"merchant_id": merchant_id, "amount_usd": 100},
    )
    assert rec.status_code == 200
    data = rec.json()
    assert data["resolved_category"] == "Dining"
    assert data["card_count"] == 20
    assert data["best"]["estimated_value_usd"] > 0
    assert data["rankings"][0]["rank"] == 1


def test_homepage_has_confirm_flow():
    res = client.get("/")
    assert res.status_code == 200
    assert "confirmModal" in res.text
    assert "wallet-ui.js" in res.text
    js = client.get("/static/wallet-ui.js")
    assert js.status_code == 200
    assert "api/merchant/resolve" in js.text
