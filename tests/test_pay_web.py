"""Payment-moment homepage and merchant API."""

import pytest
from fastapi.testclient import TestClient

from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.merchant_google_places import GooglePlaceMatch
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.web.app import app
from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

client = TestClient(app)


def _wallet_loader(db_path):
    def load_wallet(card_keys, client=None):
        cards = []
        with session(db_path) as conn:
            repo = CardDataRepository(conn)
            for key in card_keys:
                detail = repo.get_card_detail(key)
                if not detail:
                    raise RuntimeError(f"Missing card in test db: {key}")
                cards.append(normalize_card_detail(detail))
        return cards

    return load_wallet


def test_index_page_loads():
    res = client.get("/")
    assert res.status_code == 200
    assert "i18n.js" in res.text
    assert "app.css" in res.text
    assert "savings.js" in res.text
    assert "wallet-ui.js" in res.text
    assert "analytics.js" in res.text
    assert "pwa.js" in res.text
    assert "manifest.webmanifest" in res.text
    assert "apple-touch-icon" in res.text
    assert "view-language" in res.text
    assert "savingsBanner" in res.text
    assert "valuationModal" in res.text
    assert "btnValuationHelp" in res.text


def test_pwa_assets():
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert "PayCue" in manifest.text
    assert "standalone" in manifest.text

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "serviceWorker" not in sw.text  # is the worker itself
    assert "fetch" in sw.text

    for path in (
        "/static/icons/icon.svg",
        "/static/icons/apple-touch-icon.png",
        "/static/icons/icon-192.png",
        "/static/icons/icon-512.png",
    ):
        icon = client.get(path)
        assert icon.status_code == 200, path


def test_api_cards_registry_image_urls_when_bundled():
    from credit_rewards.ingest.scrape.registry import load_card_registry

    keys = [str(e["card_key"]) for e in load_card_registry()]
    res = client.get("/api/cards")
    assert res.status_code == 200
    cards = res.json()["cards"]
    assert len(cards) == len(keys)
    assert all(c.get("image_url") for c in cards)


def test_merchant_resolve_url():
    res = client.post("/api/merchant/resolve", json={"merchant_url": "https://chipotle.com"})
    assert res.status_code == 200
    body = res.json()
    assert body["best"]["spendBonusCategoryName"] == "Dining"
    assert body["needsConfirmation"] is True
    assert body["candidates"]


def test_merchant_resolve_long_checkout_url():
    url = (
        "https://payments.example.com/v1/checkout?"
        "success=https%3A%2F%2Fwww.amazon.com%2Fgp%2Fbuy%2Fthankyou"
    )
    res = client.post("/api/merchant/resolve", json={"merchant_url": url})
    assert res.status_code == 200
    assert res.json()["best"]["merchantName"] == "Amazon"


def test_merchant_resolve_name():
    res = client.post("/api/merchant/resolve", json={"merchant_name": "Starbucks"})
    assert res.status_code == 200
    assert res.json()["best"]["spendBonusCategoryName"] == "Dining"


def test_merchant_resolve_haidilao_in_store():
    res = client.post(
        "/api/merchant/resolve",
        json={"merchant_name": "Haidilao hotpot", "purchase_channel": "in_store"},
    )
    assert res.status_code == 200
    assert res.json()["best"]["merchantName"] == "Haidilao"
    assert res.json()["best"]["spendBonusCategoryName"] == "Dining"


def test_merchant_resolve_unknown_in_store_uses_google_text(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: True)
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    fake = (
        GooglePlaceMatch(
            place_id="places/ChIJlocal",
            display_name="See U Morning",
            formatted_address="123 Main St",
            spend_bonus_category_name="Dining",
            primary_type="cafe",
            types=("cafe",),
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
    res = client.post(
        "/api/merchant/resolve",
        json={"merchant_name": "See you Morning", "purchase_channel": "in_store"},
    )
    assert res.status_code == 200
    assert res.json()["best"]["merchantId"].startswith("gmaps:")
    assert res.json()["best"]["spendBonusCategoryName"] == "Dining"


def test_merchant_resolve_unknown_404(monkeypatch):
    monkeypatch.setattr("credit_rewards.merchant_mapping.NOMINATIM_ENABLED", False)
    monkeypatch.setattr("credit_rewards.merchant_google_places.google_places_enabled", lambda: False)
    res = client.post("/api/merchant/resolve", json={"merchant_name": "Not A Real Store XYZ"})
    assert res.status_code == 404


def test_api_cards_lists_registry():
    res = client.get("/api/cards")
    assert res.status_code == 200
    assert res.json()["total"] == 20


def test_recommend_with_catalog_starbucks_card(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )

    resolve = client.post("/api/merchant/resolve", json={"merchant_name": "Starbucks"})
    assert resolve.status_code == 200
    merchant_id = resolve.json()["best"]["merchantId"]

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": merchant_id,
            "amount_usd": 25,
            "card_keys": ["chase-starbucksrewardsvisa", "amex-gold"],
        },
    )
    assert rec.status_code == 200, rec.text
    data = rec.json()
    assert data["card_count"] == 2
    starbucks = next(r for r in data["rankings"] if r["card_key"] == "chase-starbucksrewardsvisa")
    assert starbucks["multiplier"] == 3.0
    assert starbucks["points_earned"] == 75.0


def test_merchant_resolve_american_airlines_url():
    res = client.post(
        "/api/merchant/resolve",
        json={"merchant_url": "https://www.aa.com/flights", "purchase_channel": "online"},
    )
    assert res.status_code == 200
    best = res.json()["best"]
    assert best["merchantId"] == "american_airlines"
    assert best["spendBonusCategoryName"] == "Airfare"


def test_recommend_aa_co_brand_at_american_airlines_merchant(twenty_card_db, monkeypatch):
    """AA MileUp must use American Airlines bonus, not generic Airfare-only matching."""
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    from credit_rewards.card_import import ensure_card_in_db

    assert ensure_card_in_db("citi-aaadvantagemileup") is True

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": "american_airlines",
            "amount_usd": 100,
            "card_keys": ["citi-aaadvantagemileup", "chase-sapphire-preferred"],
        },
    )
    assert rec.status_code == 200, rec.text
    data = rec.json()
    assert data["resolved_category"] == "Airfare"
    by_key = {r["card_key"]: r for r in data["rankings"]}
    assert by_key["citi-aaadvantagemileup"]["multiplier"] == 2.0
    assert by_key["citi-aaadvantagemileup"]["points_earned"] == 200.0
    assert by_key["chase-sapphire-preferred"]["multiplier"] == 1.0
    assert data["best"]["card_key"] == "citi-aaadvantagemileup"


def test_recommend_starbucks_co_brand_not_base_rate(twenty_card_db, monkeypatch):
    """Starbucks Visa must earn 3x at Starbucks merchant, not 0.25x base."""
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    from credit_rewards.card_import import ensure_card_in_db

    assert ensure_card_in_db("chase-starbucksrewardsvisa") is True

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": "starbucks",
            "amount_usd": 100,
            "card_keys": ["chase-starbucksrewardsvisa"],
        },
    )
    assert rec.status_code == 200, rec.text
    best = rec.json()["best"]
    assert best["card_key"] == "chase-starbucksrewardsvisa"
    assert best["multiplier"] == 3.0
    assert best["points_earned"] == 300.0
    assert best["estimated_value_usd"] == pytest.approx(10.5)
    assert best["cpp_used"] == 3.5


def test_recommend_delta_co_brand_at_delta_merchant(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    from credit_rewards.card_import import ensure_card_in_db

    assert ensure_card_in_db("amex-deltagold") is True

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": "delta",
            "amount_usd": 100,
            "card_keys": ["amex-deltagold", "chase-sapphire-preferred"],
        },
    )
    assert rec.status_code == 200, rec.text
    by_key = {r["card_key"]: r for r in rec.json()["rankings"]}
    assert by_key["amex-deltagold"]["multiplier"] >= 2.0
    assert by_key["chase-sapphire-preferred"]["multiplier"] == 1.0


def test_recommend_marriott_co_brand_at_marriott_merchant(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    from credit_rewards.card_import import ensure_card_in_db

    assert ensure_card_in_db("amex-marriottbonvoybevy") is True

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": "marriott",
            "amount_usd": 100,
            "card_keys": ["amex-marriottbonvoybevy", "chase-sapphire-preferred"],
        },
    )
    assert rec.status_code == 200, rec.text
    by_key = {r["card_key"]: r for r in rec.json()["rankings"]}
    assert by_key["amex-marriottbonvoybevy"]["multiplier"] >= 6.0
    assert rec.json()["best"]["card_key"] == "amex-marriottbonvoybevy"


@pytest.mark.parametrize(
    ("merchant_id", "co_brand_card", "generic_category", "min_multiplier"),
    [
        ("united", "chase-unitedexplorer", "Airfare", 2.0),
        ("southwest", "chase-southwestpriority", "Airfare", 2.0),
        ("hilton", "amex-hilton", "Hotels", 3.0),
        ("jetblue", "barclays-jetblue", "Airfare", 3.0),
        ("alaska_airlines", "boa-alaska", "Airfare", 2.0),
        ("costco", "citi-costcoanywherevisa", "Wholesale Clubs", 2.0),
        ("target", "tdbank-targetredcard", "All Purchases", 5.0),
        ("walmart", "capitalone-walmartrewards", "Grocery Stores", 2.0),
        ("sams_club", "synchrony-samsclub", "Wholesale Clubs", 3.0),
    ],
)
def test_recommend_co_brand_at_merchant(
    twenty_card_db, monkeypatch, merchant_id, co_brand_card, generic_category, min_multiplier
):
    """Co-brand cards must use merchant-specific earn bucket, not generic category-only."""
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    from credit_rewards.card_import import ensure_card_in_db

    assert ensure_card_in_db(co_brand_card) is True

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": merchant_id,
            "purchase_channel": "in_store",
            "amount_usd": 100,
            "card_keys": [co_brand_card, "chase-sapphire-preferred"],
        },
    )
    assert rec.status_code == 200, rec.text
    data = rec.json()
    assert data["resolved_category"] == generic_category
    by_key = {r["card_key"]: r for r in data["rankings"]}
    assert by_key[co_brand_card]["multiplier"] >= min_multiplier
    assert by_key["chase-sapphire-preferred"]["multiplier"] == 1.0
    assert by_key[co_brand_card]["estimated_value_usd"] >= by_key["chase-sapphire-preferred"]["estimated_value_usd"]
    assert data["best"]["card_key"] == co_brand_card


def test_recommend_costco_via_gmaps_merchant_id(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    from credit_rewards.card_import import ensure_card_in_db

    assert ensure_card_in_db("citi-costcoanywherevisa") is True

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": "gmaps:ChIJcostco",
            "merchant_name": "Costco Wholesale · Frisco, TX",
            "category": "Grocery Stores",
            "amount_usd": 100,
            "card_keys": ["citi-costcoanywherevisa", "chase-sapphire-preferred"],
        },
    )
    assert rec.status_code == 200, rec.text
    data = rec.json()
    by_key = {r["card_key"]: r for r in data["rankings"]}
    assert by_key["citi-costcoanywherevisa"]["multiplier"] >= 2.0
    assert by_key["citi-costcoanywherevisa"]["partner_bonus"] is True
    assert data["best"]["card_key"] == "citi-costcoanywherevisa"


def test_recommend_costco_gas_uses_4_percent(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    from credit_rewards.card_import import ensure_card_in_db

    assert ensure_card_in_db("citi-costcoanywherevisa") is True

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": "costco",
            "merchant_name": "Costco Gas",
            "purchase_channel": "in_store",
            "amount_usd": 100,
            "card_keys": ["citi-costcoanywherevisa"],
        },
    )
    assert rec.status_code == 200, rec.text
    data = rec.json()
    assert data["resolved_category"] == "Gas Stations"
    assert data["best"]["multiplier"] == 4.0
    assert data["accepted_networks"] == ["Visa"]


def test_recommend_costco_excludes_amex(twenty_card_db, monkeypatch):
    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(
        "credit_rewards.card_import.CardDataClient",
        lambda *a, **k: type("C", (), {"is_configured": False})(),
    )
    from credit_rewards.card_import import ensure_card_in_db

    assert ensure_card_in_db("citi-costcoanywherevisa") is True

    rec = client.post(
        "/api/recommend",
        json={
            "merchant_id": "costco",
            "purchase_channel": "in_store",
            "amount_usd": 100,
            "card_keys": ["citi-costcoanywherevisa", "amex-gold"],
        },
    )
    assert rec.status_code == 200, rec.text
    data = rec.json()
    assert data["best"]["card_key"] == "citi-costcoanywherevisa"
    excluded = {row["card_key"] for row in data.get("excluded_cards") or []}
    assert "amex-gold" in excluded


def test_recommend_with_confirmed_merchant_id(twenty_card_db, monkeypatch):
    monkeypatch.setattr(
        "credit_rewards.web.app.load_wallet",
        _wallet_loader(twenty_card_db),
    )
    res = client.post(
        "/api/recommend",
        json={"merchant_id": "chipotle", "amount_usd": 100},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_category"] == "Dining"
    assert data["merchant"]["merchantId"] == "chipotle"
    assert data["card_count"] == 20
    assert "valuate_as_points" in data["best"]
    assert data["best"]["valuate_as_points"] is True


def test_recommend_with_osm_merchant(twenty_card_db, monkeypatch):
    monkeypatch.setattr(
        "credit_rewards.web.app.load_wallet",
        _wallet_loader(twenty_card_db),
    )
    res = client.post(
        "/api/recommend",
        json={
            "merchant_id": "osm:12345",
            "merchant_name": "Local Cafe",
            "category": "Dining",
            "amount_usd": 40,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_category"] == "Dining"
    assert data["merchant"]["merchantId"] == "osm:12345"
    assert data["merchant"]["source"] == "nominatim"


@pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference && import-reference",
)
def test_recommend_full_library_via_merchant_url(twenty_card_db, monkeypatch):
    monkeypatch.setattr(
        "credit_rewards.web.app.load_wallet",
        _wallet_loader(twenty_card_db),
    )
    res = client.post(
        "/api/recommend",
        json={"merchant_url": "https://www.chipotle.com", "amount_usd": 100},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["full_library"] is True
    assert data["card_count"] == 20
    assert data["resolved_category"] == "Dining"
    assert data["merchant"]["merchantName"] == "Chipotle"
    assert data["best"]["estimated_value_usd"] > 0
    assert len(data["rankings"]) == 20


@pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference && import-reference",
)
def test_recommend_full_library_via_merchant_name(twenty_card_db, monkeypatch):
    monkeypatch.setattr(
        "credit_rewards.web.app.load_wallet",
        _wallet_loader(twenty_card_db),
    )
    res = client.post(
        "/api/recommend",
        json={"merchant_name": "Amazon", "amount_usd": 50},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_category"] == "Online Shopping"
