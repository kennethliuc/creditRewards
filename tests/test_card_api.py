import os

import pytest
from fastapi.testclient import TestClient

from credit_rewards.card_api.app import app
from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.scrape.issuers import AmexScraper, ChaseScraper, CitiScraper
from credit_rewards.ingest.seed_loader import seed_database
from tests.html_samples import AMEX_GOLD_HTML, CHASE_SAPPHIRE_HTML, CITI_DOUBLE_CASH_HTML


def _load_scraped_fixtures(db_file):
    seed_database(db_file)
    samples = [
        (AmexScraper(), "amex-gold", AMEX_GOLD_HTML),
        (ChaseScraper(), "chase-sapphire-preferred", CHASE_SAPPHIRE_HTML),
    ]
    with session(db_file) as conn:
        repo = CardDataRepository(conn)
        for scraper, key, html in samples:
            detail = scraper.parse_card_page(html, key, "https://example.com")
            repo.upsert_card(detail, source_url="https://example.com", source_type="scrape")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(db_file))
    _load_scraped_fixtures(db_file)
    return TestClient(app)


def test_card_list(client):
    res = client.get("/creditcard-cardlist")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert sum(len(g["card"]) for g in data) >= 2


def test_card_detail(client):
    res = client.get("/creditcard-detail-bycard/amex-gold")
    assert res.status_code == 200
    detail = res.json()[0]
    assert detail["cardKey"] == "amex-gold"
    assert any(c["spendBonusCategoryName"] == "Grocery Stores" for c in detail["spendBonusCategory"])


def test_name_search(client):
    res = client.get("/creditcard-detail-namesearch/gold")
    assert res.status_code == 200
    assert any(row["cardKey"] == "amex-gold" for row in res.json())


def test_category_cards(client):
    res = client.get("/creditcard-spendbonuscategory-categorycard/1132334901")
    assert res.status_code == 200
    keys = {row["cardKey"] for row in res.json()}
    assert "amex-gold" in keys


def test_api_usage(client):
    client.get("/creditcard-detail-bycard/amex-gold")
    res = client.get("/creditcard-apiusage/dev")
    assert res.status_code == 200
    payload = res.json()
    assert payload[0]["statusCode"][0]["apiCalls"] >= 1
