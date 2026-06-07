"""On-demand card image API and local file cache."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from credit_rewards.card_image import (
    apply_local_image_urls,
    card_image_url_for_display,
    ensure_local_card_image,
    local_image_path,
)
from credit_rewards.web.app import app


def test_card_image_endpoint():
    client = TestClient(app)
    with patch(
        "credit_rewards.web.app.fetch_card_image_url",
        return_value="/api/cards/image/file?card_key=amex-gold",
    ):
        res = client.get("/api/cards/image", params={"card_key": "amex-gold"})
    assert res.status_code == 200
    assert res.json()["image_url"].startswith("/api/cards/image/file")


def test_card_images_batch_endpoint():
    client = TestClient(app)
    with patch(
        "credit_rewards.web.app.fetch_card_image_urls",
        return_value={"amex-gold": "/api/cards/image/file?card_key=amex-gold"},
    ):
        res = client.post("/api/cards/images", json={"card_keys": ["amex-gold"]})
    assert res.status_code == 200
    assert "amex-gold" in res.json()["images"]


def test_local_image_file_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr("credit_rewards.card_image.CARD_IMAGES_DIR", tmp_path / "card_images")
    monkeypatch.setattr("credit_rewards.card_image.data_dir", lambda: tmp_path)
    img_dir = tmp_path / "card_images"
    img_dir.mkdir()
    (img_dir / "amex-gold.jpg").write_bytes(b"fake-jpeg")

    client = TestClient(app)
    res = client.get("/api/cards/image/file", params={"card_key": "amex-gold"})
    assert res.status_code == 200
    assert res.content == b"fake-jpeg"


def test_apply_local_image_urls(tmp_path, monkeypatch):
    monkeypatch.setattr("credit_rewards.card_image.CARD_IMAGES_DIR", tmp_path / "card_images")
    img_dir = tmp_path / "card_images"
    img_dir.mkdir()
    (img_dir / "amex-gold.jpg").write_bytes(b"x")

    rows = [{"card_key": "amex-gold", "image_url": ""}]
    with patch(
        "credit_rewards.card_image.resolve_wallet_card_key",
        return_value={"card_key": "amex-gold", "rewards_cc_card_key": "amex-gold", "image_url": ""},
    ):
        apply_local_image_urls(rows)
    assert rows[0]["image_url"] == "/api/cards/image/file?card_key=amex-gold"


def test_ensure_local_downloads_once(tmp_path, monkeypatch):
    monkeypatch.setattr("credit_rewards.card_image.CARD_IMAGES_DIR", tmp_path / "card_images")
    resolved = {
        "card_key": "amex-gold",
        "rewards_cc_card_key": "amex-gold",
        "image_url": "https://example.com/amex-gold.png",
    }

    class FakeResponse:
        headers = {"content-type": "image/png"}

        def raise_for_status(self):
            return None

        @property
        def content(self):
            return b"png-bytes"

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            assert url == resolved["image_url"]
            return FakeResponse()

    with patch("credit_rewards.card_image.resolve_wallet_card_key", return_value=resolved):
        with patch("credit_rewards.card_image._remote_image_url", return_value=resolved["image_url"]):
            with patch("credit_rewards.card_image.httpx.Client", return_value=FakeClient()):
                url = ensure_local_card_image("amex-gold")
    assert url.startswith("/api/cards/image/file")
    assert local_image_path("amex-gold") is not None
    assert card_image_url_for_display("amex-gold").startswith("/api/cards/image/file")
