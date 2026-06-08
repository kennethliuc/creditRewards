"""Wallet loading from CardData API, SQLite, or fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from credit_rewards.client import CardDataClient, RewardsCCError
from credit_rewards.wallet import load_wallet
from tests.twenty_cards_fixtures import reference_files_ready, twenty_card_db

pytestmark = pytest.mark.skipif(
    not reference_files_ready(),
    reason="Run: paycue-db sync-reference && import-reference",
)


def test_load_wallet_from_db_when_api_unavailable(twenty_card_db, monkeypatch):
    """Web app can recommend with only SQLite when CardData API (:8080) is down."""

    def fail_client(*args, **kwargs):
        raise RewardsCCError("simulated API down")

    monkeypatch.setenv("CREDITREWARDS_DB_PATH", str(twenty_card_db))
    monkeypatch.setattr(CardDataClient, "card_detail", fail_client)

    cards = load_wallet(["amex-gold", "chase-freedomflex"], CardDataClient())
    assert len(cards) == 2
    assert cards[0].card_key == "amex-gold"
