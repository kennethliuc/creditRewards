"""MCC → spend bonus category gap analysis for Phase-1 card universe."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credit_rewards.datastore.db import db_path, session
from credit_rewards.ingest.scrape.registry import load_card_registry
from credit_rewards.mcc_mapping import load_mcc_mapping, lookup_mcc_category

# Categories that cannot be resolved from MCC alone (portal / brand / payment rail).
MERCHANT_ONLY_PATTERNS: tuple[str, ...] = (
    "amextravel",
    "ultimate rewards",
    "chase travel",
    "citi travel",
    "capital one travel",
    "cititravel",
    "apple pay",
    "apple card",
    "amazon",
    "walmart",
    "target",
    "exxon",
    "mobil",
    "nike",
    "panera",
    "t-mobile",
    "uber eats",
    "uber",
    "lyft",
    "walgreens",
    "peloton",
    "feeding america",
    "wholesale clubs",
    "grocery delivery",
)

# Phase-1 categories that SHOULD have explicit MCC codes (bonus via merchant type).
MCC_REQUIRED_NORMALIZED: frozenset[str] = frozenset(
    {
        "dining",
        "grocery stores",
        "gas stations",
        "drugstores",
        "airfare",
        "hotels",
        "car rentals",
        "transit",
        "streaming services",
        "online shopping",
        "entertainment",
        "telecom",
        "home improvement",
        "tolls",
        "travel",
        "ridesharing",
        "live entertainment",
        "fitness clubs",
        "all purchases",
        "all",
    }
)

MCC_COVERAGE_GATE = 1.0  # 100% of categories classified with strategy
MCC_BONUS_GATE = 0.70  # ≥70% of mcc-required categories have dedicated MCC path


@dataclass
class CategoryUsage:
    category_id: int
    category_name: str
    category_group: str
    card_keys: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category_id": self.category_id,
            "category_name": self.category_name,
            "category_group": self.category_group,
            "card_count": len(self.card_keys),
            "card_keys": sorted(self.card_keys),
        }


@dataclass
class CategoryMappingStatus:
    category_id: int
    category_name: str
    category_group: str
    card_count: int
    strategy: str  # mcc_dedicated | mcc_range | mcc_fallback | merchant_only | not_classified
    mcc_codes: list[str] = field(default_factory=list)
    mapped_category_name: str = ""
    gap: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category_id": self.category_id,
            "category_name": self.category_name,
            "category_group": self.category_group,
            "card_count": self.card_count,
            "strategy": self.strategy,
            "mcc_codes": self.mcc_codes,
            "mapped_category_name": self.mapped_category_name,
            "gap": self.gap,
            "note": self.note,
        }


@dataclass
class MccGapResult:
    ok: bool
    total_categories: int
    classified_pct: float
    mcc_bonus_coverage_pct: float
    master_category_count: int
    categories: list[CategoryMappingStatus] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "total_categories": self.total_categories,
            "classified_pct": self.classified_pct,
            "mcc_bonus_coverage_pct": self.mcc_bonus_coverage_pct,
            "master_category_count": self.master_category_count,
            "categories": [c.to_dict() for c in self.categories],
            "blockers": self.blockers,
        }


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def _is_merchant_only(name: str) -> bool:
    blob = _normalize_name(name)
    return any(p in blob for p in MERCHANT_ONLY_PATTERNS)


def _mcc_index(mapping: dict[str, Any]) -> dict[str, list[str]]:
    """Map normalized spend bonus category name → list of MCC codes (exact only)."""
    index: dict[str, list[str]] = {}
    for code, row in (mapping.get("exact") or {}).items():
        cat_name = _normalize_name(str(row.get("spend_bonus_category_name") or ""))
        index.setdefault(cat_name, []).append(str(code))
    return index


def _range_category_names(mapping: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for row in mapping.get("ranges") or []:
        names.add(_normalize_name(str(row.get("spend_bonus_category_name") or "")))
    return names


def collect_card_categories(*, db_path_override: Path | None = None) -> list[CategoryUsage]:
    path = db_path_override or db_path()
    keys = {e["card_key"] for e in load_card_registry()}
    usage: dict[int, CategoryUsage] = {}

    with session(path) as conn:
        rows = conn.execute("SELECT card_key, detail_json FROM cards").fetchall()

    for row in rows:
        card_key = row["card_key"]
        if card_key not in keys:
            continue
        detail = json.loads(row["detail_json"])
        for rule in detail.get("spendBonusCategory") or []:
            cid = int(rule.get("spendBonusCategoryId") or 0)
            name = str(rule.get("spendBonusCategoryName") or "").strip()
            group = str(rule.get("spendBonusCategoryGroup") or "").strip()
            if cid not in usage:
                usage[cid] = CategoryUsage(
                    category_id=cid,
                    category_name=name,
                    category_group=group,
                )
            usage[cid].card_keys.add(card_key)

    return sorted(usage.values(), key=lambda u: (-len(u.card_keys), u.category_name))


def _master_category_count() -> int:
    path = Path(__file__).resolve().parents[3] / "data" / "reference" / "rewardscc" / "category_list.json"
    if not path.exists():
        return 0
    data = json.loads(path.read_text())
    count = 0

    def walk(node: Any) -> None:
        nonlocal count
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for sc in node.get("spendBonusCategory") or []:
                count += 1
            for sub in node.get("spendBonusSubcategoryGroup") or []:
                walk(sub)

    walk(data)
    return count


def classify_category_mapping(
    usage: CategoryUsage,
    *,
    mcc_index: dict[str, list[str]],
    range_names: set[str],
    default_name: str,
) -> CategoryMappingStatus:
    norm = _normalize_name(usage.category_name)
    card_count = len(usage.card_keys)

    if norm in {"all", "all purchases"} or usage.category_id == 34569:
        return CategoryMappingStatus(
            category_id=usage.category_id,
            category_name=usage.category_name,
            category_group=usage.category_group,
            card_count=card_count,
            strategy="mcc_default",
            mapped_category_name=default_name,
            gap=False,
            note="Catch-all category — unmapped MCC correctly uses base earn",
        )

    if _is_merchant_only(usage.category_name):
        return CategoryMappingStatus(
            category_id=usage.category_id,
            category_name=usage.category_name,
            category_group=usage.category_group,
            card_count=card_count,
            strategy="merchant_only",
            note="Portal/brand category — MCC alone cannot trigger bonus",
            gap=False,
        )

    if norm in mcc_index:
        codes = mcc_index[norm]
        return CategoryMappingStatus(
            category_id=usage.category_id,
            category_name=usage.category_name,
            category_group=usage.category_group,
            card_count=card_count,
            strategy="mcc_dedicated",
            mcc_codes=codes,
            mapped_category_name=usage.category_name,
            gap=False,
        )

    if norm in range_names:
        return CategoryMappingStatus(
            category_id=usage.category_id,
            category_name=usage.category_name,
            category_group=usage.category_group,
            card_count=card_count,
            strategy="mcc_range",
            mapped_category_name=usage.category_name,
            note="Covered by Visa MCC range bucket (airline/hotel/car rental)",
            gap=False,
        )

    # Alias buckets used in mcc yaml under different display names
    alias_map = {
        "car rentals (capital one)": "car rentals",
        "hotels (capital one)": "hotels",
        "hotels (cititravel.com)": "hotels",
        "car rentals (cititravel.com)": "car rentals",
        "air travel (capital one)": "airfare",
        "entertainment (capital one)": "entertainment",
        "all travel (ultimate rewards)": "travel",
    }
    alias_target = alias_map.get(norm)
    if alias_target and alias_target in mcc_index:
        return CategoryMappingStatus(
            category_id=usage.category_id,
            category_name=usage.category_name,
            category_group=usage.category_group,
            card_count=card_count,
            strategy="mcc_dedicated",
            mcc_codes=mcc_index[alias_target],
            mapped_category_name=alias_target,
            note=f"Alias of {alias_target}",
            gap=False,
        )
    if alias_target and alias_target in range_names:
        return CategoryMappingStatus(
            category_id=usage.category_id,
            category_name=usage.category_name,
            category_group=usage.category_group,
            card_count=card_count,
            strategy="mcc_range",
            mapped_category_name=alias_target,
            note=f"Alias range bucket for {alias_target}",
            gap=False,
        )

    requires_mcc = norm in MCC_REQUIRED_NORMALIZED or any(
        k in norm for k in ("travel", "dining", "grocery", "gas", "drug", "stream", "transit", "hotel")
    )

    if requires_mcc:
        return CategoryMappingStatus(
            category_id=usage.category_id,
            category_name=usage.category_name,
            category_group=usage.category_group,
            card_count=card_count,
            strategy="mcc_fallback",
            mapped_category_name=default_name,
            gap=True,
            note="No dedicated MCC — checkout will use base earn (All Purchases fallback)",
        )

    return CategoryMappingStatus(
        category_id=usage.category_id,
        category_name=usage.category_name,
        category_group=usage.category_group,
        card_count=card_count,
        strategy="merchant_only",
        note="Specialty category — classify as merchant-only until merchant map exists",
        gap=False,
    )


def run_mcc_gap_analysis(*, db_path_override: Path | None = None) -> MccGapResult:
    mapping = load_mcc_mapping()
    mcc_index = _mcc_index(mapping)
    range_names = _range_category_names(mapping)
    default_name = str(
        (mapping.get("default_category") or {}).get("spend_bonus_category_name") or "All Purchases"
    )

    usages = collect_card_categories(db_path_override=db_path_override)
    statuses = [
        classify_category_mapping(
            u,
            mcc_index=mcc_index,
            range_names=range_names,
            default_name=default_name,
        )
        for u in usages
    ]

    classified = sum(1 for s in statuses if s.strategy != "not_classified")
    classified_pct = round(100.0 * classified / len(statuses), 1) if statuses else 100.0

    mcc_required = [
        s for s in statuses
        if _normalize_name(s.category_name) in MCC_REQUIRED_NORMALIZED
        or s.strategy == "mcc_fallback"
    ]
    mcc_ok = sum(
        1
        for s in mcc_required
        if s.strategy in ("mcc_dedicated", "mcc_range", "merchant_only", "mcc_default")
    )
    mcc_bonus_pct = round(100.0 * mcc_ok / len(mcc_required), 1) if mcc_required else 100.0

    gaps = [s for s in statuses if s.gap]
    blockers: list[str] = []
    if classified_pct < MCC_COVERAGE_GATE * 100:
        blockers.append(f"MCC/Classifier: {classified_pct}% categories classified (need 100%)")
    if mcc_bonus_pct < MCC_BONUS_GATE * 100:
        blockers.append(
            f"MCC/Coverage: {mcc_bonus_pct}% bonus categories have MCC path "
            f"(need ≥{MCC_BONUS_GATE * 100}%)"
        )
    if gaps:
        names = ", ".join(s.category_name for s in gaps[:8])
        blockers.append(f"MCC Agent: add MCC mapping for gap categories: {names}")

    return MccGapResult(
        ok=not blockers,
        total_categories=len(statuses),
        classified_pct=classified_pct,
        mcc_bonus_coverage_pct=mcc_bonus_pct,
        master_category_count=_master_category_count(),
        categories=statuses,
        blockers=blockers,
    )


def write_mcc_gap_report(
    result: MccGapResult,
    *,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    out = output_dir or Path(__file__).resolve().parents[3] / "reports" / "validation"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / f"mcc-gap-{stamp}.json"
    json_path.write_text(json.dumps({**result.to_dict(), "date": stamp}, indent=2) + "\n")

    md_lines = [
        f"# MCC category gap ({stamp})",
        "",
        f"Phase-1 card categories: **{result.total_categories}**",
        f"Rewards CC master list: **{result.master_category_count}** leaf categories",
        f"Classified: **{result.classified_pct}%** · MCC bonus path: **{result.mcc_bonus_coverage_pct}%**",
        "",
        "| Category | Cards | Strategy | Gap | MCC codes | Note |",
        "|----------|-------|----------|-----|-----------|------|",
    ]
    for row in result.categories:
        codes = ", ".join(row.mcc_codes[:3]) or "—"
        md_lines.append(
            f"| {row.category_name} | {row.card_count} | {row.strategy} | "
            f"{'yes' if row.gap else 'no'} | {codes} | {row.note or '—'} |"
        )
    md_path = out / f"mcc-gap-{stamp}.md"
    md_path.write_text("\n".join(md_lines) + "\n")
    return json_path, md_path
