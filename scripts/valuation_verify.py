#!/usr/bin/env python3
"""
Multi-agent valuation verification (Designer evidence + Implementation + Independent).

Usage:
  python scripts/valuation_verify.py
  python scripts/valuation_verify.py --production https://paycue-production.up.railway.app
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
        "expected_usd": 8.8,
        "note": "4× MR @ 2.2¢",
    },
    {
        "id": "G02",
        "card_key": "amex-gold",
        "category": "Dining",
        "amount": 25.0,
        "expected_usd": 2.2,
        "note": "4× MR @ 2.2¢ on $25",
    },
    {
        "id": "G03",
        "card_key": "citi-double-cash",
        "category": "Anything",
        "amount": 100.0,
        "expected_usd": 3.4,
        "note": "2% → TY @ 1.7¢",
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
        "expected_usd": 10.0,
        "note": "5× UR @ 2.0¢",
    },
]

EVIDENCE_TABLE = [
    {
        "program": "American Express Membership Rewards",
        "official_cpp": 2.2,
        "floor_cpp": 0.6,
        "portal_cpp": 2.0,
        "benchmark_cpp": 2.0,
        "proof": "Amex Pay-with-Points floor 0.6¢; Amex Travel ~2¢; RC valuation 2.2¢",
    },
    {
        "program": "Chase Ultimate Rewards",
        "official_cpp": 2.0,
        "floor_cpp": 1.0,
        "portal_cpp": 2.0,
        "benchmark_cpp": 2.0,
        "proof": "UR portal with Sapphire; statement credit 1¢ floor",
    },
    {
        "program": "Citi ThankYou Rewards",
        "official_cpp": 1.7,
        "floor_cpp": 0.8,
        "portal_cpp": 1.6,
        "benchmark_cpp": 1.7,
        "proof": "TY portal + transfer partners; Double Cash override",
    },
    {
        "program": "Capital One Miles",
        "official_cpp": 1.85,
        "floor_cpp": 0.5,
        "portal_cpp": 1.0,
        "benchmark_cpp": 1.85,
        "proof": "Travel erasure ~1¢; partner transfers up to ~1.85¢ cited",
    },
    {
        "program": "Bilt Points",
        "official_cpp": 2.2,
        "floor_cpp": 1.0,
        "portal_cpp": 2.2,
        "benchmark_cpp": 2.2,
        "proof": "Bilt travel 2.2¢ documented",
    },
    {
        "program": "Wells Fargo Go Far Rewards",
        "official_cpp": 1.0,
        "floor_cpp": 1.0,
        "portal_cpp": 1.0,
        "benchmark_cpp": 1.0,
        "proof": "Effectively cash-equivalent rewards",
    },
    {
        "program": "Cash",
        "official_cpp": 1.0,
        "floor_cpp": 1.0,
        "portal_cpp": 1.0,
        "benchmark_cpp": 1.0,
        "proof": "Literal cash back",
    },
]


def agent_evidence() -> dict:
    """RedemptionEvidence agent — static proof vs official table."""
    from credit_rewards.official_cpp import fallback_program_table

    table = fallback_program_table()
    rows = []
    failures = []
    for row in EVIDENCE_TABLE:
        program = row["program"]
        official = table.get(program, row["official_cpp"])
        candidates = [row["floor_cpp"], row["portal_cpp"], row["benchmark_cpp"]]
        max_defensible = max(candidates)
        ok = official <= 3.5 and official >= row["floor_cpp"] and official <= max(max_defensible, row["official_cpp"]) + 0.05
        if official != row["official_cpp"]:
            ok = abs(official - row["official_cpp"]) < 0.01 and ok
        rows.append({**row, "resolved_official_cpp": official, "pass": ok})
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
    """IndependentVerifier — ≥2 signals without reading design narrative."""
    from credit_rewards.benchmarks import load_program_benchmarks
    from credit_rewards.official_cpp import fallback_program_table, load_official_cpp_config
    from credit_rewards.ingest.reference_sync import load_reference_card
    from credit_rewards.ingest.scrape.registry import load_card_registry

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
        signals: list[str] = []

        bench = benchmarks.get(program_name)
        if bench:
            signals.append(f"upgraded_points:{bench['cpp_default']}")

        rc_vals = []
        for entry in load_card_registry():
            ref = load_reference_card(entry["card_key"])
            if not ref:
                continue
            row = ref[0] if isinstance(ref, list) else ref
            if str(row.get("baseSpendEarnType") or "") == program_name:
                rc_vals.append(float(row.get("baseSpendEarnValuation") or 0))
        if rc_vals:
            signals.append(f"rewards_cc_max:{max(rc_vals)}")

        if bench and rc_vals:
            bench_val = float(bench["cpp_default"])
            rc_max = max(rc_vals)
            if abs(official - max(bench_val, rc_max)) > 0.25:
                challenges.append(
                    {
                        "program": program_name,
                        "issue": "official_cpp diverges >0.25¢ from max(UP, RC)",
                        "official": official,
                        "up": bench_val,
                        "rc_max": rc_max,
                    }
                )
            else:
                verified.append({"program": program_name, "official_cpp": official, "signals": len(signals)})
        elif len(signals) < 2:
            challenges.append(
                {"program": program_name, "issue": "fewer than 2 independent signals", "signals": signals}
            )
        else:
            verified.append({"program": program_name, "official_cpp": official, "signals": len(signals)})

    return {
        "agent": "IndependentVerifier",
        "pass": len(challenges) == 0,
        "verified": verified,
        "challenges": challenges,
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
                and abs(float(best.get("estimated_value_usd", 0)) - 8.8) < 0.15
                and abs(float(best.get("cpp_used", 0)) - 2.2) < 0.05
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

    lines.extend(["", "## Golden scenarios", ""])
    impl = next(a for a in payload["agents"] if a["agent"] == "ImplementationAuditor")
    lines.append("| ID | Card | Expected | Actual | Pass |")
    lines.append("|----|------|----------|--------|------|")
    for s in impl.get("scenarios", []):
        icon = "✅" if s.get("pass") else "❌"
        lines.append(
            f"| {s['id']} | {s['card_key']} | ${s['expected_usd']} | ${s.get('actual_usd', '?')} | {icon} |"
        )

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
        agent_production_smoke(args.production or None),
    ]
    valuation_ready = all(a.get("pass") for a in agents if not a.get("skipped"))

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
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
