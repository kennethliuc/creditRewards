"""Shared QA models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

QASStatus = Literal["pass", "fail", "warn", "skip"]


@dataclass
class QAResult:
    id: str
    track: str
    name: str
    status: QASStatus
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "track": self.track,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class QAContext:
    base_url: str
    client: Any  # httpx.Client
    run_browser: bool = True
    recommend_workers: int = 10
    browser_available: bool = False
    catalog_keys: list[str] = field(default_factory=list)
    merchant_starbucks_id: str = "starbucks"


@dataclass
class QAAgentReport:
    agent_id: str
    agent_name: str
    results: list[QAResult] = field(default_factory=list)
    duration_ms: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "duration_ms": self.duration_ms,
            "notes": self.notes,
            "results": [r.to_dict() for r in self.results],
            "summary": summarize_results(self.results),
        }


def summarize_results(results: list[QAResult]) -> dict[str, Any]:
    counts = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    blockers = [r for r in results if r.status == "fail"]
    warnings = [r for r in results if r.status == "warn"]
    return {
        "total": len(results),
        "counts": counts,
        "ready": len(blockers) == 0,
        "blockers": [r.to_dict() for r in blockers],
        "warnings": [r.to_dict() for r in warnings],
    }
