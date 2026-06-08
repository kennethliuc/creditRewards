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


def test_walmart_url_online_shopping():
    result = resolve_merchant(merchant_url="https://www.walmart.com/checkout")
    assert result.best
    assert result.best.merchant_name == "Walmart"
    assert result.best.spend_bonus_category_name == "Online Shopping"
    assert result.purchase_channel == "online"


def test_walmart_name_in_store_grocery():
    result = resolve_merchant(merchant_name="Walmart")
    assert result.best
    assert result.best.spend_bonus_category_name == "Grocery Stores"
    assert result.purchase_channel == "in_store"


def test_costco_online_vs_in_store():
    online = resolve_merchant(merchant_url="https://www.costco.com/Checkout")
    in_store = resolve_merchant(merchant_name="Costco")
    assert online.best.spend_bonus_category_name == "Online Shopping"
    assert in_store.best.spend_bonus_category_name == "Wholesale Clubs"


def test_central_market_url_uses_catalog():
    result = resolve_merchant(merchant_url="http://centralmarket.com/")
    assert result.best
    assert result.best.merchant_id == "central_market"
    assert result.best.spend_bonus_category_name == "Grocery Stores"


def test_channel_categories_for_row():
    from credit_rewards.merchant_mapping import channel_categories_for_row, load_merchant_catalog

    walmart = next(r for r in load_merchant_catalog() if r["id"] == "walmart")
    cats = channel_categories_for_row(walmart)
    assert cats["online"] == "Online Shopping"
    assert cats["in_store"] == "Grocery Stores"


def test_lookup_merchant_by_id_respects_channel():
    online = lookup_merchant_by_id("walmart", purchase_channel="online")
    instore = lookup_merchant_by_id("walmart", purchase_channel="in_store")
    assert online.spend_bonus_category_name == "Online Shopping"
    assert instore.spend_bonus_category_name == "Grocery Stores"


def test_unknown_domain_online_fallback(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    result = resolve_merchant_url("https://unknown-shop-xyz.example.com/pay?id=1")
    assert result.best
    assert result.best.merchant_id.startswith("web:")
    assert result.best.spend_bonus_category_name == "Online Shopping"


def test_chick_fil_a_alias_in_store():
    result = resolve_merchant(merchant_name="chick a fila", purchase_channel="in_store")
    assert result.best
    assert result.best.merchant_name == "Chick-fil-A"
    assert result.best.spend_bonus_category_name == "Dining"
    assert result.best.source == "catalog"


def test_unknown_name_raises(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: False)
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
    assert hits[0]["category"] == "Dining"


def test_suggestions_fuzzy_typo():
    hits = merchant_suggestions("chpotle")
    assert hits
    assert hits[0]["name"] == "Chipotle"


def test_fuzzy_name_resolve_chik_fila():
    result = resolve_merchant(merchant_name="chikfila")
    assert result.best
    assert result.best.merchant_name == "Chick-fil-A"
    assert result.best.match_type == "fuzzy_name"
    assert result.needs_confirmation is True


def test_fuzzy_name_resolve_in_n_out():
    result = resolve_merchant(merchant_name="in n ot")
    assert result.best
    assert result.best.merchant_name == "In-N-Out Burger"
    assert result.best.match_type == "fuzzy_name"
    assert result.needs_confirmation is True


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
    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_text_queries",
        lambda queries: (),
    )
    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_with_location_queries",
        lambda *args, **kwargs: (),
    )

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


def test_haidilao_hotpot_catalog_in_store():
    result = resolve_merchant(merchant_name="Haidilao hotpot", purchase_channel="in_store")
    assert result.best
    assert result.best.merchant_name == "Haidilao"
    assert result.best.spend_bonus_category_name == "Dining"
    assert result.needs_confirmation is False


def test_dining_name_heuristic_without_catalog(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)

    def no_google(*_a, **_k):
        return None

    monkeypatch.setattr("credit_rewards.merchant_mapping._google_places_resolve", no_google)
    result = resolve_merchant(
        merchant_name="Sichuan Hotpot House",
        purchase_channel="in_store",
    )
    assert result.best
    assert result.best.spend_bonus_category_name == "Dining"
    assert result.best.match_type == "name_hint"
    assert result.needs_confirmation is True
