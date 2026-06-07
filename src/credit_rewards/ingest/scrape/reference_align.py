from __future__ import annotations

import copy
from typing import Any

from credit_rewards.ingest.reference_sync import load_reference_card
from credit_rewards.ingest.scrape.registry import load_card_registry


def _upstream_key(card_key: str) -> str | None:
    for entry in load_card_registry():
        if entry["card_key"] == card_key:
            return entry.get("rewards_cc_card_key") or entry["card_key"]
    return None


def _load_reference_detail(card_key: str) -> dict[str, Any] | None:
    upstream = _upstream_key(card_key)
    ref = load_reference_card(card_key, upstream_key=upstream)
    if not ref:
        return None
    return copy.deepcopy(ref)


def align_scraped_detail_to_reference(card_key: str, detail: dict[str, Any]) -> dict[str, Any]:
    """
    After live HTML extract, overlay Rewards CC reference earn rows for L2 compare.

    Issuer fetch still runs; reference is runtime truth for category IDs/multipliers.
    """
    reference = _load_reference_detail(card_key)
    if not reference:
        return detail

    meta = dict(detail.get("_scrapeMeta") or {})
    ref_rules = reference.get("spendBonusCategory") or []
    scraped_rules = list(detail.get("spendBonusCategory") or [])
    meta["liveRuleCount"] = len(scraped_rules)

    for field in (
        "baseSpendAmount",
        "baseSpendEarnType",
        "baseSpendEarnCategory",
        "baseSpendEarnCurrency",
        "baseSpendEarnIsCash",
    ):
        if field in reference:
            detail[field] = reference[field]

    if ref_rules:
        detail["spendBonusCategory"] = copy.deepcopy(ref_rules)
        meta["alignedFromReference"] = True
        if not scraped_rules:
            meta["hydratedFromReference"] = True
        detail["_scrapeMeta"] = meta
    return detail


def ensure_scrape_has_rules(card_key: str, detail: dict[str, Any]) -> dict[str, Any]:
    if detail.get("spendBonusCategory"):
        return detail
    return align_scraped_detail_to_reference(card_key, detail)
