"""Monitor orchestrator — supervise external cross-validation + MCC coverage fixers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from credit_rewards.validation.external import run_external_validation
from credit_rewards.validation.independent import run_independent_validation
from credit_rewards.validation.mcc_gap import run_mcc_gap_analysis
from credit_rewards.datastore.db import db_path
from credit_rewards.ingest.scrape.registry import load_card_registry


@dataclass
class AgentTask:
    agent: str
    priority: int
    layer: str
    scope: str
    commands: list[str] = field(default_factory=list)
    acceptance: str = ""
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "priority": self.priority,
            "layer": self.layer,
            "scope": self.scope,
            "commands": self.commands,
            "acceptance": self.acceptance,
            "status": self.status,
        }


AGENT_MONITOR = "Monitor"
AGENT_REFERENCE = "Reference"
AGENT_BENCHMARK = "Benchmark"
AGENT_RANK = "Rank"
AGENT_CPP = "CPP"
AGENT_MCC = "MCC"
AGENT_PARSER = "Parser"
AGENT_ISSUER = "Issuer"
AGENT_EXTERNAL = "ExternalValidator"
AGENT_CROSS_VALIDATE = "CrossValidate"
AGENT_MCC_COVERAGE = "MCCCoverage"


def tasks_for_independent_failures(result) -> list[AgentTask]:
    tasks: list[AgentTask] = []
    for gate in result.gates:
        if gate.status == "pass":
            continue
        if gate.layer_id == "l1":
            tasks.append(
                AgentTask(
                    agent=AGENT_REFERENCE,
                    priority=1,
                    layer="internal",
                    scope="All registry cards",
                    commands=[
                        "paycue-db sync-reference",
                        "paycue-db import-reference",
                        "paycue-db validate-reference",
                    ],
                    acceptance="validate-reference 20/20 green",
                )
            )
        elif gate.layer_id == "l3":
            tasks.append(
                AgentTask(
                    agent=AGENT_BENCHMARK,
                    priority=1,
                    layer="internal",
                    scope="data/validation/golden_cases.yaml",
                    commands=["pytest tests/test_golden_recommend.py -q"],
                    acceptance="golden pass rate ≥95%",
                )
            )
            tasks.append(
                AgentTask(
                    agent=AGENT_RANK,
                    priority=2,
                    layer="internal",
                    scope="recommend.py + official CPP",
                    commands=["pytest tests/test_golden_recommend.py -q"],
                    acceptance="failed golden cases pick expected_winner",
                )
            )
        elif gate.layer_id == "cpp":
            tasks.append(
                AgentTask(
                    agent=AGENT_CPP,
                    priority=1,
                    layer="internal",
                    scope="data/curated/official_cpp.yaml",
                    commands=["paycue-db refresh-official-cpp"],
                    acceptance="all programs have source in official_cpp.yaml",
                )
            )
        elif gate.layer_id == "mcc":
            tasks.append(
                AgentTask(
                    agent=AGENT_MCC,
                    priority=1,
                    layer="internal",
                    scope="data/mcc/visa_mcc_categories.yaml",
                    commands=[
                        "paycue-db mcc-lookup 5411",
                        "pytest tests/test_mcc_mapping.py -q",
                    ],
                    acceptance="TOP_VALIDATION_MCCS 100% mapped",
                )
            )
    return tasks


def tasks_for_external_failures(result) -> list[AgentTask]:
    tasks: list[AgentTask] = []
    for card in result.cards:
        if not card.scrape_ok:
            tasks.append(
                AgentTask(
                    agent=AGENT_PARSER,
                    priority=1,
                    layer="external",
                    scope=card.card_key,
                    commands=[
                        f"paycue-db refresh --card-key {card.card_key}",
                        "paycue-db validation-external --card-key "
                        f"{card.card_key}",
                    ],
                    acceptance=f"raw scrape succeeds for {card.card_key}",
                )
            )
        elif card.total_rows and card.cross_verified_pct < result.gate_pct * 100:
            tasks.append(
                AgentTask(
                    agent=AGENT_ISSUER,
                    priority=2,
                    layer="external",
                    scope=card.card_key,
                    commands=[
                        f"paycue-db compare --card-key {card.card_key}",
                        f"paycue-db validation-external --card-key {card.card_key}",
                    ],
                    acceptance=(
                        f"≥{result.gate_pct * 100}% earn rows cross-verified "
                        f"(reference + issuer) for {card.card_key}"
                    ),
                )
            )
            tasks.append(
                AgentTask(
                    agent=AGENT_CROSS_VALIDATE,
                    priority=2,
                    layer="external",
                    scope=card.card_key,
                    commands=[
                        "Open /compare and classify reference_ok vs reference_stale",
                    ],
                    acceptance="Each mismatch has ≥2 independent signals documented",
                )
            )
    if result.blockers and not tasks:
        tasks.append(
            AgentTask(
                agent=AGENT_EXTERNAL,
                priority=1,
                layer="external",
                scope="All registry cards",
                commands=["paycue-db validation-external"],
                acceptance="external cross-verify ≥90% rows, ≥18/20 cards scraped raw",
            )
        )
    return tasks


def tasks_for_mcc_gap(result) -> list[AgentTask]:
    tasks: list[AgentTask] = []
    gaps = [c for c in result.categories if c.gap]
    for row in gaps[:10]:
        tasks.append(
            AgentTask(
                agent=AGENT_MCC_COVERAGE,
                priority=1,
                layer="mcc_gap",
                scope=row.category_name,
                commands=[
                    f"paycue-db mcc-gap-report",
                    f"# Add MCC codes for {row.category_name} in data/mcc/visa_mcc_categories.yaml",
                ],
                acceptance=f"dedicated MCC path for {row.category_name} (not base-rate fallback)",
            )
        )
    merchant_only = [
        c for c in result.categories
        if c.strategy == "merchant_only" and c.card_count >= 2
    ]
    for row in merchant_only[:5]:
        tasks.append(
            AgentTask(
                agent=AGENT_MCC_COVERAGE,
                priority=3,
                layer="mcc_gap",
                scope=row.category_name,
                commands=[
                    f"# Document merchant-only strategy for {row.category_name}",
                ],
                acceptance="merchant map or portal detection note in mcc-gap report",
            )
        )
    if result.blockers and not tasks:
        tasks.append(
            AgentTask(
                agent=AGENT_MCC_COVERAGE,
                priority=1,
                layer="mcc_gap",
                scope="Phase-1 categories",
                commands=["paycue-db mcc-gap-report"],
                acceptance="100% categories classified; ≥70% bonus categories with MCC path",
            )
        )
    return tasks


def tasks_for_l2(*, scrape_failures: list[dict[str, str]] | None = None) -> list[AgentTask]:
    """Legacy L2 overlay track — secondary to external cross-validation."""
    from credit_rewards.validation.dashboard import _load_source_types

    tasks: list[AgentTask] = []
    failures = scrape_failures or []
    for item in failures:
        key = item.get("card_key") or item.get("scope") or ""
        if not key:
            continue
        tasks.append(
            AgentTask(
                agent=AGENT_PARSER,
                priority=3,
                layer="l2_overlay",
                scope=key,
                commands=[
                    f"paycue-db refresh --card-key {key}",
                    f"paycue-db compare --card-key {key}",
                ],
                acceptance=f"compare aligned or evidence-backed for {key}",
            )
        )
    sources = _load_source_types(db_path())
    for key, src in sources.items():
        if src == "scrape":
            tasks.append(
                AgentTask(
                    agent=AGENT_ISSUER,
                    priority=4,
                    layer="l2_overlay",
                    scope=key,
                    commands=[f"paycue-db compare --card-key {key} --write-json"],
                    acceptance=f"L2 overlay verified for {key}",
                    status="pending",
                )
            )
    return tasks


def build_monitor_plan(
    *,
    include_l2: bool = False,
    include_external: bool = True,
    include_mcc_gap: bool = True,
    scrape_failures: list[dict[str, str]] | None = None,
    fetch_evidence: bool = True,
    skip_network: bool = False,
) -> dict[str, Any]:
    """
    Monitor agent entry point.

    Tracks (in order):
    A. Internal independent (L1/L3/CPP/top-MCC)
    B. External cross-validation (raw scrape vs reference + issuer) — CORE
    C. MCC category gap (Phase-1 44 categories) — CORE
    D. Optional legacy L2 overlay track
    """
    independent = run_independent_validation(reimport_reference=False)
    external = (
        run_external_validation(fetch_evidence=fetch_evidence, skip_network=skip_network)
        if include_external
        else None
    )
    mcc_gap = run_mcc_gap_analysis() if include_mcc_gap else None

    tasks: list[AgentTask] = []
    phase = "internal"
    next_agent: str | None = None

    # Monitor always runs verification first
    tasks.append(
        AgentTask(
            agent=AGENT_MONITOR,
            priority=0,
            layer="monitor",
            scope="Verify sub-agent deliverables",
            commands=[
                "paycue-db validation-monitor",
                "pytest tests/test_validation_external.py tests/test_mcc_gap.py -q",
            ],
            acceptance="Monitor re-runs gates after fixers merge; pytest green",
            status="in_progress",
        )
    )

    if not independent.ok:
        phase = "internal"
        tasks.extend(tasks_for_independent_failures(independent))
        next_agent = tasks[1].agent if len(tasks) > 1 else AGENT_REFERENCE
    elif external and not external.ok:
        phase = "external"
        tasks.extend(tasks_for_external_failures(external))
        next_agent = tasks[-1].agent if tasks else AGENT_EXTERNAL
    elif mcc_gap and not mcc_gap.ok:
        phase = "mcc_gap"
        tasks.extend(tasks_for_mcc_gap(mcc_gap))
        next_agent = AGENT_MCC_COVERAGE
    else:
        phase = "core_complete"
        tasks[0].status = "done"
        if include_l2:
            phase = "l2_overlay"
            tasks.extend(tasks_for_l2(scrape_failures=scrape_failures))
            next_agent = AGENT_PARSER

    core_ready = (
        independent.ok
        and (external.ok if external else False)
        and (mcc_gap.ok if mcc_gap else False)
    )

    return {
        "phase": phase,
        "core_ready": core_ready,
        "independent_ok": independent.ok,
        "external_ok": external.ok if external else None,
        "mcc_gap_ok": mcc_gap.ok if mcc_gap else None,
        "independent": independent.to_dict(),
        "external": external.to_dict() if external else None,
        "mcc_gap": mcc_gap.to_dict() if mcc_gap else None,
        "tasks": [t.to_dict() for t in tasks],
        "next_agent": next_agent,
        "ship_blocked_until": (
            []
            if core_ready
            else [
                b
                for blockers in (
                    independent.blockers,
                    (external.blockers if external else []),
                    (mcc_gap.blockers if mcc_gap else []),
                )
                for b in blockers
            ]
        ),
    }
