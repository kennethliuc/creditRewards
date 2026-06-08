"""Rewards CC spend categories that represent merchant/co-brand bonuses (not generic MCC buckets)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from credit_rewards.paths import data_dir

CATEGORY_LIST_PATH = data_dir() / "reference" / "rewardscc" / "category_list.json"

# Generic spend buckets — not merchant co-brand bonuses.
GENERIC_CATEGORY_NAMES = frozenset(
    {
        "Dining",
        "Grocery Stores",
        "Gas Stations",
        "Travel",
        "Airfare",
        "Hotels",
        "Online Shopping",
        "Drugstores",
        "Streaming Services",
        "Entertainment",
        "Lyft",
        "Transit",
        "Telecom",
        "Wholesale Clubs",
        "All Purchases",
        "Car Rental",
        "Home Improvement",
        "Fitness Clubs",
        "Live Entertainment",
        "Rent",
        "Utilities",
        "Utilities (select U.S. providers)",
        "Utilities (U.S. providers)",
        "Foreign Transactions",
        "Car Wash",
        "Cosmetic Stores",
        "Pet Shops",
        "Veterinary",
        "Home Repair",
        "Select Charities",
        "Select Clothing Stores",
    }
)

# Portal-specific categories (issuer travel portals), not merchant co-brand.
_PORTAL_MARKERS = (
    "Capital One",
    "CitiTravel",
    "Robinhood",
    "U.S. Bank",
    "LuxuryCard",
    "amextravel.com",
)


def _normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _is_co_brand_category(name: str) -> bool:
    if not name or name in GENERIC_CATEGORY_NAMES:
        return False
    if name.startswith("All "):
        return False
    if "Ultimate Rewards" in name:
        return False
    lowered = name.lower()
    if any(marker.lower() in lowered for marker in _PORTAL_MARKERS):
        return False
    if "(" in name and any(marker in name for marker in _PORTAL_MARKERS):
        return False
    return True


@lru_cache(maxsize=1)
def load_co_brand_category_index() -> dict[str, tuple[str, int]]:
    """Map normalized label → (canonical category name, spendBonusCategoryId)."""
    payload = json.loads(CATEGORY_LIST_PATH.read_text())
    index: dict[str, tuple[str, int]] = {}
    for group in payload:
        for sub in group.get("spendBonusSubcategoryGroup") or []:
            for cat in sub.get("spendBonusCategory") or []:
                name = str(cat.get("spendBonusCategoryName") or "").strip()
                cat_id = cat.get("spendBonusCategoryId")
                if cat_id is None or not _is_co_brand_category(name):
                    continue
                canonical = (name, int(cat_id))
                index[_normalize_label(name)] = canonical
    return index


def co_brand_category_id(name: str) -> int | None:
    row = load_co_brand_category_index().get(_normalize_label(name))
    return row[1] if row else None


def _token_match(merchant_norm: str, cat_norm: str) -> bool:
    if not merchant_norm or not cat_norm:
        return False
    shorter, longer = (
        (merchant_norm, cat_norm)
        if len(merchant_norm) <= len(cat_norm)
        else (cat_norm, merchant_norm)
    )
    # Avoid "aa" matching "aaa" — require minimum length for substring hits.
    if len(shorter) >= 4 and shorter in longer:
        return True
    stop = {"air", "airlines", "airline", "lines", "the", "stores", "store", "market", "com", "net", "org", "www"}
    tokens = [t for t in merchant_norm.split() if t not in stop and len(t) > 2]
    if not tokens:
        return False
    return all(token in cat_norm for token in tokens)


def resolve_co_brand_category_names(
    merchant_name: str,
    *,
    aliases: list[str] | None = None,
    explicit: list[str] | None = None,
) -> list[str]:
    """
    Resolve Rewards CC co-brand spend category names for a merchant.

    Order: explicit YAML overrides → exact name/alias match → substring match.
    """
    index = load_co_brand_category_index()
    ordered: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        text = (name or "").strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        ordered.append(text)

    for name in explicit or []:
        add(name)

    candidates = [merchant_name, *(aliases or [])]
    for raw in candidates:
        norm = _normalize_label(raw)
        if not norm:
            continue
        hit = index.get(norm)
        if hit:
            add(hit[0])
            continue
        for cat_norm, (cat_name, _cat_id) in index.items():
            if _token_match(norm, cat_norm):
                add(cat_name)
                break

    return ordered


def co_brand_category_ids_for_merchants() -> dict[str, int]:
    """All co-brand category IDs — full Rewards CC index + merchant catalog overrides."""
    from credit_rewards.merchant_mapping import load_merchant_catalog

    index = load_co_brand_category_index()
    ids: dict[str, int] = {name: cat_id for name, cat_id in index.values()}

    for row in load_merchant_catalog():
        names = resolve_co_brand_category_names(
            str(row.get("name") or ""),
            aliases=[str(a) for a in (row.get("aliases") or [])],
            explicit=[str(x) for x in (row.get("co_brand_bonus_categories") or [])],
        )
        for name in names:
            cat_id = ids.get(name)
            if cat_id is not None:
                ids[name] = cat_id
    return ids


def category_snapshot_path(category_id: int, *, reference_dir: Path | None = None) -> Path:
    root = reference_dir or (data_dir() / "reference" / "rewardscc")
    return root / f"category_{category_id}.json"
