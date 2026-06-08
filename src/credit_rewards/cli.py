from __future__ import annotations

import typer

from credit_rewards.client import CardDataClient
from credit_rewards.models import PurchaseContext
from credit_rewards.official_cpp import (
    enrich_card_profile,
    fallback_program_table,
    resolve_card_official_cpp,
)
from credit_rewards.recommend import recommend_best_cards
from credit_rewards.wallet import load_wallet

app = typer.Typer(help="PayCue — which card at payment time?")


def _enrich_wallet(cards, program_table=None):
    table = program_table or fallback_program_table()
    enriched = []
    for card in cards:
        detail = {
            "cardKey": card.card_key,
            "baseSpendEarnType": card.reward_program,
            "baseSpendEarnCurrency": card.base_earn_currency,
        }
        cpp, program = resolve_card_official_cpp(card.card_key, detail, table)
        enriched.append(
            enrich_card_profile(card, official_cpp=cpp, resolved_program=program)
        )
    return enriched


@app.command()
def recommend(
    cards: str = typer.Option(..., help="Comma-separated cardKeys, e.g. amex-gold,chase-freedomflex"),
    category: str = typer.Option(..., help='Spend category, e.g. "Grocery Stores"'),
    amount: float = typer.Option(..., help="Purchase amount in USD"),
) -> None:
    """Recommend the best card from your wallet for a purchase."""
    card_keys = [c.strip() for c in cards.split(",") if c.strip()]
    wallet = _enrich_wallet(load_wallet(card_keys, CardDataClient()))
    purchase = PurchaseContext(category=category, amount_usd=amount)
    results = recommend_best_cards(wallet, purchase)

    if not results:
        typer.echo("No cards loaded.", err=True)
        raise typer.Exit(1)

    top = results[0]
    typer.echo(f"\nUse: {top.card_name}")
    typer.echo(f"Est. value: ${top.estimated_value_usd:.2f} on ${amount:.2f}")
    typer.echo(f"{top.reason}\n")
    typer.echo("All cards ranked:")
    for row in results:
        typer.echo(f"  #{row.rank} {row.card_name} — ${row.estimated_value_usd:.2f} ({row.multiplier:g}x)")


if __name__ == "__main__":
    app()
