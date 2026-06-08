"""Free POI lookup via OpenStreetMap Nominatim — maps unknown store names to categories."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import yaml

from credit_rewards.paths import data_dir

OSM_MAP_PATH = data_dir() / "merchants" / "osm_category_map.yaml"
NOMINATIM_URL = os.getenv(
    "CREDITREWARDS_NOMINATIM_URL",
    "https://nominatim.openstreetmap.org/search",
)
NOMINATIM_ENABLED = os.getenv("CREDITREWARDS_NOMINATIM", "1").lower() not in {
    "0",
    "false",
    "no",
}
USER_AGENT = os.getenv(
    "CREDITREWARDS_USER_AGENT",
    "PayCue/0.1 (payment-moment category lookup; contact: dev@localhost)",
)
_LAST_CALL = 0.0
_MIN_INTERVAL_S = 1.1  # Nominatim usage policy: max 1 req/s


@dataclass(frozen=True)
class NominatimMatch:
    place_id: str
    display_name: str
    spend_bonus_category_name: str
    osm_class: str
    osm_type: str
    match_type: str
    confidence: str
    score: int

    @property
    def merchant_id(self) -> str:
        return f"osm:{self.place_id}"

    def to_merchant_dict(self, *, input_kind: str, matched_on: str) -> dict[str, Any]:
        return {
            "merchantId": self.merchant_id,
            "merchantName": self.display_name.split(",")[0].strip(),
            "spendBonusCategoryName": self.spend_bonus_category_name,
            "matchType": self.match_type,
            "matchedOn": matched_on,
            "inputKind": input_kind,
            "confidence": self.confidence,
            "score": self.score,
            "source": "nominatim",
        }


def load_osm_category_map(path: Path | None = None) -> dict[str, Any]:
    target = path or OSM_MAP_PATH
    return yaml.safe_load(target.read_text()) or {}


def _category_from_osm_tags(
    *,
    osm_class: str,
    osm_type: str,
    extratags: dict[str, str],
    display_name: str,
    mapping: dict[str, Any],
) -> tuple[str, str]:
    for rule in mapping.get("rules") or []:
        if str(rule.get("class", "")) == osm_class and str(rule.get("type", "")) == osm_type:
            return str(rule["category"]), "osm_class_type"

    for key, category in (mapping.get("extratags") or {}).items():
        if ":" not in key:
            continue
        prefix, value = key.split(":", 1)
        if extratags.get(prefix) == value:
            return str(category), "osm_extratag"

    name_lower = display_name.lower()
    for hint in mapping.get("name_hints") or []:
        pattern = hint.get("pattern", "")
        if pattern and re.search(pattern, name_lower):
            return str(hint["category"]), "osm_name_hint"

    return str(mapping.get("default_category") or "All Purchases"), "osm_default"


def _throttle() -> None:
    global _LAST_CALL
    now = time.monotonic()
    wait = _MIN_INTERVAL_S - (now - _LAST_CALL)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL = time.monotonic()


def _nominatim_search(query: str, *, limit: int = 3) -> list[dict[str, Any]]:
    if not NOMINATIM_ENABLED:
        return []
    _throttle()
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "extratags": 1,
        "namedetails": 1,
        "countrycodes": "us",
        "limit": limit,
    }
    headers = {"User-Agent": USER_AGENT}
    try:
        response = httpx.get(NOMINATIM_URL, params=params, headers=headers, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []
    except httpx.HTTPError:
        return []


@lru_cache(maxsize=256)
def lookup_store_name_nominatim(query: str) -> NominatimMatch | None:
    """Resolve a store name outside our YAML catalog using OSM Nominatim (free)."""
    q = query.strip()
    if len(q) < 2:
        return None

    mapping = load_osm_category_map()
    rows = _nominatim_search(q, limit=5)
    if not rows:
        return None

    best: NominatimMatch | None = None
    q_lower = q.lower()
    for row in rows:
        display = str(row.get("display_name") or row.get("name") or q)
        name = str(row.get("name") or display.split(",")[0])
        if q_lower not in name.lower() and q_lower not in display.lower():
            # Allow partial only for longer queries
            if len(q) >= 5 and q_lower[:5] not in name.lower():
                continue

        osm_class = str(row.get("class") or row.get("category") or "")
        osm_type = str(row.get("type") or "")
        extratags = {str(k): str(v) for k, v in (row.get("extratags") or {}).items()}
        category, match_type = _category_from_osm_tags(
            osm_class=osm_class,
            osm_type=osm_type,
            extratags=extratags,
            display_name=display,
            mapping=mapping,
        )
        importance = float(row.get("importance") or 0)
        score = 55 - int(importance * 20)
        candidate = NominatimMatch(
            place_id=str(row.get("place_id") or row.get("osm_id") or name),
            display_name=display,
            spend_bonus_category_name=category,
            osm_class=osm_class,
            osm_type=osm_type,
            match_type=match_type,
            confidence="medium" if match_type != "osm_default" else "low",
            score=score,
        )
        if best is None or candidate.score < best.score:
            best = candidate
    return best


def lookup_domain_brand_nominatim(domain: str) -> NominatimMatch | None:
    """When URL host is unknown in catalog, search Nominatim using brand label from domain."""
    from credit_rewards.merchant_url_parse import expand_domain_brand_queries, registrable_label

    label = registrable_label(domain)
    if len(label) < 3:
        return None
    for query in expand_domain_brand_queries(label):
        match = lookup_store_name_nominatim(query)
        if match:
            return NominatimMatch(
                place_id=match.place_id,
                display_name=match.display_name,
                spend_bonus_category_name=match.spend_bonus_category_name,
                osm_class=match.osm_class,
                osm_type=match.osm_type,
                match_type="nominatim_domain_brand",
                confidence=match.confidence,
                score=match.score + 5,
            )
    return None
