from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml

from credit_rewards.merchant_nominatim import (
    NOMINATIM_ENABLED,
    lookup_domain_brand_nominatim,
    lookup_store_name_nominatim,
)
from credit_rewards.merchant_url_parse import (
    extract_domains_from_text,
    extract_embedded_urls,
    is_payment_gateway_host,
    primary_host,
    registrable_label,
    url_haystack,
)

from credit_rewards.paths import data_dir

MERCHANT_DATA_PATH = data_dir() / "merchants" / "merchant_categories.yaml"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.best is not None,
            "best": self.best.to_dict() if self.best else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "needsConfirmation": self.needs_confirmation,
            "parsedHost": self.parsed_host,
            "inputUrl": self.input_url,
        }


def load_merchant_catalog(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or MERCHANT_DATA_PATH
    data = yaml.safe_load(target.read_text()) or {}
    return list(data.get("merchants") or [])


def lookup_merchant_by_id(
    merchant_id: str,
    *,
    catalog: list[dict[str, Any]] | None = None,
) -> MerchantCategoryMatch:
    if merchant_id.startswith("osm:"):
        raise MerchantNotFoundError(
            f"External merchant {merchant_id!r} — pass confirmed category on recommend"
        )
    merchants = catalog or load_merchant_catalog()
    for row in merchants:
        if str(row["id"]) == merchant_id:
            return MerchantCategoryMatch(
                merchant_id=str(row["id"]),
                merchant_name=str(row["name"]),
                spend_bonus_category_name=str(row["spend_bonus_category_name"]),
                match_type="confirmed",
                matched_on=str(row["id"]),
                input_kind="confirmed",
                confidence=CONFIDENCE_HIGH,
                score=0,
                source="catalog",
            )
    raise MerchantNotFoundError(f"Unknown merchant_id: {merchant_id!r}")


def _normalize_name(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^\w\s']", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def extract_domain(url: str) -> str:
    return primary_host(url)


def _confidence_from_score(score: int) -> str:
    if score <= 10:
        return CONFIDENCE_HIGH
    if score <= 35:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


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
) -> None:
    for row in merchants:
        merchant_id = str(row["id"])
        merchant_name = str(row["name"])
        category = str(row["spend_bonus_category_name"])
        aliases = [str(a) for a in (row.get("aliases") or [])]

        best_for_row: tuple[int, str, str] | None = None
        for domain in row.get("domains") or []:
            hit = _score_domain_in_url(host, haystack, str(domain))
            if hit and (best_for_row is None or hit[0] < best_for_row[0]):
                best_for_row = (hit[0], hit[1], str(domain))

        name_hit = _score_name_in_url(haystack, merchant_name, aliases)
        if name_hit and (best_for_row is None or name_hit[0] < best_for_row[0]):
            best_for_row = (name_hit[0], name_hit[1], merchant_name)

        if best_for_row:
            score, match_type, matched_on = best_for_row
            existing = scored.get(merchant_id)
            if existing is None or score < existing.score:
                scored[merchant_id] = MerchantCategoryMatch(
                    merchant_id=merchant_id,
                    merchant_name=merchant_name,
                    spend_bonus_category_name=category,
                    match_type=match_type,
                    matched_on=matched_on,
                    input_kind=input_kind,
                    confidence=_confidence_from_score(score),
                    score=score,
                    source="catalog",
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


def resolve_merchant_url(
    url: str,
    *,
    catalog: list[dict[str, Any]] | None = None,
) -> MerchantResolveResult:
    """Fuzzy-match merchant from a long checkout/payment URL."""
    merchants = catalog or load_merchant_catalog()
    host, haystack = url_haystack(url)
    scored: dict[str, MerchantCategoryMatch] = {}

    for candidate_url in extract_embedded_urls(url):
        c_host, c_hay = url_haystack(candidate_url)
        _score_catalog_for_context(c_host, c_hay, merchants, scored)

    _score_catalog_for_context(host, haystack, merchants, scored)

    for domain in extract_domains_from_text(haystack):
        _score_catalog_for_context(domain, haystack, merchants, scored)

    if not scored:
        _nominatim_url_fallback(url, scored)

    candidates = sorted(scored.values(), key=lambda m: (m.score, m.merchant_name))
    best = candidates[0] if candidates else None
    return MerchantResolveResult(
        best=best,
        candidates=candidates[:8],
        needs_confirmation=True,
        parsed_host=host,
        input_url=url.strip(),
    )


def _match_by_name(name: str, merchants: list[dict[str, Any]]) -> MerchantResolveResult:
    query = _normalize_name(name)
    if not query:
        raise ValueError("Empty store name")

    exact: list[MerchantCategoryMatch] = []
    for row in merchants:
        candidates = [str(row["name"]), *(str(a) for a in (row.get("aliases") or []))]
        for candidate in candidates:
            normalized = _normalize_name(candidate)
            if query == normalized:
                kind = "alias" if normalized != _normalize_name(str(row["name"])) else "name"
                exact.append(
                    MerchantCategoryMatch(
                        merchant_id=str(row["id"]),
                        merchant_name=str(row["name"]),
                        spend_bonus_category_name=str(row["spend_bonus_category_name"]),
                        match_type=kind,
                        matched_on=candidate,
                        input_kind="name",
                        confidence=CONFIDENCE_HIGH,
                        score=0 if kind == "name" else 5,
                        source="catalog",
                    )
                )

    if len(exact) == 1:
        return MerchantResolveResult(best=exact[0], candidates=exact, needs_confirmation=False)
    if len(exact) > 1:
        return MerchantResolveResult(best=exact[0], candidates=exact, needs_confirmation=True)

    partial: list[MerchantCategoryMatch] = []
    if len(query) >= 4:
        for row in merchants:
            candidates = [str(row["name"]), *(str(a) for a in (row.get("aliases") or []))]
            for candidate in candidates:
                normalized = _normalize_name(candidate)
                if query in normalized or normalized in query:
                    partial.append(
                        MerchantCategoryMatch(
                            merchant_id=str(row["id"]),
                            merchant_name=str(row["name"]),
                            spend_bonus_category_name=str(row["spend_bonus_category_name"]),
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
        return MerchantResolveResult(
            best=partial[0],
            candidates=partial[:8],
            needs_confirmation=True,
        )

    if NOMINATIM_ENABLED:
        nm = lookup_store_name_nominatim(name)
        if nm:
            match = _nominatim_to_match(nm, input_kind="name", matched_on=name)
            return MerchantResolveResult(
                best=match,
                candidates=[match],
                needs_confirmation=True,
            )

    return MerchantResolveResult(best=None, candidates=[], needs_confirmation=False)


def resolve_merchant(
    *,
    merchant_url: str | None = None,
    merchant_name: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
) -> MerchantResolveResult:
    url = (merchant_url or "").strip()
    name = (merchant_name or "").strip()
    if url and name:
        raise ValueError("Provide merchant_url or merchant_name, not both")
    if not url and not name:
        raise ValueError("Provide merchant_url or merchant_name")

    if url:
        return resolve_merchant_url(url, catalog=catalog)
    return _match_by_name(name, catalog or load_merchant_catalog())


def lookup_merchant_category(
    *,
    merchant_url: str | None = None,
    merchant_name: str | None = None,
    merchant_id: str | None = None,
    category: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
) -> MerchantCategoryMatch:
    if category and merchant_id and merchant_id.startswith("osm:"):
        return MerchantCategoryMatch(
            merchant_id=merchant_id,
            merchant_name=merchant_name or merchant_id,
            spend_bonus_category_name=category,
            match_type="confirmed",
            matched_on=merchant_id,
            input_kind="confirmed",
            confidence=CONFIDENCE_MEDIUM,
            score=0,
            source="nominatim",
        )
    if merchant_id:
        return lookup_merchant_by_id(merchant_id, catalog=catalog)

    result = resolve_merchant(
        merchant_url=merchant_url,
        merchant_name=merchant_name,
        catalog=catalog,
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
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "category": row["spend_bonus_category_name"],
            "domains": row.get("domains") or [],
        }
        for row in rows
    ]


def merchant_suggestions(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    normalized = _normalize_name(query)
    if not normalized:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in load_merchant_catalog():
        name = _normalize_name(str(row["name"]))
        if normalized in name or name.startswith(normalized):
            scored.append((0 if name.startswith(normalized) else 1, row))
        else:
            for alias in row.get("aliases") or []:
                alias_norm = _normalize_name(str(alias))
                if normalized in alias_norm:
                    scored.append((2, row))
                    break
    scored.sort(key=lambda item: (item[0], item[1]["name"]))
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for _, row in scored:
        mid = str(row["id"])
        if mid in seen:
            continue
        seen.add(mid)
        results.append(
            {
                "id": row["id"],
                "name": row["name"],
                "category": row["spend_bonus_category_name"],
            }
        )
        if len(results) >= limit:
            break
    return results
