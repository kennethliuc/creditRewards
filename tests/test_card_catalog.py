"""Card catalog issuer search and images."""

from credit_rewards.card_catalog import (
    catalog_coverage_stats,
    enrich_registry_cards,
    list_issuers,
    search_cards_by_issuer,
)


def test_registry_cards_list():
    cards = enrich_registry_cards()
    assert len(cards) >= 20


def test_catalog_market_coverage_goal():
    stats = catalog_coverage_stats()
    assert stats["issuerCount"] == 28
    assert stats["supportedIssuerCount"] == 30
    assert stats["marketShareTargetPct"] >= 94.0
    assert stats["marketShareCoveredPct"] >= 90.0


def test_search_issuer_chase():
    matches = search_cards_by_issuer("Chase")
    assert matches
    assert all("Chase" in m["issuer"] for m in matches)


def test_list_issuers_top_tier_only():
    issuers = list_issuers()
    assert len(issuers) == 28
    assert issuers == sorted(issuers, key=str.casefold)
    assert issuers[0] == "American Express"
    assert "KeyBank" not in issuers
    assert "Santander" not in issuers
    assert "Busey Bank" not in issuers
    for name in issuers:
        assert search_cards_by_issuer(name, limit=1), f"{name} has no catalog cards"


def test_search_issuer_amex_alias():
    matches = search_cards_by_issuer("amex")
    assert matches
    assert any("American Express" in m["issuer"] for m in matches)
