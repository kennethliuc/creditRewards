from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_REWARDS_CC_URL = "https://rewards-credit-card-api.p.rapidapi.com"
DEFAULT_LOCAL_DATA_URL = "http://127.0.0.1:8080"
RAPIDAPI_HOST = "rewards-credit-card-api.p.rapidapi.com"


def upstream_api_enabled() -> bool:
    """Optional Rewards CC / RapidAPI — off by default; use committed reference + SQLite."""
    if os.getenv("CREDITREWARDS_USE_UPSTREAM_API", "").lower() not in {"1", "true", "yes"}:
        return False
    return bool(os.getenv("REWARDS_CC_API_KEY", "").strip())


class RewardsCCError(Exception):
    """Credit card data API request failed."""


class CardDataClient:
    """HTTP client for Rewards CC–compatible card data APIs (local or RapidAPI)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        use_local: bool | None = None,
        *,
        use_upstream: bool | None = None,
    ) -> None:
        if use_upstream is None:
            use_upstream = upstream_api_enabled()
        local_url = os.getenv("CREDITREWARDS_DATA_API_URL", "")
        if use_local is None:
            use_local = not use_upstream

        if use_upstream:
            self.api_key = api_key or os.getenv("REWARDS_CC_API_KEY", "")
            self.base_url = (
                base_url or os.getenv("REWARDS_CC_BASE_URL") or DEFAULT_REWARDS_CC_URL
            ).rstrip("/")
            self.provider = "rewardscc"
        elif use_local:
            self.base_url = (local_url or DEFAULT_LOCAL_DATA_URL).rstrip("/")
            self.api_key = ""
            self.provider = "local"
        else:
            self.base_url = ""
            self.api_key = ""
            self.provider = "offline"

    @property
    def is_configured(self) -> bool:
        if self.provider == "rewardscc":
            return bool(self.api_key)
        if self.provider == "local":
            return bool(self.base_url)
        return False

    def _headers(self) -> dict[str, str]:
        if self.provider != "rewardscc":
            return {}
        if not self.api_key:
            raise RewardsCCError(
                "REWARDS_CC_API_KEY is not set. PayCue uses local reference data and SQLite by default. "
                "Set CREDITREWARDS_USE_UPSTREAM_API=1 only for optional one-off sync commands."
            )
        return {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": RAPIDAPI_HOST,
        }

    def get(self, path: str) -> Any:
        if self.provider == "offline":
            raise RewardsCCError("Upstream API disabled (offline mode).")
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.get(url, headers=self._headers(), timeout=30.0)
        except httpx.HTTPError as exc:
            raise RewardsCCError(f"Network error calling {url}: {exc}") from exc

        if response.status_code == 429:
            raise RewardsCCError("Rate limited (429). Check your plan usage.")
        if response.status_code >= 400:
            raise RewardsCCError(f"API error {response.status_code}: {response.text[:200]}")

        return response.json()

    def card_detail(self, card_key: str) -> list[dict[str, Any]]:
        return self.get(f"creditcard-detail-bycard/{card_key}")

    def card_list(self) -> list[dict[str, Any]]:
        """Full US card list grouped by issuer (MEGA/SUPREME or local CardData API)."""
        payload = self.get("creditcard-cardlist")
        return payload if isinstance(payload, list) else []

    def search_cards(self, query: str) -> list[dict[str, Any]]:
        return self.get(f"creditcard-detail-namesearch/{query}")

    def category_list(self) -> list[dict[str, Any]]:
        return self.get("creditcard-spendbonuscategory-categorylist/")

    def category_cards(self, category_id: int) -> list[dict[str, Any]]:
        return self.get(f"creditcard-spendbonuscategory-categorycard/{category_id}")

    def transfer_program_list(self) -> list[dict[str, Any]]:
        return self.get("creditcard-pointtransfer-transferprogramlist/")

    def transfer_program_cards(self, partner_id: int) -> list[dict[str, Any]]:
        return self.get(f"creditcard-pointtransfer-transferprogramcard/{partner_id}")

    def api_usage(self, skey: str) -> list[dict[str, Any]]:
        return self.get(f"creditcard-apiusage/{skey}")


# Backward-compatible alias
RewardsCCClient = CardDataClient
