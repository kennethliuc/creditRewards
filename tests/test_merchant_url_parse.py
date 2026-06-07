"""Checkout URL parsing helpers."""

from credit_rewards.merchant_url_parse import (
    extract_domains_from_text,
    extract_embedded_urls,
    is_payment_gateway_host,
    registrable_label,
    url_haystack,
)


def test_extract_embedded_urls_from_stripe_return():
    url = (
        "https://checkout.stripe.com/c/pay/cs_live_abc"
        "?return_url=https%3A%2F%2Fwww.chipotle.com%2Forder%2Fdone"
    )
    embedded = extract_embedded_urls(url)
    assert any("chipotle.com" in u for u in embedded)


def test_extract_domains_from_long_query():
    haystack = (
        "checkout.stripe.com pay?merchant=wholefoodsmarket.com"
        "&success=https%3A%2F%2Fwww.amazon.com%2Fgp%2Fbuy"
    )
    domains = extract_domains_from_text(haystack)
    assert "wholefoodsmarket.com" in domains
    assert "amazon.com" in domains
    assert "checkout.stripe.com" not in domains


def test_registrable_label():
    assert registrable_label("www.chipotle.com") == "chipotle"
    assert registrable_label("shop.wholefoodsmarket.com") == "wholefoodsmarket"


def test_payment_gateway_detection():
    assert is_payment_gateway_host("checkout.stripe.com")
    assert not is_payment_gateway_host("chipotle.com")


def test_url_haystack_includes_decoded_query():
    host, hay = url_haystack("https://pay.example.com/?store=starbucks.com")
    assert host == "pay.example.com"
    assert "starbucks.com" in hay
