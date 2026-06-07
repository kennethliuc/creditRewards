"""Markdown + JSON report writers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports" / "qa"

STATUS_ICON = {"pass": "✅", "fail": "❌", "warn": "⚠️", "skip": "⏭️"}


def render_supervisor_markdown(payload: dict[str, Any], generated_at: str) -> str:
    summary = payload["summary"]
    base_url = payload["base_url"]
    lines = [
        "# Production QA Report (Multi-Agent)",
        "",
        f"**URL:** {base_url}  ",
        f"**Generated:** {generated_at}  ",
        f"**Supervisor:** {payload.get('supervisor', 'QASupervisor')}  ",
        f"**Overall:** {'✅ PASS' if summary['ready'] else '❌ FAIL'} "
        f"({summary['counts']['pass']} pass, {summary['counts']['warn']} warn, "
        f"{summary['counts']['fail']} fail, {summary['counts']['skip']} skip)",
        "",
        "## Agent summary",
        "",
        "| Agent | Duration | Pass | Warn | Fail | Skip |",
        "|-------|----------|------|------|------|------|",
    ]

    for agent_id, agent in sorted((payload.get("agents") or {}).items()):
        s = agent.get("summary", {})
        c = s.get("counts", {})
        lines.append(
            f"| {agent.get('agent_name', agent_id)} | {agent.get('duration_ms', 0)}ms | "
            f"{c.get('pass', 0)} | {c.get('warn', 0)} | {c.get('fail', 0)} | {c.get('skip', 0)} |"
        )

    lines.extend(["", "## Blockers", ""])
    blockers = summary.get("blockers") or []
    if not blockers:
        lines.append("_None_")
    else:
        for b in blockers[:80]:
            lines.append(f"- **{b['id']}** ({b.get('track', '?')}) {b['name']}: {b['detail'][:200]}")
        if len(blockers) > 80:
            lines.append(f"- _…and {len(blockers) - 80} more (see JSON)_")

    lines.extend(["", "## Warnings", ""])
    warnings = summary.get("warnings") or []
    if not warnings:
        lines.append("_None_")
    else:
        for w in warnings[:40]:
            lines.append(f"- **{w['id']}** {w['name']}: {w['detail'][:200]}")

    # Catalog sweep detail
    cat = (payload.get("agents") or {}).get("catalog_rec", {})
    for r in cat.get("results") or []:
        if r.get("id") == "CAT-01" and r.get("evidence", {}).get("failures"):
            lines.extend(["", "## Catalog card failures (first 30)", ""])
            for item in r["evidence"]["failures"][:30]:
                lines.append(f"- `{item['card_key']}`: {item['detail'][:120]}")
            fc = r["evidence"].get("failure_count", 0)
            if fc > 30:
                lines.append(f"- _…{fc - 30} more in JSON_")
            break

    lines.extend(["", "## All checks", "", "| Agent | ID | Status | Name | Detail |", "|-------|-----|--------|------|--------|"])
    agent_name_by_id = {aid: a.get("agent_name", aid) for aid, a in (payload.get("agents") or {}).items()}
    result_agent: dict[str, str] = {}
    for aid, a in (payload.get("agents") or {}).items():
        for r in a.get("results") or []:
            result_agent[r["id"]] = a.get("agent_name", aid)

    for r in payload.get("results") or []:
        icon = STATUS_ICON.get(r["status"], r["status"])
        agent = result_agent.get(r["id"], "?")
        detail = str(r.get("detail", "")).replace("|", "\\|")[:90]
        lines.append(f"| {agent} | {r['id']} | {icon} | {r['name']} | {detail} |")

    lines.extend(
        [
            "",
            "Plan: [docs/validation/qa-production-plan.md](../../docs/validation/qa-production-plan.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any]) -> dict[str, str]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    payload["generated_at"] = generated_at

    md_path = REPORTS_DIR / f"production-{stamp}.md"
    json_path = REPORTS_DIR / f"production-{stamp}.json"
    md_path.write_text(render_supervisor_markdown(payload, generated_at), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    latest_md = REPORTS_DIR / "production-latest.md"
    latest_json = REPORTS_DIR / "production-latest.json"
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

    return {"report_md": str(md_path), "report_json": str(json_path)}
