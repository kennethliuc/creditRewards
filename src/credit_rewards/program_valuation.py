from __future__ import annotations

import json
from typing import Any

from credit_rewards.benchmarks import load_program_benchmarks
from credit_rewards.models import CardProfile, PurchaseContext
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.official_cpp import resolve_card_official_cpp
from credit_rewards.valuation import compute_earn_value, effective_cpp


def extract_valuation_fields(detail: dict[str, Any]) -> dict[str, Any]:
    """Parse Rewards CC card-detail valuation fields (cpp = cents per point)."""
    cpp_default = float(detail.get("baseSpendEarnValuation") or 1.0)
    cpp_floor = float(detail.get("baseSpendEarnCashValue") or cpp_default)
    is_cash = bool(int(detail.get("baseSpendEarnIsCash") or 0))
    if not is_cash and cpp_floor <= 0:
        cpp_floor = cpp_default
    return {
        "program_name": detail.get("baseSpendEarnType") or "",
        "earn_currency": (detail.get("baseSpendEarnCurrency") or "points").lower(),
        "cpp_default": cpp_default,
        "cpp_cash_floor": cpp_floor,
        "is_cash_redeemable": is_cash,
        "source": "rewardscc",
    }


def merge_benchmark(row: dict[str, Any], benchmarks: dict[str, dict[str, float]]) -> dict[str, Any]:
    bench = benchmarks.get(row["program_name"])
    if not bench:
        return row
    merged = dict(row)
    merged["benchmark_cpp_default"] = bench["cpp_default"]
    merged["benchmark_cpp_cash_floor"] = bench["cpp_cash_floor"]
    merged["benchmark_source"] = bench["benchmark_source"]
    return merged


def build_card_valuation_summary(
    detail: dict[str, Any],
    *,
    card_key: str | None = None,
    program_table: dict[str, float] | None = None,
    example_amount_usd: float = 100.0,
    example_category: str = "Anything",
) -> dict[str, Any]:
    """Build user-facing valuation payload with single official CPP."""
    from credit_rewards.official_cpp import enrich_card_profile, resolve_card_official_cpp

    key = card_key or str(detail.get("cardKey") or "")
    table = program_table or {}
    official_cpp, resolved_program = resolve_card_official_cpp(key, detail, table)

    card = normalize_card_detail(detail)
    card = enrich_card_profile(
        card,
        official_cpp=official_cpp,
        resolved_program=resolved_program,
    )
    purchase = PurchaseContext(category=example_category, amount_usd=example_amount_usd)
    mult, points, value, reason = compute_earn_value(card, purchase)

    return {
        "cardKey": key,
        "cardName": detail.get("cardName"),
        "rewardProgram": resolved_program,
        "officialCpp": round(official_cpp, 4),
        "dollarPerPoint": round(official_cpp / 100.0, 4),
        "examplePurchase": {
            "amountUsd": example_amount_usd,
            "category": example_category,
            "multiplier": mult,
            "pointsEarned": round(points, 2),
            "estimatedValueUsd": round(value, 2),
            "reason": reason,
        },
    }


def points_to_dollars(card: CardProfile, points: float) -> float:
    cpp = effective_cpp(card)
    return points * (cpp / 100.0)


def program_valuation_from_detail_json(detail_json: str) -> dict[str, Any]:
    detail = json.loads(detail_json)
    row = extract_valuation_fields(detail)
    return merge_benchmark(row, load_program_benchmarks())
