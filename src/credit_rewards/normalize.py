from __future__ import annotations

from datetime import date
from typing import Any

from credit_rewards.models import CardProfile, EarnRule


def _parse_date(value: str) -> date | None:
    if not value or not value.strip():
        return None
    return date.fromisoformat(value[:10])


def normalize_card_detail(payload: list[dict[str, Any]] | dict[str, Any]) -> CardProfile:
    """Convert Rewards CC card detail response to CardProfile."""
    row = payload[0] if isinstance(payload, list) else payload

    category_rules: list[EarnRule] = []
    for rule in row.get("spendBonusCategory") or []:
        category_rules.append(
            EarnRule(
                category_name=rule.get("spendBonusCategoryName") or "",
                category_id=rule.get("spendBonusCategoryId"),
                multiplier=float(rule.get("earnMultiplier") or 0),
                description=rule.get("spendBonusDesc") or "",
                is_date_limit=bool(rule.get("isDateLimit")),
                limit_begin=_parse_date(rule.get("limitBeginDate") or ""),
                limit_end=_parse_date(rule.get("limitEndDate") or ""),
                is_spend_limit=bool(rule.get("isSpendLimit")),
                spend_limit=float(rule.get("spendLimit") or 0),
                spend_limit_reset_period=rule.get("spendLimitResetPeriod") or "",
            )
        )

    cpp_default = float(row.get("baseSpendEarnValuation") or 1.0)
    cpp_floor = float(row.get("baseSpendEarnCashValue") or cpp_default)
    if not row.get("baseSpendEarnIsCash"):
        cpp_floor = min(cpp_floor, cpp_default) if cpp_floor else cpp_default

    currency = (row.get("baseSpendEarnCurrency") or "points").lower()

    return CardProfile(
        card_key=row.get("cardKey") or "",
        card_name=row.get("cardName") or "",
        card_issuer=row.get("cardIssuer") or "",
        reward_program=row.get("baseSpendEarnType") or "",
        base_spend_amount=float(row.get("baseSpendAmount") or 1.0),
        base_earn_currency=currency,
        cpp_default=cpp_default,
        cpp_cash_floor=cpp_floor if cpp_floor > 0 else 1.0,
        is_cash_redeemable=bool(row.get("baseSpendEarnIsCash")),
        category_rules=category_rules,
    )
