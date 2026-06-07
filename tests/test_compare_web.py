import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from credit_rewards.ingest.scrape.issuers import AmexScraper
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.ingest.seed_loader import seed_database
from credit_rewards.web.app import app
from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from tests.html_samples import AMEX_GOLD_HTML

REFERENCE_DIR = (
    __import__("credit_rewards.ingest.reference_sync", fromlist=["REFERENCE_DIR"]).REFERENCE_DIR
)


def _load_scraped_fixtures(db_file):
    seed_database(db_file)
    scraper = AmexScraper()
    with session(db_file) as conn:
        repo = CardDataRepository(conn)
        detail = scraper.parse_card_page(
            AMEX_GOLD_HTML, "amex-gold", "https://example.com/amex-gold"
        )
        repo.upsert_card(
            detail,
            source_url="https://example.com/amex-gold",
            source_type="scrape",
        )


def _copy_reference_card(tmp_ref: Path, card_key: str = "amex-gold") -> None:
    src = REFERENCE_DIR / "cards" / f"{card_key}.json"
    if not src.exists():
        pytest.skip(f"Reference fixture missing: {src}")
    cards_dir = tmp_ref / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, cards_dir / f"{card_key}.json")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    ref_dir = tmp_path / "reference"
    _copy_reference_card(ref_dir)
    _load_scraped_fixtures(db_file)

    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(db_file))
    monkeypatch.setenv("CREDITREWARDS_FETCH_EVIDENCE", "0")
    monkeypatch.setattr("credit_rewards.ingest.compare.REFERENCE_DIR", ref_dir)

    registry = [e for e in load_card_registry() if e["card_key"] == "amex-gold"]
    monkeypatch.setattr("credit_rewards.ingest.compare.load_card_registry", lambda: registry)

    return TestClient(app)


def test_compare_page(client):
    res = client.get("/compare")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Scrape vs API" in res.text


def test_api_compare_all(client):
    res = client.get("/api/compare")
    assert res.status_code == 200
    data = res.json()
    assert "cards" in data
    assert data["total"] >= 1
    assert "aligned_count" in data
    assert "mismatch_count" in data

    card = next(c for c in data["cards"] if c["card_key"] == "amex-gold")
    assert "scraped_rules" in card
    assert "reference_rules" in card
    assert "aligned" in card
    assert isinstance(card["scraped_rules"], list)
    assert isinstance(card["reference_rules"], list)
    assert isinstance(card["aligned"], bool)

    if card["scraped_rules"]:
        rule = card["scraped_rules"][0]
        assert "category_name" in rule
        assert "multiplier" in rule
        assert "description" in rule

    assert "diff" in card
    assert "scrape_verified" in card
    assert "parser_fix_needed" in card


def test_api_compare_single_card(client):
    res = client.get("/api/compare/amex-gold")
    assert res.status_code == 200
    card = res.json()
    assert card["card_key"] == "amex-gold"
    assert card["scraped_rules"]
    assert card["reference_rules"]


def test_api_compare_unknown_card(client):
    res = client.get("/api/compare/not-a-real-card")
    assert res.status_code == 404
