#!/usr/bin/env python3
"""
Multi-agent valuation verification (Designer evidence + Implementation + Independent).

Usage:
  python scripts/valuation_verify.py
  python scripts/valuation_verify.py --production https://credit-rewards-production.up.railway.app
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REPORTS_DIR = ROOT / "reports" / "validation"

GOLDEN_SCENARIOS = [
    {
        "id": "G01",
        "card_key": "amex-gold",
        "category": "Grocery Stores",
        "amount": 100.0,
        "expected_usd": 5.88,
        "note": "4× MR @ 1.47¢ typical",
    },
    {
        "id": "G02",
        "card_key": "amex-gold",
        "category": "Dining",
        "amount": 25.0,
        "expected_usd": 1.47,
        "note": "4× MR @ 1.47¢ on $25",
    },
    {
        "id": "G03",
        "card_key": "citi-double-cash",
        "category": "Anything",
        "amount": 100.0,
        "expected_usd": 2.37,
        "note": "2% → TY @ 1.185¢ typical",
    },
    {
        "id": "G04",
        "card_key": "wells-fargo-active-cash",
        "category": "Anything",
        "amount": 100.0,
        "expected_usd": 2.0,
        "note": "2% cash",
    },
    {
        "id": "G05",
        "card_key": "chase-sapphire-preferred",
        "category": "Travel",
        "amount": 100.0,
        "expected_usd": 6.91,
        "note": "5× UR @ 1.3825¢ typical",
    },
]

EVIDENCE_TABLE = [
    {
        "program": "American Express Membership Rewards",
        "official_cpp": 1.47,
        "floor_cpp": 0.6,
        "portal_cpp": 2.0,
        "transfer_cpp": 1.8,
        "benchmark_cpp": 2.0,
        "legacy_max_cpp": 2.2,
        "proof": "Typical utilization: 50%×$1 mental floor + 35% portal + 15% transfer, cap 2.0¢",
    },
    {
        "program": "Chase Ultimate Rewards",
        "official_cpp": 1.3825,
        "floor_cpp": 1.0,
        "portal_cpp": 1.75,
        "transfer_cpp": 1.8,
        "benchmark_cpp": 2.0,
        "legacy_max_cpp": 2.0,
        "proof": "Typical utilization weighted; cap UP benchmark 2.0¢",
    },
    {
        "program": "Citi ThankYou Rewards",
        "official_cpp": 1.185,
        "floor_cpp": 0.8,
        "portal_cpp": 1.6,
        "transfer_cpp": 1.5,
        "benchmark_cpp": 1.7,
        "legacy_max_cpp": 1.7,
        "proof": "Typical utilization weighted; cap UP benchmark 1.7¢",
    },
    {
        "program": "Capital One Miles",
        "official_cpp": 1.215,
        "floor_cpp": 0.5,
        "portal_cpp": 1.4,
        "transfer_cpp": 1.5,
        "benchmark_cpp": 1.85,
        "legacy_max_cpp": 1.85,
        "proof": "Typical utilization weighted; cap UP benchmark 1.85¢",
    },
    {
        "program": "Bilt Points",
        "official_cpp": 1.57,
        "floor_cpp": 1.0,
        "portal_cpp": 2.2,
        "transfer_cpp": 2.0,
        "benchmark_cpp": 2.2,
        "legacy_max_cpp": 2.2,
        "proof": "Typical utilization weighted; cap UP benchmark 2.2¢",
    },
    {
        "program": "Wells Fargo Go Far Rewards",
        "official_cpp": 1.0,
        "floor_cpp": 1.0,
        "portal_cpp": 1.0,
        "transfer_cpp": 1.0,
        "benchmark_cpp": 1.0,
        "legacy_max_cpp": 1.0,
        "proof": "Effectively cash-equivalent rewards",
    },
    {
        "program": "Cash",
        "official_cpp": 1.0,
        "floor_cpp": 1.0,
        "portal_cpp": 1.0,
        "transfer_cpp": 1.0,
        "benchmark_cpp": 1.0,
        "legacy_max_cpp": 1.0,
        "proof": "Literal cash back",
    },
]

RANKING_SCENARIOS = [
    {
        "id": "R01",
        "wallet": ["amex-gold", "citi-double-cash"],
        "category": "Grocery Stores",
        "amount": 100.0,
        "expected_winner": "amex-gold",
    },
    {
        "id": "R02",
        "wallet": ["amex-gold", "chase-sapphire-preferred"],
        "category": "Dining",
        "amount": 100.0,
        "expected_winner": "amex-gold",
    },
    {
        "id": "R03",
        "wallet": ["chase-freedom-unlimited", "citi-double-cash"],
        "category": "All Purchases",
        "amount": 50.0,
        "expected_winner": "citi-doublecash",
    },
]


def agent_evidence() -> dict:
    """RedemptionEvidence agent — typical CPP vs legacy max."""
    from credit_rewards.official_cpp import fallback_program_table

    table = fallback_program_table()
    rows = []
    failures = []
    for row in EVIDENCE_TABLE:
        program = row["program"]
        official = table.get(program, row["official_cpp"])
        ok = (
            official <= row["benchmark_cpp"] + 0.01
            and official >= row["floor_cpp"] - 0.01
            and official <= row["legacy_max_cpp"] + 0.01
            and abs(official - row["official_cpp"]) < 0.01
        )
        rows.append(
            {
                **row,
                "resolved_official_cpp": official,
                "delta_vs_legacy_max": round(official - row["legacy_max_cpp"], 4),
                "pass": ok,
            }
        )
        if not ok:
            failures.append(program)
    return {
        "agent": "RedemptionEvidence",
        "pass": not failures,
        "failures": failures,
        "rows": rows,
    }


def agent_implementation() -> dict:
    """ImplementationAuditor — golden scenarios from reference data."""
    from credit_rewards.models import PurchaseContext
    from credit_rewards.normalize import normalize_card_detail
    from credit_rewards.official_cpp import enrich_card_profile, fallback_program_table, resolve_card_official_cpp
    from credit_rewards.valuation import compute_earn_value
    from credit_rewards.ingest.reference_sync import load_reference_card
    from credit_rewards.ingest.scrape.registry import load_card_registry

    registry = {e["card_key"] for e in load_card_registry()}
    table = fallback_program_table()
    results = []
    failures = []

    for scenario in GOLDEN_SCENARIOS:
        key = scenario["card_key"]
        ref = load_reference_card(key)
        if not ref:
            results.append({**scenario, "pass": False, "detail": "missing reference"})
            failures.append(scenario["id"])
            continue
        card = normalize_card_detail(ref)
        detail = ref[0] if isinstance(ref, list) else ref
        cpp, program = resolve_card_official_cpp(key, detail, table)
        card = enrich_card_profile(card, official_cpp=cpp, resolved_program=program)
        purchase = PurchaseContext(category=scenario["category"], amount_usd=scenario["amount"])
        mult, pts, value, reason, cpp_used, _, _ = compute_earn_value(card, purchase)
        ok = abs(value - scenario["expected_usd"]) < 0.11
        results.append(
            {
                **scenario,
                "pass": ok,
                "actual_usd": round(value, 2),
                "multiplier": mult,
                "points_earned": round(pts, 2),
                "cpp_used": cpp_used,
                "program": program,
                "reason": reason[:80],
            }
        )
        if not ok:
            failures.append(scenario["id"])

    return {
        "agent": "ImplementationAuditor",
        "pass": not failures,
        "failures": failures,
        "scenarios": results,
        "registry_card_count": len(registry),
    }


def agent_independent() -> dict:
    """IndependentVerifier — typical CPP within floor..benchmark, below legacy max."""
    from credit_rewards.benchmarks import load_program_benchmarks, typical_utilization_cpp
    from credit_rewards.official_cpp import fallback_program_table, load_official_cpp_config

    benchmarks = load_program_benchmarks()
    table = fallback_program_table()
    config = load_official_cpp_config()
    challenges = []
    verified = []

    for program_name in config.programs:
        if program_name == "Cash":
            verified.append({"program": program_name, "official_cpp": 1.0, "signals": 2})
            continue

        official = table.get(program_name, 0)
        bench = benchmarks.get(program_name)
        if not bench:
            challenges.append({"program": program_name, "issue": "missing benchmark row"})
            continue

        typical = typical_utilization_cpp(bench)
        floor = float(bench.get("cpp_cash_floor") or 1.0)
        cap = float(bench.get("cpp_default") or typical)

        if abs(official - typical) > 0.01:
            challenges.append(
                {
                    "program": program_name,
                    "issue": "official_cpp != typical_utilization_cpp(benchmark)",
                    "official": official,
                    "typical": typical,
                }
            )
        elif official < floor - 0.01 or official > cap + 0.01:
            challenges.append(
                {
                    "program": program_name,
                    "issue": "official_cpp outside floor..benchmark",
                    "official": official,
                    "floor": floor,
                    "cap": cap,
                }
            )
        else:
            verified.append(
                {
                    "program": program_name,
                    "official_cpp": official,
                    "benchmark_cap": cap,
                    "signals": 2,
                }
            )

    return {
        "agent": "IndependentVerifier",
        "pass": len(challenges) == 0,
        "verified": verified,
        "challenges": challenges,
    }


def agent_ranking_stability() -> dict:
    """Compare recommend winners under typical CPP — ranking must stay stable."""
    from credit_rewards.models import PurchaseContext
    from credit_rewards.normalize import normalize_card_detail
    from credit_rewards.official_cpp import enrich_card_profile, fallback_program_table, resolve_card_official_cpp
    from credit_rewards.recommend import recommend_best_cards
    from credit_rewards.ingest.reference_sync import load_reference_card

    table = fallback_program_table()

    def _wallet(keys: list[str]):
        cards = []
        for key in keys:
            ref = load_reference_card(key)
            if not ref:
                raise ValueError(f"missing card {key}")
            detail = ref[0] if isinstance(ref, list) else ref
            card = normalize_card_detail(ref)
            cpp, program = resolve_card_official_cpp(key, detail, table)
            cards.append(enrich_card_profile(card, official_cpp=cpp, resolved_program=program))
        return cards

    results = []
    failures = []
    for scenario in RANKING_SCENARIOS:
        wallet = _wallet(scenario["wallet"])
        purchase = PurchaseContext(category=scenario["category"], amount_usd=scenario["amount"])
        ranked = recommend_best_cards(wallet, purchase)
        winner = ranked[0].card_key if ranked else None
        ok = winner == scenario["expected_winner"]
        results.append({**scenario, "actual_winner": winner, "pass": ok})
        if not ok:
            failures.append(scenario["id"])

    return {
        "agent": "RankingStability",
        "pass": not failures,
        "failures": failures,
        "scenarios": results,
    }


def agent_production_smoke(base_url: str | None) -> dict:
    if not base_url:
        return {"agent": "ProductionSmoke", "pass": True, "skipped": True}
    try:
        import httpx

        with httpx.Client(timeout=30) as client:
            res = client.post(
                f"{base_url.rstrip('/')}/api/recommend",
                json={"merchant_id": "starbucks", "amount_usd": 100, "card_keys": ["amex-gold"]},
            )
            if res.status_code != 200:
                return {"agent": "ProductionSmoke", "pass": False, "detail": res.text[:200]}
            data = res.json()
            best = data.get("best") or {}
            ok = (
                best.get("card_key") == "amex-gold"
                and abs(float(best.get("estimated_value_usd", 0)) - 5.88) < 0.15
                and abs(float(best.get("cpp_used", 0)) - 1.47) < 0.05
            )
            return {
                "agent": "ProductionSmoke",
                "pass": ok,
                "best": best,
            }
    except Exception as exc:
        return {"agent": "ProductionSmoke", "pass": False, "detail": str(exc)[:200]}


def render_markdown(payload: dict) -> str:
    lines = [
        "# Valuation Verification Report",
        "",
        f"**Generated:** {payload['generated_at']}  ",
        f"**Aggregation:** typical_utilization  ",
        f"**Overall:** {'✅ valuation_ready' if payload['valuation_ready'] else '❌ NOT READY'}",
        "",
        "## Agent results",
        "",
    ]
    for agent in payload["agents"]:
        icon = "✅" if agent.get("pass") else "❌"
        lines.append(f"- {icon} **{agent['agent']}**")
        if agent.get("failures"):
            lines.append(f"  - failures: {agent['failures']}")
        if agent.get("challenges"):
            for c in agent["challenges"][:5]:
                lines.append(f"  - challenge: {c.get('program')} — {c.get('issue')}")

    lines.extend(["", "## CPP table (typical vs legacy max)", ""])
    evidence = next(a for a in payload["agents"] if a["agent"] == "RedemptionEvidence")
    lines.append("| Program | Typical CPP | Legacy max | Δ |")
    lines.append("|---------|-------------|------------|---|")
    for row in evidence.get("rows", []):
        lines.append(
            f"| {row['program']} | {row['resolved_official_cpp']}¢ | "
            f"{row['legacy_max_cpp']}¢ | {row['delta_vs_legacy_max']:+.3f}¢ |"
        )

    lines.extend(["", "## Golden scenarios", ""])
    impl = next(a for a in payload["agents"] if a["agent"] == "ImplementationAuditor")
    lines.append("| ID | Card | Expected | Actual | Pass |")
    lines.append("|----|------|----------|--------|------|")
    for s in impl.get("scenarios", []):
        icon = "✅" if s.get("pass") else "❌"
        lines.append(
            f"| {s['id']} | {s['card_key']} | ${s['expected_usd']} | ${s.get('actual_usd', '?')} | {icon} |"
        )

    rank = next((a for a in payload["agents"] if a["agent"] == "RankingStability"), None)
    if rank:
        lines.extend(["", "## Ranking stability", ""])
        lines.append("| ID | Expected winner | Actual | Pass |")
        lines.append("|----|-----------------|--------|------|")
        for s in rank.get("scenarios", []):
            icon = "✅" if s.get("pass") else "❌"
            lines.append(f"| {s['id']} | {s['expected_winner']} | {s.get('actual_winner')} | {icon} |")

    lines.extend(
        [
            "",
            "Design: [docs/architecture/points-to-dollar-valuation-report.md](../../docs/architecture/points-to-dollar-valuation-report.md)",
            "Agents: [docs/validation/valuation-multi-agent-system.md](../../docs/validation/valuation-multi-agent-system.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Valuation multi-agent verification")
    parser.add_argument("--production", default="", help="Optional production URL smoke test")
    args = parser.parse_args()

    agents = [
        agent_evidence(),
        agent_implementation(),
        agent_independent(),
        agent_ranking_stability(),
        agent_production_smoke(args.production or None),
    ]
    valuation_ready = all(a.get("pass") for a in agents if not a.get("skipped"))

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "aggregation": "typical_utilization",
        "valuation_ready": valuation_ready,
        "agents": agents,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    json_path = REPORTS_DIR / f"valuation-verify-{stamp}.json"
    md_path = REPORTS_DIR / f"valuation-evidence-{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    (REPORTS_DIR / "valuation-verify-latest.json").write_text(json_path.read_text(), encoding="utf-8")
    (REPORTS_DIR / "valuation-evidence-latest.md").write_text(md_path.read_text(), encoding="utf-8")

    print(f"Report → {md_path}")
    print(f"valuation_ready={'PASS' if valuation_ready else 'FAIL'}")
    for a in agents:
        print(f"  [{a['agent']}] {'PASS' if a.get('pass') else 'FAIL'}")
    return 0 if valuation_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
