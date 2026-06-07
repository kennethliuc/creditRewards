"""Merchants agent — every catalog merchant, both channels."""

from __future__ import annotations

from credit_rewards.qa.agents.base import BaseQAAgent, url
from credit_rewards.qa.models import QAContext, QAAgentReport, QAResult

AUSTIN_LAT = 30.2672
AUSTIN_LNG = -97.7431


class MerchantsAgent(BaseQAAgent):
    agent_id = "merchants"
    agent_name = "Merchants Agent"

    def run(self, ctx: QAContext) -> QAAgentReport:
        return self._wrap(ctx, self._checks)

    def _checks(self, ctx: QAContext) -> list[QAResult]:
        results: list[QAResult] = []

        cfg = ctx.client.get(url(ctx, "/api/merchant/config"))
        if cfg.status_code == 200:
            data = cfg.json()
            gmaps = bool(data.get("googlePlacesEnabled"))
            results.append(
                QAResult(
                    "MCH-00",
                    "C",
                    "Merchant config",
                    "pass" if gmaps else "warn",
                    f"googlePlaces={gmaps}, nearby={data.get('nearbyStoresEnabled')}",
                )
            )

        nearby = ctx.client.get(
            url(ctx, "/api/merchant/nearby"),
            params={"latitude": AUSTIN_LAT, "longitude": AUSTIN_LNG, "limit": 5},
        )
        if nearby.status_code == 200:
            places = nearby.json().get("places") or []
            results.append(
                QAResult(
                    "MCH-01",
                    "C",
                    "Nearby stores API",
                    "pass" if places else "warn",
                    f"{len(places)} places",
                )
            )

        merchants_res = ctx.client.get(url(ctx, "/api/merchants"))
        merchants = merchants_res.json().get("merchants") or [] if merchants_res.status_code == 200 else []
        results.append(
            QAResult(
                "MCH-02",
                "C",
                "Merchant catalog list",
                "pass" if len(merchants) >= 25 else "fail",
                f"{len(merchants)} merchants",
            )
        )

        online_fail: list[str] = []
        instore_fail: list[str] = []
        for m in merchants:
            mid = m.get("id") or m.get("name")
            name = m.get("name") or mid
            domains = m.get("domains") or []
            if domains:
                res = ctx.client.post(
                    url(ctx, "/api/merchant/resolve"),
                    json={"merchant_url": f"https://www.{domains[0]}/", "purchase_channel": "online"},
                )
                if res.status_code != 200:
                    online_fail.append(str(name))
            res = ctx.client.post(
                url(ctx, "/api/merchant/resolve"),
                json={
                    "merchant_name": name,
                    "purchase_channel": "in_store",
                    "latitude": AUSTIN_LAT,
                    "longitude": AUSTIN_LNG,
                },
            )
            if res.status_code != 200:
                instore_fail.append(str(name))

        results.append(
            QAResult(
                "MCH-03",
                "C",
                "Resolve online (all merchants w/ domain)",
                "pass" if not online_fail else "fail",
                f"{len(merchants) - len(online_fail)}/{len([m for m in merchants if m.get('domains')])} OK"
                + (f"; fail: {online_fail[:8]}" if online_fail else ""),
                {"failures": online_fail},
            )
        )
        results.append(
            QAResult(
                "MCH-04",
                "C",
                "Resolve in-store (all merchants + GPS)",
                "pass" if not instore_fail else "fail",
                f"{len(merchants) - len(instore_fail)}/{len(merchants)} OK"
                + (f"; fail: {instore_fail[:8]}" if instore_fail else ""),
                {"failures": instore_fail},
            )
        )

        sug = ctx.client.get(url(ctx, "/api/merchants"), params={"q": "wal", "purchase_channel": "in_store"})
        suggestions = sug.json().get("suggestions") or [] if sug.status_code == 200 else []
        results.append(
            QAResult(
                "MCH-05",
                "C",
                "Merchant suggestions API",
                "pass" if suggestions else "fail",
                f"{len(suggestions)} suggestions for 'wal'",
            )
        )

        fuzzy = ctx.client.post(
            url(ctx, "/api/merchant/resolve"),
            json={
                "merchant_url": (
                    "https://checkout.stripe.com/pay/cs_test"
                    "?return_url=https%3A%2F%2Fwww.chipotle.com%2Forder"
                )
            },
        )
        if fuzzy.status_code == 200:
            data = fuzzy.json()
            ok = (data.get("best") or {}).get("merchantName") == "Chipotle"
            results.append(
                QAResult("MCH-06", "C", "Fuzzy checkout URL", "pass" if ok else "fail", str(data.get("best")))
            )

        return results
