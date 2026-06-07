"""Enhanced checkout URL parsing — nested URLs, payment gateways, brand domains."""

from __future__ import annotations

import re
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
