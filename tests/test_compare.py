from __future__ import annotations

import json

import pytest

from credit_rewards.datastore.db import init_db, session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.compare import compare_card
from credit_rewards.ingest.scrape.issuers import AmexScraper
from tests.html_samples import AMEX_GOLD_HTML

AMEX_GOLD_REFERENCE = {
    "cardKey": "amex-gold",
    "cardIssuer": "American Express",
    "cardName": "American Express® Gold",
    "cardUrl": "https://www.americanexpress.com/us/credit-cards/card/gold-card",
    "baseSpendAmount": 1.0,
    "spendBonusCategory": [
        {
            "spendBonusCategoryName": "Airfare",
            "spendBonusCategoryId": 2013874334,
            "spendBonusCategoryGroup": "Travel",
            "earnMultiplier": 3.0,
            "spendBonusDesc": "3x on flights booked directly with airlines",
        },
        {
            "spendBonusCategoryName": "Dining",
            "spendBonusCategoryId": 160378660,
            "spendBonusCategoryGroup": "Dining",
            "earnMultiplier": 4.0,
            "spendBonusDesc": "4x at restaurants worldwide",
        },
        {
            "spendBonusCategoryName": "Grocery Stores",
            "spendBonusCategoryId": 1132334901,
            "spendBonusCategoryGroup": "Shopping",
            "earnMultiplier": 4.0,
            "spendBonusDesc": "4x on groceries at U.S. supermarkets",
        },
    ],
}


@pytest.fixture()
def compare_env(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    ref_dir = tmp_path / "reference"
    cards_dir = ref_dir / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "amex-gold.json").write_text(
        json.dumps([AMEX_GOLD_REFERENCE], indent=2) + "\n"
    )
    (ref_dir / "manifest.json").write_text(
        json.dumps({"synced_at": "2026-06-01T00:00:00+00:00", "cards": {}}) + "\n"
    )
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(db_file))
    init_db(db_file)
    detail = AmexScraper().parse_card_page(
        AMEX_GOLD_HTML, "amex-gold", "https://example.com/amex-gold"
    )
    with session(db_file) as conn:
        CardDataRepository(conn).upsert_card(
            detail, source_url="https://example.com/amex-gold", source_type="scrape"
        )
    return db_file, ref_dir


def _dining_match(report):
    return next(
        (
            m
            for m in report.matched
            if m.scraped.spend_bonus_category_name == "Dining"
            or m.reference.spend_bonus_category_name == "Dining"
        ),
        None,
    )


def test_compare_dining_multiplier_matches(compare_env):
    db_file, ref_dir = compare_env
    report = compare_card(
        "amex-gold", reference_dir=ref_dir, db_path=db_file, fetch_evidence=False
    )
    dining = _dining_match(report)
    assert dining is not None
    assert dining.scraped.earn_multiplier == pytest.approx(4.0)
    assert dining.reference.earn_multiplier == pytest.approx(4.0)


def test_compare_detects_multiplier_mismatch(compare_env):
    db_file, ref_dir = compare_env
    ref_path = ref_dir / "cards" / "amex-gold.json"
    payload = json.loads(ref_path.read_text())
    for rule in payload[0]["spendBonusCategory"]:
        if rule["spendBonusCategoryName"] == "Dining":
            rule["earnMultiplier"] = 3.0
    ref_path.write_text(json.dumps(payload, indent=2) + "\n")

    report = compare_card(
        "amex-gold", reference_dir=ref_dir, db_path=db_file, fetch_evidence=False
    )
    dining_mismatch = next(
        (m for m in report.mismatches if m.mismatch_type == "multiplier_mismatch"),
        None,
    )
    assert dining_mismatch is not None
    assert "Dining" in dining_mismatch.explanation or "dining" in dining_mismatch.explanation.lower()
    assert not report.aligned


def test_compare_airfare_in_matched(compare_env):
    db_file, ref_dir = compare_env
    report = compare_card(
        "amex-gold", reference_dir=ref_dir, db_path=db_file, fetch_evidence=False
    )
    airfare = next(
        (
            m
            for m in report.matched
            if m.reference.spend_bonus_category_name == "Airfare"
        ),
        None,
    )
    assert airfare is not None
    assert airfare.scraped.earn_multiplier == pytest.approx(3.0)
    assert airfare.reference.earn_multiplier == pytest.approx(3.0)


def test_compare_evidence_marks_scrape_ok_when_api_wrong(compare_env):
    db_file, ref_dir = compare_env
    ref_path = ref_dir / "cards" / "amex-gold.json"
    payload = json.loads(ref_path.read_text())
    for rule in payload[0]["spendBonusCategory"]:
        if rule["spendBonusCategoryName"] == "Dining":
            rule["earnMultiplier"] = 3.0
    ref_path.write_text(json.dumps(payload, indent=2) + "\n")

    report = compare_card(
        "amex-gold",
        reference_dir=ref_dir,
        db_path=db_file,
        issuer_html=AMEX_GOLD_HTML,
        fetch_evidence=False,
    )
    dining = next(m for m in report.mismatches if "Dining" in m.explanation or (
        m.scraped and m.scraped.spend_bonus_category_name == "Dining"
    ))
    assert dining.evidence_verdict == "scrape_supported"
    assert dining.evidence_action == "keep_scrape"
    assert dining.evidence_scrape
