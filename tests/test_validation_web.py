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
    monkeypatch.setattr("credit_rewards.ingest.reference_validate.REFERENCE_DIR", ref_dir)

    registry = [e for e in load_card_registry() if e["card_key"] == "amex-gold"]
    monkeypatch.setattr("credit_rewards.ingest.compare.load_card_registry", lambda: registry)
    monkeypatch.setattr("credit_rewards.validation.dashboard.load_card_registry", lambda: registry)

    golden = tmp_path / "golden_cases.yaml"
    golden.write_text(
        "cases:\n"
        "  - id: smoke\n"
        "    wallet: [amex-gold]\n"
        "    spend: { category: Dining, amount_usd: 10 }\n"
        "    expected_winner: amex-gold\n"
    )
    monkeypatch.setattr(
        "credit_rewards.validation.dashboard.GOLDEN_CASES_PATH",
        golden,
    )
    monkeypatch.setattr(
        "credit_rewards.validation.golden.DEFAULT_GOLDEN_PATH",
        golden,
    )

    return TestClient(app)


def test_validation_page(client):
    res = client.get("/validation")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Validation Dashboard" in res.text


def test_api_validation(client):
    res = client.get("/api/validation")
    assert res.status_code == 200
    data = res.json()
    assert "layers" in data
    assert "independent_ready" in data
    assert "cards" in data
    assert "l3" in data
    assert "mcc" in data
    assert "ship_ready" in data
    assert data["l3"]["total"] >= 1
    assert len(data["layers"]) == 5
    assert any(layer["id"] == "l1" for layer in data["layers"])
