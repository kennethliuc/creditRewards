"""Card catalog sync — full issuer card list merge."""

from credit_rewards.ingest.card_catalog_sync import (
    absorb_card_list_groups,
    merge_manual_catalog_rows,
    normalize_bilt_catalog_rows,
)


def test_absorb_card_list_groups_adds_and_merges():
    by_rc: dict = {}
    reg_by_rc = {"chase-hyatt": {"card_key": "chase-hyatt", "issuer": "Chase"}}
    groups = [
        {
            "cardIssuer": "Chase",
            "card": [
                {"cardKey": "chase-hyatt", "cardName": "World of Hyatt Credit Card", "isActive": 0},
                {"cardKey": "chase-plain", "cardName": "Chase Plain Visa", "isActive": 1},
            ],
        }
    ]
    added = absorb_card_list_groups(groups, by_rc, reg_by_rc=reg_by_rc)
    assert added == 2
    assert by_rc["chase-hyatt"]["card_name"] == "World of Hyatt Credit Card"
    assert by_rc["chase-hyatt"]["card_key"] == "chase-hyatt"
    assert by_rc["chase-plain"]["issuer"] == "Chase"

    added_again = absorb_card_list_groups(groups, by_rc, reg_by_rc=reg_by_rc)
    assert added_again == 0
    assert len(by_rc) == 2


def test_merge_manual_catalog_rows():
    by_rc: dict = {}
    added = merge_manual_catalog_rows(by_rc)
    assert added >= 8
    assert "keybank-cashrewards" in by_rc
    assert by_rc["keybank-cashrewards"]["issuer"] == "KeyBank"
    assert "santander-ultimatecashback" in by_rc


def test_normalize_bilt_catalog_rows():
    by_rc = {
        "wellsfargo-bilt": {
            "card_key": "wellsfargo-bilt",
            "rewards_cc_card_key": "wellsfargo-bilt",
            "card_name": "Bilt World Elite Mastercard",
            "issuer": "Wells Fargo",
            "in_registry": False,
        }
    }
    normalize_bilt_catalog_rows(by_rc)
    assert "wellsfargo-bilt" not in by_rc
    assert by_rc["cardless-biltblue"]["card_key"] == "bilt-mastercard"
