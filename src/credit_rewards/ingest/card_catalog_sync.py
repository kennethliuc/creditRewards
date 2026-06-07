"""Build card_catalog_index.json from Rewards CC category + transfer discovery."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from credit_rewards.client import CardDataClient, RewardsCCError
from credit_rewards.ingest.bulk_sync import collect_card_keys_from_payload, extract_category_ids
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.paths import data_dir


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _registry_map() -> dict[str, dict[str, Any]]:
    by_rc: dict[str, dict[str, Any]] = {}
    for entry in load_card_registry():
        rc = str(entry.get("rewards_cc_card_key") or entry["card_key"])
        by_rc[rc] = entry
    return by_rc


def discover_catalog_rows(
    client: CardDataClient,
    *,
    sleep_seconds: float = 0.04,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Discover cardKey/name/issuer via spend categories + transfer programs."""
    by_rc_key: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    reg_by_rc = _registry_map()

    def absorb(payload: Any) -> None:
        for row in _rows_from_payload(payload):
            rc_key = str(row.get("cardKey") or "").strip()
            if not rc_key:
                continue
            if rc_key in by_rc_key:
                continue
            reg = reg_by_rc.get(rc_key)
            wallet_key = str(reg["card_key"]) if reg else rc_key
            by_rc_key[rc_key] = {
                "card_key": wallet_key,
                "rewards_cc_card_key": rc_key,
                "card_name": str(row.get("cardName") or rc_key),
                "issuer": str(row.get("cardIssuer") or (reg.get("issuer") if reg else "")),
                "in_registry": bool(reg),
            }

    try:
        category_list = client.category_list()
    except RewardsCCError as exc:
        raise RewardsCCError(f"category list: {exc}") from exc

    for cat_id in extract_category_ids(category_list):
        try:
            absorb(client.category_cards(cat_id))
        except RewardsCCError as exc:
            errors.append(f"category {cat_id}: {exc}")
        if sleep_seconds:
            time.sleep(sleep_seconds)

    try:
        programs = client.transfer_program_list()
    except RewardsCCError as exc:
        errors.append(f"transfer list: {exc}")
        programs = []

    for program in programs if isinstance(programs, list) else []:
        partner_id = program.get("transferPartnerId")
        if partner_id is None:
            continue
        try:
            absorb(client.transfer_program_cards(int(partner_id)))
        except RewardsCCError as exc:
            errors.append(f"transfer {partner_id}: {exc}")
        if sleep_seconds:
            time.sleep(sleep_seconds)

    # Ensure registry cards present even if missing from API walk.
    for entry in load_card_registry():
        rc_key = str(entry.get("rewards_cc_card_key") or entry["card_key"])
        wallet_key = str(entry["card_key"])
        if rc_key not in by_rc_key:
            by_rc_key[rc_key] = {
                "card_key": wallet_key,
                "rewards_cc_card_key": rc_key,
                "card_name": wallet_key.replace("-", " ").title(),
                "issuer": str(entry.get("issuer") or ""),
                "in_registry": True,
            }

    return by_rc_key, errors


def attach_card_images(
    client: CardDataClient,
    rows: dict[str, dict[str, Any]],
    *,
    sleep_seconds: float = 0.05,
    skip_existing: bool = True,
    progress_every: int = 100,
) -> int:
    fetched = 0
    cache: dict[str, str] = {}
    for row in rows.values():
        rc_key = str(row["rewards_cc_card_key"])
        if skip_existing and row.get("image_url"):
            cache[rc_key] = str(row["image_url"])
            continue
        if rc_key in cache:
            row["image_url"] = cache[rc_key]
            continue
        url = ""
        try:
            payload = client.get(f"creditcard-card-image/{rc_key}")
            if isinstance(payload, list) and payload:
                url = str(payload[0].get("cardImageUrl") or "")
        except RewardsCCError:
            url = ""
        cache[rc_key] = url
        row["image_url"] = url
        fetched += 1
        if progress_every and fetched % progress_every == 0:
            print(f"  … {fetched} images fetched", flush=True)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return fetched


def load_existing_rows() -> dict[str, dict[str, Any]]:
    path = data_dir() / "card_catalog_index.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    rows: dict[str, dict[str, Any]] = {}
    for card in payload.get("cards") or []:
        rc = str(card.get("rewards_cc_card_key") or card.get("card_key") or "")
        if rc:
            rows[rc] = dict(card)
    return rows


def write_catalog_index(
    rows: dict[str, dict[str, Any]],
    *,
    errors: list[str] | None = None,
    image_fetch_count: int = 0,
) -> Path:
    cards = sorted(rows.values(), key=lambda r: (str(r["issuer"]), str(r["card_name"])))
    issuers = sorted({str(c["issuer"]) for c in cards if c.get("issuer")})
    payload = {
        "updated": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source": "rewardscc_categories",
        "card_count": len(cards),
        "issuer_count": len(issuers),
        "image_fetch_count": image_fetch_count,
        "sync_errors": errors or [],
        "cards": cards,
    }
    dest = data_dir() / "card_catalog_index.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return dest
