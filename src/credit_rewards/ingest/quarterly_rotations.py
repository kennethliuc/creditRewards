"""Merge curated quarterly rotation schedules into card reference details."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from credit_rewards.paths import data_dir

ROTATIONS_PATH = data_dir() / "curated" / "quarterly_rotations.yaml"


@lru_cache(maxsize=1)
def load_quarterly_rotations() -> dict[str, dict[str, Any]]:
    if not ROTATIONS_PATH.exists():
        return {}
    data = yaml.safe_load(ROTATIONS_PATH.read_text()) or {}
    cards = data.get("cards") or {}
    return {str(k): dict(v) for k, v in cards.items() if isinstance(v, dict)}


def clear_quarterly_rotations_cache() -> None:
    load_quarterly_rotations.cache_clear()


def _build_rotation_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    multiplier = float(config.get("multiplier") or 5.0)
    spend_limit = int(config.get("spend_limit") or 1500)
    reset = str(config.get("spend_limit_reset_period") or "Quarter")
    rules: list[dict[str, Any]] = []
    for quarter in config.get("quarters") or []:
        if not isinstance(quarter, dict):
            continue
        begin = str(quarter.get("begin") or "")
        end = str(quarter.get("end") or "")
        if not begin or not end:
            continue
        for cat in quarter.get("categories") or []:
            if not isinstance(cat, dict):
                continue
            cat_id = cat.get("id")
            name = str(cat.get("name") or "")
            if cat_id is None or not name:
                continue
            rules.append(
                {
                    "spendBonusCategoryType": "Multi Category",
                    "spendBonusCategoryName": name,
                    "spendBonusCategoryId": int(cat_id),
                    "spendBonusCategoryGroup": str(cat.get("group") or ""),
                    "spendBonusSubcategoryGroup": str(cat.get("subcategory") or ""),
                    "spendBonusDesc": str(cat.get("desc") or f"Earn {multiplier:g}% in {name}"),
                    "earnMultiplier": multiplier,
                    "isDateLimit": 1,
                    "limitBeginDate": begin,
                    "limitEndDate": end,
                    "isSpendLimit": 1,
                    "spendLimit": spend_limit,
                    "spendLimitResetPeriod": reset,
                }
            )
    return rules


def enrich_with_quarterly_rotations(
    detail: dict[str, Any],
    *,
    card_key: str,
) -> dict[str, Any]:
    """Replace date-limited rotating rules with curated schedule; keep permanent bonuses."""
    config = load_quarterly_rotations().get(card_key)
    if not config:
        return detail

    rotating = _build_rotation_rules(config)
    if not rotating:
        return detail

    existing = list(detail.get("spendBonusCategory") or [])
    permanent = [rule for rule in existing if not int(rule.get("isDateLimit") or 0)]
    merged = dict(detail)
    merged["spendBonusCategory"] = rotating + permanent
    return merged
