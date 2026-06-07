from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

BENCHMARKS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "reference" / "program_benchmarks.yaml"
)


def load_program_benchmarks(path: Path | None = None) -> dict[str, dict[str, float]]:
    """Load independent CPP benchmarks keyed by program name."""
    target = path or BENCHMARKS_PATH
    if not target.exists():
        return {}
    payload = yaml.safe_load(target.read_text()) or {}
    result: dict[str, dict[str, float]] = {}
    for row in payload.get("programs") or []:
        name = row.get("program_name") or ""
        if not name:
            continue
        result[name] = {
            "cpp_default": float(row.get("cpp_default") or 1.0),
            "cpp_cash_floor": float(row.get("cpp_cash_floor") or 1.0),
            "benchmark_source": str(payload.get("source_name") or "benchmark"),
        }
    return result
