"""Enhanced checkout URL parsing — nested URLs, payment gateways, brand domains."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

# Checkout/payment hosts — merchant identity is usually in query/path, not this host.
PAYMENT_GATEWAY_HOSTS = frozenset(
    {
        "checkout.stripe.com",
        "pay.stripe.com",
        "hooks.stripe.com",
        "www.paypal.com",
        "paypal.com",
        "pay.paypal.com",
        "www.sandbox.paypal.com",
        "checkout.shopify.com",
        "shop.app",
        "pay.google.com",
        "payments.google.com",
        "wallet.google.com",
        "secure.acceptance.paypal.com",
        "checkout.square.site",
        "buy.stripe.com",
    }
)

DOMAIN_IN_TEXT = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"([a-z0-9][-a-z0-9]*(?:\.[a-z0-9][-a-z0-9]*)*\.[a-z]{2,24})",
    re.IGNORECASE,
)

NESTED_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedStoreBrand:
    """Store identity inferred from a merchant website URL."""

    display_name: str
    domain: str
    host: str
    brand_slug: str
    search_queries: tuple[str, ...]
    source: str  # domain | embedded_domain


def format_brand_display_name(phrase: str) -> str:
    """Human-readable store name (central market → Central Market)."""
    parts: list[str] = []
    for token in re.split(r"[\s\-]+", phrase.strip()):
        if not token:
            continue
        if token.isupper() and len(token) <= 4:
            parts.append(token)
        else:
            parts.append(token.capitalize())
    return " ".join(parts)


def expand_domain_brand_queries(label: str) -> list[str]:
    """Turn domain slugs into search phrases (centralmarket → central market)."""
    raw = label.replace("-", " ").strip().lower()
    if not raw:
        return []
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", q.strip())
        if len(q) >= 3 and q not in seen:
            seen.add(q)
            queries.append(q)

    add(raw)
    if " " not in raw:
        for suffix in ("market", "mart", "foods", "shop", "store", "fresh"):
            if raw.endswith(suffix) and len(raw) > len(suffix) + 2:
                stem = raw[: -len(suffix)]
                if stem.isalpha():
                    add(f"{stem} {suffix}")
    return queries


def normalize_url_input(url: str) -> str:
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw


def primary_host(url: str) -> str:
    parsed = urlparse(normalize_url_input(url))
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def url_haystack(url: str) -> tuple[str, str]:
    raw = normalize_url_input(url)
    parsed = urlparse(raw)
    host = primary_host(url)
    parts = [host, parsed.path or "", parsed.query or "", parsed.fragment or ""]
    decoded = unquote(" ".join(parts))
    nested = " ".join(NESTED_URL.findall(decoded))
    combined = f"{decoded} {nested} {parsed.path} {parsed.query} {parsed.fragment}".lower()
    return host, re.sub(r"\s+", " ", combined).strip()


def extract_embedded_urls(url: str) -> list[str]:
    """Pull merchant URLs hidden inside payment-gateway query params."""
    _, haystack = url_haystack(url)
    found: list[str] = []
    seen: set[str] = set()
    for match in NESTED_URL.findall(haystack):
        candidate = unquote(match).strip().rstrip(".,;)\\]")
        if candidate not in seen:
            seen.add(candidate)
            found.append(candidate)
    raw = normalize_url_input(url)
    if raw not in seen:
        found.insert(0, raw)
    return found


def extract_domains_from_text(text: str) -> list[str]:
    """Find domain-like tokens anywhere in a long checkout URL string."""
    decoded = unquote(text.lower())
    found: list[str] = []
    seen: set[str] = set()
    for match in DOMAIN_IN_TEXT.finditer(decoded):
        domain = match.group(1).lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain not in seen and _looks_like_merchant_domain(domain):
            seen.add(domain)
            found.append(domain)
    return found


def registrable_label(domain: str) -> str:
    """Best-effort brand slug from domain (chipotle.com → chipotle)."""
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    parts = domain.split(".")
    if len(parts) >= 2 and parts[-2] in {"co", "com", "org", "net"} and len(parts) >= 3:
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0]


def parse_store_brand_from_url(url: str) -> ParsedStoreBrand | None:
    """Parse a merchant store name from a website or checkout URL."""
    host, haystack = url_haystack(url)
    merchant_domain: str | None = None
    source = "domain"

    if is_payment_gateway_host(host):
        embedded_domains: list[str] = []
        for embedded in extract_embedded_urls(url):
            embedded_host, _ = url_haystack(embedded)
            if not is_payment_gateway_host(embedded_host):
                embedded_domains.append(embedded_host)
        for domain in extract_domains_from_text(haystack):
            if not is_payment_gateway_host(domain):
                embedded_domains.append(domain)
        if not embedded_domains:
            return None
        merchant_domain = embedded_domains[0]
        source = "embedded_domain"
    else:
        merchant_domain = host

    label = registrable_label(merchant_domain)
    queries = expand_domain_brand_queries(label)
    if not queries:
        return None

    display_query = max(queries, key=lambda q: ((" " in q), len(q)))
    return ParsedStoreBrand(
        display_name=format_brand_display_name(display_query),
        domain=merchant_domain,
        host=host,
        brand_slug=label,
        search_queries=tuple(queries),
        source=source,
    )


def infer_text_queries_from_url(url: str) -> list[str]:
    parsed = parse_store_brand_from_url(url)
    return list(parsed.search_queries) if parsed else []


def google_maps_search_queries(parsed: ParsedStoreBrand) -> list[str]:
    """Search phrases for Google Maps Places Text Search."""
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", q.strip())
        key = q.lower()
        if len(q) >= 3 and key not in seen:
            seen.add(key)
            queries.append(q)

    add(parsed.display_name)
    for q in parsed.search_queries:
        add(q)
    add(f"{parsed.display_name} {parsed.domain}")
    return queries


def is_payment_gateway_host(host: str) -> bool:
    host = host.lower()
    if host in PAYMENT_GATEWAY_HOSTS:
        return True
    return any(
        host.endswith(suffix)
        for suffix in (
            ".stripe.com",
            ".paypal.com",
            ".shopify.com",
            ".myshopify.com",
            ".square.site",
        )
    )


def _looks_like_merchant_domain(domain: str) -> bool:
    if domain in PAYMENT_GATEWAY_HOSTS:
        return False
    for suffix in (".stripe.com", ".paypal.com", ".google.com", "google.com"):
        if domain.endswith(suffix) or domain == suffix:
            return False
    return "." in domain and len(domain) > 3
