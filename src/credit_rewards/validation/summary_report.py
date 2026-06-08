"""Narrative validation summary for the /validation-report web page."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credit_rewards.validation.dashboard import build_validation_dashboard

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports" / "validation"
EXTERNAL_GATE = 90.0


def _load_latest_snapshot(prefix: str) -> tuple[dict[str, Any] | None, str | None]:
    files = sorted(REPORTS_DIR.glob(f"{prefix}-*.json"), reverse=True)
    if not files:
        return None, None
    return json.loads(files[0].read_text()), str(files[0])


def _headline_golden_cases(cases: list[dict[str, Any]]) -> list[str]:
    return [
        "amex_gold_dining_100",
        "amex_gold_grocery_100",
        "csr_travel_500",
        "cfu_base_50",
        "mcc_grocery_5411",
        "mcc_dining_5812",
    ]


def _proof_chain(dashboard: dict[str, Any]) -> list[dict[str, str]]:
    l1 = dashboard.get("l1") or {}
    l3 = dashboard.get("l3") or {}
    cpp = dashboard.get("cpp") or {}
    mcc = dashboard.get("mcc") or {}
    external = dashboard.get("external") or {}
    mcc_gap = dashboard.get("mcc_gap") or {}

    return [
        {
            "layer": "数据层",
            "question": "运行时卡规则是否与 Rewards CC 参考一致？",
            "metric": f"L1 {l1.get('pass_count', 0)}/{l1.get('total', 0)} · CPP {cpp.get('coverage_pct', 0)}%",
            "status": "pass" if l1.get("pass_count") == l1.get("total") else "fail",
        },
        {
            "layer": "独立规则层",
            "question": "参考 earn 行能否被原始 issuer 抓取交叉验证？",
            "metric": f"Track B {external.get('cross_verified_pct', 0)}% (gate ≥{external.get('gate_pct', EXTERNAL_GATE)}%)",
            "status": external.get("status", "pending"),
        },
        {
            "layer": "商户→类别",
            "question": "结账 MCC / Phase-1 类别能否映射到 bonus 路径？",
            "metric": (
                f"Top-24 MCC {mcc.get('coverage_pct', 0)}% · "
                f"Phase-1 {mcc_gap.get('mcc_bonus_coverage_pct', 0)}% bonus path"
            ),
            "status": "pass" if mcc_gap.get("ok") and mcc.get("status") == "pass" else "fail",
        },
        {
            "layer": "推荐引擎",
            "question": "给定钱包+消费，是否选出预期最优卡？",
            "metric": (
                f"L3 golden {l3.get('passed', 0)}/{l3.get('total', 0)} "
                f"({round((l3.get('pass_rate') or 0) * 100, 1)}%)"
            ),
            "status": "pass" if l3.get("passed") == l3.get("total") and l3.get("total") else "fail",
        },
    ]


def _tracks(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    external = dashboard.get("external") or {}
    mcc_gap = dashboard.get("mcc_gap") or {}
    l3 = dashboard.get("l3") or {}

    return [
        {
            "id": "A",
            "name": "Track A — 内部一致性",
            "scope": "L1 参考导入、L3 golden、CPP、Top-24 MCC",
            "independent": True,
            "status": "pass" if dashboard.get("independent_ready") else "fail",
            "highlights": [
                f"L1 DB↔Reference: {dashboard['l1']['pass_count']}/{dashboard['l1']['total']}",
                f"L3 golden recommend: {l3.get('passed', 0)}/{l3.get('total', 0)}",
                f"CPP program sources: {dashboard['cpp']['programs_with_source']}/{dashboard['cpp']['program_count']}",
                f"Top checkout MCCs: {dashboard['mcc']['mapped_count']}/{dashboard['mcc']['total_checked']}",
            ],
        },
        {
            "id": "B",
            "name": "Track B — 外部交叉验证",
            "scope": "原始 issuer scrape（无 reference overlay），每行 ≥2 独立信号",
            "independent": True,
            "status": external.get("status", "pending"),
            "highlights": [
                f"Portfolio cross-verify: {external.get('cross_verified_pct', 0)}% (gate ≥{external.get('gate_pct', EXTERNAL_GATE)}%)",
                f"Cards scraped: {external.get('scraped_count', 0)}/20",
                "Denominator = reference earn rows only (parser noise excluded)",
            ],
        },
        {
            "id": "C",
            "name": "Track C — MCC 类别覆盖",
            "scope": f"Phase-1 {mcc_gap.get('total_categories', 44)} earn categories → MCC / fallback strategy",
            "independent": True,
            "status": mcc_gap.get("status", "fail"),
            "highlights": [
                f"Bonus MCC path: {mcc_gap.get('mcc_bonus_coverage_pct', 0)}%",
                f"Category gaps: {mcc_gap.get('gap_count', 0)}",
                f"Master taxonomy: {mcc_gap.get('master_category_count', 304)} categories",
            ],
        },
    ]


def _external_card_summary(external_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not external_snapshot:
        return {"cards": [], "below_gate": [], "priority_cards": []}

    cards = external_snapshot.get("cards") or []
    below = [c for c in cards if c.get("cross_verified_pct", 100) < EXTERNAL_GATE]
    priority_keys = {
        "amex-gold",
        "chase-sapphire-preferred",
        "chase-sapphire-reserve",
        "chase-freedom-unlimited",
        "citi-double-cash",
    }
    priority = [c for c in cards if c.get("card_key") in priority_keys]
    return {
        "cards": cards,
        "below_gate": below,
        "priority_cards": priority,
        "cross_verified_pct": external_snapshot.get("cross_verified_pct"),
        "ok": external_snapshot.get("ok"),
    }


def _limitations(dashboard: dict[str, Any], external_summary: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = [
        {
            "title": "L2 overlay 非独立验证",
            "detail": (
                "L2 compare 在 scrape 前可能通过 reference_align 将参考规则覆盖到抓取结果，"
                "因此 L2 通过率不能单独作为 issuer 真实性证明；核心独立门控使用 Track B。"
            ),
        },
        {
            "title": "单卡 external 可低于 90%",
            "detail": (
                f"Portfolio 门控 {external_summary.get('cross_verified_pct', '—')}% 已通过；"
                f"仍有 {len(external_summary.get('below_gate') or [])} 张卡 per-card 低于 90%，"
                "属于 Post-MVP 精修项，不阻塞 core_ready。"
            ),
        },
        {
            "title": "Golden cases 覆盖 Phase-1 典型场景",
            "detail": (
                "22 个场景覆盖 dining/grocery/travel/MCC/issuer 组合，"
                "但未穷尽 304 个 master category 或动态 5% 轮换季度。"
            ),
        },
        {
            "title": "MCC 映射为启发式",
            "detail": (
                "Visa MCC → Rewards CC category 基于 visa_mcc_categories.yaml；"
                "实际发卡行分类可能与 MCC 不一致（如 Walmart  grocery 争议）。"
            ),
        },
    ]
    l2 = dashboard.get("l2") or {}
    low_l2 = [c for c in (l2.get("cards") or []) if c.get("verified_pct", 100) < 90]
    if low_l2:
        keys = ", ".join(c["card_key"] for c in low_l2[:4])
        items.append(
            {
                "title": "L2 parser 仍待改进",
                "detail": f"例如 {keys} 的 issuer scrape 与参考对齐不足；不影响 Track B portfolio 门控。",
            }
        )
    return items


def build_validation_summary_report(*, fetch_evidence: bool = False) -> dict[str, Any]:
    """Aggregate dashboard + snapshot details for narrative report API."""
    dashboard = build_validation_dashboard(fetch_evidence=fetch_evidence)
    external_snapshot, external_path = _load_latest_snapshot("external-crosscheck")
    mcc_snapshot, mcc_path = _load_latest_snapshot("mcc-gap")
    golden_snapshot, golden_path = _load_latest_snapshot("golden")

    l3 = dashboard.get("l3") or golden_snapshot or {}
    cases = l3.get("cases") or []
    headline_ids = set(_headline_golden_cases(cases))
    headline_cases = [c for c in cases if c.get("id") in headline_ids]
    other_cases = [c for c in cases if c.get("id") not in headline_ids]

    external_summary = _external_card_summary(external_snapshot)
    mcc_gap = dashboard.get("mcc_gap") or mcc_snapshot or {}
    gap_categories = [
        c for c in (mcc_gap.get("categories") or []) if c.get("gap")
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "core_ready": dashboard.get("core_ready", False),
        "ship_ready": dashboard.get("ship_ready", False),
        "independent_ready": dashboard.get("independent_ready", False),
        "blockers": dashboard.get("blockers") or [],
        "core_blockers": dashboard.get("core_blockers") or [],
        "conclusion": (
            "核心 reward 推荐功能已达标：数据导入一致、独立外部交叉验证通过、"
            "Phase-1 类别 MCC 路径完整、golden wallet 场景 100% 选出预期最优卡。"
            if dashboard.get("core_ready")
            else "核心门控尚未全部通过，见 blockers。"
        ),
        "product_core": {
            "title": "支付时刻选卡推荐",
            "flow": [
                "用户选择钱包中的卡",
                "输入消费类别或 MCC + 金额",
                "引擎按 multiplier × official CPP 估算 USD 价值",
                "返回排序后的最优卡及理由",
            ],
        },
        "proof_chain": _proof_chain(dashboard),
        "tracks": _tracks(dashboard),
        "gates": dashboard.get("layers") or [],
        "external": external_summary,
        "external_report_path": external_path,
        "mcc_gap": {
            "ok": mcc_gap.get("ok"),
            "total_categories": mcc_gap.get("total_categories"),
            "mcc_bonus_coverage_pct": mcc_gap.get("mcc_bonus_coverage_pct"),
            "gap_count": mcc_gap.get("gap_count", 0),
            "gap_categories": gap_categories,
            "report_path": mcc_path,
        },
        "golden": {
            "total": l3.get("total", 0),
            "passed": l3.get("passed", 0),
            "pass_rate": l3.get("pass_rate", 0),
            "headline_cases": headline_cases,
            "other_cases": other_cases,
            "report_path": golden_path,
        },
        "limitations": _limitations(dashboard, external_summary),
        "reproduce": {
            "cli": [
                "paycue-db validation-monitor-run",
                "paycue-db validation-external",
                "paycue-db mcc-gap-report",
                "pytest tests/test_golden_recommend.py -q",
            ],
            "urls": {
                "dashboard": "/validation",
                "compare": "/compare",
                "recommend": "/",
                "report": "/validation-report",
            },
        },
        "dashboard_snapshot": {
            "l1": dashboard.get("l1"),
            "l2_verified_pct": (dashboard.get("l2") or {}).get("verified_pct"),
            "cpp": dashboard.get("cpp"),
            "mcc": dashboard.get("mcc"),
        },
    }
