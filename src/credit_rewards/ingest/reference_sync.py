from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credit_rewards.client import CardDataClient, RewardsCCError

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "data" / "reference" / "rewardscc"

def _category_ids_from_detail(detail: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    for rule in detail.get("spendBonusCategory") or []:
        cat_id = rule.get("spendBonusCategoryId")
        if cat_id is not None:
            ids.add(int(cat_id))
    return ids


def _reference_client() -> CardDataClient:
    """Always talk to upstream Rewards CC (never local API)."""
    return CardDataClient(use_local=False)


def sync_reference(
    card_keys: list[str] | None = None,
    output_dir: Path | None = None,
    registry: list[dict[str, Any]] | None = None,
    *,
    include_category_list: bool = True,
) -> dict[str, Any]:
    """
    Pull Rewards CC golden JSON for cards in data/card_registry.yaml only.

    Typical quota use: ~1 category list + N card details + M category-card endpoints
    where M = unique spend categories on those cards (often ~10–25 for 5 cards).
    Does NOT download the full US card catalog — use bulk-sync only if you explicitly
    want that (not recommended for this project).
    """
    client = _reference_client()
    if not client.is_configured:
        raise RewardsCCError("Set REWARDS_CC_API_KEY in .env before sync-reference.")

    out = output_dir or REFERENCE_DIR
    out.mkdir(parents=True, exist_ok=True)
    cards_dir = out / "cards"
    cards_dir.mkdir(exist_ok=True)

    api_calls = 0
    manifest: dict[str, Any] = {
        "synced_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "scope": "registry",
        "provider": client.provider,
        "base_url": client.base_url,
        "api_calls": 0,
        "cards": {},
        "endpoints": {},
    }

    from credit_rewards.ingest.scrape.registry import load_card_registry

    all_entries = registry or load_card_registry()
    if card_keys:
        key_set = set(card_keys)
        entries = [e for e in all_entries if e["card_key"] in key_set]
        unknown = key_set - {e["card_key"] for e in entries}
        if unknown:
            raise RewardsCCError(f"Unknown card_key(s) in registry: {', '.join(sorted(unknown))}")
    else:
        entries = all_entries

    category_ids: set[int] = set()
    for entry in entries:
        local_key = entry["card_key"]
        upstream_key = entry.get("rewards_cc_card_key") or local_key
        payload = client.card_detail(upstream_key)
        api_calls += 1
        path = cards_dir / f"{local_key}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        detail = payload[0] if payload else {}
        rule_count = len(detail.get("spendBonusCategory") or [])
        category_ids |= _category_ids_from_detail(detail)
        manifest["cards"][local_key] = {
            "path": str(path.relative_to(out)),
            "rule_count": rule_count,
            "rewards_cc_card_key": upstream_key,
            "issuer": entry.get("issuer", ""),
        }

    if include_category_list:
        category_list = client.category_list()
        api_calls += 1
        (out / "category_list.json").write_text(json.dumps(category_list, indent=2) + "\n")
        manifest["endpoints"]["category_list"] = "category_list.json"

    for cat_id in sorted(category_ids):
        try:
            rows = client.get(f"creditcard-spendbonuscategory-categorycard/{cat_id}")
            api_calls += 1
            fname = f"category_{cat_id}.json"
            (out / fname).write_text(json.dumps(rows, indent=2) + "\n")
            manifest["endpoints"][f"category_{cat_id}"] = fname
        except RewardsCCError as exc:
            manifest["endpoints"][f"category_{cat_id}"] = f"skipped ({exc})"

    skey = os.getenv("REWARDS_CC_SKEY", "")
    if skey:
        usage = client.api_usage(skey)
        (out / "api_usage.json").write_text(json.dumps(usage, indent=2) + "\n")
        manifest["endpoints"]["api_usage"] = "api_usage.json"

    manifest["api_calls"] = api_calls
    manifest["category_ids_synced"] = sorted(category_ids)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def load_reference_card(
    card_key: str,
    reference_dir: Path | None = None,
    upstream_key: str | None = None,
) -> dict[str, Any] | None:
    root = reference_dir or REFERENCE_DIR
    for name in (upstream_key, card_key):
        if not name:
            continue
        path = root / "cards" / f"{name}.json"
        if path.exists():
            payload = json.loads(path.read_text())
            if isinstance(payload, list):
                if not payload:
                    return {"cardKey": card_key, "spendBonusCategory": []}
                return payload[0]
            return payload
    return None
