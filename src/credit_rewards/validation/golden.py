from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.mcc_mapping import lookup_mcc_category
from credit_rewards.models import PurchaseContext
from credit_rewards.normalize import normalize_card_detail
from credit_rewards.official_cpp import enrich_card_profile, fallback_program_table, resolve_card_official_cpp
from credit_rewards.recommend import recommend_best_cards

DEFAULT_GOLDEN_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "validation" / "golden_cases.yaml"
)


def _load_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text()) or {}
    return list(payload.get("cases") or [])


def _wallet_from_db(card_keys: list[str], db_path: Path | None) -> list[Any]:
    table = fallback_program_table()
    profiles = []
    with session(db_path) as conn:
        repo = CardDataRepository(conn)
        for key in card_keys:
            detail_rows = repo.get_card_detail(key)
            if not detail_rows:
                raise ValueError(f"Card not in DB: {key}")
            card = normalize_card_detail(detail_rows)
            cpp, program = resolve_card_official_cpp(key, detail_rows[0], table)
            profiles.append(enrich_card_profile(card, official_cpp=cpp, resolved_program=program))
    return profiles


def _resolve_category(case: dict[str, Any]) -> str:
    spend = case.get("spend") or {}
    if spend.get("category"):
        return str(spend["category"])
    mcc = spend.get("mcc")
    if mcc:
        return lookup_mcc_category(str(mcc)).spend_bonus_category_name
    raise ValueError("golden case spend requires category or mcc")


def run_golden_cases(
    *,
    path: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    target = path or DEFAULT_GOLDEN_PATH
    cases = _load_cases(target)
    if not cases:
        return {
            "configured": False,
            "path": str(target),
            "total": 0,
            "passed": 0,
            "pass_rate": 0.0,
            "cases": [],
            "message": "Add data/validation/golden_cases.yaml to enable L3 checks",
        }

    results: list[dict[str, Any]] = []
    passed = 0
    for case in cases:
        case_id = case.get("id") or "unnamed"
        try:
            wallet = _wallet_from_db(list(case.get("wallet") or []), db_path)
            spend = case.get("spend") or {}
            category = _resolve_category(case)
            amount = float(spend.get("amount_usd") or 0)
            if amount <= 0:
                raise ValueError("amount_usd must be > 0")
            purchase = PurchaseContext(category=category, amount_usd=amount)
            rankings = recommend_best_cards(wallet, purchase)
            if not rankings:
                raise ValueError("no rankings")
            actual = rankings[0].card_key
            expected = str(case.get("expected_winner") or "")
            ok = actual == expected
            if ok:
                passed += 1
            results.append(
                {
                    "id": case_id,
                    "ok": ok,
                    "expected_winner": expected,
                    "actual_winner": actual,
                    "actual_value_usd": rankings[0].estimated_value_usd,
                    "category": category,
                    "amount_usd": amount,
                    "reason": case.get("reason") or rankings[0].reason,
                    "rankings": [
                        {
                            "card_key": r.card_key,
                            "estimated_value_usd": r.estimated_value_usd,
                            "multiplier": r.multiplier,
                        }
                        for r in rankings[:3]
                    ],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": case_id,
                    "ok": False,
                    "expected_winner": case.get("expected_winner"),
                    "error": str(exc),
                }
            )

    total = len(cases)
    return {
        "configured": True,
        "path": str(target),
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "cases": results,
    }
