"""Infra + PWA agent — pages, health, static assets."""

from __future__ import annotations

from credit_rewards.qa.agents.base import BaseQAAgent, url
from credit_rewards.qa.models import QAContext, QAAgentReport, QAResult


class InfraAgent(BaseQAAgent):
    agent_id = "infra"
    agent_name = "Infra & PWA Agent"

    def run(self, ctx: QAContext) -> QAAgentReport:
        return self._wrap(ctx, self._checks)

    def _checks(self, ctx: QAContext) -> list[QAResult]:
        results: list[QAResult] = []

        res = ctx.client.get(url(ctx, "/api/health"))
        results.append(
            QAResult("INF-01", "A", "Health endpoint", "pass" if res.status_code == 200 else "fail", f"HTTP {res.status_code}")
        )

        res = ctx.client.get(url(ctx, "/"))
        html = res.text
        markers = ["confirmModal", "wallet-ui.js", "view-pay", "view-manage", "view-savings-history"]
        missing = [m for m in markers if m not in html]
        results.append(
            QAResult(
                "INF-02",
                "A",
                "Homepage views & modals",
                "pass" if res.status_code == 200 and not missing else "fail",
                f"missing={missing}" if missing else "all views present",
            )
        )

        for path, rid, name in [
            ("/manifest.webmanifest", "PWA-01", "Web manifest"),
            ("/sw.js", "PWA-02", "Service worker"),
        ]:
            res = ctx.client.get(url(ctx, path))
            ok = res.status_code == 200
            if path.endswith("webmanifest") and ok:
                ok = bool(res.json().get("name"))
            if path.endswith("sw.js") and ok:
                ok = "install" in res.text
            results.append(QAResult(rid, "A", name, "pass" if ok else "fail", f"HTTP {res.status_code}"))

        static_paths = [
            "/static/wallet-ui.js",
            "/static/app.css",
            "/static/i18n.js",
            "/static/savings.js",
            "/static/pwa.js",
        ]
        bad = [p for p in static_paths if ctx.client.get(url(ctx, p)).status_code != 200]
        results.append(
            QAResult(
                "INF-03",
                "A",
                "Static bundles",
                "pass" if not bad else "fail",
                "all OK" if not bad else ", ".join(bad),
            )
        )

        mon = ctx.client.get(url(ctx, "/api/payment-ui/monitor"), params={"skip_tests": "true"})
        if mon.status_code == 200:
            data = mon.json()
            ready = bool(data.get("page_ready"))
            results.append(
                QAResult(
                    "INF-04",
                    "A",
                    "Payment UI monitor",
                    "pass" if ready else "warn",
                    f"page_ready={ready}",
                    {"blockers": data.get("blockers") or []},
                )
            )
        else:
            results.append(QAResult("INF-04", "A", "Payment UI monitor", "fail", f"HTTP {mon.status_code}"))

        return results
