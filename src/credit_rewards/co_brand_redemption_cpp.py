"""Co-brand redemption CPP — value when loyalty currency is used at the partner merchant."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from credit_rewards.paths import data_dir

CO_BRAND_REDEMPTION_PATH = data_dir() / "curated" / "co_brand_redemption_cpp.yaml"


@dataclass(frozen=True)
class CoBrandRedemptionEntry:
    merchant_id: str
    programs: tuple[str, ...]
    redemption_cpp: float
    source: str = ""


def _normalize_program(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


def _program_matches(resolved_program: str, entry_programs: tuple[str, ...]) -> bool:
    target = _normalize_program(resolved_program)
    if not target:
        return False
    for program in entry_programs:
        norm = _normalize_program(program)
        if not norm:
            continue
        if target == norm or target in norm or norm in target:
            return True
    return False


@lru_cache(maxsize=1)
def load_co_brand_redemption_index() -> dict[str, CoBrandRedemptionEntry]:
    path = CO_BRAND_REDEMPTION_PATH
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text()) or {}
    cap = float(payload.get("sanity_cap_cpp") or 3.5)
    index: dict[str, CoBrandRedemptionEntry] = {}
    for merchant_id, row in (payload.get("merchants") or {}).items():
        if not isinstance(row, dict):
            continue
        programs = tuple(str(p) for p in (row.get("programs") or []) if str(p).strip())
        cpp = min(float(row.get("redemption_cpp") or 1.0), cap)
        index[str(merchant_id)] = CoBrandRedemptionEntry(
            merchant_id=str(merchant_id),
            programs=programs,
            redemption_cpp=cpp,
            source=str(row.get("source") or ""),
        )
    return index


def co_brand_redemption_cpp(
    *,
    merchant_id: str | None,
    resolved_program: str,
) -> float | None:
    """
    Return co-brand redemption CPP when the purchase merchant matches the card program.

    Example: Delta SkyMiles card at delta.com → 1.2¢/mile (not generic 1.0¢ fallback).
    """
    mid = (merchant_id or "").strip()
    if not mid or mid.startswith(("osm:", "gmaps:", "web:")):
        return None
    entry = load_co_brand_redemption_index().get(mid)
    if not entry:
        return None
    if not _program_matches(resolved_program, entry.programs):
        return None
    return entry.redemption_cpp


def reload_co_brand_redemption_index() -> None:
    load_co_brand_redemption_index.cache_clear()


def load_config_meta(path: Path | None = None) -> dict[str, Any]:
    target = path or CO_BRAND_REDEMPTION_PATH
    if not target.is_file():
        return {}
    return yaml.safe_load(target.read_text()) or {}
