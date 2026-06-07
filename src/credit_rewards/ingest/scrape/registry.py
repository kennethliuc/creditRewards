from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = Path(__file__).resolve().parents[4] / "data" / "card_registry.yaml"


def load_card_registry(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or REGISTRY_PATH
    if not source.exists():
        raise FileNotFoundError(f"Card registry not found: {source}")
    data = yaml.safe_load(source.read_text())
    return list(data.get("cards") or [])
