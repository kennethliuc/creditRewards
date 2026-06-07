from __future__ import annotations

from credit_rewards.models import CardProfile, EarnRule, PurchaseContext


def effective_cpp(card: CardProfile) -> float:
    if card.official_cpp > 0:
        return card.official_cpp
    return card.cpp_default


def _category_matches(rule_name: str, query: str) -> bool:
    a = rule_name.strip().lower()
    b = query.strip().lower()
    return a == b or b in a or a in b


def _rule_active(rule: EarnRule, as_of) -> bool:
    if not rule.is_date_limit:
        return True
    if rule.limit_begin and as_of < rule.limit_begin:
        return False
    if rule.limit_end and as_of > rule.limit_end:
        return False
    return True


def best_multiplier(card: CardProfile, category: str, as_of=None) -> tuple[float, EarnRule | None]:
    from datetime import date

    today = as_of or date.today()
    best = card.base_spend_amount
    best_rule: EarnRule | None = None

    for rule in card.category_rules:
        if not _category_matches(rule.category_name, category):
            continue
        if not _rule_active(rule, today):
            continue
        if rule.multiplier > best:
            best = rule.multiplier
            best_rule = rule

    return best, best_rule


def _is_percent_cash(card: CardProfile) -> bool:
    if card.valuate_as_points:
        return False
    currency = card.base_earn_currency
    program = card.reward_program.lower()
    return currency in {"cash", "cashback"} or "cash" in program and "point" not in program


def compute_earn_value(
    card: CardProfile,
    purchase: PurchaseContext,
) -> tuple[float, float, float, str]:
    """
    Returns (multiplier, points_earned, estimated_value_usd, reason).
    Single official CPP — no valuation modes.
    """
    from datetime import date

    as_of = purchase.as_of or date.today()
    multiplier, rule = best_multiplier(card, purchase.category, as_of)

    if _is_percent_cash(card):
        value = purchase.amount_usd * multiplier / 100.0
        reason = f"{multiplier:g}% cash back"
        if rule:
            reason = rule.description or f"{multiplier:g}% on {rule.category_name}"
        return multiplier, multiplier * purchase.amount_usd / 100.0, value, reason

    cpp = effective_cpp(card)
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

    return multiplier, points, value, reason
