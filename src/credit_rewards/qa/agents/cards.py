"""Cards agent — registry, issuers, images, coverage."""

from __future__ import annotations

from credit_rewards.qa.agents.base import BaseQAAgent, url
from credit_rewards.qa.models import QAContext, QAAgentReport, QAResult


class CardsAgent(BaseQAAgent):
    agent_id = "cards"
    agent_name = "Cards Agent"

    def run(self, ctx: QAContext) -> QAAgentReport:
        return self._wrap(ctx, self._checks)

    def _checks(self, ctx: QAContext) -> list[QAResult]:
        results: list[QAResult] = []

        cov = ctx.client.get(url(ctx, "/api/cards/coverage"))
        if cov.status_code != 200:
            results.append(QAResult("CRD-00", "B", "Catalog coverage", "fail", f"HTTP {cov.status_code}"))
            return results
        cov_data = cov.json()
        expected = int(cov_data.get("cardCount") or 0)
        results.append(
            QAResult(
                "CRD-00",
                "B",
                "Catalog coverage stats",
                "pass" if expected >= 500 else "warn",
                f"{expected} cards, {cov_data.get('issuerCount')} issuers",
                cov_data,
            )
        )

        reg = ctx.client.get(url(ctx, "/api/cards"))
        cards = reg.json().get("cards") or [] if reg.status_code == 200 else []
        with_img = sum(1 for c in cards if c.get("image_url"))
        img_files_ok = 0
        img_files_fail: list[str] = []
        for c in cards:
            key = c.get("card_key")
            if not key:
                continue
            fr = ctx.client.get(url(ctx, "/api/cards/image/file"), params={"card_key": key})
            if fr.status_code == 200:
                img_files_ok += 1
            else:
                img_files_fail.append(str(key))

        results.append(
            QAResult(
                "CRD-01",
                "B",
                "Registry cards (20) list + images",
                "pass" if len(cards) >= 20 and img_files_ok == len(cards) else "fail",
                f"{len(cards)} cards, {with_img} image_url, {img_files_ok} PNG files OK",
                {"failed_images": img_files_fail[:10]},
            )
        )

        issuers = ctx.client.get(url(ctx, "/api/cards/issuers"))
        issuer_list = issuers.json().get("issuers") or [] if issuers.status_code == 200 else []
        results.append(
            QAResult(
                "CRD-02",
                "B",
                "Issuer autocomplete list",
                "pass" if len(issuer_list) >= 20 else "fail",
                f"{len(issuer_list)} issuers",
            )
        )

        issuer_img_warn = 0
        issuer_img_ok = 0
        issuer_fail: list[str] = []
        for q in issuer_list:
            res = ctx.client.get(url(ctx, "/api/cards/by-issuer"), params={"q": q})
            if res.status_code != 200:
                issuer_fail.append(q)
                continue
            matches = res.json().get("matches") or []
            if not matches:
                issuer_fail.append(q)
                continue
            for m in matches:
                if m.get("image_url"):
                    issuer_img_ok += 1
                elif m.get("in_registry"):
                    issuer_img_warn += 1

        results.append(
            QAResult(
                "CRD-03",
                "B",
                "Issuer search (all issuers)",
                "pass" if not issuer_fail else "fail",
                f"failed issuers: {issuer_fail}" if issuer_fail else f"all {len(issuer_list)} issuers return matches",
            )
        )

        batch = ctx.client.post(url(ctx, "/api/cards/images"), json={"card_keys": [c["card_key"] for c in cards[:5]]})
        results.append(
            QAResult(
                "CRD-04",
                "B",
                "Batch card images API",
                "pass" if batch.status_code == 200 and batch.json().get("images") else "fail",
                f"HTTP {batch.status_code}",
            )
        )

        if issuer_img_ok == 0 and issuer_img_warn > 0:
            results.append(
                QAResult(
                    "CRD-05",
                    "B",
                    "Issuer search card art",
                    "warn",
                    "Registry cards in issuer results lack image_url on production",
                )
            )

        return results
