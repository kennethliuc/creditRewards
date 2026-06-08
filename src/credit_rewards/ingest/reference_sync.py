from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credit_rewards.client import CardDataClient, RewardsCCError, upstream_api_enabled
from credit_rewards.official_cpp import infer_program_from_metadata, normalize_earn_type

from credit_rewards.paths import data_dir

REFERENCE_DIR = data_dir() / "reference" / "rewardscc"

def _category_ids_from_detail(detail: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    for rule in detail.get("spendBonusCategory") or []:
        cat_id = rule.get("spendBonusCategoryId")
        if cat_id is not None:
            ids.add(int(cat_id))
    return ids


def _reference_client() -> CardDataClient:
    """Optional upstream Rewards CC (one-off sync commands only)."""
    return CardDataClient(use_upstream=True)


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
        raise RewardsCCError(
            "Upstream API disabled. Set CREDITREWARDS_USE_UPSTREAM_API=1 and REWARDS_CC_API_KEY "
            "for optional sync-reference, or use committed data under data/reference/."
        )

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
    from credit_rewards.ingest.quarterly_rotations import enrich_with_quarterly_rotations

    root = reference_dir or REFERENCE_DIR
    for name in (upstream_key, card_key):
        if not name:
            continue
        path = root / "cards" / f"{name}.json"
        if path.exists():
            payload = json.loads(path.read_text())
            if isinstance(payload, list):
                if not payload:
                    return enrich_with_quarterly_rotations(
                        {"cardKey": card_key, "spendBonusCategory": []},
                        card_key=card_key,
                    )
                return enrich_with_quarterly_rotations(payload[0], card_key=card_key)
            return enrich_with_quarterly_rotations(payload, card_key=card_key)
    return None


def _infer_spend_type_from_meta(card_key: str, meta: dict[str, Any]) -> str | None:
    detail = {
        "cardIssuer": meta.get("cardIssuer") or "",
        "baseSpendEarnType": "",
    }
    return infer_program_from_metadata(card_key, detail)


def assemble_card_from_category_snapshots(
    card_key: str,
    upstream_key: str | None = None,
    reference_dir: Path | None = None,
) -> dict[str, Any] | None:
    """
    Build a minimal card detail from synced category_*.json rows when cards/{key}.json is missing.
    Used for catalog wallet cards (e.g. chase-starbucksrewardsvisa) on Railway without live API.
    """
    root = reference_dir or REFERENCE_DIR
    if not root.is_dir():
        return None

    keys = {k for k in (upstream_key, card_key) if k}
    rules_by_id: dict[int, dict[str, Any]] = {}
    meta: dict[str, Any] = {}

    for path in sorted(root.glob("category_*.json")):
        try:
            rows = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if row.get("cardKey") not in keys:
                continue
            if not meta:
                meta = {
                    "cardName": row.get("cardName") or card_key,
                    "cardIssuer": row.get("cardIssuer") or "",
                    "cardNetwork": row.get("cardNetwork") or "",
                    "spendType": row.get("spendType") or "",
                }
            cat_id = row.get("spendBonusCategoryId")
            if cat_id is None:
                continue
            rules_by_id[int(cat_id)] = {
                "spendBonusCategoryName": row.get("spendBonusCategoryName") or "",
                "spendBonusCategoryId": int(cat_id),
                "spendBonusDesc": row.get("spendBonusDesc") or "",
                "earnMultiplier": float(row.get("earnMultiplier") or 0),
                "isDateLimit": int(row.get("isDateLimit") or 0),
                "limitBeginDate": row.get("limitBeginDate") or "",
                "limitEndDate": row.get("limitEndDate") or "",
                "isSpendLimit": int(row.get("isSpendLimit") or 0),
                "spendLimit": float(row.get("spendLimit") or 0),
                "spendLimitResetPeriod": row.get("spendLimitResetPeriod") or "",
            }

    if not rules_by_id:
        return None

    spend_type = str(meta.get("spendType") or "").strip()
    if not spend_type or spend_type.lower() in {"points", "point"}:
        spend_type = _infer_spend_type_from_meta(card_key, meta) or "Points"
    spend_type = normalize_earn_type(spend_type) or spend_type
    detail = {
        "cardKey": card_key,
        "cardName": meta.get("cardName") or card_key,
        "cardIssuer": meta.get("cardIssuer") or "",
        "cardNetwork": meta.get("cardNetwork") or "",
        "baseSpendAmount": 0.25,
        "baseSpendEarnType": spend_type,
        "baseSpendEarnCategory": spend_type,
        "baseSpendEarnCurrency": "points",
        "baseSpendEarnValuation": 1.0,
        "baseSpendEarnIsCash": 0,
        "baseSpendEarnCashValue": 1.0,
        "isActive": 1,
        "spendBonusCategory": list(rules_by_id.values()),
    }
    from credit_rewards.ingest.quarterly_rotations import enrich_with_quarterly_rotations

    return enrich_with_quarterly_rotations(detail, card_key=card_key)


def catalog_card_has_offline_reference(card_key: str, upstream_key: str | None = None) -> bool:
    return bool(
        load_reference_card(card_key, upstream_key=upstream_key)
        or assemble_card_from_category_snapshots(card_key, upstream_key)
    )


def list_catalog_cards_missing_offline_reference() -> list[dict[str, Any]]:
    from credit_rewards.card_catalog import load_catalog_index

    missing: list[dict[str, Any]] = []
    for row in load_catalog_index():
        wallet_key = str(row.get("card_key") or "")
        rc_key = str(row.get("rewards_cc_card_key") or wallet_key)
        if not catalog_card_has_offline_reference(wallet_key, rc_key):
            missing.append(dict(row))
    return missing


def backfill_catalog_reference_cards(
    *,
    sleep_seconds: float = 0.05,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """
    One-time: save creditcard-detail JSON for wallet catalog cards missing offline data.
    Requires CREDITREWARDS_USE_UPSTREAM_API=1 + REWARDS_CC_API_KEY.
    """
    client = _reference_client()
    if not client.is_configured:
        raise RewardsCCError(
            "Set CREDITREWARDS_USE_UPSTREAM_API=1 and REWARDS_CC_API_KEY to backfill reference JSON."
        )

    out = output_dir or REFERENCE_DIR
    cards_dir = out / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    missing = list_catalog_cards_missing_offline_reference()
    saved: list[str] = []
    errors: list[str] = []
    for row in missing:
        rc_key = str(row.get("rewards_cc_card_key") or row.get("card_key") or "")
        if not rc_key:
            continue
        dest = cards_dir / f"{rc_key}.json"
        try:
            payload = client.card_detail(rc_key)
        except RewardsCCError as exc:
            errors.append(f"{rc_key}: {exc}")
            continue
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        saved.append(rc_key)
        if sleep_seconds:
            import time

            time.sleep(sleep_seconds)

    return {
        "missing_before": len(missing),
        "saved": saved,
        "saved_count": len(saved),
        "errors": errors,
        "output_dir": str(out),
    }
