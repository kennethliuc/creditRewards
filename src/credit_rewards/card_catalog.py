"""Card catalog index (issuer search, images) for wallet onboarding."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.merchant_fuzzy import fuzzy_name_score
from credit_rewards.paths import data_dir

CATALOG_INDEX_PATH = data_dir() / "card_catalog_index.json"
ISSUER_ALIASES_PATH = data_dir() / "card_issuer_aliases.yaml"
MARKET_SHARE_PATH = data_dir() / "card_issuer_market_share.yaml"

# Common US issuers for index build + fuzzy hints.
DEFAULT_ISSUER_QUERIES = [
    "Chase",
    "American Express",
    "Amex",
    "Citi",
    "Capital One",
    "Discover",
    "Wells Fargo",
    "Bank of America",
    "US Bank",
    "Barclays",
    "Synchrony",
    "Goldman Sachs",
    "Apple Card",
    "Bilt",
]


def _normalize(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^\w\s']", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


@lru_cache(maxsize=1)
def load_issuer_aliases() -> dict[str, list[str]]:
    if not ISSUER_ALIASES_PATH.exists():
        return {}
    data = yaml.safe_load(ISSUER_ALIASES_PATH.read_text()) or {}
    return {str(k): [str(a) for a in (v or [])] for k, v in (data.get("aliases") or {}).items()}


def clear_catalog_cache() -> None:
    load_catalog_index.cache_clear()
    load_catalog_index_all.cache_clear()
    _top_tier_issuer_names_in_data.cache_clear()
    load_issuer_aliases.cache_clear()
    load_market_share_issuers.cache_clear()


@lru_cache(maxsize=1)
def load_catalog_index_all() -> list[dict[str, Any]]:
    """Full Rewards CC catalog snapshot (all issuers)."""
    if CATALOG_INDEX_PATH.exists():
        payload = json.loads(CATALOG_INDEX_PATH.read_text())
        return list(payload.get("cards") or [])

    cards: list[dict[str, Any]] = []
    for entry in load_card_registry():
        cards.append(
            {
                "card_key": entry["card_key"],
                "rewards_cc_card_key": entry.get("rewards_cc_card_key") or entry["card_key"],
                "card_name": _registry_card_name(entry["card_key"]),
                "issuer": entry.get("issuer") or "",
                "in_registry": True,
            }
        )
    return cards


@lru_cache(maxsize=1)
def load_market_share_issuers() -> list[dict[str, Any]]:
    if not MARKET_SHARE_PATH.exists():
        return []
    data = yaml.safe_load(MARKET_SHARE_PATH.read_text()) or {}
    return list(data.get("issuers") or [])


@lru_cache(maxsize=1)
def load_catalog_index() -> list[dict[str, Any]]:
    """Top-tier issuers only — used for issuer search and autocomplete."""
    return [row for row in load_catalog_index_all() if is_top_tier_issuer(str(row.get("issuer") or ""))]


def _registry_card_name(card_key: str) -> str:
    return card_key.replace("-", " ").title()


def registry_by_key() -> dict[str, dict[str, Any]]:
    return {entry["card_key"]: entry for entry in load_card_registry()}


def catalog_card_keys() -> set[str]:
    keys: set[str] = set()
    for row in load_catalog_index():
        keys.add(str(row["card_key"]))
        rc = row.get("rewards_cc_card_key")
        if rc:
            keys.add(str(rc))
    for entry in load_card_registry():
        keys.add(str(entry["card_key"]))
        rc = entry.get("rewards_cc_card_key")
        if rc:
            keys.add(str(rc))
    return keys


def resolve_wallet_card_key(card_key: str) -> dict[str, Any]:
    """Map wallet card_key to catalog/registry row."""
    key = card_key.strip()
    reg = registry_by_key()
    if key in reg:
        entry = reg[key]
        return {
            "card_key": key,
            "rewards_cc_card_key": entry.get("rewards_cc_card_key") or key,
            "card_name": _registry_card_name(key),
            "issuer": entry.get("issuer") or "",
            "image_url": entry.get("image_url") or _image_for_key(key),
            "in_registry": True,
        }
    for row in load_catalog_index_all():
        if str(row.get("card_key")) == key or str(row.get("rewards_cc_card_key")) == key:
            return {
                "card_key": str(row.get("card_key") or key),
                "rewards_cc_card_key": str(row.get("rewards_cc_card_key") or key),
                "card_name": str(row.get("card_name") or key),
                "issuer": str(row.get("issuer") or ""),
                "image_url": str(row.get("image_url") or ""),
                "in_registry": bool(row.get("in_registry")),
            }
    return {
        "card_key": key,
        "rewards_cc_card_key": key,
        "card_name": _registry_card_name(key),
        "issuer": "",
        "image_url": "",
        "in_registry": False,
    }


def _image_for_key(card_key: str) -> str:
    for row in load_catalog_index_all():
        if str(row.get("card_key")) == card_key:
            return str(row.get("image_url") or "")
    return ""


def _expand_query_issuers(query: str) -> set[str]:
    q = _normalize(query)
    if not q:
        return set()
    hits = {q}
    for canonical, alias_list in load_issuer_aliases().items():
        canon_norm = _normalize(canonical)
        alias_norms = {_normalize(a) for a in alias_list}
        if q == canon_norm or q in alias_norms:
            hits.add(canon_norm)
            hits.update(alias_norms)
            continue
        if fuzzy_name_score(q, canon_norm) >= 0.72:
            hits.add(canon_norm)
    return hits


def _expand_card_issuer(issuer: str) -> set[str]:
    target = _normalize(issuer)
    if not target:
        return set()
    hits = {target}
    for canonical, alias_list in load_issuer_aliases().items():
        canon_norm = _normalize(canonical)
        alias_norms = {_normalize(a) for a in alias_list}
        if target == canon_norm or target in alias_norms:
            hits.add(canon_norm)
            hits.update(alias_norms)
    return hits


def _issuer_score(query: str, issuer: str) -> float:
    query_issuers = _expand_query_issuers(query)
    card_issuers = _expand_card_issuer(issuer)
    if not query_issuers or not card_issuers:
        return 0.0
    if query_issuers & card_issuers:
        return 1.0
    best = 0.0
    for q in query_issuers:
        for target in card_issuers:
            if q in target or target in q:
                best = max(best, 0.92)
            best = max(best, fuzzy_name_score(q, target))
    return best


def _issuer_in_catalog(catalog_issuers: set[str], target_name: str, aliases: list[str]) -> bool:
    labels = {_normalize(target_name), *(_normalize(a) for a in aliases)}
    for issuer in catalog_issuers:
        expanded = _expand_card_issuer(issuer)
        if labels & expanded:
            return True
        for label in labels:
            if _issuer_score(label, issuer) >= 0.88:
                return True
    return False


@lru_cache(maxsize=1)
def _top_tier_issuer_names_in_data() -> set[str]:
    """Issuer strings in catalog data that belong to a supported top-tier bank."""
    labels: set[str] = set()
    all_issuers = {str(r.get("issuer") or "").strip() for r in load_catalog_index_all() if r.get("issuer")}
    for row in load_market_share_issuers():
        canonical = str(row.get("name") or "")
        aliases = [str(a) for a in (row.get("aliases") or [])]
        for issuer in all_issuers:
            if _issuer_in_catalog({issuer}, canonical, aliases):
                labels.add(issuer)
    return labels


def is_top_tier_issuer(issuer: str) -> bool:
    """Whether issuer is one of the ~30 US issuers we support in the picker."""
    name = str(issuer or "").strip()
    if not name:
        return False
    return name in _top_tier_issuer_names_in_data()


def catalog_coverage_stats() -> dict[str, Any]:
    """Estimate market coverage for supported top-tier issuers."""
    catalog_issuers = {
        str(r.get("issuer") or "").strip()
        for r in load_catalog_index()
        if r.get("issuer")
    }
    rows = load_market_share_issuers()
    covered = 0.0
    total = 0.0
    missing: list[str] = []
    matched: list[str] = []
    for row in rows:
        share = float(row.get("share_pct") or 0)
        total += share
        name = str(row.get("name") or "")
        aliases = [str(a) for a in (row.get("aliases") or [])]
        if _issuer_in_catalog(catalog_issuers, name, aliases):
            covered += share
            matched.append(name)
        else:
            missing.append(name)
    return {
        "cardCount": len(load_catalog_index()),
        "issuerCount": len(list_issuers()),
        "supportedIssuerCount": len(rows),
        "marketShareTargetPct": round(total, 1),
        "marketShareCoveredPct": round(covered, 1),
        "topIssuersMatched": matched,
        "topIssuersMissing": missing,
    }


def list_issuers(*, limit: int = 30) -> list[str]:
    """Top-tier issuer names that have at least one card in the catalog."""
    catalog_issuers = {
        str(r.get("issuer") or "").strip()
        for r in load_catalog_index()
        if r.get("issuer")
    }
    names: list[str] = []
    for row in load_market_share_issuers():
        name = str(row["name"])
        aliases = [str(a) for a in (row.get("aliases") or [])]
        if _issuer_in_catalog(catalog_issuers, name, aliases):
            names.append(name)
    names.sort(key=str.casefold)
    return names[:limit]


def search_cards_by_issuer(
    issuer_query: str,
    *,
    limit: int = 48,
    min_score: float = 0.72,
) -> list[dict[str, Any]]:
    query = issuer_query.strip()
    if len(_normalize(query)) < 2:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in load_catalog_index():
        card_key = str(row.get("card_key") or "")
        if not card_key or card_key in seen:
            continue
        issuer = str(row.get("issuer") or "")
        ratio = _issuer_score(query, issuer)
        if ratio < min_score:
            continue
        seen.add(card_key)
        scored.append(
            (
                ratio,
                {
                    "card_key": card_key,
                    "rewards_cc_card_key": str(row.get("rewards_cc_card_key") or card_key),
                    "card_name": str(row.get("card_name") or card_key),
                    "issuer": issuer,
                    "image_url": str(row.get("image_url") or ""),
                    "in_registry": bool(row.get("in_registry")),
                },
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]["card_name"]))
    return [row for _, row in scored[:limit]]


def enrich_registry_cards() -> list[dict[str, Any]]:
    """Registry cards with image URLs for /api/cards."""
    index_by_key = {str(r["card_key"]): r for r in load_catalog_index()}
    cards: list[dict[str, Any]] = []
    for entry in load_card_registry():
        key = str(entry["card_key"])
        idx = index_by_key.get(key, {})
        cards.append(
            {
                "card_key": key,
                "rewards_cc_card_key": entry.get("rewards_cc_card_key") or key,
                "card_name": _registry_card_name(key),
                "issuer": entry.get("issuer") or "",
                "reward_program": entry.get("reward_program") or "",
                "image_url": entry.get("image_url") or idx.get("image_url") or "",
                "in_registry": True,
            }
        )
    return cards
