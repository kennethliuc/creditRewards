"""Fuzzy merchant name scoring."""

from credit_rewards.merchant_fuzzy import (
    FUZZY_MIN_RATIO,
    fuzzy_name_score,
    levenshtein_distance,
    similarity_ratio,
)


def test_levenshtein_identical():
    assert levenshtein_distance("chipotle", "chipotle") == 0


def test_similarity_ratio_typo():
    ratio = similarity_ratio("chpotle", "chipotle")
    assert ratio >= 0.7


def test_fuzzy_name_score_prefix():
    assert fuzzy_name_score("chip", "chipotle") >= 0.88


def test_fuzzy_name_score_typo():
    assert fuzzy_name_score("chik fil a", "chick fil a") >= FUZZY_MIN_RATIO
