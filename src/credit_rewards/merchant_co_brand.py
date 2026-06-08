"""Merchant co-brand bonus categories for recommend (e.g. Starbucks → Starbucks earn bucket)."""

from __future__ import annotations

from typing import Any

from credit_rewards.co_brand_category_index import resolve_co_brand_category_names
from credit_rewards.merchant_mapping import load_merchant_catalog


def co_brand_bonus_categories_for_merchant(
    merchant_id: str,
    *,
    catalog: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return co-brand spend categories for a catalog merchant id."""
    mid = (merchant_id or "").strip()
    if not mid or mid.startswith(("osm:", "gmaps:", "web:")):
        return []

    for row in catalog or load_merchant_catalog():
        if str(row.get("id") or "") != mid:
            continue
        explicit = [str(x) for x in (row.get("co_brand_bonus_categories") or []) if str(x).strip()]
        # Merchant aliases (e.g. "aa") are for catalog lookup only — not co-brand fuzzy match.
        return resolve_co_brand_category_names(
            str(row.get("name") or ""),
            explicit=explicit,
        )
    return []


def co_brand_bonus_categories_for_purchase(
    *,
    merchant_id: str | None = None,
    merchant_name: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
) -> list[str]:
    """
    Resolve co-brand spend categories for recommend.

    1. Known catalog merchant id → name/alias auto-match (+ optional explicit overrides)
    2. Fallback: match merchant display name against Rewards CC co-brand category index
       (covers Google/OSM hits and any co-brand merchant in category_list)
    """
    mid = (merchant_id or "").strip()
    if mid and not mid.startswith(("osm:", "gmaps:", "web:")):
        from_catalog = co_brand_bonus_categories_for_merchant(mid, catalog=catalog)
        if from_catalog:
            return from_catalog

    name = (merchant_name or "").strip()
    if name:
        return resolve_co_brand_category_names(name)
    return []


def purchase_bonus_categories(
    primary_category: str,
    merchant_id: str | None = None,
    merchant_name: str | None = None,
) -> list[str]:
    """All spend categories to evaluate for a purchase (primary + co-brand)."""
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

    add(primary_category)
    for name in co_brand_bonus_categories_for_purchase(
        merchant_id=merchant_id,
        merchant_name=merchant_name,
    ):
        add(name)
    return ordered
