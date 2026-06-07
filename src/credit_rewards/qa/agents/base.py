"""Base class for QA sub-agents."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from credit_rewards.qa.models import QAAgentReport, QAContext, QAResult


def url(ctx: QAContext, path: str) -> str:
    return f"{ctx.base_url.rstrip('/')}{path}"


class BaseQAAgent(ABC):
    agent_id: str = "base"
    agent_name: str = "Base Agent"

    @abstractmethod
    def run(self, ctx: QAContext) -> QAAgentReport:
        raise NotImplementedError

    def _wrap(self, ctx: QAContext, fn) -> QAAgentReport:
        start = time.perf_counter()
        try:
            results = fn(ctx)
        except Exception as exc:
            results = [
                QAResult(
                    f"{self.agent_id}-ERR",
                    self.agent_id[0].upper(),
                    f"{self.agent_name} crashed",
                    "fail",
                    str(exc)[:300],
                )
            ]
        elapsed = int((time.perf_counter() - start) * 1000)
        return QAAgentReport(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            results=results,
            duration_ms=elapsed,
        )
