"""QA Supervisor — orchestrates sub-agents against production deployment."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from credit_rewards.qa.agents import ALL_AGENTS
from credit_rewards.qa.models import QAAgentReport, QAContext, QAResult, summarize_results

DEFAULT_BASE_URL = "https://credit-rewards-production.up.railway.app"

# Agents safe to run in parallel (separate concerns / no shared browser).
PARALLEL_AGENTS = {"infra", "cards", "merchants", "auth", "aux"}
SEQUENTIAL_AGENTS = {"catalog_rec", "browser"}


class QASupervisor:
    """Monitor agent: dispatches QA sub-agents and merges reports."""

    def __init__(self, agents=None):
        self.agents = agents or ALL_AGENTS

    def run(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        run_browser: bool = True,
        recommend_workers: int = 10,
        parallel: bool = True,
        agent_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if "localhost" in base_url or "127.0.0.1" in base_url:
            raise ValueError(
                "Production QA must target the deployed URL, not localhost. "
                f"Use default {DEFAULT_BASE_URL} or pass --base-url explicitly for staging."
            )

        agents = self.agents
        if agent_ids:
            wanted = set(agent_ids)
            agents = [a for a in agents if a.agent_id in wanted]
            if not agents:
                raise ValueError(f"No agents matched: {agent_ids}")

        agent_reports: list[QAAgentReport] = []

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            ctx = QAContext(
                base_url=base_url.rstrip("/"),
                client=client,
                run_browser=run_browser,
                recommend_workers=recommend_workers,
            )

            parallel_agents = [a for a in agents if a.agent_id in PARALLEL_AGENTS]
            sequential_agents = [a for a in agents if a.agent_id in SEQUENTIAL_AGENTS]

            if parallel and len(parallel_agents) > 1:
                # httpx client is not thread-safe — each agent gets its own client clone context
                def run_agent(agent):
                    with httpx.Client(timeout=60.0, follow_redirects=True) as thread_client:
                        thread_ctx = QAContext(
                            base_url=ctx.base_url,
                            client=thread_client,
                            run_browser=False,
                            recommend_workers=recommend_workers,
                            merchant_starbucks_id=ctx.merchant_starbucks_id,
                        )
                        report = agent.run(thread_ctx)
                        if thread_ctx.merchant_starbucks_id:
                            ctx.merchant_starbucks_id = thread_ctx.merchant_starbucks_id
                        if thread_ctx.catalog_keys:
                            ctx.catalog_keys = thread_ctx.catalog_keys
                        return report

                with ThreadPoolExecutor(max_workers=min(6, len(parallel_agents))) as pool:
                    futures = {pool.submit(run_agent, agent): agent for agent in parallel_agents}
                    for fut in as_completed(futures):
                        agent_reports.append(fut.result())
            else:
                for agent in parallel_agents:
                    agent_reports.append(agent.run(ctx))

            for agent in sequential_agents:
                agent_reports.append(agent.run(ctx))

        all_results: list[QAResult] = []
        for report in sorted(agent_reports, key=lambda r: r.agent_id):
            all_results.extend(report.results)

        summary = summarize_results(all_results)
        per_agent = {r.agent_id: r.to_dict() for r in agent_reports}

        return {
            "supervisor": "QASupervisor",
            "base_url": base_url,
            "parallel": parallel,
            "recommend_workers": recommend_workers,
            "run_browser": run_browser,
            "summary": summary,
            "agents": per_agent,
            "results": [r.to_dict() for r in all_results],
        }


def run_production_qa(**kwargs) -> dict[str, Any]:
    """Entry point used by scripts/qa_production.py."""
    from credit_rewards.qa.report import write_reports

    payload = QASupervisor().run(**kwargs)
    paths = write_reports(payload)
    payload.update(paths)
    return payload
