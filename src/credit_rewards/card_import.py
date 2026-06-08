"""Import card reward data into SQLite for wallet recommend."""

from __future__ import annotations

import time
from typing import Any

from credit_rewards.card_catalog import resolve_wallet_card_key
from credit_rewards.client import CardDataClient, RewardsCCError, upstream_api_enabled
from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.reference_sync import (
    assemble_card_from_category_snapshots,
    load_reference_card,
)


def card_exists_in_db(card_key: str) -> bool:
    import json

    with session() as conn:
        row = conn.execute(
            "SELECT detail_json FROM cards WHERE card_key = ?",
            (card_key,),
        ).fetchone()
        if not row:
            return False
        try:
            detail = json.loads(row["detail_json"])
            if isinstance(detail, list):
                detail = detail[0] if detail else {}
            rules = detail.get("spendBonusCategory") if isinstance(detail, dict) else None
            return bool(rules)
        except (json.JSONDecodeError, TypeError, KeyError):
            return False


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

    if not upstream_api_enabled():
        return False

    client = CardDataClient(use_upstream=True)

    for attempt in range(3):
        try:
            payload = client.card_detail(rc_key)
        except RewardsCCError:
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
                continue
            return False
        if not payload:
            return False

        detail = dict(payload[0] if isinstance(payload, list) else payload)
        detail["cardKey"] = wallet_key
        url = str(detail.get("cardUrl") or "")
        _upsert_detail(detail, source_type="rewardscc", source_url=url)
        return True

    return False


def ensure_wallet_cards_in_db(card_keys: list[str]) -> list[str]:
    missing: list[str] = []
    for key in card_keys:
        if not ensure_card_in_db(key):
            missing.append(key)
    return missing


def import_catalog_wallet_to_db(*, limit: int | None = None) -> dict[str, Any]:
    """
    Pre-load wallet catalog cards into SQLite (reference JSON + category snapshots).
    Run at Docker build so production recommend works without live API for ~380+ cards.
    Skips cards that need live API (imported on first recommend when REWARDS_CC_API_KEY is set).
    """
    from credit_rewards.card_catalog import load_catalog_index

    rows = load_catalog_index()
    if limit is not None:
        rows = rows[:limit]

    imported: list[str] = []
    skipped: list[str] = []
    for row in rows:
        key = str(row.get("card_key") or "").strip()
        if not key:
            continue
        if ensure_card_in_db(key):
            imported.append(key)
        else:
            skipped.append(key)

    return {
        "imported": imported,
        "skipped": skipped,
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "total": len(rows),
        "live_api": upstream_api_enabled(),
    }
