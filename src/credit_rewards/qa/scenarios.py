"""Backward-compatible re-exports; prefer credit_rewards.qa.models."""

from credit_rewards.qa.models import QAContext, QAResult

__all__ = ["QAContext", "QAResult", "API_CHECKS", "run_api_checks"]

# Legacy smoke checks — supervisor agents supersede these.
API_CHECKS: list = []


def run_api_checks(ctx: QAContext) -> list[QAResult]:
    from credit_rewards.qa.agents.infra import InfraAgent
    from credit_rewards.qa.agents.merchants import MerchantsAgent

    results: list[QAResult] = []
    results.extend(InfraAgent().run(ctx).results)
    results.extend(MerchantsAgent().run(ctx).results)
    return results
