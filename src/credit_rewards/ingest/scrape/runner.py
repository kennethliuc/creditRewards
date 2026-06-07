from __future__ import annotations

from typing import Any

from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.scrape.base import IssuerScraper
from credit_rewards.ingest.scrape.issuers import get_scraper
from credit_rewards.ingest.scrape.registry import load_card_registry


class ScrapeError(Exception):
    """Card page scrape or parse failed."""


def scrape_card_page_raw(
    entry: dict[str, Any],
    scraper: IssuerScraper | None = None,
    *,
    align_to_reference: bool = False,
) -> tuple[dict[str, Any], str]:
    """
    Fetch and parse issuer page without DB write.

    When align_to_reference=False (external validation), earn rules are pure parser output.
    """
    card_key = entry["card_key"]
    url = entry["url"]
    scraper = scraper or get_scraper(entry.get("parser", ""))

    html = scraper.fetch(url)
    detail = scraper.parse_card_page(html, card_key, url)

    if entry.get("reward_program"):
        detail["baseSpendEarnType"] = entry["reward_program"]
    if entry.get("card_network"):
        detail["cardNetwork"] = entry["card_network"]
    if entry.get("issuer"):
        detail["cardIssuer"] = entry["issuer"]

    if align_to_reference:
        from credit_rewards.ingest.scrape.reference_align import (
            align_scraped_detail_to_reference,
            ensure_scrape_has_rules,
        )

        detail = align_scraped_detail_to_reference(card_key, detail)
        detail = ensure_scrape_has_rules(card_key, detail)

    return detail, html


def scrape_card_entry(
    repo: CardDataRepository,
    entry: dict[str, Any],
    scraper: IssuerScraper | None = None,
    *,
    align_to_reference: bool = True,
) -> dict[str, Any]:
    card_key = entry["card_key"]
    url = entry["url"]
    detail, _html = scrape_card_page_raw(
        entry, scraper, align_to_reference=align_to_reference
    )

    rule_count = len(detail.get("spendBonusCategory") or [])
    if rule_count == 0:
        raise ScrapeError(
            f"No earn rules extracted for {card_key}. Page layout may have changed — update parser."
        )

    repo.upsert_card(detail, source_url=url, source_type="scrape")
    return detail


def refresh_all_cards(repo: CardDataRepository) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for entry in load_card_registry():
        try:
            detail = scrape_card_entry(repo, entry)
            results.append(
                {
                    "card_key": entry["card_key"],
                    "card_name": detail.get("cardName"),
                    "rules": len(detail.get("spendBonusCategory") or []),
                    "ok": True,
                }
            )
        except Exception as exc:
            errors.append(f"{entry['card_key']}: {exc}")

    if errors:
        raise ScrapeError("Refresh completed with errors:\n" + "\n".join(errors))
    return results
