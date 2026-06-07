from __future__ import annotations

import json
from pathlib import Path

from credit_rewards.client import CardDataClient, RewardsCCClient, RewardsCCError
from credit_rewards.models import CardProfile
from credit_rewards.normalize import normalize_card_detail

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def load_fixture_card(card_key: str) -> CardProfile:
    path = FIXTURES_DIR / f"{card_key}.json"
    if not path.exists():
        raise RewardsCCError(f"No fixture for card '{card_key}'. Add tests/fixtures/{card_key}.json")
    payload = json.loads(path.read_text())
    return normalize_card_detail(payload)


def _load_from_db(card_key: str) -> CardProfile | None:
    from credit_rewards.datastore.db import session
    from credit_rewards.datastore.repository import CardDataRepository

    with session() as conn:
        detail = CardDataRepository(conn).get_card_detail(card_key)
        if detail:
            return normalize_card_detail(detail)
    return None


def load_wallet(card_keys: list[str], client: CardDataClient | None = None) -> list[CardProfile]:
    client = client or CardDataClient()
    cards: list[CardProfile] = []

    for key in card_keys:
        key = key.strip()
        if not key:
            continue
        loaded: CardProfile | None = None
        if client.is_configured:
            try:
                payload = client.card_detail(key)
                loaded = normalize_card_detail(payload)
            except RewardsCCError:
                loaded = None
        if loaded is None:
            loaded = _load_from_db(key)
        if loaded is None:
            loaded = load_fixture_card(key)
        cards.append(loaded)

    return cards
