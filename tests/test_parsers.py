from credit_rewards.ingest.scrape.issuers import AmexScraper, ChaseScraper, CitiScraper
from tests.html_samples import AMEX_GOLD_HTML, CHASE_SAPPHIRE_HTML, CITI_DOUBLE_CASH_HTML


def test_amex_parser_extracts_grocery_and_dining():
    detail = AmexScraper().parse_card_page(AMEX_GOLD_HTML, "amex-gold", "https://example.com")
    rules = detail["spendBonusCategory"]
    names = {r["spendBonusCategoryName"] for r in rules}
    assert "Grocery Stores" in names
    assert "Dining" in names
    assert "Airfare" in names
    assert "amextravel.com" in names

    grocery = next(r for r in rules if r["spendBonusCategoryName"] == "Grocery Stores")
    assert grocery["earnMultiplier"] == 4.0
    assert grocery["isSpendLimit"] == 1

    dining = next(r for r in rules if r["spendBonusCategoryName"] == "Dining")
    assert dining["earnMultiplier"] == 4.0

    airfare = next(r for r in rules if r["spendBonusCategoryName"] == "Airfare")
    assert airfare["earnMultiplier"] == 3.0
    assert airfare["spendBonusCategoryId"] == 2013874334

    amex_travel = next(r for r in rules if r["spendBonusCategoryName"] == "amextravel.com")
    assert amex_travel["earnMultiplier"] == 2.0

    for r in rules:
        assert len(r["spendBonusCategoryName"]) <= 50


def test_chase_parser_extracts_travel_and_dining():
    detail = ChaseScraper().parse_card_page(
        CHASE_SAPPHIRE_HTML, "chase-sapphire-preferred", "https://example.com"
    )
    names = {r["spendBonusCategoryName"] for r in detail["spendBonusCategory"]}
    assert "Dining" in names
    assert "Travel" in names or "Chase Travel" in names


def test_citi_parser_extracts_cash_back():
    detail = CitiScraper().parse_card_page(CITI_DOUBLE_CASH_HTML, "citi-double-cash", "https://example.com")
    assert detail["baseSpendAmount"] == 2.0
    assert detail["baseSpendEarnCurrency"] == "cash"
