"""Fuzzy store-name matching against the merchant catalog."""

from __future__ import annotations

FUZZY_MIN_RATIO = 0.72
FUZZY_HIGH_RATIO = 0.92


def levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def similarity_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    dist = levenshtein_distance(a, b)
    return 1.0 - dist / max(len(a), len(b))


def fuzzy_name_score(query_normalized: str, label_normalized: str) -> float:
    if not query_normalized or not label_normalized:
        return 0.0
    if query_normalized == label_normalized:
        return 1.0
    if label_normalized.startswith(query_normalized) or query_normalized.startswith(label_normalized):
        return 0.95
    if query_normalized in label_normalized or label_normalized in query_normalized:
        return 0.88
    return similarity_ratio(query_normalized, label_normalized)
