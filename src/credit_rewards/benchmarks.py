from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from credit_rewards.paths import data_dir

BENCHMARKS_PATH = data_dir() / "reference" / "program_benchmarks.yaml"

DEFAULT_UTILIZATION_WEIGHTS = (0.5, 0.35, 0.15)


def load_program_benchmarks(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load independent CPP benchmarks keyed by program name."""
    target = path or BENCHMARKS_PATH
    if not target.exists():
        return {}
    payload = yaml.safe_load(target.read_text()) or {}
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("programs") or []:
        name = row.get("program_name") or ""
        if not name:
            continue
        weights = row.get("utilization_weights") or list(DEFAULT_UTILIZATION_WEIGHTS)
        result[name] = {
            "cpp_default": float(row.get("cpp_default") or 1.0),
            "cpp_cash_floor": float(row.get("cpp_cash_floor") or 1.0),
            "cpp_portal": float(row.get("cpp_portal") or row.get("cpp_default") or 1.0),
            "cpp_transfer": float(
                row.get("cpp_transfer") or row.get("cpp_portal") or row.get("cpp_default") or 1.0
            ),
            "cpp_utilization_floor": row.get("cpp_utilization_floor"),
            "utilization_weights": [float(w) for w in weights],
            "benchmark_source": str(payload.get("source_name") or "benchmark"),
        }
    return result


def typical_utilization_cpp(row: dict[str, Any]) -> float:
    """
    Weighted typical redemption CPP (¢/pt), capped at cpp_default benchmark.

    Weights: floor (cash-out mental anchor), portal, transfer — see program_benchmarks.yaml.
    """
    weights = row.get("utilization_weights") or list(DEFAULT_UTILIZATION_WEIGHTS)
    if len(weights) != 3:
        weights = list(DEFAULT_UTILIZATION_WEIGHTS)
    w_floor, w_portal, w_transfer = (float(w) for w in weights)

    cpp_cash_floor = float(row.get("cpp_cash_floor") or 1.0)
    cpp_benchmark = float(row.get("cpp_default") or 1.0)
    cpp_portal = float(row.get("cpp_portal") or cpp_benchmark)
    cpp_transfer = float(row.get("cpp_transfer") or cpp_portal)

    raw_floor = row.get("cpp_utilization_floor")
    floor_component = float(raw_floor) if raw_floor is not None else max(cpp_cash_floor, 1.0)

    typical = w_floor * floor_component + w_portal * cpp_portal + w_transfer * cpp_transfer
    capped = min(typical, cpp_benchmark)
    return max(capped, cpp_cash_floor)
