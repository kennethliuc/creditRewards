"""Visa MCC (ISO 18245) → Rewards CC category mapping tests."""

import pytest

from credit_rewards.mcc_mapping import lookup_mcc_category, mcc_match_to_dict


def test_grocery_mcc_5411():
    match = lookup_mcc_category("5411")
    assert match.spend_bonus_category_name == "Grocery Stores"
    assert match.spend_bonus_category_id == 1132334901
    assert match.match_type == "exact"


def test_dining_mcc_5812():
    match = lookup_mcc_category("5812")
    assert match.spend_bonus_category_name == "Dining"
    assert match.match_type == "exact"


def test_airline_range_3010():
    match = lookup_mcc_category("3010")
    assert match.spend_bonus_category_name == "Airfare"
    assert match.match_type == "range"


def test_gas_mcc_5542():
    match = lookup_mcc_category("5542")
    assert match.spend_bonus_category_name == "Gas Stations"
    assert match.spend_bonus_category_id == 1455345350


def test_unknown_mcc_defaults():
    match = lookup_mcc_category("9999")
    assert match.match_type == "default"
    assert match.spend_bonus_category_name == "All Purchases"


def test_mcc_code_is_four_digits():
    match = lookup_mcc_category("5411")
    assert match.mcc == "5411"
    assert len(match.mcc) == 4


def test_api_dict_shape():
    payload = mcc_match_to_dict(lookup_mcc_category("5912"))
    assert payload["spendBonusCategoryName"] == "Drugstores"
    assert "mappingSource" in payload


def test_top_validation_mccs_mapped():
    from credit_rewards.validation.dashboard import TOP_VALIDATION_MCCS

    unmapped = [
        item["code"]
        for item in TOP_VALIDATION_MCCS
        if lookup_mcc_category(item["code"]).mcc_description.startswith("Unmapped")
    ]
    assert not unmapped, unmapped
