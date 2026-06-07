#!/usr/bin/env python3
"""Run multi-agent production QA against the live CreditRewards deployment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_rewards.qa.supervisor import DEFAULT_BASE_URL, run_production_qa  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CreditRewards multi-agent production QA (supervisor + sub-agents)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Deployed URL only (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip Browser UI agent (Playwright)",
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Run API agents sequentially",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Concurrent recommend workers for catalog sweep (default: 4; retries failures sequentially)",
    )
    parser.add_argument(
        "--agents",
        nargs="*",
        help="Run only these agent ids (e.g. catalog_rec cards browser)",
    )
    args = parser.parse_args()

    if "127.0.0.1" in args.base_url or "localhost" in args.base_url:
        print("ERROR: Production QA must target the deployed site, not localhost.", file=sys.stderr)
        return 2

    print(f"Supervisor starting → {args.base_url.rstrip('/')}")
    report = run_production_qa(
        base_url=args.base_url.rstrip("/"),
        run_browser=not args.no_browser,
        parallel=not args.no_parallel,
        recommend_workers=max(1, min(args.workers, 12)),
        agent_ids=args.agents or None,
    )
    s = report["summary"]
    print(f"Report → {report['report_md']}")
    print(
        f"Overall: {'PASS' if s['ready'] else 'FAIL'} | "
        f"pass={s['counts']['pass']} warn={s['counts']['warn']} "
        f"fail={s['counts']['fail']} skip={s['counts']['skip']}"
    )
    for aid, agent in sorted((report.get("agents") or {}).items()):
        c = agent.get("summary", {}).get("counts", {})
        print(
            f"  [{agent.get('agent_name', aid)}] "
            f"{agent.get('duration_ms', 0)}ms — "
            f"pass={c.get('pass', 0)} fail={c.get('fail', 0)} warn={c.get('warn', 0)}"
        )
    if s["blockers"]:
        print("\nTop blockers:")
        for b in s["blockers"][:15]:
            print(f"  - {b['id']} {b['name']}: {b['detail'][:120]}")
        if len(s["blockers"]) > 15:
            print(f"  … {len(s['blockers']) - 15} more in report JSON")
    return 0 if s["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
