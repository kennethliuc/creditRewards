from __future__ import annotations

import json
from pathlib import Path

from credit_rewards.client import CardDataClient, RewardsCCClient, RewardsCCError, upstream_api_enabled
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
    from credit_rewards.card_catalog import resolve_wallet_card_key
    from credit_rewards.datastore.db import session
    from credit_rewards.datastore.repository import CardDataRepository

    resolved = resolve_wallet_card_key(card_key)
    keys_to_try = [resolved["card_key"], resolved["rewards_cc_card_key"], card_key]
    seen: set[str] = set()
    with session() as conn:
        repo = CardDataRepository(conn)
        for key in keys_to_try:
            k = str(key).strip()
            if not k or k in seen:
                continue
            seen.add(k)
            detail = repo.get_card_detail(k)
            if detail:
                return normalize_card_detail(detail)
    return None


def load_wallet(card_keys: list[str], client: CardDataClient | None = None) -> list[CardProfile]:
    client = client or CardDataClient()
    cards: list[CardProfile] = []
    missing: list[str] = []

    for key in card_keys:
        key = key.strip()
        if not key:
            continue
        loaded: CardProfile | None = _load_from_db(key)
        if loaded is None and upstream_api_enabled():
            try:
                from credit_rewards.card_catalog import resolve_wallet_card_key

                resolved = resolve_wallet_card_key(key)
                rc_key = str(resolved["rewards_cc_card_key"])
                payload = CardDataClient(use_upstream=True).card_detail(rc_key)
                loaded = normalize_card_detail(payload)
            except RewardsCCError:
                loaded = None
        if loaded is None:
            try:
                loaded = load_fixture_card(key)
            except RewardsCCError:
                missing.append(key)
                continue
        cards.append(loaded)

    if missing:
        names = ", ".join(missing)
        raise RewardsCCError(
            f"Reward data not available for: {names}. "
            "Remove the card or choose one from the popular list."
        )

    return cards
