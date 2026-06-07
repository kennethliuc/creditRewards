from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from credit_rewards.client import CardDataClient, RewardsCCError
from credit_rewards.ingest.reference_sync import REFERENCE_DIR

DEFAULT_MAX_CALLS = int(os.getenv("REWARDS_CC_BULK_MAX_CALLS", "48000"))


def _walk_category_ids(node: Any, ids: set[int]) -> None:
    if isinstance(node, dict):
        if "spendBonusCategoryId" in node:
            ids.add(int(node["spendBonusCategoryId"]))
        for value in node.values():
            _walk_category_ids(value, ids)
    elif isinstance(node, list):
        for item in node:
            _walk_category_ids(item, ids)


def extract_category_ids(category_list: Any) -> list[int]:
    ids: set[int] = set()
    _walk_category_ids(category_list, ids)
    return sorted(ids)


def collect_card_keys_from_payload(payload: Any) -> set[str]:
    keys: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("cardKey"):
                keys.add(str(node["cardKey"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return keys


class BulkSyncStats:
    def __init__(self) -> None:
        self.api_calls = 0
        self.skipped_cached = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_calls": self.api_calls,
            "skipped_cached": self.skipped_cached,
            "errors": self.errors,
        }


def bulk_sync_rewardscc(
    output_dir: Path | None = None,
    *,
    force: bool = False,
    max_calls: int = DEFAULT_MAX_CALLS,
    sleep_seconds: float = 0.05,
) -> dict[str, Any]:
    """
    One-shot download of Rewards CC credit-card data into local reference cache.
    Designed to burn monthly quota once, then develop offline against local files.
    """
    client = CardDataClient(use_local=False)
    if not client.is_configured:
        raise RewardsCCError("Set REWARDS_CC_API_KEY in .env before bulk-sync.")

    root = output_dir or REFERENCE_DIR
    root.mkdir(parents=True, exist_ok=True)
    categories_dir = root / "categories"
    cards_dir = root / "cards"
    transfer_dir = root / "transfer"
    categories_dir.mkdir(exist_ok=True)
    cards_dir.mkdir(exist_ok=True)
    transfer_dir.mkdir(exist_ok=True)

    stats = BulkSyncStats()

    def fetch(path: str, dest: Path, *, skip_if_exists: bool = True) -> Any:
        if stats.api_calls >= max_calls:
            raise RewardsCCError(f"Stopped at max_calls={max_calls} (quota guard)")
        if skip_if_exists and dest.exists() and not force:
            stats.skipped_cached += 1
            return json.loads(dest.read_text())
        payload = client.get(path)
        stats.api_calls += 1
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        if sleep_seconds:
            time.sleep(sleep_seconds)
        return payload

    started = datetime.now(UTC).replace(microsecond=0).isoformat()

    # 1) Category taxonomy
    category_list = fetch(
        "creditcard-spendbonuscategory-categorylist/",
        root / "category_list.json",
    )
    category_ids = extract_category_ids(category_list)

    # 2) Cards per spend category
    all_keys: set[str] = set()
    for cat_id in category_ids:
        try:
            payload = fetch(
                f"creditcard-spendbonuscategory-categorycard/{cat_id}",
                categories_dir / f"{cat_id}.json",
            )
            all_keys |= collect_card_keys_from_payload(payload)
        except RewardsCCError as exc:
            stats.errors.append(f"category {cat_id}: {exc}")

    # 3) Point transfer programs
    try:
        programs = fetch(
            "creditcard-pointtransfer-transferprogramlist/",
            transfer_dir / "programs.json",
        )
        for program in programs if isinstance(programs, list) else []:
            partner_id = program.get("transferPartnerId")
            if partner_id is None:
                continue
            try:
                rows = fetch(
                    f"creditcard-pointtransfer-transferprogramcard/{partner_id}",
                    transfer_dir / f"{partner_id}.json",
                )
                all_keys |= collect_card_keys_from_payload(rows)
            except RewardsCCError as exc:
                stats.errors.append(f"transfer {partner_id}: {exc}")
    except RewardsCCError as exc:
        stats.errors.append(f"transfer list: {exc}")

    # 4) Full card detail for every discovered cardKey
    card_keys_sorted = sorted(all_keys)
    fetched_cards = 0
    for card_key in card_keys_sorted:
        try:
            fetch(
                f"creditcard-detail-bycard/{card_key}",
                cards_dir / f"{card_key}.json",
            )
            fetched_cards += 1
        except RewardsCCError as exc:
            stats.errors.append(f"card {card_key}: {exc}")

    manifest = {
        "synced_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "started_at": started,
        "provider": "rewardscc",
        "base_url": client.base_url,
        "stats": stats.to_dict(),
        "counts": {
            "categories": len(category_ids),
            "unique_card_keys": len(card_keys_sorted),
            "card_details_on_disk": len(list(cards_dir.glob("*.json"))),
        },
        "max_calls_limit": max_calls,
        "note": "Develop against this cache. Re-run bulk-sync monthly; do not call API during dev.",
    }
    (root / "bulk_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def iter_reference_cards(reference_dir: Path | None = None) -> Iterator[tuple[str, dict[str, Any]]]:
    root = reference_dir or REFERENCE_DIR
    cards_dir = root / "cards"
    if not cards_dir.exists():
        return
    for path in sorted(cards_dir.glob("*.json")):
        payload = json.loads(path.read_text())
        detail = payload[0] if isinstance(payload, list) and payload else payload
        if isinstance(detail, dict):
            yield path.stem, detail
