"""Google Places merchant resolution with location bias."""

from credit_rewards.merchant_google_places import GooglePlaceMatch
from credit_rewards.merchant_mapping import lookup_merchant_category, resolve_merchant


def test_catalog_exact_match_skips_google_with_location(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    called = {"n": 0}

    def fake_lookup(*args, **kwargs):
        called["n"] += 1
        return None

    monkeypatch.setattr("credit_rewards.merchant_mapping._google_places_resolve", fake_lookup)

    result = resolve_merchant(
        merchant_name="Walmart",
        latitude=30.27,
        longitude=-97.74,
    )
    assert called["n"] == 0
    assert result.best
    assert result.best.merchant_id == "walmart"
    assert result.best.source == "catalog"
    assert result.needs_confirmation is False


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
        "credit_rewards.merchant_mapping.lookup_places_for_store_name",
        lambda queries, query_for_ranking, latitude=None, longitude=None: fake
        if any("grill" in q.lower() for q in queries)
        else (),
    )

    result = resolve_merchant(
        merchant_name="Mystery Local Grill",
        latitude=37.3382,
        longitude=-121.8863,
    )
    assert result.best
    assert result.best.merchant_id.startswith("gmaps:")
    assert result.best.spend_bonus_category_name == "Dining"
    assert result.best.source == "google_places"


def test_resolve_without_location_uses_google_text_search(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)

    fake = (
        GooglePlaceMatch(
            place_id="places/ChIJlocal",
            display_name="See U Morning",
            formatted_address="123 Main St, Austin, TX",
            spend_bonus_category_name="Dining",
            primary_type="cafe",
            types=("cafe", "restaurant"),
            match_type="google_primary_type",
            confidence="high",
            score=12,
        ),
    )

    monkeypatch.setattr(
        "credit_rewards.merchant_mapping.lookup_places_for_store_name",
        lambda queries, query_for_ranking, latitude=None, longitude=None: fake
        if any("morning" in q.lower() for q in queries)
        else (),
    )

    result = resolve_merchant(merchant_name="See you Morning", purchase_channel="in_store")
    assert result.best
    assert result.best.merchant_id.startswith("gmaps:")
    assert result.best.spend_bonus_category_name == "Dining"
    assert result.best.source == "google_places"


def test_resolve_url_includes_parsed_store_name(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    monkeypatch.setattr("credit_rewards.merchant_mapping.load_merchant_catalog", lambda: [])

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
    monkeypatch.setattr("credit_rewards.merchant_mapping.load_merchant_catalog", lambda: [])

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


def test_nearby_api_returns_places(monkeypatch):
    from credit_rewards.merchant_google_places import lookup_nearby_stores

    fake = [
        {
            "merchantId": "gmaps:ChIJtest",
            "merchantName": "Target",
            "displayName": "Target",
            "shortAddress": "123 Main St",
            "formattedAddress": "123 Main St, Austin, TX",
            "spendBonusCategoryName": "Department Stores",
            "confidence": "high",
            "distanceMeters": 120,
            "source": "google_places",
        }
    ]
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr(
        "credit_rewards.merchant_google_places.lookup_nearby_stores",
        lambda lat, lng, limit=5: fake,
    )

    from fastapi.testclient import TestClient

    from credit_rewards.web.app import app

    res = TestClient(app).get(
        "/api/merchant/nearby",
        params={"latitude": 30.27, "longitude": -97.74, "limit": 5},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["places"][0]["displayName"] == "Target"
    assert body["places"][0]["distanceMeters"] == 120


def test_nearby_api_disabled(monkeypatch):
    from fastapi.testclient import TestClient

    from credit_rewards.web.app import app

    monkeypatch.setattr(
        "credit_rewards.merchant_google_places.google_places_enabled",
        lambda: False,
    )
    res = TestClient(app).get(
        "/api/merchant/nearby",
        params={"latitude": 30.27, "longitude": -97.74},
    )
    assert res.status_code == 200
    assert res.json()["places"] == []


def test_lookup_nearby_stores_sorts_by_distance(monkeypatch):
    from credit_rewards.merchant_google_places import lookup_nearby_stores

    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)

    def fake_nearby(lat, lng, *, radius_m=600, max_results=5):
        return [
            {
                "id": "places/far",
                "displayName": {"text": "Far Store"},
                "formattedAddress": "Far Rd",
                "primaryType": "supermarket",
                "types": ["supermarket"],
                "location": {"latitude": lat + 0.01, "longitude": lng},
            },
            {
                "id": "places/near",
                "displayName": {"text": "Near Store"},
                "formattedAddress": "Near Rd",
                "primaryType": "supermarket",
                "types": ["supermarket"],
                "location": {"latitude": lat + 0.0001, "longitude": lng},
            },
        ]

    monkeypatch.setattr("credit_rewards.merchant_google_places._places_search_nearby", fake_nearby)
    places = lookup_nearby_stores(30.0, -97.0, limit=2)
    assert len(places) == 2
    assert places[0]["displayName"] == "Near Store"
    assert places[0]["distanceMeters"] < places[1]["distanceMeters"]


def test_lookup_gmaps_confirmed_category():
    match = lookup_merchant_category(
        merchant_id="gmaps:ChIJtest",
        category="Dining",
        merchant_name="Chipotle",
    )
    assert match.source == "google_places"
    assert match.spend_bonus_category_name == "Dining"
