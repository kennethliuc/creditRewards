"""Import card reward data into SQLite for wallet recommend."""

from __future__ import annotations

from credit_rewards.card_catalog import resolve_wallet_card_key
from credit_rewards.client import CardDataClient, RewardsCCError
from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository


def card_exists_in_db(card_key: str) -> bool:
    with session() as conn:
        row = conn.execute("SELECT 1 FROM cards WHERE card_key = ?", (card_key,)).fetchone()
        return row is not None


def ensure_card_in_db(card_key: str) -> bool:
    """Fetch Rewards CC detail and upsert when API is configured."""
    resolved = resolve_wallet_card_key(card_key)
    wallet_key = str(resolved["card_key"])
    if card_exists_in_db(wallet_key):
        return True

    client = CardDataClient(use_local=False)
    if not client.is_configured:
        return False

    rc_key = str(resolved["rewards_cc_card_key"])
    try:
        payload = client.card_detail(rc_key)
    except RewardsCCError:
        return False
    if not payload:
        return False

    detail = dict(payload[0] if isinstance(payload, list) else payload)
    detail["cardKey"] = wallet_key
    url = str(detail.get("cardUrl") or "")
    with session() as conn:
        CardDataRepository(conn).upsert_card(detail, source_url=url, source_type="rewardscc")
    return True


def ensure_wallet_cards_in_db(card_keys: list[str]) -> list[str]:
    missing: list[str] = []
    for key in card_keys:
        if not ensure_card_in_db(key):
            missing.append(key)
    return missing
