from __future__ import annotations

from typing import Any

from credit_rewards.ingest.scrape.base import IssuerScraper
from credit_rewards.ingest.scrape.parsers import (
    _collect_earn_rules,
    _html_embedded_reward_text,
    extract_earn_rules,
    meta_description,
    page_title,
    rules_to_spend_bonus_category,
)


_AMEX_CARD_CATEGORY_IDS: dict[str, set[int]] = {
    "amex-gold": {160378660, 1132334901, 2013874334, 1120466653},
    "amex-blue-cash-preferred": {
        1132334901,
        248970942,
        1982334500,
        1455345350,
        1468589631,
        11030576,
    },
}


class AmexScraper(IssuerScraper):
    issuer_name = "American Express"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        rules = extract_earn_rules(html, card_key=card_key)
        keep_ids = _AMEX_CARD_CATEGORY_IDS.get(card_key)
        if keep_ids:
            rules = [r for r in rules if int(r.category_meta["spendBonusCategoryId"]) in keep_ids]
        title = page_title(html) or card_key
        return {
            "cardKey": card_key,
            "cardIssuer": self.issuer_name,
            "cardName": title.split("|")[0].strip()[:120],
            "cardNetwork": "American Express",
            "cardType": "Personal",
            "cardUrl": source_url,
            "baseSpendAmount": 1.0,
            "baseSpendEarnType": "American Express Membership Rewards",
            "baseSpendEarnCategory": "Flex point",
            "baseSpendEarnCurrency": "points",
            "baseSpendEarnValuation": 2.2,
            "baseSpendEarnIsCash": 1,
            "baseSpendEarnCashValue": 0.6,
            "isActive": 1,
            "spendBonusCategory": rules_to_spend_bonus_category(rules),
            "benefit": [],
            "annualSpend": [],
            "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
        }


class ChaseScraper(IssuerScraper):
    issuer_name = "Chase"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        rules = extract_earn_rules(html)
        title = page_title(html) or card_key
        return {
            "cardKey": card_key,
            "cardIssuer": self.issuer_name,
            "cardName": title.split("|")[0].strip()[:120],
            "cardNetwork": "Visa",
            "cardType": "Personal",
            "cardUrl": source_url,
            "baseSpendAmount": 1.0,
            "baseSpendEarnType": "Chase Ultimate Rewards",
            "baseSpendEarnCategory": "Flex point",
            "baseSpendEarnCurrency": "points",
            "baseSpendEarnValuation": 2.0,
            "baseSpendEarnIsCash": 1,
            "baseSpendEarnCashValue": 1.0,
            "isActive": 1,
            "spendBonusCategory": rules_to_spend_bonus_category(rules),
            "benefit": [],
            "annualSpend": [],
            "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
        }


class CitiScraper(IssuerScraper):
    issuer_name = "Citi"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        rules = extract_earn_rules(html, card_key=card_key)
        if "double-cash" in card_key:
            rules = [
                r
                for r in rules
                if r.multiplier <= 2.01
                and "all" in (r.category_meta.get("spendBonusCategoryName") or "").lower()
            ]
        title = page_title(html) or card_key
        multiplier = 1.0
        if "double-cash" in card_key:
            multiplier = 2.0
        elif rules:
            multiplier = max(r.multiplier for r in rules)
        earn_type = "ThankYou Points" if "custom" in card_key or "strata" in card_key or "premier" in card_key else "Cash Back"
        is_cash = 1 if earn_type == "Cash Back" else 0
        return {
            "cardKey": card_key,
            "cardIssuer": self.issuer_name,
            "cardName": title.split("|")[0].strip()[:120],
            "cardNetwork": "Mastercard",
            "cardType": "Personal",
            "cardUrl": source_url,
            "baseSpendAmount": multiplier,
            "baseSpendEarnType": earn_type,
            "baseSpendEarnCategory": "Cash" if is_cash else "Flex point",
            "baseSpendEarnCurrency": "cash" if is_cash else "points",
            "baseSpendEarnValuation": 1.0 if is_cash else 1.6,
            "baseSpendEarnIsCash": is_cash,
            "baseSpendEarnCashValue": 1.0 if is_cash else 0.5,
            "isActive": 1,
            "spendBonusCategory": rules_to_spend_bonus_category(rules),
            "benefit": [],
            "annualSpend": [],
            "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
        }


def _points_detail(
    *,
    card_key: str,
    source_url: str,
    html: str,
    issuer: str,
    network: str,
    program: str,
    valuation: float = 1.0,
    cash_value: float = 1.0,
) -> dict[str, Any]:
    rules = extract_earn_rules(html)
    title = page_title(html) or card_key
    return {
        "cardKey": card_key,
        "cardIssuer": issuer,
        "cardName": title.split("|")[0].strip()[:120],
        "cardNetwork": network,
        "cardType": "Personal",
        "cardUrl": source_url,
        "baseSpendAmount": 1.0,
        "baseSpendEarnType": program,
        "baseSpendEarnCategory": "Flex point",
        "baseSpendEarnCurrency": "points",
        "baseSpendEarnValuation": valuation,
        "baseSpendEarnIsCash": 1,
        "baseSpendEarnCashValue": cash_value,
        "isActive": 1,
        "spendBonusCategory": rules_to_spend_bonus_category(rules),
        "benefit": [],
        "annualSpend": [],
        "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
    }


def _cash_detail(
    *,
    card_key: str,
    source_url: str,
    html: str,
    issuer: str,
    network: str,
    program: str = "Cash Back",
    base_rate: float = 1.0,
) -> dict[str, Any]:
    rules = extract_earn_rules(html)
    title = page_title(html) or card_key
    if rules:
        base_rate = max(base_rate, max(r.multiplier for r in rules))
    return {
        "cardKey": card_key,
        "cardIssuer": issuer,
        "cardName": title.split("|")[0].strip()[:120],
        "cardNetwork": network,
        "cardType": "Personal",
        "cardUrl": source_url,
        "baseSpendAmount": base_rate,
        "baseSpendEarnType": program,
        "baseSpendEarnCategory": "Cash",
        "baseSpendEarnCurrency": "cash",
        "baseSpendEarnValuation": 1.0,
        "baseSpendEarnIsCash": 1,
        "baseSpendEarnCashValue": 1.0,
        "isActive": 1,
        "spendBonusCategory": rules_to_spend_bonus_category(rules),
        "benefit": [],
        "annualSpend": [],
        "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
    }


class CapitalOneScraper(IssuerScraper):
    issuer_name = "Capital One"

    def _extract_rules(self, html: str, card_key: str) -> list:
        from credit_rewards.ingest.scrape.parsers import ParsedEarnRule

        rules = extract_earn_rules(html, card_key=card_key)
        if "venture-x" in card_key:
            rules = [
                r
                for r in rules
                if "(capital one)" in (r.category_meta.get("spendBonusCategoryName") or "").lower()
            ]
        embedded = _html_embedded_reward_text(html)
        if not embedded:
            return rules
        merged: dict[int, ParsedEarnRule] = {int(r.category_meta["spendBonusCategoryId"]): r for r in rules}
        for rule in _collect_earn_rules([embedded], allow_bare_multipliers=False):
            cat_id = int(rule.category_meta["spendBonusCategoryId"])
            existing = merged.get(cat_id)
            if not existing or rule.multiplier > existing.multiplier:
                merged[cat_id] = rule
        if "venture-x" in card_key:
            return [
                r
                for r in merged.values()
                if "(capital one)" in (r.category_meta.get("spendBonusCategoryName") or "").lower()
            ]
        return list(merged.values())

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        rules = self._extract_rules(html, card_key)
        if "savor" in card_key:
            title = page_title(html) or card_key
            return {
                "cardKey": card_key,
                "cardIssuer": self.issuer_name,
                "cardName": title.split("|")[0].strip()[:120],
                "cardNetwork": "Mastercard",
                "cardType": "Personal",
                "cardUrl": source_url,
                "baseSpendAmount": max((r.multiplier for r in rules), default=1.0),
                "baseSpendEarnType": "Cash Back",
                "baseSpendEarnCategory": "Cash",
                "baseSpendEarnCurrency": "cash",
                "baseSpendEarnValuation": 1.0,
                "baseSpendEarnIsCash": 1,
                "baseSpendEarnCashValue": 1.0,
                "isActive": 1,
                "spendBonusCategory": rules_to_spend_bonus_category(rules),
                "benefit": [],
                "annualSpend": [],
                "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
            }
        title = page_title(html) or card_key
        return {
            "cardKey": card_key,
            "cardIssuer": self.issuer_name,
            "cardName": title.split("|")[0].strip()[:120],
            "cardNetwork": "Visa",
            "cardType": "Personal",
            "cardUrl": source_url,
            "baseSpendAmount": 1.0,
            "baseSpendEarnType": "Capital One Miles",
            "baseSpendEarnCategory": "Flex point",
            "baseSpendEarnCurrency": "points",
            "baseSpendEarnValuation": 1.0,
            "baseSpendEarnIsCash": 1,
            "baseSpendEarnCashValue": 1.0,
            "isActive": 1,
            "spendBonusCategory": rules_to_spend_bonus_category(rules),
            "benefit": [],
            "annualSpend": [],
            "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
        }


class DiscoverScraper(IssuerScraper):
    issuer_name = "Discover"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        return _cash_detail(
            card_key=card_key,
            source_url=source_url,
            html=html,
            issuer=self.issuer_name,
            network="Discover",
        )


class WellsFargoScraper(IssuerScraper):
    issuer_name = "Wells Fargo"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        return _cash_detail(
            card_key=card_key,
            source_url=source_url,
            html=html,
            issuer=self.issuer_name,
            network="Visa",
            base_rate=2.0 if "active-cash" in card_key else 1.0,
        )


class BofaScraper(IssuerScraper):
    issuer_name = "Bank of America"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        rules = extract_earn_rules(html)
        embedded = _html_embedded_reward_text(html)
        if embedded:
            from credit_rewards.ingest.scrape.parsers import ParsedEarnRule

            merged: dict[int, ParsedEarnRule] = {int(r.category_meta["spendBonusCategoryId"]): r for r in rules}
            for rule in _collect_earn_rules([embedded], allow_bare_multipliers=False):
                cat_id = int(rule.category_meta["spendBonusCategoryId"])
                existing = merged.get(cat_id)
                if not existing or rule.multiplier > existing.multiplier:
                    merged[cat_id] = rule
            rules = list(merged.values())
        title = page_title(html) or card_key
        base_rate = max((r.multiplier for r in rules), default=1.0)
        return {
            "cardKey": card_key,
            "cardIssuer": self.issuer_name,
            "cardName": title.split("|")[0].strip()[:120],
            "cardNetwork": "Visa",
            "cardType": "Personal",
            "cardUrl": source_url,
            "baseSpendAmount": base_rate,
            "baseSpendEarnType": "Cash Back",
            "baseSpendEarnCategory": "Cash",
            "baseSpendEarnCurrency": "cash",
            "baseSpendEarnValuation": 1.0,
            "baseSpendEarnIsCash": 1,
            "baseSpendEarnCashValue": 1.0,
            "isActive": 1,
            "spendBonusCategory": rules_to_spend_bonus_category(rules),
            "benefit": [],
            "annualSpend": [],
            "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
        }


class AppleScraper(IssuerScraper):
    issuer_name = "Goldman Sachs"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        return _cash_detail(
            card_key=card_key,
            source_url=source_url,
            html=html,
            issuer=self.issuer_name,
            network="Mastercard",
            program="Cash Back",
        )


class BiltScraper(IssuerScraper):
    issuer_name = "Wells Fargo"

    def parse_card_page(self, html: str, card_key: str, source_url: str) -> dict[str, Any]:
        rules = extract_earn_rules(html, card_key=card_key)
        title = page_title(html) or card_key
        return {
            "cardKey": card_key,
            "cardIssuer": "Bilt",
            "cardName": title.split("|")[0].strip()[:120],
            "cardNetwork": "Mastercard",
            "cardType": "Personal",
            "cardUrl": source_url,
            "baseSpendAmount": 1.0,
            "baseSpendEarnType": "Bilt Points",
            "baseSpendEarnCategory": "Flex point",
            "baseSpendEarnCurrency": "points",
            "baseSpendEarnValuation": 1.0,
            "baseSpendEarnIsCash": 1,
            "baseSpendEarnCashValue": 1.0,
            "isActive": 1,
            "spendBonusCategory": rules_to_spend_bonus_category(rules),
            "benefit": [],
            "annualSpend": [],
            "_scrapeMeta": {"description": meta_description(html), "ruleCount": len(rules)},
        }


PARSERS: dict[str, type[IssuerScraper]] = {
    "amex": AmexScraper,
    "chase": ChaseScraper,
    "citi": CitiScraper,
    "capitalone": CapitalOneScraper,
    "discover": DiscoverScraper,
    "wellsfargo": WellsFargoScraper,
    "bofa": BofaScraper,
    "apple": AppleScraper,
    "bilt": BiltScraper,
}


def get_scraper(parser_name: str) -> IssuerScraper:
    cls = PARSERS.get(parser_name.lower())
    if not cls:
        from credit_rewards.ingest.scrape.base import GenericIssuerScraper

        return GenericIssuerScraper()
    return cls()
