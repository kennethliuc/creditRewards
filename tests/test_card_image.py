"""On-demand card image API: manifest CDN URLs + SVG placeholder."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from credit_rewards.card_image import (
    apply_local_image_urls,
    card_image_url_for_display,
    placeholder_image_url,
    resolve_card_image_url,
)
from credit_rewards.web.app import app


def test_card_image_endpoint():
    client = TestClient(app)
    with patch(
        "credit_rewards.web.app.resolve_card_image_url",
        return_value="https://creditcards.chase.com/example.webp",
    ):
        res = client.get("/api/cards/image", params={"card_key": "amex-gold"})
    assert res.status_code == 200
    assert res.json()["image_url"].startswith("https://")


def test_card_images_batch_endpoint():
    client = TestClient(app)
    with patch(
        "credit_rewards.web.app.resolve_card_image_urls",
        return_value={"amex-gold": "https://example.com/amex-gold.png"},
    ):
        res = client.post("/api/cards/images", json={"card_keys": ["amex-gold"]})
    assert res.status_code == 200
    assert res.json()["images"]["amex-gold"].startswith("https://")


def test_placeholder_endpoint():
    client = TestClient(app)
    res = client.get("/api/cards/image/placeholder", params={"card_key": "amex-gold"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in res.content


def test_apply_local_image_urls_uses_placeholder_when_no_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("credit_rewards.card_image.IMAGE_URLS_PATH", tmp_path / "missing.yaml")
    monkeypatch.setattr("credit_rewards.card_image.IMAGE_SOURCES_PATH", tmp_path / "missing2.yaml")
    monkeypatch.setattr("credit_rewards.card_image.CARD_IMAGES_DIR", tmp_path / "card_images")
    rows = [{"card_key": "unknown-test-card", "image_url": ""}]
    with patch(
        "credit_rewards.card_image.resolve_wallet_card_key",
        return_value={
            "card_key": "unknown-test-card",
            "rewards_cc_card_key": "unknown-test-card",
            "card_name": "Unknown Test",
            "issuer": "Test Bank",
            "image_url": "",
        },
    ):
        apply_local_image_urls(rows)
    assert rows[0]["image_url"] == placeholder_image_url("unknown-test-card")


def test_resolve_always_returns_url(tmp_path, monkeypatch):
    monkeypatch.setattr("credit_rewards.card_image.IMAGE_URLS_PATH", tmp_path / "missing.yaml")
    monkeypatch.setattr("credit_rewards.card_image.CARD_IMAGES_DIR", tmp_path / "card_images")
    with patch(
        "credit_rewards.card_image.resolve_wallet_card_key",
        return_value={"card_key": "x-card", "rewards_cc_card_key": "x-card", "card_name": "X", "issuer": "", "image_url": ""},
    ):
        with patch("credit_rewards.card_image._scrape_official_image_url", return_value=""):
            url = resolve_card_image_url("x-card", allow_scrape=False)
    assert url.startswith("/api/cards/image/placeholder")
