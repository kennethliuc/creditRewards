"""Program name resolution for catalog cards."""

from __future__ import annotations

from credit_rewards.official_cpp import (
    CASH_PROGRAM,
    infer_program_from_metadata,
    normalize_earn_type,
    resolve_program_name,
    load_official_cpp_config,
)


def test_normalize_cash_back_aliases():
    assert normalize_earn_type("Cash Back") == CASH_PROGRAM
    assert normalize_earn_type("cashback") == CASH_PROGRAM


def test_points_card_with_cash_redemption_flag_stays_points_program():
    config = load_official_cpp_config()
    detail = {
        "baseSpendEarnType": "American Express Membership Rewards",
        "baseSpendEarnIsCash": 1,
        "baseSpendEarnCurrency": "points",
    }
    assert resolve_program_name("amex-gold", detail, config) == "American Express Membership Rewards"


def test_infer_program_from_chase_issuer_when_spend_missing():
    detail = {"cardIssuer": "Chase", "baseSpendEarnType": ""}
    assert infer_program_from_metadata("chase-unknown", detail) == "Chase Ultimate Rewards"


def test_cfu_override_still_wins_over_cash_label():
    config = load_official_cpp_config()
    detail = {"baseSpendEarnType": "Cash", "baseSpendEarnIsCash": 0}
    assert (
        resolve_program_name("chase-freedom-unlimited", detail, config)
        == "Chase Ultimate Rewards"
    )


def test_catalog_audit_runs():
    from scripts.audit_program_resolution import audit_catalog

    report = audit_catalog(limit=50)
    assert report["catalog_count"] == 50
    assert report["with_detail"] > 0
    assert "resolved_programs" in report
