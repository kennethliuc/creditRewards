from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

AWARDWALLET_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "awardwallet"
DEFAULT_BASE_URL = "https://us-cc-api.awardwallet.com/v1"


class AwardWalletCCError(Exception):
    pass


def _auth_header() -> str:
    user = os.getenv("AWARDWALLET_CC_API_USER", "").strip()
    password = os.getenv("AWARDWALLET_CC_API_PASSWORD", "").strip()
    if not user or not password:
        raise AwardWalletCCError(
            "Set AWARDWALLET_CC_API_USER and AWARDWALLET_CC_API_PASSWORD in .env "
            "(request credentials at https://awardwallet.com/api/cc)"
        )
    return f"{user}:{password}"


def fetch_awardwallet_cards(*, show_expired: bool = False) -> dict[str, Any]:
    """Fetch AwardWallet Credit Card Bonus API /v1/cards (commercial API key required)."""
    base = os.getenv("AWARDWALLET_CC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    params = {"showExpiredBonuses": "true"} if show_expired else None
    with httpx.Client(timeout=60.0) as client:
        response = client.get(
            f"{base}/cards",
            headers={"X-Authentication": _auth_header()},
            params=params,
        )
    if response.status_code == 401:
        raise AwardWalletCCError("AwardWallet authentication failed (401)")
    if response.status_code >= 400:
        raise AwardWalletCCError(f"AwardWallet API error {response.status_code}: {response.text[:200]}")
    return response.json()


def cache_awardwallet_cards(payload: dict[str, Any], *, cache_dir=AWARDWALLET_CACHE_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "cards.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_awardwallet_point_values(*, cache_dir=AWARDWALLET_CACHE_DIR) -> dict[str, float]:
    """
    Load awardWalletPointValue keyed by normalized card name from cached AW response.
    Match to local cards via fuzzy name in sync step / registry.
    """
    path = cache_dir / "cards.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    values: dict[str, float] = {}
    for card in payload.get("cards") or []:
        name = (card.get("cardName") or "").strip().lower()
        val = card.get("awardWalletPointValue")
        if name and val is not None:
            values[name] = float(val)
    return values


def _normalize_name(name: str) -> str:
    cleaned = name.lower().replace("®", "").replace("™", "")
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def load_awardwallet_by_registry_key(
    registry: list[dict[str, Any]],
    *,
    cache_dir=AWARDWALLET_CACHE_DIR,
) -> dict[str, float]:
    """Map local card_key → awardWalletPointValue using registry + fuzzy name match."""
    path = cache_dir / "cards.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    aw_cards = payload.get("cards") or []
    aw_by_norm = {_normalize_name(c.get("cardName") or ""): c for c in aw_cards}

    result: dict[str, float] = {}
    for entry in registry:
        card_key = entry["card_key"]
        candidates = [
            entry.get("awardwallet_card_name") or "",
            entry.get("card_name") or "",
            card_key.replace("-", " "),
        ]
        matched = None
        for raw in candidates:
            norm = _normalize_name(raw)
            if not norm:
                continue
            if norm in aw_by_norm:
                matched = aw_by_norm[norm]
                break
            for aw_norm, row in aw_by_norm.items():
                if norm in aw_norm or aw_norm in norm:
                    matched = row
                    break
            if matched:
                break
        if matched and matched.get("awardWalletPointValue") is not None:
            result[card_key] = float(matched["awardWalletPointValue"])
    return result
