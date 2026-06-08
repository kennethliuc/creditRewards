"""Merchant lookup via Google Maps Places API (New) — text + optional user location."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import yaml

from credit_rewards.paths import data_dir

GOOGLE_MAP_PATH = data_dir() / "merchants" / "google_place_category_map.yaml"
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
DEFAULT_RADIUS_M = float(os.getenv("CREDITREWARDS_GOOGLE_PLACES_RADIUS_M", "8000"))
NEARBY_RADIUS_M = float(os.getenv("CREDITREWARDS_NEARBY_RADIUS_M", "600"))
NEARBY_STORE_TYPES = (
    "supermarket",
    "grocery_store",
    "department_store",
    "shopping_mall",
    "restaurant",
    "cafe",
    "coffee_shop",
    "fast_food_restaurant",
    "pharmacy",
    "convenience_store",
    "clothing_store",
    "electronics_store",
    "home_goods_store",
    "hardware_store",
    "gas_station",
)


def _api_key() -> str:
    return os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("CREDITREWARDS_GOOGLE_MAPS_API_KEY", "")


def google_places_enabled() -> bool:
    return (
        bool(_api_key())
        and os.getenv("CREDITREWARDS_GOOGLE_PLACES", "1").lower() not in {"0", "false", "no"}
    )


@dataclass(frozen=True)
class GooglePlaceMatch:
    place_id: str
    display_name: str
    formatted_address: str
    spend_bonus_category_name: str
    primary_type: str
    types: tuple[str, ...]
    match_type: str
    confidence: str
    score: int
    website_uri: str = ""

    @property
    def merchant_id(self) -> str:
        raw = self.place_id.removeprefix("places/")
        return f"gmaps:{raw}"


def load_google_category_map(path: Path | None = None) -> dict[str, Any]:
    target = path or GOOGLE_MAP_PATH
    return yaml.safe_load(target.read_text()) or {}


def _category_from_place(
    *,
    primary_type: str,
    types: list[str],
    display_name: str,
    mapping: dict[str, Any],
) -> tuple[str, str]:
    primary_map = mapping.get("primary_types") or {}
    if primary_type and primary_type in primary_map:
        return str(primary_map[primary_type]), "google_primary_type"

    type_map = mapping.get("types") or {}
    for t in types:
        if t in type_map:
            return str(type_map[t]), "google_type"

    name_lower = display_name.lower()
    for hint in mapping.get("name_hints") or []:
        pattern = hint.get("pattern", "")
        if pattern and re.search(pattern, name_lower):
            return str(hint["category"]), "google_name_hint"

    return str(mapping.get("default_category") or "All Purchases"), "google_default"


def _website_matches_brand(website_uri: str, *, domain: str, brand_slug: str) -> bool:
    website = website_uri.lower()
    if not website:
        return False
    domain = domain.lower()
    brand_slug = brand_slug.lower()
    return domain in website or brand_slug in website


def _places_search(
    text_query: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_m: float = DEFAULT_RADIUS_M,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    if not google_places_enabled():
        return []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _api_key(),
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.types,places.primaryType,places.location,places.websiteUri"
        ),
    }
    body: dict[str, Any] = {
        "textQuery": text_query.strip(),
        "maxResultCount": max_results,
        "languageCode": "en",
    }
    if latitude is not None and longitude is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": radius_m,
            }
        }
    try:
        response = httpx.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=12.0)
        response.raise_for_status()
        payload = response.json()
        return list(payload.get("places") or [])
    except httpx.HTTPError:
        return []


def _row_to_match(
    row: dict[str, Any],
    *,
    rank: int,
    parsed_brand: Any | None = None,
) -> GooglePlaceMatch | None:
    place_id = str(row.get("id") or "")
    if not place_id:
        return None
    display = row.get("displayName") or {}
    name = str(display.get("text") or display or "Unknown")
    address = str(row.get("formattedAddress") or "")
    website_uri = str(row.get("websiteUri") or "")
    primary_type = str(row.get("primaryType") or "")
    types = tuple(str(t) for t in (row.get("types") or []))
    mapping = load_google_category_map()
    category, match_type = _category_from_place(
        primary_type=primary_type,
        types=list(types),
        display_name=name,
        mapping=mapping,
    )
    score = 12 + rank * 8
    confidence = "high" if rank == 0 and match_type != "google_default" else "medium"
    if match_type == "google_default":
        score += 15
        confidence = "low"

    if parsed_brand is not None:
        if _website_matches_brand(
            website_uri,
            domain=parsed_brand.domain,
            brand_slug=parsed_brand.brand_slug,
        ):
            score -= 30
            match_type = "google_website_domain"
            confidence = "high"
        elif parsed_brand.display_name.lower() in name.lower():
            score -= 12
            match_type = "google_name_match"
            if confidence == "low":
                confidence = "medium"

    return GooglePlaceMatch(
        place_id=place_id,
        display_name=name,
        formatted_address=address,
        spend_bonus_category_name=category,
        primary_type=primary_type,
        types=types,
        match_type=match_type,
        confidence=confidence,
        score=score,
        website_uri=website_uri,
    )


@lru_cache(maxsize=256)
def lookup_places_with_location(
    text_query: str,
    latitude: float,
    longitude: float,
) -> tuple[GooglePlaceMatch, ...]:
    q = text_query.strip()
    if len(q) < 2:
        return ()
    rows = _places_search(q, latitude=latitude, longitude=longitude)
    matches: list[GooglePlaceMatch] = []
    for rank, row in enumerate(rows):
        match = _row_to_match(row, rank=rank)
        if match:
            matches.append(match)
    return tuple(matches)


@lru_cache(maxsize=256)
def lookup_places_text_only(text_query: str) -> tuple[GooglePlaceMatch, ...]:
    q = text_query.strip()
    if len(q) < 2:
        return ()
    rows = _places_search(q)
    matches: list[GooglePlaceMatch] = []
    for rank, row in enumerate(rows):
        match = _row_to_match(row, rank=rank)
        if match:
            matches.append(match)
    return tuple(matches)


def lookup_places_with_location_queries(
    text_queries: list[str],
    latitude: float,
    longitude: float,
) -> tuple[GooglePlaceMatch, ...]:
    for query in text_queries:
        matches = lookup_places_with_location(query, latitude, longitude)
        if matches:
            return matches
    return ()


def lookup_places_text_queries(text_queries: list[str]) -> tuple[GooglePlaceMatch, ...]:
    """Text search without GPS — same Places API as Google Maps name search."""
    for query in text_queries:
        matches = lookup_places_text_only(query)
        if matches:
            return matches
    return ()


def lookup_places_for_parsed_brand(
    parsed_brand: Any,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
) -> tuple[GooglePlaceMatch, ...]:
    """Map a parsed website brand to Google Maps place candidates."""
    from credit_rewards.merchant_url_parse import google_maps_search_queries

    queries = google_maps_search_queries(parsed_brand)
    collected: list[GooglePlaceMatch] = []
    seen_ids: set[str] = set()

    for query in queries:
        if latitude is not None and longitude is not None:
            rows = _places_search(query, latitude=latitude, longitude=longitude)
        else:
            rows = _places_search(query)
        for rank, row in enumerate(rows):
            match = _row_to_match(row, rank=rank, parsed_brand=parsed_brand)
            if not match:
                continue
            pid = match.place_id
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            collected.append(match)
        if collected:
            break

    collected.sort(key=lambda m: (m.score, m.display_name))
    return tuple(collected[:8])


def infer_text_query_from_url(url: str) -> str:
    from credit_rewards.merchant_url_parse import infer_text_queries_from_url

    queries = infer_text_queries_from_url(url)
    return queries[0] if queries else ""


def infer_text_queries_from_url(url: str) -> list[str]:
    from credit_rewards.merchant_url_parse import infer_text_queries_from_url as _infer

    return _infer(url)


def google_match_to_category_match(gm: GooglePlaceMatch, *, input_kind: str, matched_on: str):
    from credit_rewards.merchant_mapping import MerchantCategoryMatch

    address_line = f" · {gm.formatted_address}" if gm.formatted_address else ""
    return MerchantCategoryMatch(
        merchant_id=gm.merchant_id,
        merchant_name=f"{gm.display_name}{address_line}",
        spend_bonus_category_name=gm.spend_bonus_category_name,
        match_type=gm.match_type,
        matched_on=matched_on,
        input_kind=input_kind,
        confidence=gm.confidence,
        score=gm.score,
        source="google_places",
    )


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371000.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _place_location(row: dict[str, Any]) -> tuple[float, float] | None:
    loc = row.get("location") or {}
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)


def _places_search_nearby(
    latitude: float,
    longitude: float,
    *,
    radius_m: float = NEARBY_RADIUS_M,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    if not google_places_enabled():
        return []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _api_key(),
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.types,places.primaryType,places.location,places.websiteUri"
        ),
    }
    body: dict[str, Any] = {
        "includedTypes": list(NEARBY_STORE_TYPES),
        "maxResultCount": max(max_results, 5),
        "rankPreference": "DISTANCE",
        "languageCode": "en",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": radius_m,
            }
        },
    }
    try:
        response = httpx.post(PLACES_NEARBY_URL, headers=headers, json=body, timeout=12.0)
        response.raise_for_status()
        payload = response.json()
        return list(payload.get("places") or [])
    except httpx.HTTPError:
        return []


def _nearby_place_dict(
    match: GooglePlaceMatch,
    *,
    distance_m: float | None,
) -> dict[str, Any]:
    short_address = match.formatted_address.split(",", 1)[0] if match.formatted_address else ""
    return {
        "merchantId": match.merchant_id,
        "merchantName": match.display_name,
        "displayName": match.display_name,
        "shortAddress": short_address,
        "formattedAddress": match.formatted_address,
        "spendBonusCategoryName": match.spend_bonus_category_name,
        "confidence": match.confidence,
        "distanceMeters": round(distance_m) if distance_m is not None else None,
        "source": "google_places",
    }


def lookup_nearby_stores(
    latitude: float,
    longitude: float,
    *,
    limit: int = 5,
    radius_m: float | None = None,
) -> list[dict[str, Any]]:
    """Return nearby retail/food POIs for in-store quick pick (sorted by distance)."""
    radius = radius_m if radius_m is not None else NEARBY_RADIUS_M
    rows = _places_search_nearby(latitude, longitude, radius_m=radius, max_results=max(limit, 5))
    ranked: list[tuple[float, GooglePlaceMatch]] = []
    seen: set[str] = set()
    for rank, row in enumerate(rows):
        match = _row_to_match(row, rank=rank)
        if not match or match.place_id in seen:
            continue
        seen.add(match.place_id)
        loc = _place_location(row)
        distance = _haversine_m(latitude, longitude, loc[0], loc[1]) if loc else float(rank)
        ranked.append((distance, match))
    ranked.sort(key=lambda item: item[0])
    out: list[dict[str, Any]] = []
    for distance, match in ranked[:limit]:
        out.append(_nearby_place_dict(match, distance_m=distance))
    return out
