"""Catalog recommend agent — recommend API for every catalog card."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from credit_rewards.qa.agents.base import BaseQAAgent, url
from credit_rewards.qa.catalog_keys import fetch_catalog_keys
from credit_rewards.qa.models import QAContext, QAAgentReport, QAResult


class CatalogRecommendAgent(BaseQAAgent):
    agent_id = "catalog_rec"
    agent_name = "Catalog Recommend Agent"

    def run(self, ctx: QAContext) -> QAAgentReport:
        return self._wrap(ctx, self._checks)

    def _resolve_starbucks(self, ctx: QAContext) -> str | None:
        if ctx.merchant_starbucks_id:
            return ctx.merchant_starbucks_id
        res = ctx.client.post(
            url(ctx, "/api/merchant/resolve"),
            json={"merchant_name": "Starbucks", "purchase_channel": "in_store"},
        )
        if res.status_code != 200:
            return None
        mid = (res.json().get("best") or {}).get("merchantId")
        ctx.merchant_starbucks_id = str(mid or "starbucks")
        return ctx.merchant_starbucks_id

    def _recommend_one(self, base_url: str, merchant_id: str, card_key: str) -> tuple[str, bool, str]:
        try:
            with httpx.Client(timeout=90.0, follow_redirects=True) as client:
                res = client.post(
                    f"{base_url.rstrip('/')}/api/recommend",
                    json={"merchant_id": merchant_id, "amount_usd": 25, "card_keys": [card_key]},
                )
                if res.status_code == 200:
                    data = res.json()
                    if data.get("card_count", 0) >= 1:
                        return card_key, True, "ok"
                    return card_key, False, "empty rankings"
                try:
                    detail = res.json().get("detail", res.text)
                except Exception:
                    detail = res.text
                return card_key, False, str(detail)[:200]
        except httpx.TimeoutException:
            return card_key, False, "timeout"
        except Exception as exc:
            return card_key, False, str(exc)[:120]

    def _checks(self, ctx: QAContext) -> list[QAResult]:
        results: list[QAResult] = []

        keys, key_notes = fetch_catalog_keys(ctx)
        results.extend(key_notes)
        ctx.catalog_keys = keys

        if not keys:
            results.append(QAResult("CAT-01", "D", "Full catalog recommend sweep", "fail", "No catalog keys"))
            return results

        merchant_id = self._resolve_starbucks(ctx)
        if not merchant_id:
            results.append(QAResult("CAT-01", "D", "Full catalog recommend sweep", "fail", "Could not resolve Starbucks"))
            return results

        passed = 0
        failed: list[tuple[str, str]] = []
        workers = max(1, min(ctx.recommend_workers, 4))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._recommend_one, ctx.base_url, merchant_id, key): key for key in keys
            }
            for fut in as_completed(futures):
                try:
                    key, ok, detail = fut.result(timeout=120)
                except Exception as exc:
                    key = futures[fut]
                    ok, detail = False, str(exc)[:120]
                if ok:
                    passed += 1
                else:
                    failed.append((key, detail))

        # Sequential retry — parallel import can race Rewards CC API rate limits.
        retry_passed = 0
        still_failed: list[tuple[str, str]] = []
        for key, _detail in failed:
            ok = False
            last_detail = _detail
            for _ in range(3):
                _key, ok, last_detail = self._recommend_one(ctx.base_url, merchant_id, key)
                if ok:
                    retry_passed += 1
                    break
                time.sleep(0.25)
            if not ok:
                still_failed.append((key, last_detail))

        passed += retry_passed
        failed = still_failed

        fail_count = len(failed)
        results.append(
            QAResult(
                "CAT-01",
                "D",
                "Full catalog recommend (in-store Starbucks)",
                "pass" if fail_count == 0 else "fail",
                f"{passed}/{len(keys)} cards OK, {fail_count} failed",
                {
                    "passed": passed,
                    "total": len(keys),
                    "failures": [{"card_key": k, "detail": d} for k, d in failed[:100]],
                    "failure_count": fail_count,
                },
            )
        )

        if failed:
            sample = ", ".join(k for k, _ in failed[:12])
            results.append(
                QAResult(
                    "CAT-02",
                    "D",
                    "Failed card keys (sample)",
                    "fail",
                    sample + ("…" if len(failed) > 12 else ""),
                    {"all_failures": [k for k, _ in failed]},
                )
            )

        reg = ctx.client.get(url(ctx, "/api/cards"))
        registry_keys = [c["card_key"] for c in (reg.json().get("cards") or [])] if reg.status_code == 200 else []
        reg_failed = [k for k, _ in failed if k in registry_keys]
        results.append(
            QAResult(
                "CAT-03",
                "D",
                "Registry cards recommend",
                "pass" if not reg_failed else "fail",
                f"{len(registry_keys) - len(reg_failed)}/{len(registry_keys)} registry OK",
                {"registry_failures": reg_failed},
            )
        )

        return results
