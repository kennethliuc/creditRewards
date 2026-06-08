from __future__ import annotations

import hashlib
import re
from typing import Any

_MERCHANT_HINTS = (
    "travel agency",
    "amextravel",
    "chase ultimate rewards",
    "chase travel",
    "portal",
    "apple pay",
    "select merchants",
)


def stable_card_id(card_key: str) -> int:
    digest = hashlib.sha256(card_key.encode()).hexdigest()
    return int(digest[:8], 16)


def _is_merchant_bonus(rule: dict[str, Any]) -> bool:
    name = (rule.get("spendBonusCategoryName") or "").lower()
    sub = (rule.get("spendBonusSubcategoryGroup") or "").lower()
    desc = (rule.get("spendBonusDesc") or "").lower()
    blob = f"{name} {sub} {desc}"
    return any(hint in blob for hint in _MERCHANT_HINTS)


def _format_multiplier(multiplier: float) -> str:
    if multiplier == int(multiplier):
        return f"{int(multiplier)}X"
    return f"{multiplier:g}X"


def build_short_earning_description(detail: dict[str, Any]) -> str:
    """AwardWallet-style one-line earn summary from local rules."""
    rules = detail.get("spendBonusCategory") or []
    base = float(detail.get("baseSpendAmount") or 1.0)
    currency = detail.get("baseSpendEarnType") or detail.get("baseSpendEarnCategory") or "points"

    parts: list[str] = []
    for rule in sorted(rules, key=lambda r: float(r.get("earnMultiplier") or 0), reverse=True):
        mult = float(rule.get("earnMultiplier") or 0)
        if mult <= base:
            continue
        name = rule.get("spendBonusCategoryName") or "purchases"
        parts.append(f"{_format_multiplier(mult)} on {name.lower()}")

    if not parts:
        return f"{_format_multiplier(base)} on all purchases"

    tail = f"and {_format_multiplier(base)} on all other purchases"
    if len(parts) == 1:
        return f"{parts[0]}, {tail}"
    if len(parts) == 2:
        return f"{parts[0]}, {parts[1]}, {tail}"
    head = ", ".join(parts[:-1])
    return f"{head}, {parts[-1]}, {tail} ({currency})"


def _aw_date(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    return str(value).strip()


def _rule_to_category(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "categoryId": int(rule["spendBonusCategoryId"]),
        "categoryName": rule.get("spendBonusCategoryName") or "",
        "multiplier": float(rule.get("earnMultiplier") or 0),
        "startDate": _aw_date(rule.get("limitBeginDate")),
        "endDate": _aw_date(rule.get("limitEndDate")),
        "description": rule.get("spendBonusDesc") or "",
        "spendLimit": float(rule.get("spendLimit") or 0) or None,
        "spendLimitResetPeriod": rule.get("spendLimitResetPeriod") or None,
    }


def _rule_to_merchant_group(rule: dict[str, Any]) -> dict[str, Any]:
    name = rule.get("spendBonusCategoryName") or "Merchant bonus"
    return {
        "merchantGroupId": int(rule["spendBonusCategoryId"]),
        "merchantGroupName": name,
        "multiplier": float(rule.get("earnMultiplier") or 0),
        "startDate": _aw_date(rule.get("limitBeginDate")),
        "endDate": _aw_date(rule.get("limitEndDate")),
        "description": rule.get("spendBonusDesc") or "",
        "merchantNames": [
            {
                "merchantId": stable_card_id(f"{name}:{rule['spendBonusCategoryId']}"),
                "merchantName": name,
            }
        ],
    }


def to_awardwallet_card(
    detail: dict[str, Any],
    *,
    card_id: int | None = None,
    awardwallet_point_value: float | None = None,
) -> dict[str, Any]:
    """
    Map local Rewards CC-shaped card detail → AwardWallet Credit Card Bonus API shape.
    See https://awardwallet.com/api/cc#introduction
    """
    card_key = detail.get("cardKey") or ""
    currency_raw = (detail.get("baseSpendEarnCurrency") or "points").lower()
    is_cashback = currency_raw in {"cash", "cashback"} or bool(int(detail.get("baseSpendEarnIsCash") or 0))

    earning_categories: list[dict[str, Any]] = []
    earning_merchants: list[dict[str, Any]] = []

    for rule in detail.get("spendBonusCategory") or []:
        if _is_merchant_bonus(rule):
            earning_merchants.append(_rule_to_merchant_group(rule))
        else:
            earning_categories.append(_rule_to_category(rule))

    base = float(detail.get("baseSpendAmount") or 1.0)
    has_base = any(
        re.search(r"all purchases|anything|all other", c.get("categoryName", ""), re.I)
        for c in earning_categories
    )
    if not has_base and base > 0:
        earning_categories.insert(
            0,
            {
                "categoryId": 0,
                "categoryName": "All Purchases",
                "multiplier": base,
                "startDate": None,
                "endDate": None,
                "description": f"{_format_multiplier(base)} on all purchases",
                "spendLimit": None,
                "spendLimitResetPeriod": None,
            },
        )

    card_type = (detail.get("cardType") or "Personal").strip().lower()
    if card_type not in {"personal", "business"}:
        card_type = "personal"

    payload: dict[str, Any] = {
        "cardId": card_id or stable_card_id(card_key),
        "cardKey": card_key,
        "issuingBank": detail.get("cardIssuer") or "",
        "cardName": detail.get("cardName") or "",
        "cardType": card_type,
        "isCashback": is_cashback,
        "isDiscontinued": not bool(int(detail.get("isActive", 1))),
        "shortEarningDescription": build_short_earning_description(detail),
        "awardWalletPointValue": awardwallet_point_value,
        "currencyName": detail.get("baseSpendEarnType") or detail.get("baseSpendEarnCategory") or "",
        "earningCategories": earning_categories,
        "earningMerchants": earning_merchants,
        "creditRewardsExtensions": {
            "cardUrl": detail.get("cardUrl"),
            "cardNetwork": detail.get("cardNetwork"),
            "annualFee": detail.get("annualFee"),
            "creditRewardsPointValue": float(detail.get("baseSpendEarnValuation") or 1.0),
            "creditRewardsCashValue": float(detail.get("baseSpendEarnCashValue") or 1.0),
            "signupBonusDesc": detail.get("signupBonusDesc") if detail.get("isSignupBonus") else None,
            "benefitCount": len(detail.get("benefit") or []),
            "transferPartnersSupported": True,
        },
    }
    return payload


def build_cards_response(
    cards: list[dict[str, Any]],
    *,
    aw_point_values: dict[str, float] | None = None,
) -> dict[str, Any]:
    aw_values = aw_point_values or {}
    mapped = []
    for detail in cards:
        key = detail.get("cardKey") or ""
        mapped.append(
            to_awardwallet_card(
                detail,
                awardwallet_point_value=aw_values.get(key),
            )
        )
    return {
        "cards": mapped,
        "meta": {
            "version": "1.0",
            "format": "awardwallet-credit-card-bonus-compatible",
            "source": "paycue-local",
            "reference": "https://awardwallet.com/api/cc",
        },
    }
