"""Auth + wallet API agent (backend; UI not exposed)."""

from __future__ import annotations

import uuid

from credit_rewards.qa.agents.base import BaseQAAgent, url
from credit_rewards.qa.models import QAContext, QAAgentReport, QAResult


class AuthApiAgent(BaseQAAgent):
    agent_id = "auth"
    agent_name = "Auth & Wallet API Agent"

    def run(self, ctx: QAContext) -> QAAgentReport:
        return self._wrap(ctx, self._checks)

    def _checks(self, ctx: QAContext) -> list[QAResult]:
        results: list[QAResult] = []
        email = f"qa-{uuid.uuid4().hex[:10]}@example.com"
        password = "QaTestPass123!"

        reg = ctx.client.post(
            url(ctx, "/api/auth/register"),
            json={
                "email": email,
                "password": password,
                "cards": [{"card_key": "amex-gold", "card_name": "Amex Gold"}],
            },
        )
        results.append(
            QAResult(
                "AUTH-01",
                "F",
                "Register + session",
                "pass" if reg.status_code == 200 else "fail",
                f"HTTP {reg.status_code}: {reg.text[:120]}",
            )
        )
        if reg.status_code != 200:
            return results

        me = ctx.client.get(url(ctx, "/api/auth/me"))
        results.append(
            QAResult(
                "AUTH-02",
                "F",
                "Auth me",
                "pass" if me.status_code == 200 and me.json().get("email") == email else "fail",
                me.text[:80],
            )
        )

        wallet = ctx.client.get(url(ctx, "/api/wallet"))
        cards = wallet.json().get("cards") or [] if wallet.status_code == 200 else []
        results.append(
            QAResult(
                "AUTH-03",
                "F",
                "Wallet GET",
                "pass" if wallet.status_code == 200 and len(cards) >= 1 else "fail",
                f"{len(cards)} cards",
            )
        )

        put = ctx.client.put(
            url(ctx, "/api/wallet"),
            json={
                "cards": [
                    {"card_key": "amex-gold", "card_name": "Amex Gold"},
                    {"card_key": "chase-sapphirepreferred", "card_name": "Sapphire"},
                ]
            },
        )
        results.append(
            QAResult("AUTH-04", "F", "Wallet PUT", "pass" if put.status_code == 200 else "fail", put.text[:80])
        )

        logout = ctx.client.post(url(ctx, "/api/auth/logout"))
        results.append(
            QAResult("AUTH-05", "F", "Logout", "pass" if logout.status_code == 200 else "fail", f"HTTP {logout.status_code}")
        )

        login = ctx.client.post(url(ctx, "/api/auth/login"), json={"email": email, "password": password})
        results.append(
            QAResult("AUTH-06", "F", "Login", "pass" if login.status_code == 200 else "fail", login.text[:80])
        )

        return results
