"""Merchant co-brand bonus categories for recommend (e.g. Starbucks → Starbucks earn bucket)."""

from __future__ import annotations

from typing import Any

from credit_rewards.co_brand_category_index import resolve_co_brand_category_names
from credit_rewards.merchant_mapping import load_merchant_catalog


def clean_merchant_display_name(name: str) -> str:
    """Strip address suffix from Google/OSM labels (Costco · 123 Main → Costco)."""
    return name.split("·", 1)[0].strip()


def catalog_merchant_id_for_display_name(
    display_name: str,
    *,
    catalog: list[dict[str, Any]] | None = None,
) -> str | None:
    """
    Map a POI display name to a catalog merchant id when the brand is known.

    Enables co-brand earn for Google/OSM hits (gmaps:ChIJ… → costco) without
    maintaining every store location in YAML.
    """
    from credit_rewards.merchant_mapping import _normalize_name

    clean = clean_merchant_display_name(display_name)
    if not clean:
        return None
    norm = _normalize_name(clean)
    if not norm:
        return None

    best_id: str | None = None
    best_score = -1
    for row in catalog or load_merchant_catalog():
        merchant_id = str(row.get("id") or "")
        if not merchant_id:
            continue
        candidates = [str(row["name"]), *(str(a) for a in (row.get("aliases") or []))]
        for candidate in candidates:
            cnorm = _normalize_name(candidate)
            if not cnorm:
                continue
            if norm == cnorm:
                return merchant_id
            score = 0
            if len(norm) >= 4 and len(cnorm) >= 4:
                if norm in cnorm:
                    score = len(norm)
                elif cnorm in norm:
                    score = len(cnorm)
            if score > best_score:
                best_score = score
                best_id = merchant_id
    return best_id if best_score >= 4 else None


def canonical_merchant_id_for_purchase(
    *,
    merchant_id: str | None = None,
    merchant_name: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
) -> str | None:
    """Prefer catalog merchant id for co-brand + redemption when POI id is external."""
    mid = (merchant_id or "").strip()
    if mid and not mid.startswith(("osm:", "gmaps:", "web:")):
        return mid
    name = clean_merchant_display_name(merchant_name or "")
    if not name:
        return mid or None
    return catalog_merchant_id_for_display_name(name, catalog=catalog) or mid or None


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
            aliases=[str(a) for a in (row.get("aliases") or [])],
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
    2. Google/OSM/web POI → map display name to catalog merchant when possible
    3. Fallback: match merchant display name against Rewards CC co-brand category index
    """
    cat = catalog or load_merchant_catalog()
    canon = canonical_merchant_id_for_purchase(
        merchant_id=merchant_id,
        merchant_name=merchant_name,
        catalog=cat,
    )
    if canon and not str(canon).startswith(("osm:", "gmaps:", "web:")):
        from_catalog = co_brand_bonus_categories_for_merchant(canon, catalog=cat)
        if from_catalog:
            return from_catalog

    name = clean_merchant_display_name(merchant_name or "")
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
