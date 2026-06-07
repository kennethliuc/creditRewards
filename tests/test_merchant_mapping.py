"""Merchant name / URL → spend category mapping."""

import pytest

from credit_rewards.merchant_mapping import (
    MerchantNotFoundError,
    extract_domain,
    list_merchants,
    lookup_merchant_by_id,
    lookup_merchant_category,
    merchant_suggestions,
    resolve_merchant,
    resolve_merchant_url,
)


def test_url_chipotle_domain():
    result = resolve_merchant_url("https://www.chipotle.com/order/checkout?cart=abc123")
    assert result.best
    assert result.best.merchant_name == "Chipotle"
    assert result.best.spend_bonus_category_name == "Dining"
    assert result.best.match_type == "domain_host_exact"
    assert result.needs_confirmation is True


def test_long_checkout_url_fuzzy_in_query():
    url = (
        "https://checkout.stripe.com/c/pay/cs_live_abc123"
        "?return_url=https%3A%2F%2Fwww.chipotle.com%2Forder%2Fconfirmation%3Fid%3Dxyz"
    )
    result = resolve_merchant_url(url)
    assert result.best
    assert result.best.merchant_name == "Chipotle"
    assert result.best.match_type in {
        "domain_host_exact",
        "domain_url_fuzzy",
        "domain_url_substring",
        "domain_host_subdomain",
    }


def test_url_without_scheme():
    result = resolve_merchant_url("amazon.com/gp/buy/spc/handlers/display.html?ref=checkout")
    assert result.best
    assert result.best.merchant_name == "Amazon"
    assert result.best.spend_bonus_category_name == "Online Shopping"


def test_name_whole_foods_alias():
    result = resolve_merchant(merchant_name="Whole Foods")
    assert result.best
    assert result.best.spend_bonus_category_name == "Grocery Stores"
    assert result.needs_confirmation is False


def test_name_exact():
    match = lookup_merchant_category(merchant_name="Netflix")
    assert match.spend_bonus_category_name == "Streaming Services"


def test_lookup_by_merchant_id():
    match = lookup_merchant_category(merchant_id="chipotle")
    assert match.merchant_name == "Chipotle"
    assert match.match_type == "confirmed"


def test_unknown_domain_raises(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    result = resolve_merchant_url("https://unknown-shop-xyz.example.com/pay?id=1")
    assert result.best is None


def test_unknown_name_raises(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    with pytest.raises(MerchantNotFoundError):
        lookup_merchant_category(merchant_name="Mystery Store 999")


def test_both_url_and_name_rejected():
    with pytest.raises(ValueError):
        resolve_merchant(merchant_url="https://chipotle.com", merchant_name="Chipotle")


def test_extract_domain_strips_www():
    assert extract_domain("https://www.delta.com/flights") == "delta.com"


def test_list_merchants_not_empty():
    merchants = list_merchants()
    assert len(merchants) >= 20


def test_suggestions_prefix():
    hits = merchant_suggestions("chip")
    assert hits
    assert hits[0]["name"] == "Chipotle"


def test_api_resolve_shape():
    result = resolve_merchant(merchant_url="https://pay.example.com/?merchant=wholefoodsmarket.com")
    assert result.best
    assert result.best.merchant_name == "Whole Foods Market"
    payload = result.to_dict()
    assert payload["needsConfirmation"] is True
    assert payload["best"]["merchantId"]


def test_lookup_osm_merchant_with_confirmed_category():
    match = lookup_merchant_category(
        merchant_id="osm:12345",
        category="Dining",
        merchant_name="Joe's Pizza",
    )
    assert match.merchant_id == "osm:12345"
    assert match.spend_bonus_category_name == "Dining"
    assert match.source == "nominatim"


def test_nominatim_name_fallback(monkeypatch):
    from credit_rewards.merchant_nominatim import NominatimMatch

    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", True)

    def fake_lookup(name):
        if "local cafe" in name.lower():
            return NominatimMatch(
                place_id="999",
                display_name="Local Cafe, Austin, TX",
                spend_bonus_category_name="Dining",
                osm_class="amenity",
                osm_type="cafe",
                match_type="osm_class_type",
                confidence="medium",
                score=50,
            )
        return None

    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_store_name_nominatim",
        fake_lookup,
    )
    result = resolve_merchant(merchant_name="Local Cafe Austin")
    assert result.best
    assert result.best.merchant_id == "osm:999"
    assert result.best.spend_bonus_category_name == "Dining"
    assert result.best.source == "nominatim"
