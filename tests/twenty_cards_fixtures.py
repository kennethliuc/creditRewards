"""Shared fixtures for 20-card CardData API integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from credit_rewards.datastore.db import init_db, session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.reference_import import import_reference_to_db
from credit_rewards.ingest.reference_sync import REFERENCE_DIR
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.ingest.seed_loader import seed_database

REGISTRY_CARD_KEYS = [entry["card_key"] for entry in load_card_registry()]
EXPECTED_CARD_COUNT = 20


def reference_files_ready() -> bool:
    cards_dir = REFERENCE_DIR / "cards"
    if not cards_dir.exists():
        return False
    return all((cards_dir / f"{key}.json").exists() for key in REGISTRY_CARD_KEYS)


@pytest.fixture(scope="session")
def registry_card_keys() -> list[str]:
    assert len(REGISTRY_CARD_KEYS) == EXPECTED_CARD_COUNT, (
        f"Expected {EXPECTED_CARD_COUNT} registry cards, got {len(REGISTRY_CARD_KEYS)}"
    )
    return REGISTRY_CARD_KEYS


@pytest.fixture()
def twenty_card_db(tmp_path, monkeypatch):
    if not reference_files_ready():
        pytest.skip(
            "Missing reference JSON for 20 cards. Run: "
            "paycue-db sync-reference && paycue-db import-reference"
        )
    db_file = tmp_path / "twenty.db"
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(db_file))
    init_db(db_file)
    seed_database(db_file)
    result = import_reference_to_db(db_path=db_file)
    if result["count"] != EXPECTED_CARD_COUNT:
        pytest.skip(f"Only imported {result['count']}/{EXPECTED_CARD_COUNT} reference cards")
    from credit_rewards.ingest.official_cpp_refresh import refresh_official_cpp

    refresh_official_cpp(db_path=db_file)
    return db_file


def load_reference_detail(card_key: str) -> dict:
    upstream = next(
        (
            e.get("rewards_cc_card_key") or e["card_key"]
            for e in load_card_registry()
            if e["card_key"] == card_key
        ),
        card_key,
    )
    path = REFERENCE_DIR / "cards" / f"{card_key}.json"
    if not path.exists():
        path = REFERENCE_DIR / "cards" / f"{upstream}.json"
    payload = json.loads(path.read_text())
    detail = payload[0] if isinstance(payload, list) else payload
    detail = dict(detail)
    detail["cardKey"] = card_key
    return detail


def category_ids_for_cards(db_file) -> set[int]:
    ids: set[int] = set()
    with session(db_file) as conn:
        rows = conn.execute("SELECT detail_json FROM cards").fetchall()
        for row in rows:
            detail = json.loads(row["detail_json"])
            for rule in detail.get("spendBonusCategory") or []:
                cat_id = rule.get("spendBonusCategoryId")
                if cat_id is not None:
                    ids.add(int(cat_id))
    return ids
