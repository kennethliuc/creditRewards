from __future__ import annotations

import json
from typing import Any

from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.reference_sync import REFERENCE_DIR, load_reference_card
from credit_rewards.ingest.scrape.registry import load_card_registry


def _registry_upstream_key(card_key: str) -> str | None:
    for entry in load_card_registry():
        if entry["card_key"] == card_key:
            return entry.get("rewards_cc_card_key") or entry["card_key"]
    return None


def _registry_url(card_key: str) -> str:
    for entry in load_card_registry():
        if entry["card_key"] == card_key:
            return entry.get("url") or ""
    return ""


def import_reference_to_db(
    card_keys: list[str] | None = None,
    *,
    reference_dir=REFERENCE_DIR,
    db_path=None,
) -> dict[str, Any]:
    """
    Load Rewards CC reference JSON into local SQLite for CardData API.
    Normalizes cardKey to our registry local card_key while preserving reward rules.
    """
    keys = card_keys or [e["card_key"] for e in load_card_registry()]
    imported: list[str] = []
    missing: list[str] = []

    with session(db_path) as conn:
        repo = CardDataRepository(conn)
        category_path = reference_dir / "category_list.json"
        if category_path.exists():
            repo.set_category_list_payload(json.loads(category_path.read_text()))

        for local_key in keys:
            upstream = _registry_upstream_key(local_key) or local_key
            reference = load_reference_card(local_key, reference_dir, upstream_key=upstream)
            if not reference:
                missing.append(local_key)
                continue
            detail = dict(reference)
            detail["cardKey"] = local_key
            url = detail.get("cardUrl") or _registry_url(local_key)
            repo.upsert_card(detail, source_url=url, source_type="reference")
            imported.append(local_key)

    return {
        "imported": imported,
        "missing": missing,
        "count": len(imported),
    }
