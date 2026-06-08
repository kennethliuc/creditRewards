"""Build card_catalog_index.json from Rewards CC category + transfer discovery."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from credit_rewards.client import CardDataClient, RewardsCCError
from credit_rewards.ingest.bulk_sync import collect_card_keys_from_payload, extract_category_ids
from credit_rewards.ingest.reference_sync import REFERENCE_DIR
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.paths import data_dir

REFERENCE_CARD_LIST_PATH = data_dir() / "reference" / "rewardscc" / "card_list.json"


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


def load_reference_card_list() -> list[dict[str, Any]]:
    if not REFERENCE_CARD_LIST_PATH.exists():
        return []
    payload = json.loads(REFERENCE_CARD_LIST_PATH.read_text())
    return payload if isinstance(payload, list) else []


def absorb_card_list_groups(
    groups: list[dict[str, Any]],
    by_rc_key: dict[str, dict[str, Any]],
    *,
    reg_by_rc: dict[str, dict[str, Any]],
) -> int:
    """Merge grouped card-list rows into discovery map. Returns newly added keys."""
    added = 0
    for group in groups:
        issuer = str(group.get("cardIssuer") or "").strip()
        for card in group.get("card") or []:
            if not isinstance(card, dict):
                continue
            rc_key = str(card.get("cardKey") or "").strip()
            if not rc_key:
                continue
            reg = reg_by_rc.get(rc_key)
            wallet_key = str(reg["card_key"]) if reg else rc_key
            card_name = str(card.get("cardName") or rc_key)
            if rc_key in by_rc_key:
                row = by_rc_key[rc_key]
                if card_name and len(card_name) > len(str(row.get("card_name") or "")):
                    row["card_name"] = card_name
                if issuer and not str(row.get("issuer") or "").strip():
                    row["issuer"] = issuer
                continue
            by_rc_key[rc_key] = {
                "card_key": wallet_key,
                "rewards_cc_card_key": rc_key,
                "card_name": card_name,
                "issuer": issuer or (str(reg.get("issuer") or "") if reg else ""),
                "in_registry": bool(reg),
            }
            added += 1
    return added


def fetch_card_list_rows(client: CardDataClient) -> tuple[list[dict[str, Any]], str | None]:
    """Try live/local card list API, then cached reference JSON."""
    try:
        groups = client.card_list()
        if groups:
            return groups, client.provider
    except RewardsCCError:
        pass
    cached = load_reference_card_list()
    if cached:
        return cached, "reference_cache"
    return [], None


def discover_catalog_rows_from_reference(
    reference_dir: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build catalog rows from committed reference snapshots (no upstream API)."""
    root = reference_dir or REFERENCE_DIR
    by_rc_key: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    reg_by_rc = _registry_map()

    cached = load_reference_card_list()
    if cached:
        added = absorb_card_list_groups(cached, by_rc_key, reg_by_rc=reg_by_rc)
        errors.append(f"card_list:reference_cache:+{added}")

    def absorb(payload: Any) -> None:
        for row in _rows_from_payload(payload):
            rc_key = str(row.get("cardKey") or "").strip()
            if not rc_key:
                continue
            reg = reg_by_rc.get(rc_key)
            wallet_key = str(reg["card_key"]) if reg else rc_key
            card_name = str(row.get("cardName") or rc_key)
            issuer = str(row.get("cardIssuer") or (reg.get("issuer") if reg else ""))
            existing = by_rc_key.get(rc_key)
            if existing:
                if card_name and len(card_name) > len(str(existing.get("card_name") or "")):
                    existing["card_name"] = card_name
                if issuer and not str(existing.get("issuer") or "").strip():
                    existing["issuer"] = issuer
                continue
            by_rc_key[rc_key] = {
                "card_key": wallet_key,
                "rewards_cc_card_key": rc_key,
                "card_name": card_name,
                "issuer": issuer,
                "in_registry": bool(reg),
            }

    for path in sorted(root.glob("category_*.json")):
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        absorb(payload)

    cards_dir = root / "cards"
    if cards_dir.is_dir():
        for path in sorted(cards_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"cards/{path.name}: {exc}")
                continue
            detail = payload[0] if isinstance(payload, list) and payload else payload
            if isinstance(detail, dict) and detail.get("cardKey"):
                absorb([detail])

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

    errors.append(f"reference_categories:{root}")
    return by_rc_key, errors


def discover_catalog_rows(
    client: CardDataClient,
    *,
    sleep_seconds: float = 0.04,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Discover cardKey/name/issuer via card list + spend categories + transfer programs."""
    by_rc_key: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    reg_by_rc = _registry_map()

    card_list_groups, card_list_source = fetch_card_list_rows(client)
    if card_list_groups:
        added = absorb_card_list_groups(card_list_groups, by_rc_key, reg_by_rc=reg_by_rc)
        errors.append(f"card_list:{card_list_source}:+{added}")

    def absorb(payload: Any) -> None:
        for row in _rows_from_payload(payload):
            rc_key = str(row.get("cardKey") or "").strip()
            if not rc_key:
                continue
            reg = reg_by_rc.get(rc_key)
            wallet_key = str(reg["card_key"]) if reg else rc_key
            card_name = str(row.get("cardName") or rc_key)
            issuer = str(row.get("cardIssuer") or (reg.get("issuer") if reg else ""))
            existing = by_rc_key.get(rc_key)
            if existing:
                if card_name and len(card_name) > len(str(existing.get("card_name") or "")):
                    existing["card_name"] = card_name
                if issuer and not str(existing.get("issuer") or "").strip():
                    existing["issuer"] = issuer
                continue
            by_rc_key[rc_key] = {
                "card_key": wallet_key,
                "rewards_cc_card_key": rc_key,
                "card_name": card_name,
                "issuer": issuer,
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
    discovery_sources: dict[str, int] | None = None,
) -> Path:
    cards = sorted(rows.values(), key=lambda r: (str(r["issuer"]), str(r["card_name"])))
    issuers = sorted({str(c["issuer"]) for c in cards if c.get("issuer")})
    payload = {
        "updated": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source": "rewardscc_cardlist+categories",
        "card_count": len(cards),
        "issuer_count": len(issuers),
        "image_fetch_count": image_fetch_count,
        "discovery_sources": discovery_sources or {},
        "sync_errors": errors or [],
        "cards": cards,
        "scope": "top_tier_issuers",
    }
    dest = data_dir() / "card_catalog_index.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return dest
