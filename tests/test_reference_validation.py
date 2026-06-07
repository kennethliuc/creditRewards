import pytest

from credit_rewards.ingest.reference_sync import REFERENCE_DIR, load_reference_card
from credit_rewards.ingest.reference_validate import validate_card_against_reference


@pytest.mark.skipif(
    not (REFERENCE_DIR / "manifest.json").exists(),
    reason="Run credit-rewards-db sync-reference after setting REWARDS_CC_API_KEY",
)
@pytest.mark.xfail(
    reason="Scraper vs Rewards CC reference — run validate-reference to track gaps",
    strict=False,
)
def test_local_api_matches_rewardscc_reference():
    manifest = __import__("json").loads((REFERENCE_DIR / "manifest.json").read_text())
    for card_key in manifest.get("cards", {}):
        result = validate_card_against_reference(card_key)
        assert result.ok, f"{card_key}: {[str(d) for d in result.diffs] + result.notes}"


def test_reference_loader_skips_missing():
    assert load_reference_card("nonexistent-card-xyz") is None
