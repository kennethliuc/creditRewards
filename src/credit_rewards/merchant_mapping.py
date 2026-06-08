from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml

from credit_rewards.merchant_fuzzy import (
    FUZZY_HIGH_RATIO,
    FUZZY_MIN_RATIO,
    fuzzy_name_score,
)
from credit_rewards.merchant_nominatim import (
    NOMINATIM_ENABLED,
    lookup_domain_brand_nominatim,
    lookup_store_name_nominatim,
)
from credit_rewards.merchant_google_places import (
    google_match_to_category_match,
    google_places_enabled,
    lookup_places_for_parsed_brand,
    lookup_places_for_store_name,
)
from credit_rewards.merchant_url_parse import (
    ParsedStoreBrand,
    extract_domains_from_text,
    extract_embedded_urls,
    infer_text_queries_from_url,
    is_payment_gateway_host,
    parse_store_brand_from_url,
    primary_host,
    registrable_label,
    url_haystack,
)

from credit_rewards.paths import data_dir

MERCHANT_DATA_PATH = data_dir() / "merchants" / "merchant_categories.yaml"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

PURCHASE_ONLINE = "online"
PURCHASE_IN_STORE = "in_store"

_DINING_NAME_HINTS = (
    "hotpot",
    "hot pot",
    "bbq",
    "barbecue",
    "grill",
    "kitchen",
    "sushi",
    "ramen",
    "pizza",
    "cafe",
    "coffee",
    "bistro",
    "steakhouse",
    "steak house",
    "diner",
    "taqueria",
    "bakery",
    "seafood",
    "noodle",
    "wok",
    "dim sum",
    "restaurant",
)


class MerchantNotFoundError(ValueError):
    """Raised when URL or store name cannot be mapped to a spend category."""


@dataclass(frozen=True)
class MerchantCategoryMatch:
    merchant_id: str
    merchant_name: str
    spend_bonus_category_name: str
    match_type: str
    matched_on: str
    input_kind: str  # url | name | confirmed
    confidence: str = CONFIDENCE_HIGH
    score: int = 0
    source: str = "catalog"

    def to_dict(self) -> dict[str, Any]:
        return {
            "merchantId": self.merchant_id,
            "merchantName": self.merchant_name,
            "spendBonusCategoryName": self.spend_bonus_category_name,
            "matchType": self.match_type,
            "matchedOn": self.matched_on,
            "inputKind": self.input_kind,
            "confidence": self.confidence,
            "score": self.score,
            "source": self.source,
        }


@dataclass(frozen=True)
class MerchantResolveResult:
    best: MerchantCategoryMatch | None
    candidates: list[MerchantCategoryMatch]
    needs_confirmation: bool
    parsed_host: str = ""
    input_url: str = ""
    parsed_store_name: str = ""
    parsed_store_domain: str = ""
    purchase_channel: str = PURCHASE_ONLINE

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.best is not None,
            "best": self.best.to_dict() if self.best else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "needsConfirmation": self.needs_confirmation,
            "parsedHost": self.parsed_host,
            "inputUrl": self.input_url,
            "parsedStoreName": self.parsed_store_name,
            "parsedStoreDomain": self.parsed_store_domain,
            "purchaseChannel": self.purchase_channel,
        }


def load_merchant_catalog(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or MERCHANT_DATA_PATH
    data = yaml.safe_load(target.read_text()) or {}
    return list(data.get("merchants") or [])


def channel_categories_for_row(row: dict[str, Any]) -> dict[str, str]:
    """Online vs in-store spend categories for a catalog merchant."""
    base = str(row["spend_bonus_category_name"])
    online = str(row.get("online_category") or base)
    in_store = str(row.get("in_store_category") or base)
    return {
        "online": online,
        "in_store": in_store,
        "default": base,
    }


def lookup_merchant_by_id(
    merchant_id: str,
    *,
    catalog: list[dict[str, Any]] | None = None,
    purchase_channel: str | None = None,
) -> MerchantCategoryMatch:
    if merchant_id.startswith("osm:") or merchant_id.startswith("gmaps:"):
        raise MerchantNotFoundError(
            f"External merchant {merchant_id!r} — pass confirmed category on recommend"
        )
    if merchant_id.startswith("web:"):
        raise MerchantNotFoundError(
            f"Web merchant {merchant_id!r} — pass confirmed category on recommend"
        )
    merchants = catalog or load_merchant_catalog()
    channel = purchase_channel or PURCHASE_ONLINE
    for row in merchants:
        if str(row["id"]) == merchant_id:
            category = _spend_category_for_row(row, channel)
            return MerchantCategoryMatch(
                merchant_id=str(row["id"]),
                merchant_name=str(row["name"]),
                spend_bonus_category_name=category,
                match_type="confirmed",
                matched_on=str(row["id"]),
                input_kind="confirmed",
                confidence=CONFIDENCE_HIGH,
                score=0,
                source="catalog",
            )
    raise MerchantNotFoundError(f"Unknown merchant_id: {merchant_id!r}")


def _catalog_match_from_row(
    row: dict[str, Any],
    *,
    purchase_channel: str,
    match_type: str,
    matched_on: str,
    input_kind: str,
    score: int,
    confidence: str | None = None,
) -> MerchantCategoryMatch:
    return MerchantCategoryMatch(
        merchant_id=str(row["id"]),
        merchant_name=str(row["name"]),
        spend_bonus_category_name=_spend_category_for_row(row, purchase_channel),
        match_type=match_type,
        matched_on=matched_on,
        input_kind=input_kind,
        confidence=confidence or _confidence_from_score(score),
        score=score,
        source="catalog",
    )


def _normalize_name(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^\w\s']", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def expand_store_name_queries(name: str) -> list[str]:
    """Generate spelling variants for in-store name search (chick a fila → chick fil a)."""
    queries: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        q = re.sub(r"\s+", " ", raw.strip())
        key = _normalize_name(q)
        if len(key) >= 3 and key not in seen:
            seen.add(key)
            queries.append(q)

    add(name)
    normalized = _normalize_name(name)
    add(normalized)
    if " a " in f" {normalized} ":
        add(re.sub(r"\ba\b", "", normalized).strip())
        add(normalized.replace(" a ", " "))
    compact = re.sub(r"\s+", "", normalized)
    if len(compact) >= 4:
        add(compact)
    parts = normalized.split()
    if len(parts) >= 2:
        add("-".join(parts))
    return queries


def _fuzzy_catalog_matches(
    name: str,
    merchants: list[dict[str, Any]],
    *,
    purchase_channel: str,
    limit: int = 8,
) -> list[MerchantCategoryMatch]:
    """Edit-distance matches when exact/partial substring match fails."""
    search_queries = expand_store_name_queries(name)
    query_norms = [_normalize_name(q) for q in search_queries if len(_normalize_name(q)) >= 3]
    if not query_norms:
        return []

    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for row in merchants:
        labels = [str(row["name"]), *(str(a) for a in (row.get("aliases") or []))]
        best_ratio = 0.0
        best_label = ""
        for qn in query_norms:
            for label in labels:
                ln = _normalize_name(label)
                if len(ln) < 3:
                    continue
                ratio = fuzzy_name_score(qn, ln)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_label = label
        if best_ratio >= FUZZY_MIN_RATIO:
            ranked.append((best_ratio, best_label, row))

    ranked.sort(key=lambda item: (-item[0], str(item[2]["name"])))
    matches: list[MerchantCategoryMatch] = []
    for ratio, matched_on, row in ranked[:limit]:
        confidence = CONFIDENCE_HIGH if ratio >= FUZZY_HIGH_RATIO else CONFIDENCE_MEDIUM
        matches.append(
            _catalog_match_from_row(
                row,
                purchase_channel=purchase_channel,
                match_type="fuzzy_name",
                matched_on=matched_on,
                input_kind="name",
                score=int((1.0 - ratio) * 100),
                confidence=confidence,
            )
        )
    return matches


def extract_domain(url: str) -> str:
    return primary_host(url)


def _confidence_from_score(score: int) -> str:
    if score <= 10:
        return CONFIDENCE_HIGH
    if score <= 35:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _spend_category_for_row(row: dict[str, Any], purchase_channel: str) -> str:
    if purchase_channel == PURCHASE_ONLINE:
        return str(row.get("online_category") or row["spend_bonus_category_name"])
    if purchase_channel == PURCHASE_IN_STORE:
        return str(row.get("in_store_category") or row["spend_bonus_category_name"])
    return str(row["spend_bonus_category_name"])


def _infer_online_category(brand_name: str) -> str:
    from credit_rewards.merchant_google_places import load_google_category_map

    mapping = load_google_category_map()
    name_lower = brand_name.lower()
    for hint in mapping.get("name_hints") or []:
        pattern = str(hint.get("pattern") or "")
        if pattern and re.search(pattern, name_lower):
            return str(hint["category"])
    return "Online Shopping"


def _score_domain_in_url(host: str, haystack: str, domain: str) -> tuple[int, str] | None:
    domain = domain.lower().strip()
    if not domain:
        return None
    if host == domain:
        return 0, "domain_host_exact"
    if host.endswith(f".{domain}"):
        return 8, "domain_host_subdomain"
    boundary = rf"(?:^|[/.?=&@#_\-]){re.escape(domain)}(?:[/?#&.\s\-]|$)"
    if re.search(boundary, haystack):
        return 25, "domain_url_fuzzy"
    label = registrable_label(domain)
    compact = re.sub(r"[^\w]", "", haystack)
    compact_label = re.sub(r"[^\w]", "", label)
    if len(compact_label) >= 4 and compact_label in compact:
        return 32, "domain_brand_in_url"
    if domain in haystack:
        return 45, "domain_url_substring"
    return None


def _score_name_in_url(haystack: str, merchant_name: str, aliases: list[str]) -> tuple[int, str] | None:
    tokens = [_normalize_name(merchant_name), *(_normalize_name(a) for a in aliases)]
    compact_hay = re.sub(r"[^\w]", "", haystack)
    best: tuple[int, str] | None = None
    for token in tokens:
        if len(token) < 4:
            continue
        compact_token = re.sub(r"[^\w]", "", token)
        if compact_token and compact_token in compact_hay:
            candidate = (38, "name_url_fuzzy")
            if best is None or candidate[0] < best[0]:
                best = candidate
    return best


def _nominatim_to_match(nm, *, input_kind: str, matched_on: str) -> MerchantCategoryMatch:
    return MerchantCategoryMatch(
        merchant_id=nm.merchant_id,
        merchant_name=nm.display_name.split(",")[0].strip(),
        spend_bonus_category_name=nm.spend_bonus_category_name,
        match_type=nm.match_type,
        matched_on=matched_on,
        input_kind=input_kind,
        confidence=nm.confidence,
        score=nm.score,
        source="nominatim",
    )


def _score_catalog_for_context(
    host: str,
    haystack: str,
    merchants: list[dict[str, Any]],
    scored: dict[str, MerchantCategoryMatch],
    *,
    input_kind: str = "url",
    purchase_channel: str = PURCHASE_ONLINE,
) -> None:
    for row in merchants:
        merchant_id = str(row["id"])
        aliases = [str(a) for a in (row.get("aliases") or [])]

        best_for_row: tuple[int, str, str] | None = None
        for domain in row.get("domains") or []:
            hit = _score_domain_in_url(host, haystack, str(domain))
            if hit and (best_for_row is None or hit[0] < best_for_row[0]):
                best_for_row = (hit[0], hit[1], str(domain))

        name_hit = _score_name_in_url(haystack, str(row["name"]), aliases)
        if name_hit and (best_for_row is None or name_hit[0] < best_for_row[0]):
            best_for_row = (name_hit[0], name_hit[1], str(row["name"]))

        if best_for_row:
            score, match_type, matched_on = best_for_row
            existing = scored.get(merchant_id)
            if existing is None or score < existing.score:
                scored[merchant_id] = _catalog_match_from_row(
                    row,
                    purchase_channel=purchase_channel,
                    match_type=match_type,
                    matched_on=matched_on,
                    input_kind=input_kind,
                    score=score,
                )


def _nominatim_url_fallback(url: str, scored: dict[str, MerchantCategoryMatch]) -> None:
    if not NOMINATIM_ENABLED:
        return
    host, haystack = url_haystack(url)
    domains = extract_domains_from_text(haystack)
    if not domains and not is_payment_gateway_host(host):
        domains = [host]

    for domain in domains:
        if is_payment_gateway_host(domain):
            continue
        nm = lookup_domain_brand_nominatim(domain)
        if not nm:
            continue
        mid = nm.merchant_id
        match = _nominatim_to_match(nm, input_kind="url", matched_on=domain)
        if mid not in scored or match.score < scored[mid].score:
            scored[mid] = match


def _nominatim_parsed_brand_fallback(
    parsed: ParsedStoreBrand,
    scored: dict[str, MerchantCategoryMatch],
) -> None:
    if not NOMINATIM_ENABLED:
        return
    for query in parsed.search_queries:
        nm = lookup_store_name_nominatim(query)
        if not nm:
            continue
        mid = nm.merchant_id
        match = _nominatim_to_match(nm, input_kind="url", matched_on=parsed.display_name)
        if mid not in scored or match.score < scored[mid].score:
            scored[mid] = match
        break


def _merge_resolve_results(
    primary: MerchantResolveResult,
    secondary: MerchantResolveResult,
) -> MerchantResolveResult:
    if not secondary.best:
        return primary
    if not primary.best:
        return secondary
    merged = {m.merchant_id: m for m in primary.candidates}
    for match in secondary.candidates:
        if match.merchant_id not in merged or match.score < merged[match.merchant_id].score:
            merged[match.merchant_id] = match
    candidates = sorted(merged.values(), key=lambda m: (m.score, m.merchant_name))
    return MerchantResolveResult(
        best=candidates[0],
        candidates=candidates[:8],
        needs_confirmation=True,
        parsed_host=primary.parsed_host or secondary.parsed_host,
        input_url=primary.input_url or secondary.input_url,
        parsed_store_name=primary.parsed_store_name or secondary.parsed_store_name,
        parsed_store_domain=primary.parsed_store_domain or secondary.parsed_store_domain,
    )


def _url_resolve_context(
    result: MerchantResolveResult,
    *,
    parsed: ParsedStoreBrand | None,
    host: str,
    url: str,
    purchase_channel: str,
) -> MerchantResolveResult:
    return MerchantResolveResult(
        best=result.best,
        candidates=result.candidates,
        needs_confirmation=result.needs_confirmation,
        parsed_host=host,
        input_url=url.strip(),
        parsed_store_name=parsed.display_name if parsed else "",
        parsed_store_domain=parsed.domain if parsed else "",
        purchase_channel=purchase_channel,
    )


def _online_parsed_brand_match(parsed: ParsedStoreBrand) -> MerchantCategoryMatch:
    category = _infer_online_category(parsed.display_name)
    return MerchantCategoryMatch(
        merchant_id=f"web:{parsed.domain}",
        merchant_name=f"{parsed.display_name}（官网网购）",
        spend_bonus_category_name=category,
        match_type="url_online_brand",
        matched_on=parsed.domain,
        input_kind="url",
        confidence=CONFIDENCE_MEDIUM,
        score=18,
        source="url_parse",
    )


def _google_maps_resolve_parsed_brand(
    parsed: ParsedStoreBrand,
    *,
    latitude: float | None,
    longitude: float | None,
) -> MerchantResolveResult | None:
    """Use Google Maps to map a parsed website brand to a real store POI."""
    if not google_places_enabled():
        return None
    matches = lookup_places_for_parsed_brand(
        parsed,
        latitude=latitude,
        longitude=longitude,
    )
    if not matches:
        return None
    candidates = [
        google_match_to_category_match(m, input_kind="url", matched_on=parsed.display_name)
        for m in matches
    ]
    return MerchantResolveResult(
        best=candidates[0],
        candidates=candidates[:8],
        needs_confirmation=True,
    )


def _google_places_resolve(
    text_query: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    input_kind: str,
    matched_on: str,
    text_queries: list[str] | None = None,
) -> MerchantResolveResult | None:
    if not google_places_enabled():
        return None
    queries = text_queries or expand_store_name_queries(text_query)
    if not queries:
        return None
    matches = lookup_places_for_store_name(
        queries,
        query_for_ranking=text_query,
        latitude=latitude,
        longitude=longitude,
    )
    if not matches:
        return None
    candidates = [
        google_match_to_category_match(m, input_kind=input_kind, matched_on=matched_on)
        for m in matches
    ]
    return MerchantResolveResult(
        best=candidates[0],
        candidates=candidates[:8],
        needs_confirmation=True,
    )


def _merge_google_with_catalog(
    catalog_result: MerchantResolveResult,
    google_result: MerchantResolveResult | None,
) -> MerchantResolveResult:
    """Prefer Google when catalog miss or low-confidence fuzzy hit."""
    if not google_result:
        return catalog_result
    if not catalog_result.best:
        return MerchantResolveResult(
            best=google_result.best,
            candidates=google_result.candidates,
            needs_confirmation=google_result.needs_confirmation,
            parsed_host=catalog_result.parsed_host,
            input_url=catalog_result.input_url,
            parsed_store_name=catalog_result.parsed_store_name,
            parsed_store_domain=catalog_result.parsed_store_domain,
        )
    if catalog_result.best.score <= 15 and catalog_result.best.source == "catalog":
        # Strong catalog domain match — keep catalog
        merged = {m.merchant_id: m for m in catalog_result.candidates}
        for g in google_result.candidates:
            if g.merchant_id not in merged or g.score < merged[g.merchant_id].score:
                merged[g.merchant_id] = g
        candidates = sorted(merged.values(), key=lambda m: (m.score, m.merchant_name))
        return MerchantResolveResult(
            best=candidates[0],
            candidates=candidates[:8],
            needs_confirmation=True,
            parsed_host=catalog_result.parsed_host,
            input_url=catalog_result.input_url,
            parsed_store_name=catalog_result.parsed_store_name,
            parsed_store_domain=catalog_result.parsed_store_domain,
        )
    return MerchantResolveResult(
        best=google_result.best,
        candidates=google_result.candidates,
        needs_confirmation=google_result.needs_confirmation,
        parsed_host=catalog_result.parsed_host,
        input_url=catalog_result.input_url,
        parsed_store_name=catalog_result.parsed_store_name,
        parsed_store_domain=catalog_result.parsed_store_domain,
    )


def resolve_merchant_url(
    url: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    catalog: list[dict[str, Any]] | None = None,
    purchase_channel: str = PURCHASE_ONLINE,
) -> MerchantResolveResult:
    """Fuzzy-match merchant from a long checkout/payment URL."""
    merchants = catalog or load_merchant_catalog()
    parsed = parse_store_brand_from_url(url)
    host, haystack = url_haystack(url)
    scored: dict[str, MerchantCategoryMatch] = {}

    for candidate_url in extract_embedded_urls(url):
        c_host, c_hay = url_haystack(candidate_url)
        _score_catalog_for_context(
            c_host, c_hay, merchants, scored, purchase_channel=purchase_channel
        )

    _score_catalog_for_context(
        host, haystack, merchants, scored, purchase_channel=purchase_channel
    )

    for domain in extract_domains_from_text(haystack):
        _score_catalog_for_context(
            domain, haystack, merchants, scored, purchase_channel=purchase_channel
        )

    if purchase_channel == PURCHASE_IN_STORE:
        if not scored:
            _nominatim_url_fallback(url, scored)
        if not scored and parsed:
            _nominatim_parsed_brand_fallback(parsed, scored)

    candidates = sorted(scored.values(), key=lambda m: (m.score, m.merchant_name))
    best = candidates[0] if candidates else None
    catalog_result = MerchantResolveResult(
        best=best,
        candidates=candidates[:8],
        needs_confirmation=True,
        parsed_host=host,
        input_url=url.strip(),
        parsed_store_name=parsed.display_name if parsed else "",
        parsed_store_domain=parsed.domain if parsed else "",
        purchase_channel=purchase_channel,
    )

    if purchase_channel == PURCHASE_ONLINE and parsed and not catalog_result.best:
        online_match = _online_parsed_brand_match(parsed)
        catalog_result = MerchantResolveResult(
            best=online_match,
            candidates=[online_match],
            needs_confirmation=True,
            parsed_host=host,
            input_url=url.strip(),
            parsed_store_name=parsed.display_name,
            parsed_store_domain=parsed.domain,
            purchase_channel=purchase_channel,
        )
    elif parsed and (not catalog_result.best or catalog_result.best.score > 10):
        name_result = _match_by_name(
            parsed.display_name,
            merchants,
            latitude=None,
            longitude=None,
            purchase_channel=purchase_channel,
        )
        catalog_result = _merge_resolve_results(catalog_result, name_result)

    if purchase_channel == PURCHASE_IN_STORE and parsed and google_places_enabled():
        catalog_strong = (
            catalog_result.best is not None
            and catalog_result.best.source == "catalog"
            and catalog_result.best.score <= 10
        )
        use_google_maps = latitude is not None or not catalog_strong
        if use_google_maps:
            google_result = _google_maps_resolve_parsed_brand(
                parsed,
                latitude=latitude,
                longitude=longitude,
            )
            catalog_result = _merge_google_with_catalog(catalog_result, google_result)
    elif (
        purchase_channel == PURCHASE_IN_STORE
        and latitude is not None
        and longitude is not None
    ):
        queries = infer_text_queries_from_url(url)
        matched_on = queries[0] if queries else url[:120]
        google_result = _google_places_resolve(
            matched_on,
            latitude=latitude,
            longitude=longitude,
            input_kind="url",
            matched_on=matched_on,
            text_queries=queries,
        )
        catalog_result = _merge_google_with_catalog(catalog_result, google_result)

    return _url_resolve_context(
        catalog_result,
        parsed=parsed,
        host=host,
        url=url,
        purchase_channel=purchase_channel,
    )


def _match_by_name(
    name: str,
    merchants: list[dict[str, Any]],
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    purchase_channel: str = PURCHASE_IN_STORE,
) -> MerchantResolveResult:
    if not _normalize_name(name):
        raise ValueError("Empty store name")
    search_queries = expand_store_name_queries(name)
    query_variants = {_normalize_name(q) for q in search_queries}

    exact: list[MerchantCategoryMatch] = []
    seen_exact: set[str] = set()
    for row in merchants:
        candidates = [str(row["name"]), *(str(a) for a in (row.get("aliases") or []))]
        category = _spend_category_for_row(row, purchase_channel)
        merchant_id = str(row["id"])
        if merchant_id in seen_exact:
            continue
        for candidate in candidates:
            normalized = _normalize_name(candidate)
            if normalized not in query_variants and not any(
                q == normalized or q in normalized or normalized in q for q in query_variants
            ):
                continue
            kind = "alias" if normalized != _normalize_name(str(row["name"])) else "name"
            exact.append(
                MerchantCategoryMatch(
                    merchant_id=merchant_id,
                    merchant_name=str(row["name"]),
                    spend_bonus_category_name=category,
                    match_type=kind,
                    matched_on=candidate,
                    input_kind="name",
                    confidence=CONFIDENCE_HIGH,
                    score=0 if kind == "name" else 5,
                    source="catalog",
                )
            )
            seen_exact.add(merchant_id)
            break

    if len(exact) == 1:
        return MerchantResolveResult(best=exact[0], candidates=exact, needs_confirmation=False)
    if len(exact) > 1:
        return MerchantResolveResult(best=exact[0], candidates=exact, needs_confirmation=True)

    partial: list[MerchantCategoryMatch] = []
    for row in merchants:
        candidates = [str(row["name"]), *(str(a) for a in (row.get("aliases") or []))]
        category = _spend_category_for_row(row, purchase_channel)
        for candidate in candidates:
            normalized = _normalize_name(candidate)
            if len(normalized) < 4:
                continue
            if not any(
                len(q) >= 4 and (q in normalized or normalized in q)
                for q in query_variants
            ):
                continue
            partial.append(
                MerchantCategoryMatch(
                    merchant_id=str(row["id"]),
                    merchant_name=str(row["name"]),
                    spend_bonus_category_name=category,
                    match_type="alias" if candidate != row["name"] else "name",
                    matched_on=candidate,
                    input_kind="name",
                    confidence=CONFIDENCE_MEDIUM,
                    score=20,
                    source="catalog",
                )
            )
    partial = sorted({m.merchant_id: m for m in partial}.values(), key=lambda m: m.score)
    if partial:
        catalog_result = MerchantResolveResult(
            best=partial[0],
            candidates=partial[:8],
            needs_confirmation=len(partial) > 1,
        )
        if len(partial) > 1 and purchase_channel == PURCHASE_IN_STORE:
            google_result = _google_places_resolve(
                name,
                latitude=latitude,
                longitude=longitude,
                input_kind="name",
                matched_on=name,
                text_queries=search_queries,
            )
            if google_result:
                return google_result
        return catalog_result

    fuzzy = _fuzzy_catalog_matches(
        name,
        merchants,
        purchase_channel=purchase_channel,
    )
    if fuzzy:
        return MerchantResolveResult(
            best=fuzzy[0],
            candidates=fuzzy[:8],
            needs_confirmation=True,
        )

    if purchase_channel == PURCHASE_IN_STORE:
        google_result = _google_places_resolve(
            name,
            latitude=latitude,
            longitude=longitude,
            input_kind="name",
            matched_on=name,
            text_queries=search_queries,
        )
        if google_result:
            return google_result

    if NOMINATIM_ENABLED:
        for query in search_queries:
            nm = lookup_store_name_nominatim(query)
            if not nm:
                continue
            match = _nominatim_to_match(nm, input_kind="name", matched_on=name)
            return MerchantResolveResult(
                best=match,
                candidates=[match],
                needs_confirmation=True,
            )

    if purchase_channel == PURCHASE_IN_STORE:
        hinted = _dining_name_heuristic(name)
        if hinted:
            return hinted

    return MerchantResolveResult(best=None, candidates=[], needs_confirmation=False)


def _dining_name_heuristic(name: str) -> MerchantResolveResult | None:
    """Fallback when catalog / Google / Nominatim miss — common restaurant-shaped names."""
    if not _normalize_name(name):
        return None
    norm = _normalize_name(name)
    if not any(hint in norm for hint in _DINING_NAME_HINTS):
        return None
    slug = re.sub(r"[^\w]+", "-", norm).strip("-") or "store"
    match = MerchantCategoryMatch(
        merchant_id=f"dining:{slug[:48]}",
        merchant_name=name.strip(),
        spend_bonus_category_name="Dining",
        match_type="name_hint",
        matched_on=name.strip(),
        input_kind="name",
        confidence=CONFIDENCE_LOW,
        score=80,
        source="name_heuristic",
    )
    return MerchantResolveResult(best=match, candidates=[match], needs_confirmation=True)


def resolve_merchant(
    *,
    merchant_url: str | None = None,
    merchant_name: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    catalog: list[dict[str, Any]] | None = None,
    purchase_channel: str | None = None,
) -> MerchantResolveResult:
    url = (merchant_url or "").strip()
    name = (merchant_name or "").strip()
    if url and name:
        raise ValueError("Provide merchant_url or merchant_name, not both")
    if not url and not name:
        raise ValueError("Provide merchant_url or merchant_name")

    if url:
        channel = purchase_channel or PURCHASE_ONLINE
        return resolve_merchant_url(
            url,
            latitude=latitude,
            longitude=longitude,
            catalog=catalog,
            purchase_channel=channel,
        )
    channel = purchase_channel or PURCHASE_IN_STORE
    result = _match_by_name(
        name,
        catalog or load_merchant_catalog(),
        latitude=latitude,
        longitude=longitude,
        purchase_channel=channel,
    )
    return MerchantResolveResult(
        best=result.best,
        candidates=result.candidates,
        needs_confirmation=result.needs_confirmation,
        purchase_channel=channel,
    )


def lookup_merchant_category(
    *,
    merchant_url: str | None = None,
    merchant_name: str | None = None,
    merchant_id: str | None = None,
    category: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    purchase_channel: str | None = None,
) -> MerchantCategoryMatch:
    if category and merchant_id and (
        merchant_id.startswith("osm:")
        or merchant_id.startswith("gmaps:")
        or merchant_id.startswith("web:")
    ):
        if merchant_id.startswith("gmaps:"):
            source = "google_places"
        elif merchant_id.startswith("web:"):
            source = "url_parse"
        else:
            source = "nominatim"
        return MerchantCategoryMatch(
            merchant_id=merchant_id,
            merchant_name=merchant_name or merchant_id,
            spend_bonus_category_name=category,
            match_type="confirmed",
            matched_on=merchant_id,
            input_kind="confirmed",
            confidence=CONFIDENCE_MEDIUM,
            score=0,
            source=source,
        )
    if merchant_id:
        return lookup_merchant_by_id(merchant_id, catalog=catalog)

    result = resolve_merchant(
        merchant_url=merchant_url,
        merchant_name=merchant_name,
        catalog=catalog,
        purchase_channel=purchase_channel,
    )
    if not result.best:
        if merchant_url:
            host = extract_domain(merchant_url)
            raise MerchantNotFoundError(
                f"No merchant found for checkout URL (host {host!r}). "
                "Try store name or a URL with the merchant domain embedded."
            )
        raise MerchantNotFoundError(
            f"No category found for store name {merchant_name!r}. "
            "Check spelling or paste the checkout URL."
        )
    return result.best


def list_merchants(*, catalog: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = catalog or load_merchant_catalog()
    results: list[dict[str, Any]] = []
    for row in rows:
        channels = channel_categories_for_row(row)
        results.append(
            {
                "id": row["id"],
                "name": row["name"],
                "category": channels["default"],
                "onlineCategory": channels["online"],
                "inStoreCategory": channels["in_store"],
                "domains": row.get("domains") or [],
            }
        )
    return results


def merchant_suggestions(
    query: str,
    *,
    limit: int = 8,
    purchase_channel: str | None = None,
) -> list[dict[str, Any]]:
    normalized = _normalize_name(query)
    if not normalized:
        return []
    channel = purchase_channel or PURCHASE_IN_STORE
    merchants = load_merchant_catalog()
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in merchants:
        name = _normalize_name(str(row["name"]))
        if normalized in name or name.startswith(normalized):
            scored.append((0 if name.startswith(normalized) else 1, row))
        else:
            for alias in row.get("aliases") or []:
                alias_norm = _normalize_name(str(alias))
                if normalized in alias_norm or alias_norm.startswith(normalized):
                    scored.append((2, row))
                    break
    scored.sort(key=lambda item: (item[0], item[1]["name"]))
    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    def append_row(row: dict[str, Any]) -> None:
        mid = str(row["id"])
        if mid in seen:
            return
        seen.add(mid)
        channels = channel_categories_for_row(row)
        results.append(
            {
                "id": row["id"],
                "name": row["name"],
                "category": _spend_category_for_row(row, channel),
                "onlineCategory": channels["online"],
                "inStoreCategory": channels["in_store"],
            }
        )

    for _, row in scored:
        append_row(row)
        if len(results) >= limit:
            return results

    if len(normalized) >= 3:
        for match in _fuzzy_catalog_matches(
            query,
            merchants,
            purchase_channel=channel,
            limit=limit,
        ):
            row = next(m for m in merchants if str(m["id"]) == match.merchant_id)
            append_row(row)
            if len(results) >= limit:
                break
    return results
