from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from credit_rewards.datastore.repository import CardDataRepository


class IssuerScraper(ABC):
    issuer_name: str

    @abstractmethod
    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        """Return Rewards CC–shaped card detail dict."""

    def fetch(self, url: str) -> str:
        response = httpx.get(
            url,
            timeout=30.0,
            headers={"User-Agent": "PayCueBot/0.1 (+research; contact: local-dev)"},
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text


class GenericIssuerScraper(IssuerScraper):
    """
    Phase-1 scraper: fetch issuer page and store raw HTML reference + minimal metadata.
    Structured field extraction is issuer-specific and added incrementally.
    """

    issuer_name = "Generic"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        title_match = re.search(r"<title>([^<]+)</title>", html, re.I)
        title = title_match.group(1).strip() if title_match else card_key
        return {
            "cardKey": card_key,
            "cardIssuer": "Unknown",
            "cardName": title[:120],
            "cardNetwork": "",
            "cardUrl": source_url,
            "baseSpendAmount": 1.0,
            "baseSpendEarnType": "",
            "baseSpendEarnCurrency": "points",
            "baseSpendEarnValuation": 1.0,
            "baseSpendEarnIsCash": 0,
            "baseSpendEarnCashValue": 1.0,
            "isActive": 1,
            "spendBonusCategory": [],
            "benefit": [],
            "annualSpend": [],
            "_scrapeNote": "Generic parser — enrich manually or add issuer-specific scraper",
        }


def scrape_and_upsert(
    repo: CardDataRepository,
    card_key: str,
    source_url: str,
    scraper: IssuerScraper | None = None,
) -> dict[str, Any]:
    scraper = scraper or GenericIssuerScraper()
    html = scraper.fetch(source_url)
    detail = scraper.parse_card_page(html, card_key, source_url)
    repo.upsert_card(detail, source_url=source_url, source_type="scrape")
    return detail
