"""Sync Rewards CC category-card snapshots for merchant co-brand bonuses."""

from __future__ import annotations

import json
from pathlib import Path

from credit_rewards.client import CardDataClient, RewardsCCError, upstream_api_enabled
from credit_rewards.co_brand_category_index import (
    category_snapshot_path,
    co_brand_category_ids_for_merchants,
    load_co_brand_category_index,
)
from credit_rewards.paths import data_dir


def sync_co_brand_categories(
    *,
    reference_dir: Path | None = None,
    only_missing: bool = True,
    extra_category_ids: list[int] | None = None,
) -> dict:
    client = CardDataClient(use_upstream=True)
    if not client.is_configured:
        raise RewardsCCError(
            "Set CREDITREWARDS_USE_UPSTREAM_API=1 and REWARDS_CC_API_KEY before sync-co-brand-categories."
        )

    root = reference_dir or (data_dir() / "reference" / "rewardscc")
    root.mkdir(parents=True, exist_ok=True)

    ids: dict[str, int] = co_brand_category_ids_for_merchants()
    for _norm, (name, cat_id) in load_co_brand_category_index().items():
        if cat_id in (extra_category_ids or []):
            ids[name] = cat_id

    synced: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for name, cat_id in sorted(ids.items(), key=lambda x: x[1]):
        path = category_snapshot_path(cat_id, reference_dir=root)
        if only_missing and path.exists():
            skipped.append(path.name)
            continue
        try:
            rows = client.get(f"creditcard-spendbonuscategory-categorycard/{cat_id}")
            path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
            synced.append(f"{path.name} ({name}, {len(rows)} cards)")
        except RewardsCCError as exc:
            errors.append(f"{cat_id} {name}: {exc}")

    return {
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "category_count": len(ids),
    }
