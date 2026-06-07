"""Auxiliary pages — compare, validation dashboards."""

from __future__ import annotations

from credit_rewards.qa.agents.base import BaseQAAgent, url
from credit_rewards.qa.models import QAContext, QAAgentReport, QAResult


class AuxPagesAgent(BaseQAAgent):
    agent_id = "aux"
    agent_name = "Aux Pages Agent"

    def run(self, ctx: QAContext) -> QAAgentReport:
        return self._wrap(ctx, self._checks)

    def _checks(self, ctx: QAContext) -> list[QAResult]:
        results: list[QAResult] = []

        for path, rid, name in [
            ("/compare", "AUX-01", "Compare page"),
            ("/validation", "AUX-02", "Validation dashboard"),
            ("/validation-report", "AUX-03", "Validation report page"),
        ]:
            res = ctx.client.get(url(ctx, path))
            results.append(
                QAResult(rid, "G", name, "pass" if res.status_code == 200 else "fail", f"HTTP {res.status_code}")
            )

        for path, rid, name in [
            ("/api/compare", "AUX-04", "Compare API list"),
            ("/api/validation", "AUX-05", "Validation API"),
            ("/api/validation/monitor", "AUX-06", "Validation monitor"),
        ]:
            res = ctx.client.get(url(ctx, path))
            ok = res.status_code == 200
            if rid == "AUX-04" and ok:
                ok = bool(res.json())
            if rid == "AUX-05" and ok:
                ok = "core_ready" in res.json()
            results.append(QAResult(rid, "G", name, "pass" if ok else "fail", f"HTTP {res.status_code}"))

        detail = ctx.client.get(url(ctx, "/api/compare/amex-gold"))
        results.append(
            QAResult(
                "AUX-07",
                "G",
                "Compare card detail",
                "pass" if detail.status_code == 200 else "fail",
                f"HTTP {detail.status_code}",
            )
        )

        return results
