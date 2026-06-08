"""Merchant payment acceptance (card network) and in-store spend context → category."""

from __future__ import annotations

import re
from typing import Any

from credit_rewards.merchant_co_brand import canonical_merchant_id_for_purchase, clean_merchant_display_name
from credit_rewards.merchant_mapping import load_merchant_catalog
from credit_rewards.models import CardProfile


def _normalize_label(text: str) -> str:
    return re.sub(r"[^\w\s]+", " ", str(text or "").lower()).strip()


def normalize_card_network(raw: str) -> str:
    """Map assorted network labels to canonical names."""
    n = (raw or "").strip().lower()
    if not n:
        return ""
    if "american express" in n or n == "amex" or " amex" in f" {n} ":
        return "American Express"
    if "mastercard" in n or "master card" in n or n == "mc":
        return "Mastercard"
    if "visa" in n:
        return "Visa"
    if "discover" in n:
        return "Discover"
    return raw.strip()


def infer_card_network(card: CardProfile) -> str:
    """Network from card detail, with name-based fallback."""
    net = normalize_card_network(card.card_network)
    if net:
        return net
    name = card.card_name.lower()
    if "american express" in name or " amex" in name or name.startswith("amex"):
        return "American Express"
    if "mastercard" in name or " master card" in name:
        return "Mastercard"
    if "visa" in name:
        return "Visa"
    if "discover" in name:
        return "Discover"
    return ""


def _catalog_row(
    merchant_id: str | None,
    merchant_name: str | None,
    *,
    catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    mid = canonical_merchant_id_for_purchase(
        merchant_id=merchant_id,
        merchant_name=merchant_name,
        catalog=catalog,
    )
    if not mid or str(mid).startswith(("osm:", "gmaps:", "web:")):
        mid = (merchant_id or "").strip()
    if not mid or mid.startswith(("osm:", "gmaps:", "web:")):
        return None
    for row in catalog or load_merchant_catalog():
        if str(row.get("id") or "") == mid:
            return row
    return None


def resolve_spend_category_for_merchant(
    *,
    merchant_id: str | None,
    merchant_name: str | None,
    purchase_channel: str,
    default_category: str,
    catalog: list[dict[str, Any]] | None = None,
) -> str:
    """
    Map merchant + POI name to spend category (e.g. Costco gas → Gas Stations).

    Uses optional `spend_contexts` on catalog rows; falls back to channel default category.
    """
    row = _catalog_row(merchant_id, merchant_name, catalog=catalog)
    if not row:
        return default_category

    contexts = row.get("spend_contexts") or {}
    if not isinstance(contexts, dict):
        return default_category

    haystack = _normalize_label(clean_merchant_display_name(merchant_name or row.get("name") or ""))
    for entry in contexts.get("matches") or []:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "").strip()
        if not category:
            continue
        for pattern in entry.get("patterns") or []:
            pat = _normalize_label(str(pattern))
            if pat and pat in haystack:
                return category

    channel = purchase_channel if purchase_channel in {"online", "in_store"} else "in_store"
    fallback_key = f"default_{channel}"
    fallback = contexts.get(fallback_key) or contexts.get("default")
    if fallback:
        return str(fallback).strip()
    return default_category


def accepted_networks_for_merchant(
    *,
    merchant_id: str | None,
    merchant_name: str | None,
    purchase_channel: str,
    catalog: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return allowed card networks at checkout, or [] if no restriction."""
    row = _catalog_row(merchant_id, merchant_name, catalog=catalog)
    if not row:
        return []

    raw = row.get("accepted_networks") or {}
    if isinstance(raw, list):
        return [normalize_card_network(str(n)) for n in raw if str(n).strip()]

    channel = purchase_channel if purchase_channel in {"online", "in_store"} else "in_store"
    nets = raw.get(channel) or raw.get("in_store") or raw.get("online") or []
    return [normalize_card_network(str(n)) for n in nets if str(n).strip()]


def payment_restriction_note(
    *,
    merchant_id: str | None,
    merchant_name: str | None,
    purchase_channel: str,
    catalog: list[dict[str, Any]] | None = None,
) -> str | None:
    row = _catalog_row(merchant_id, merchant_name, catalog=catalog)
    if not row:
        return None
    notes = row.get("payment_notes") or {}
    if isinstance(notes, str) and notes.strip():
        return notes.strip()
    if not isinstance(notes, dict):
        return None
    channel = purchase_channel if purchase_channel in {"online", "in_store"} else "in_store"
    text = notes.get(channel) or notes.get("in_store") or notes.get("default")
    return str(text).strip() if text else None


def partition_wallet_by_payment(
    wallet: list[CardProfile],
    *,
    accepted_networks: list[str],
) -> tuple[list[CardProfile], list[dict[str, str]]]:
    """Split wallet into cards that can pay at this merchant vs excluded."""
    if not accepted_networks:
        return wallet, []

    allowed = {normalize_card_network(n) for n in accepted_networks if n}
    eligible: list[CardProfile] = []
    excluded: list[dict[str, str]] = []
    networks_label = ", ".join(sorted(allowed))

    for card in wallet:
        net = infer_card_network(card)
        if net and net in allowed:
            eligible.append(card)
            continue
        if not net:
            excluded.append(
                {
                    "card_key": card.card_key,
                    "card_name": card.card_name,
                    "reason": f"Card network unknown; {networks_label} required here.",
                }
            )
            continue
        excluded.append(
            {
                "card_key": card.card_key,
                "card_name": card.card_name,
                "reason": f"{net} not accepted (Visa only at this store)." if allowed == {"Visa"} else f"{net} not accepted; use {networks_label}.",
            }
        )
    return eligible, excluded
