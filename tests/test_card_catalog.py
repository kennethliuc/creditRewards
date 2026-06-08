"""Card catalog issuer search and images."""

from credit_rewards.card_catalog import (
    catalog_coverage_stats,
    enrich_registry_cards,
    list_issuers,
    load_catalog_index,
    search_cards_by_issuer,
)


def test_registry_cards_list():
    cards = enrich_registry_cards()
    assert len(cards) >= 20


def test_catalog_market_coverage_goal():
    stats = catalog_coverage_stats()
    assert stats["issuerCount"] == 30
    assert stats["supportedIssuerCount"] == 30
    assert stats["marketShareTargetPct"] >= 94.0
    assert stats["marketShareCoveredPct"] >= 95.0
    assert stats["topIssuersMissing"] == []


def test_search_issuer_no_cross_bank_pollution():
    amex = search_cards_by_issuer("American Express")
    assert amex
    assert all(m["issuer"] == "American Express" for m in amex)

    citi = search_cards_by_issuer("Citi")
    assert citi
    assert all(m["issuer"] == "Citi" for m in citi)
    assert len(citi) >= 40

    citizens = search_cards_by_issuer("Citizens Bank")
    assert citizens
    assert all("Citizens" in m["issuer"] for m in citizens)
    assert not any(m["issuer"] == "Citi" for m in citizens)


def test_bilt_mastercard_in_catalog():
    keys = {r["card_key"] for r in load_catalog_index()}
    assert "bilt-mastercard" in keys
    assert "wellsfargo-bilt" not in keys


def test_keybank_and_santander_in_catalog():
    issuers = list_issuers()
    assert "KeyBank" in issuers
    assert "Santander" in issuers
    assert len(search_cards_by_issuer("KeyBank")) >= 3
    assert len(search_cards_by_issuer("Santander")) >= 2
    assert any(m["card_key"] == "discover-it-miles" for m in search_cards_by_issuer("Discover"))


def test_search_issuer_chase():
    matches = search_cards_by_issuer("Chase")
    assert matches
    assert all("Chase" in m["issuer"] for m in matches)
    keys = {m["card_key"] for m in matches}
    assert "chase-hyatt" in keys
    assert "chase-sapphire-reserve" in keys
    assert "chase-ritzcarlton" in keys
    assert len(matches) >= 50


def test_search_co_brand_by_name():
    hyatt = search_cards_by_issuer("Hyatt")
    assert any(m["card_key"] == "chase-hyatt" for m in hyatt)

    ritz = search_cards_by_issuer("Ritz")
    assert any("ritz" in m["card_key"] for m in ritz)

    united = search_cards_by_issuer("United Explorer")
    assert any("united" in m["card_key"] and m["issuer"] == "Chase" for m in united)

    lizi = search_cards_by_issuer("栗子")
    assert any(m["card_key"] == "chase-ritzcarlton" for m in lizi)


def test_list_issuers_top_tier_only():
    issuers = list_issuers()
    assert len(issuers) == 30
    assert issuers == sorted(issuers, key=str.casefold)
    assert issuers[0] == "American Express"
    assert "KeyBank" in issuers
    assert "Santander" in issuers
    assert "Busey Bank" not in issuers
    for name in issuers:
        assert search_cards_by_issuer(name, limit=1), f"{name} has no catalog cards"


def test_search_issuer_amex_alias():
    matches = search_cards_by_issuer("amex")
    assert matches
    assert any("American Express" in m["issuer"] for m in matches)


def test_issuer_search_returns_all_catalog_cards_per_issuer_string():
    by_issuer: dict[str, set[str]] = {}
    for row in load_catalog_index():
        issuer = str(row.get("issuer") or "")
        if issuer:
            by_issuer.setdefault(issuer, set()).add(str(row["card_key"]))

    for issuer, keys in by_issuer.items():
        found = {m["card_key"] for m in search_cards_by_issuer(issuer)}
        assert keys <= found, f"{issuer}: missing {sorted(keys - found)[:5]}"
