"""Catalog wallet cards import from reference snapshots."""

import pytest

from credit_rewards.card_import import ensure_card_in_db, ensure_wallet_cards_in_db
from credit_rewards.ingest.reference_sync import assemble_card_from_category_snapshots
from credit_rewards.wallet import load_wallet
from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference && import-reference",
)


def test_assemble_chase_starbucks_from_category_snapshots():
    detail = assemble_card_from_category_snapshots(
        "chase-starbucksrewardsvisa",
        "chase-starbucksrewardsvisa",
    )
    assert detail is not None
    assert detail["cardKey"] == "chase-starbucksrewardsvisa"
    names = {r["spendBonusCategoryName"] for r in detail["spendBonusCategory"]}
    assert "Grocery Stores" in names
    assert "Transit" in names
    assert "Starbucks" in names
    starbucks_rule = next(r for r in detail["spendBonusCategory"] if r["spendBonusCategoryName"] == "Starbucks")
    assert starbucks_rule["earnMultiplier"] == 3.0


def test_ensure_starbucks_card_in_db(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    assert ensure_card_in_db("chase-starbucksrewardsvisa") is True
    wallet = load_wallet(["chase-starbucksrewardsvisa"], client=type("C", (), {"is_configured": False})())
    assert len(wallet) == 1
    assert wallet[0].card_key == "chase-starbucksrewardsvisa"


def test_ensure_wallet_reports_missing_when_no_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(tmp_path / "empty.db"))
    from credit_rewards.datastore.db import init_db

    init_db(tmp_path / "empty.db")
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    monkeypatch.setattr(
        "credit_rewards.card_import.assemble_card_from_category_snapshots",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "credit_rewards.card_import.load_reference_card",
        lambda *a, **k: None,
    )
    missing = ensure_wallet_cards_in_db(["totally-unknown-card-xyz"])
    assert missing == ["totally-unknown-card-xyz"]
