"""Import card reward data into SQLite for wallet recommend."""

from __future__ import annotations

from typing import Any

from credit_rewards.card_catalog import resolve_wallet_card_key
from credit_rewards.client import CardDataClient, RewardsCCError
from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.reference_sync import (
    assemble_card_from_category_snapshots,
    load_reference_card,
)


def card_exists_in_db(card_key: str) -> bool:
    with session() as conn:
        row = conn.execute("SELECT 1 FROM cards WHERE card_key = ?", (card_key,)).fetchone()
        return row is not None


def _upsert_detail(detail: dict[str, Any], *, source_type: str, source_url: str = "") -> None:
    with session() as conn:
        CardDataRepository(conn).upsert_card(
            detail,
            source_url=source_url,
            source_type=source_type,
        )


def ensure_card_in_db(card_key: str) -> bool:
    """Load reward rules into SQLite: reference JSON → category snapshots → live API."""
    resolved = resolve_wallet_card_key(card_key)
    wallet_key = str(resolved["card_key"])
    if card_exists_in_db(wallet_key):
        return True

    rc_key = str(resolved["rewards_cc_card_key"])

    reference = load_reference_card(wallet_key, upstream_key=rc_key)
    if reference:
        detail = dict(reference)
        detail["cardKey"] = wallet_key
        _upsert_detail(
            detail,
            source_type="reference",
            source_url=str(detail.get("cardUrl") or ""),
        )
        return True

    assembled = assemble_card_from_category_snapshots(wallet_key, rc_key)
    if assembled:
        _upsert_detail(assembled, source_type="category_snapshot")
        return True

    client = CardDataClient(use_local=False)
    if not client.is_configured:
        return False

    try:
        payload = client.card_detail(rc_key)
    except RewardsCCError:
        return False
    if not payload:
        return False

    detail = dict(payload[0] if isinstance(payload, list) else payload)
    detail["cardKey"] = wallet_key
    url = str(detail.get("cardUrl") or "")
    _upsert_detail(detail, source_type="rewardscc", source_url=url)
    return True


def ensure_wallet_cards_in_db(card_keys: list[str]) -> list[str]:
    missing: list[str] = []
    for key in card_keys:
        if not ensure_card_in_db(key):
            missing.append(key)
    return missing
