from __future__ import annotations

from credit_rewards.models import CardProfile, PurchaseContext, Recommendation
from credit_rewards.valuation import compute_earn_value


def recommend_best_cards(
    wallet: list[CardProfile],
    purchase: PurchaseContext,
) -> list[Recommendation]:
    scored: list[Recommendation] = []

    for card in wallet:
        multiplier, points, value, reason, cpp_used, partner_checkout, partner_bonus = compute_earn_value(
            card, purchase
        )
        scored.append(
            Recommendation(
                card_key=card.card_key,
                card_name=card.card_name,
                multiplier=multiplier,
                points_earned=round(points, 2),
                estimated_value_usd=round(value, 2),
                cpp_used=round(cpp_used, 2),
                reason=reason,
                rank=0,
                valuate_as_points=card.valuate_as_points,
                resolved_program=card.resolved_program or card.reward_program,
                partner_checkout=partner_checkout,
                partner_bonus=partner_bonus,
            )
        )

    scored.sort(key=lambda r: (r.estimated_value_usd, r.partner_bonus), reverse=True)
    for idx, item in enumerate(scored, start=1):
        item.rank = idx
    return scored
