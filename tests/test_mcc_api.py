"""MCC lookup CardData API endpoint."""

import pytest
from fastapi.testclient import TestClient

from credit_rewards.card_api.app import app
from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: credit-rewards-db sync-reference",
)


@pytest.fixture()
def client(twenty_card_db):
    return TestClient(app)


def test_mcc_lookup_endpoint_grocery(client):
    res = client.get("/creditcard-mcc-lookup/5411")
    assert res.status_code == 200
    body = res.json()
    assert body["spendBonusCategoryName"] == "Grocery Stores"
    assert body["matchType"] == "exact"


def test_mcc_lookup_invalid(client):
    res = client.get("/creditcard-mcc-lookup/abcd")
    assert res.status_code == 400
