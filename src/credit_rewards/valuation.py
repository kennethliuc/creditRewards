from __future__ import annotations

from credit_rewards.co_brand_redemption_cpp import co_brand_redemption_cpp
from credit_rewards.models import CardProfile, EarnRule, PurchaseContext


def effective_cpp(card: CardProfile) -> float:
    if card.official_cpp > 0:
        return card.official_cpp
    return card.cpp_default


def effective_cpp_for_purchase(card: CardProfile, purchase: PurchaseContext) -> float:
    """Program CPP, or co-brand redemption CPP when merchant matches the card's loyalty program."""
    program = card.resolved_program or card.reward_program
    co_brand = co_brand_redemption_cpp(
        merchant_id=purchase.merchant_id,
        resolved_program=program,
    )
    if co_brand is not None:
        return co_brand
    return effective_cpp(card)


def _category_matches(rule_name: str, query: str) -> bool:
    a = rule_name.strip().lower()
    b = query.strip().lower()
    if a == b:
        return True
    # Query is the purchase/bonus category; rule names are often longer labels.
    # Only allow query-in-rule to avoid false positives (e.g. Travel rule vs "amextravel.com").
    return len(b) >= 3 and b in a


def _rule_active(rule: EarnRule, as_of) -> bool:
    if not rule.is_date_limit:
        return True
    if rule.limit_begin and as_of < rule.limit_begin:
        return False
    if rule.limit_end and as_of > rule.limit_end:
        return False
    return True


def best_multiplier(
    card: CardProfile,
    category: str,
    as_of=None,
    *,
    bonus_categories: list[str] | None = None,
) -> tuple[float, EarnRule | None]:
    from datetime import date

    today = as_of or date.today()
    categories: list[str] = []
    seen: set[str] = set()
    for name in [category, *(bonus_categories or [])]:
        text = (name or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        categories.append(text)

    best = card.base_spend_amount
    best_rule: EarnRule | None = None

    for cat in categories:
        for rule in card.category_rules:
            if not _category_matches(rule.category_name, cat):
                continue
            if not _rule_active(rule, today):
                continue
            if rule.multiplier > best:
                best = rule.multiplier
                best_rule = rule

    return best, best_rule


def _partner_bonus_applied(rule: EarnRule | None, purchase: PurchaseContext) -> bool:
    """True when earn uses the merchant's co-brand spend bucket (e.g. Delta Airlines at delta.com)."""
    if not rule or not purchase.bonus_categories:
        return False
    for cat in purchase.bonus_categories:
        if _category_matches(rule.category_name, cat):
            return True
    return False


def _is_percent_cash(card: CardProfile) -> bool:
    if card.valuate_as_points:
        return False
    currency = card.base_earn_currency
    program = card.reward_program.lower()
    return currency in {"cash", "cashback"} or "cash" in program and "point" not in program


def compute_earn_value(
    card: CardProfile,
    purchase: PurchaseContext,
) -> tuple[float, float, float, str, float, bool, bool]:
    """
    Returns (multiplier, points_earned, estimated_value_usd, reason, cpp_used,
    partner_checkout, partner_bonus).
    Uses co-brand redemption CPP when merchant matches the card's loyalty program.
    """
    from datetime import date

    as_of = purchase.as_of or date.today()
    bonus = purchase.bonus_categories
    if purchase.category and bonus:
        # primary category is always tried inside best_multiplier
        bonus = [c for c in bonus if c.strip().lower() != purchase.category.strip().lower()]
    multiplier, rule = best_multiplier(
        card,
        purchase.category,
        as_of,
        bonus_categories=bonus,
    )

    if _is_percent_cash(card):
        value = purchase.amount_usd * multiplier / 100.0
        reason = f"{multiplier:g}% cash back"
        if rule:
            reason = rule.description or f"{multiplier:g}% on {rule.category_name}"
        partner_bonus = _partner_bonus_applied(rule, purchase)
        return multiplier, multiplier * purchase.amount_usd / 100.0, value, reason, 1.0, False, partner_bonus

    program = card.resolved_program or card.reward_program
    partner_cpp = co_brand_redemption_cpp(
        merchant_id=purchase.merchant_id,
        resolved_program=program,
    )
    partner_checkout = partner_cpp is not None
    cpp = partner_cpp if partner_checkout else effective_cpp(card)
    partner_bonus = _partner_bonus_applied(rule, purchase)
    points = purchase.amount_usd * multiplier
    value = points * (cpp / 100.0)

    if rule:
        reason = rule.description or f"{multiplier:g}x on {rule.category_name}"
    else:
        reason = f"{multiplier:g}x base earn on {card.reward_program or 'purchases'}"

    cap_note = ""
    if rule and rule.is_spend_limit and rule.spend_limit > 0:
        cap_note = f" (cap ${rule.spend_limit:g}/{rule.spend_limit_reset_period or 'period'})"
    reason = f"{reason}{cap_note}"

    return multiplier, points, value, reason, cpp, partner_checkout, partner_bonus
