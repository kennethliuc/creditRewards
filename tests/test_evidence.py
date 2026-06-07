from credit_rewards.ingest.evidence import analyze_mismatch, find_evidence_snippets
from credit_rewards.ingest.scrape.parsers import html_to_text
from tests.html_samples import AMEX_GOLD_HTML


def test_find_dining_4x_on_amex_gold_page():
    text = html_to_text(AMEX_GOLD_HTML)
    snippets = find_evidence_snippets(text, 4.0, ["restaurant", "dining"])
    assert snippets
    assert any("4" in s for s in snippets)


def test_evidence_supports_scrape_when_api_wrong_on_dining():
    text = html_to_text(AMEX_GOLD_HTML)
    verdict = analyze_mismatch(
        mismatch_type="multiplier_mismatch",
        category_name="Dining",
        scrape_multiplier=4.0,
        reference_multiplier=3.0,
        page_text=text,
    )
    assert verdict.verdict == "scrape_supported"
    assert verdict.action == "keep_scrape"
    assert verdict.evidence_scrape


def test_evidence_supports_reference_for_airfare_3x():
    text = html_to_text(AMEX_GOLD_HTML)
    verdict = analyze_mismatch(
        mismatch_type="multiplier_mismatch",
        category_name="Airfare",
        scrape_multiplier=5.0,
        reference_multiplier=3.0,
        page_text=text,
    )
    assert verdict.verdict == "reference_supported"
    assert verdict.action == "fix_scrape"
