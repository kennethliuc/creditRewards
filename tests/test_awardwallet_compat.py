"""AwardWallet Credit Card Bonus API compatibility layer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from credit_rewards.awardwallet_compat import (
    build_short_earning_description,
    to_awardwallet_card,
)
from credit_rewards.card_api.app import app
from tests.twenty_cards_fixtures import (
    REGISTRY_CARD_KEYS,
    load_reference_detail,
    reference_files_ready,
    twenty_card_db,
)

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference",
)


@pytest.fixture()
def client(twenty_card_db):
    return TestClient(app)


def test_cfu_short_description_mentions_multipliers():
    detail = load_reference_detail("chase-freedom-unlimited")
    text = build_short_earning_description(detail).lower()
    assert "5" in text
    assert "dining" in text or "3" in text


def test_cfu_splits_merchant_vs_category_bonuses():
    detail = load_reference_detail("chase-freedom-unlimited")
    aw = to_awardwallet_card(detail)
    assert aw["earningCategories"]
    assert any(c["categoryName"] == "Dining" for c in aw["earningCategories"])
    assert any(m["merchantGroupName"] for m in aw["earningMerchants"])


def test_aw_card_has_extensions():
    detail = load_reference_detail("amex-gold")
    aw = to_awardwallet_card(detail, awardwallet_point_value=2.0)
    assert aw["awardWalletPointValue"] == 2.0
    assert aw["creditRewardsExtensions"]["creditRewardsPointValue"] == pytest.approx(2.2)
    assert aw["creditRewardsExtensions"]["annualFee"] == 325


@pytest.mark.parametrize("card_key", REGISTRY_CARD_KEYS)
def test_earnbonus_endpoint_for_all_cards(client, card_key):
    res = client.get(f"/creditcard-earnbonus-bycard/{card_key}")
    assert res.status_code == 200
    body = res.json()
    card = body["cards"][0]
    assert card["cardKey"] == card_key
    assert "earningCategories" in card
    assert "shortEarningDescription" in card
    assert body["meta"]["format"] == "awardwallet-credit-card-bonus-compatible"


def test_earnbonus_cards_list(client, twenty_card_db):
    res = client.get("/creditcard-earnbonus-cards/")
    assert res.status_code == 200
    assert len(res.json()["cards"]) == len(REGISTRY_CARD_KEYS)
