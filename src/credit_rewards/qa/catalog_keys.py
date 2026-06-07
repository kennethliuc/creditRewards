"""Fetch full catalog card keys from production deployment."""

from __future__ import annotations

from credit_rewards.qa.agents.base import url
from credit_rewards.qa.models import QAContext, QAResult


def fetch_catalog_keys(ctx: QAContext) -> tuple[list[str], list[QAResult]]:
    """Return all wallet card keys discoverable from the live deployment."""
    notes: list[QAResult] = []
    keys: set[str] = set()

    catalog_res = ctx.client.get(url(ctx, "/api/cards/catalog-keys"))
    if catalog_res.status_code == 200:
        payload = catalog_res.json()
        for key in payload.get("keys") or []:
            keys.add(str(key))
        notes.append(
            QAResult(
                "CAT-00",
                "D",
                "Catalog key enumeration",
                "pass",
                f"{len(keys)} keys via /api/cards/catalog-keys",
            )
        )
        return sorted(keys), notes

    cov = ctx.client.get(url(ctx, "/api/cards/coverage"))
    expected = int(cov.json().get("cardCount") or 0) if cov.status_code == 200 else 0

    reg = ctx.client.get(url(ctx, "/api/cards"))
    if reg.status_code == 200:
        for c in reg.json().get("cards") or []:
            if c.get("card_key"):
                keys.add(str(c["card_key"]))

    issuers_res = ctx.client.get(url(ctx, "/api/cards/issuers"))
    issuers = issuers_res.json().get("issuers") or [] if issuers_res.status_code == 200 else []
    for q in issuers:
        res = ctx.client.get(url(ctx, "/api/cards/by-issuer"), params={"q": q, "limit": 40})
        if res.status_code != 200:
            continue
        for m in res.json().get("matches") or []:
            if m.get("card_key"):
                keys.add(str(m["card_key"]))

    status = "warn" if expected and len(keys) < expected else "pass"
    notes.append(
        QAResult(
            "CAT-00",
            "D",
            "Catalog key enumeration",
            status,
            f"{len(keys)} keys via issuers fallback (expected {expected}); deploy catalog-keys endpoint for 100%",
        )
    )
    return sorted(keys), notes
