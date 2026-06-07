"""Checkout URL parsing helpers."""

from credit_rewards.merchant_url_parse import (
    expand_domain_brand_queries,
    extract_domains_from_text,
    extract_embedded_urls,
    format_brand_display_name,
    infer_text_queries_from_url,
    is_payment_gateway_host,
    parse_store_brand_from_url,
    google_maps_search_queries,
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


def test_expand_domain_brand_queries_splits_compound_slug():
    assert "central market" in expand_domain_brand_queries("centralmarket")
    assert expand_domain_brand_queries("centralmarket")[0] == "centralmarket"


def test_parse_store_brand_from_merchant_website():
    parsed = parse_store_brand_from_url("http://centralmarket.com/")
    assert parsed is not None
    assert parsed.display_name == "Central Market"
    assert parsed.domain == "centralmarket.com"
    assert "central market" in parsed.search_queries


def test_parse_store_brand_from_checkout_url():
    url = (
        "https://checkout.stripe.com/c/pay/cs_live_abc"
        "?return_url=https%3A%2F%2Fwww.chipotle.com%2Forder%2Fdone"
    )
    parsed = parse_store_brand_from_url(url)
    assert parsed is not None
    assert parsed.display_name == "Chipotle"
    assert parsed.source == "embedded_domain"


def test_google_maps_search_queries_from_parsed_brand():
    parsed = parse_store_brand_from_url("http://centralmarket.com/")
    assert parsed is not None
    queries = google_maps_search_queries(parsed)
    assert queries[0] == "Central Market"
    assert "centralmarket" in queries
    assert any("centralmarket.com" in q for q in queries)


def test_format_brand_display_name():
    assert format_brand_display_name("central market") == "Central Market"
    assert format_brand_display_name("whole-foods") == "Whole Foods"
