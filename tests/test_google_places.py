"""Google Places merchant resolution with location bias."""

from credit_rewards.merchant_google_places import GooglePlaceMatch
from credit_rewards.merchant_mapping import lookup_merchant_category, resolve_merchant


def test_resolve_name_with_google_location(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)

    fake = (
        GooglePlaceMatch(
            place_id="places/ChIJtest",
            display_name="Chipotle Mexican Grill",
            formatted_address="123 Main St, San Jose, CA",
            spend_bonus_category_name="Dining",
            primary_type="mexican_restaurant",
            types=("mexican_restaurant", "restaurant"),
            match_type="google_primary_type",
            confidence="high",
            score=12,
        ),
    )

    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_with_location_queries",
        lambda queries, lat, lng: fake if any("chipotle" in q.lower() for q in queries) else (),
    )

    result = resolve_merchant(
        merchant_name="chipotle",
        latitude=37.3382,
        longitude=-121.8863,
    )
    assert result.best
    assert result.best.merchant_id.startswith("gmaps:")
    assert result.best.spend_bonus_category_name == "Dining"
    assert result.best.source == "google_places"


def test_resolve_without_location_skips_google(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)

    called = {"n": 0}

    def fake_lookup(*args):
        called["n"] += 1
        return ()

    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_with_location_queries",
        fake_lookup,
    )
    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_for_parsed_brand",
        lambda *args, **kwargs: (),
    )

    resolve_merchant(merchant_name="Mystery Store XYZ")
    assert called["n"] == 0


def test_resolve_url_includes_parsed_store_name(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)

    fake = (
        GooglePlaceMatch(
            place_id="places/ChIJcm",
            display_name="Central Market",
            formatted_address="4001 N Lamar Blvd, Austin, TX",
            spend_bonus_category_name="Grocery Stores",
            primary_type="supermarket",
            types=("supermarket", "grocery_store"),
            match_type="google_primary_type",
            confidence="high",
            score=12,
        ),
    )
    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_for_parsed_brand",
        lambda parsed, latitude=None, longitude=None: fake
        if "freshbazaar" in parsed.brand_slug
        else (),
    )

    result = resolve_merchant(
        merchant_url="http://freshbazaar.com/",
        latitude=30.2672,
        longitude=-97.7431,
        purchase_channel="in_store",
    )
    assert result.parsed_store_name == "Freshbazaar"
    assert result.parsed_store_domain == "freshbazaar.com"
    assert result.best
    assert result.best.source == "google_places"


def test_resolve_url_online_skips_google_maps(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)

    called = {"n": 0}

    def fake_lookup(*args, **kwargs):
        called["n"] += 1
        return ()

    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_for_parsed_brand",
        fake_lookup,
    )

    result = resolve_merchant(merchant_url="http://freshbazaar.com/")
    assert called["n"] == 0
    assert result.purchase_channel == "online"
    assert result.best
    assert result.best.spend_bonus_category_name == "Online Shopping"
    assert result.best.source == "url_parse"


def test_resolve_nike_url_online():
    result = resolve_merchant(merchant_url="https://www.nike.com/checkout")
    assert result.best
    assert result.best.merchant_name == "Nike"
    assert result.best.spend_bonus_category_name == "Online Shopping"
    assert result.purchase_channel == "online"


def test_resolve_url_google_maps_without_location(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)

    fake = (
        GooglePlaceMatch(
            place_id="places/ChIJcm",
            display_name="Central Market",
            formatted_address="4001 N Lamar Blvd, Austin, TX",
            spend_bonus_category_name="Grocery Stores",
            primary_type="supermarket",
            types=("supermarket", "grocery_store"),
            match_type="google_name_match",
            confidence="medium",
            score=0,
        ),
    )
    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_for_parsed_brand",
        lambda parsed, latitude=None, longitude=None: fake,
    )

    result = resolve_merchant(
        merchant_url="http://freshbazaar.com/",
        purchase_channel="in_store",
    )
    assert result.best
    assert result.best.source == "google_places"


def test_lookup_web_confirmed_category():
    match = lookup_merchant_category(
        merchant_id="web:nike.com",
        category="Online Shopping",
        merchant_name="Nike（官网网购）",
    )
    assert match.source == "url_parse"
    assert match.spend_bonus_category_name == "Online Shopping"


def test_lookup_gmaps_confirmed_category():
    match = lookup_merchant_category(
        merchant_id="gmaps:ChIJtest",
        category="Dining",
        merchant_name="Chipotle",
    )
    assert match.source == "google_places"
    assert match.spend_bonus_category_name == "Dining"
