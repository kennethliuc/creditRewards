"""Account registration, login, and server wallet."""

import pytest
from fastapi.testclient import TestClient

from credit_rewards.web.app import app

client = TestClient(app)


def test_register_login_wallet_flow():
    email = "demo-user@example.com"
    cards = [
        {"card_key": "amex-gold", "nickname": "Daily Gold", "last4": "1234"},
        {"card_key": "chase-sapphire-preferred", "nickname": "", "last4": "5678"},
    ]

    reg = client.post(
        "/api/auth/register",
        json={"email": email, "password": "testpass99", "cards": cards},
    )
    assert reg.status_code == 200, reg.text
    body = reg.json()
    assert body["authenticated"] is True
    assert body["email"] == email
    assert len(body["cards"]) == 2
    assert reg.cookies.get("cr_session")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is True
    assert me.json()["cards"][0]["nickname"] == "Daily Gold"

    client.post("/api/auth/logout")
    me2 = client.get("/api/auth/me")
    assert me2.json()["authenticated"] is False

    bad = client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrong"},
    )
    assert bad.status_code == 401

    ok = client.post(
        "/api/auth/login",
        json={"email": email, "password": "testpass99"},
    )
    assert ok.status_code == 200

    updated = client.put(
        "/api/wallet",
        json={"cards": [{"card_key": "citi-double-cash", "nickname": "2x", "last4": "9999"}]},
    )
    assert updated.status_code == 200
    assert len(updated.json()["cards"]) == 1


def test_register_requires_valid_cards():
    res = client.post(
        "/api/auth/register",
        json={
            "email": "bad@example.com",
            "password": "testpass99",
            "cards": [{"card_key": "not-a-real-card"}],
        },
    )
    assert res.status_code == 400
