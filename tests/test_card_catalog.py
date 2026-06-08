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
    assert stats["issuerCount"] == 28
    assert stats["supportedIssuerCount"] == 30
    assert stats["marketShareTargetPct"] >= 94.0
    assert stats["marketShareCoveredPct"] >= 90.0


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


def test_issuer_search_returns_all_catalog_cards_per_issuer_string():
    by_issuer: dict[str, set[str]] = {}
    for row in load_catalog_index():
        issuer = str(row.get("issuer") or "")
        if issuer:
            by_issuer.setdefault(issuer, set()).add(str(row["card_key"]))

    for issuer, keys in by_issuer.items():
        found = {m["card_key"] for m in search_cards_by_issuer(issuer)}
        assert keys <= found, f"{issuer}: missing {sorted(keys - found)[:5]}"
