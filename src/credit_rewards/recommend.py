from __future__ import annotations

from credit_rewards.models import CardProfile, PurchaseContext, Recommendation
from credit_rewards.valuation import compute_earn_value, effective_cpp


def recommend_best_cards(
    wallet: list[CardProfile],
    purchase: PurchaseContext,
) -> list[Recommendation]:
    scored: list[Recommendation] = []

    for card in wallet:
        multiplier, points, value, reason = compute_earn_value(card, purchase)
        scored.append(
            Recommendation(
                card_key=card.card_key,
                card_name=card.card_name,
                multiplier=multiplier,
                points_earned=points,
                estimated_value_usd=round(value, 2),
                cpp_used=round(effective_cpp(card), 2),
                reason=reason,
                rank=0,
            )
        )

    scored.sort(key=lambda r: r.estimated_value_usd, reverse=True)
    for idx, item in enumerate(scored, start=1):
        item.rank = idx
    return scored
