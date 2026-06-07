from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MCC_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "mcc" / "visa_mcc_categories.yaml"


@dataclass(frozen=True)
class MccCategoryMatch:
    mcc: str
    mcc_description: str
    spend_bonus_category_id: int
    spend_bonus_category_name: str
    spend_bonus_category_group: str
    match_type: str  # exact | range | default
    mapping_source: str = "visa-iso-18245"


def _normalize_mcc(mcc: str | int) -> str:
    digits = "".join(ch for ch in str(mcc).strip() if ch.isdigit())
    if not digits:
        raise ValueError(f"Invalid MCC code: {mcc!r}")
    return digits.zfill(4)[-4:]


def load_mcc_mapping(path: Path | None = None) -> dict[str, Any]:
    target = path or MCC_DATA_PATH
    return yaml.safe_load(target.read_text()) or {}


def lookup_mcc_category(mcc: str | int, *, mapping: dict[str, Any] | None = None) -> MccCategoryMatch:
    """Map Visa MCC (ISO 18245) to Rewards CC spend bonus category."""
    data = mapping or load_mcc_mapping()
    code = _normalize_mcc(mcc)
    code_int = int(code)

    exact = (data.get("exact") or {}).get(code)
    if exact:
        return MccCategoryMatch(
            mcc=code,
            mcc_description=str(exact.get("mcc_description") or ""),
            spend_bonus_category_id=int(exact.get("spend_bonus_category_id") or 0),
            spend_bonus_category_name=str(exact.get("spend_bonus_category_name") or ""),
            spend_bonus_category_group=str(exact.get("spend_bonus_category_group") or ""),
            match_type="exact",
            mapping_source=str(data.get("source_name") or "visa-iso-18245"),
        )

    for row in data.get("ranges") or []:
        start = int(row.get("from"))
        end = int(row.get("to"))
        if start <= code_int <= end:
            return MccCategoryMatch(
                mcc=code,
                mcc_description=str(row.get("mcc_description") or ""),
                spend_bonus_category_id=int(row.get("spend_bonus_category_id") or 0),
                spend_bonus_category_name=str(row.get("spend_bonus_category_name") or ""),
                spend_bonus_category_group=str(row.get("spend_bonus_category_group") or ""),
                match_type="range",
                mapping_source=str(data.get("source_name") or "visa-iso-18245"),
            )

    default = data.get("default_category") or {}
    return MccCategoryMatch(
        mcc=code,
        mcc_description=str(default.get("mcc_description") or "Unmapped MCC"),
        spend_bonus_category_id=int(default.get("spend_bonus_category_id") or 0),
        spend_bonus_category_name=str(default.get("spend_bonus_category_name") or "All Purchases"),
        spend_bonus_category_group=str(default.get("spend_bonus_category_group") or "General"),
        match_type="default",
        mapping_source=str(data.get("source_name") or "visa-iso-18245"),
    )


def mcc_match_to_dict(match: MccCategoryMatch) -> dict[str, Any]:
    return {
        "mcc": match.mcc,
        "mccDescription": match.mcc_description,
        "spendBonusCategoryId": match.spend_bonus_category_id,
        "spendBonusCategoryName": match.spend_bonus_category_name,
        "spendBonusCategoryGroup": match.spend_bonus_category_group,
        "matchType": match.match_type,
        "mappingSource": match.mapping_source,
    }
