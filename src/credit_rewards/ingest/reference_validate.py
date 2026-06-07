from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.reference_sync import REFERENCE_DIR, load_reference_card


@dataclass
class FieldDiff:
    field: str
    expected: Any
    actual: Any


@dataclass
class CardValidationResult:
    card_key: str
    ok: bool
    diffs: list[FieldDiff] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _index_rules(detail: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    for rule in detail.get("spendBonusCategory") or []:
        name = (rule.get("spendBonusCategoryName") or "").strip().lower()
        if name:
            rules[name] = rule
    return rules


from credit_rewards.ingest.scrape.registry import load_card_registry


def _registry_upstream_key(card_key: str) -> str | None:
    for entry in load_card_registry():
        if entry["card_key"] == card_key:
            return entry.get("rewards_cc_card_key") or entry["card_key"]
    return None


def validate_card_against_reference(
    card_key: str,
    reference_dir=REFERENCE_DIR,
) -> CardValidationResult:
    upstream = _registry_upstream_key(card_key)
    reference = load_reference_card(card_key, reference_dir, upstream_key=upstream)
    if not reference:
        return CardValidationResult(card_key, False, notes=["Reference file missing — run sync-reference"])

    with session() as conn:
        local_rows = CardDataRepository(conn).get_card_detail(card_key)
    if not local_rows:
        return CardValidationResult(card_key, False, notes=["Local DB has no card — run refresh-all"])

    local = local_rows[0]
    diffs: list[FieldDiff] = []
    notes: list[str] = []

    ref_rules = _index_rules(reference)
    local_rules = _index_rules(local)

    for name, ref_rule in ref_rules.items():
        local_rule = local_rules.get(name)
        if not local_rule:
            diffs.append(FieldDiff(f"spendBonusCategory.{name}", "present", "missing"))
            continue
        ref_mult = float(ref_rule.get("earnMultiplier") or 0)
        loc_mult = float(local_rule.get("earnMultiplier") or 0)
        if abs(ref_mult - loc_mult) > 0.01:
            diffs.append(
                FieldDiff(
                    f"spendBonusCategory.{name}.earnMultiplier",
                    ref_mult,
                    loc_mult,
                )
            )

    for name in local_rules:
        if name not in ref_rules:
            notes.append(f"Extra local category not in reference: {name}")

    ref_base = float(reference.get("baseSpendAmount") or 1)
    loc_base = float(local.get("baseSpendAmount") or 1)
    if abs(ref_base - loc_base) > 0.01:
        diffs.append(FieldDiff("baseSpendAmount", ref_base, loc_base))

    return CardValidationResult(card_key, len(diffs) == 0, diffs=diffs, notes=notes)


def validate_all(card_keys: list[str], reference_dir=REFERENCE_DIR) -> list[CardValidationResult]:
    return [validate_card_against_reference(key, reference_dir) for key in card_keys]
