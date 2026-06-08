"""Trial analytics ingest and admin dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from credit_rewards.datastore.db import init_db
from credit_rewards.web.app import app

client = TestClient(app)

DEVICE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SESSION = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def analytics_db(tmp_path, monkeypatch):
    db = init_db(tmp_path / "analytics.db")
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(db))
    monkeypatch.setenv("CREDITREWARDS_ANALYTICS_ENABLED", "1")
    monkeypatch.setenv("CREDITREWARDS_ANALYTICS_ADMIN_PASSWORD", "trial-admin-secret")
    return db


def _ingest_payload(**overrides):
    base = {
        "device_id": DEVICE,
        "session_id": SESSION,
        "locale": "en-US",
        "user_agent": "pytest",
        "card_count": 2,
        "events": [
            {
                "event_type": "app_open",
                "occurred_at": "2026-06-01T12:00:00+00:00",
                "properties": {"path": "/"},
            },
            {
                "event_type": "screen_view",
                "occurred_at": "2026-06-01T12:00:05+00:00",
                "properties": {"view": "pay"},
            },
        ],
    }
    base.update(overrides)
    return base


def test_analytics_status_enabled(analytics_db):
    res = client.get("/api/analytics/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["admin_configured"] is True


def test_ingest_events(analytics_db):
    res = client.post("/api/analytics/events", json=_ingest_payload())
    assert res.status_code == 200
    assert res.json()["accepted"] == 2


def test_admin_summary_requires_login(analytics_db):
    res = client.get("/api/admin/analytics/summary")
    assert res.status_code == 401


def test_admin_login_and_summary(analytics_db):
    ingest = client.post("/api/analytics/events", json=_ingest_payload())
    assert ingest.status_code == 200

    bad = client.post("/api/admin/analytics/login", json={"password": "wrong"})
    assert bad.status_code == 401

    login = client.post("/api/admin/analytics/login", json={"password": "trial-admin-secret"})
    assert login.status_code == 200

    summary = client.get("/api/admin/analytics/summary?days=7")
    assert summary.status_code == 200
    data = summary.json()
    assert data["counts"]["devices_total"] >= 1
    assert data["counts"]["events_recent"] >= 2
    types = {row["event_type"] for row in data["events_by_type"]}
    assert "app_open" in types
    assert any(e["event_type"] == "screen_view" for e in data["recent_events"])


def test_admin_page_loads(analytics_db):
    res = client.get("/admin")
    assert res.status_code == 200
    assert "Trial analytics" in res.text
    assert "admin.js" in res.text


def test_index_includes_analytics_script():
    res = client.get("/")
    assert res.status_code == 200
    assert "analytics.js" in res.text
