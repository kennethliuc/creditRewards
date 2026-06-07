from __future__ import annotations

import json
from typing import Any

from credit_rewards.datastore.db import session, utc_now
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.awardwallet_sync import load_awardwallet_by_registry_key
from credit_rewards.ingest.reference_sync import load_reference_card
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.official_cpp import (
    CASH_PROGRAM,
    compute_program_official_cpp,
    load_official_cpp_config,
    resolve_program_name,
)
from credit_rewards.benchmarks import load_program_benchmarks


def _load_detail(local_key: str) -> dict[str, Any] | None:
    entry = next((e for e in load_card_registry() if e["card_key"] == local_key), None)
    if not entry:
        return None
    upstream = entry.get("rewards_cc_card_key") or local_key
    reference = load_reference_card(local_key, upstream_key=upstream)
    if not reference:
        return None
    detail = dict(reference)
    detail["cardKey"] = local_key
    return detail


def refresh_official_cpp(*, db_path=None) -> dict[str, Any]:
    """
    Recompute official_cpp per program (max of sources) and persist to program_valuations.
    """
    config = load_official_cpp_config()
    benchmarks = load_program_benchmarks()
    aw_by_card = load_awardwallet_by_registry_key(load_card_registry())

    program_rc: dict[str, list[float]] = {}
    program_aw: dict[str, list[float]] = {}

    for entry in load_card_registry():
        card_key = entry["card_key"]
        detail = _load_detail(card_key)
        if not detail:
            continue
        program = resolve_program_name(card_key, detail, config)
        program_rc.setdefault(program, []).append(
            float(detail.get("baseSpendEarnValuation") or 1.0)
        )
        if card_key in aw_by_card:
            program_aw.setdefault(program, []).append(aw_by_card[card_key])

    updated: dict[str, dict[str, Any]] = {}

    with session(db_path) as conn:
        repo = CardDataRepository(conn)
        for program_name, program_cfg in config.programs.items():
            bench = benchmarks.get(program_name)
            benchmark_cpp = float(bench["cpp_default"]) if bench else None
            manual_cpp = (
                float(program_cfg["manual_cpp"]) if program_cfg.get("manual_cpp") is not None else None
            )

            official_cpp, sources = compute_program_official_cpp(
                program_name,
                rewards_cc_values=program_rc.get(program_name, []),
                benchmark_cpp=benchmark_cpp,
                awardwallet_values=program_aw.get(program_name),
                manual_cpp=manual_cpp,
                config=config,
            )

            earn_currency = "cashback" if program_name == CASH_PROGRAM else "points"
            repo.upsert_official_program_cpp(
                program_name=program_name,
                earn_currency=earn_currency,
                official_cpp=official_cpp,
                sources=sources,
            )
            updated[program_name] = {"official_cpp": official_cpp, "sources": sources}

    return {"programs": updated, "count": len(updated)}


def build_program_cpp_table(*, db_path=None) -> dict[str, float]:
    with session(db_path) as conn:
        repo = CardDataRepository(conn)
        return repo.get_official_cpp_table()
