"""Resolve repo data/ directory in dev, Docker, and pip-installed layouts."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_REGISTRY_MARKER = "card_registry.yaml"


@lru_cache
def data_dir() -> Path:
    if raw := os.getenv("CREDITREWARDS_DATA_DIR", "").strip():
        return Path(raw)

    for base in (Path.cwd(), *Path.cwd().parents):
        candidate = base / "data"
        if (candidate / _REGISTRY_MARKER).exists():
            return candidate

    # Editable / source tree: src/credit_rewards/paths.py → repo/data
    source_candidate = Path(__file__).resolve().parents[2] / "data"
    if (source_candidate / _REGISTRY_MARKER).exists():
        return source_candidate

    return source_candidate
