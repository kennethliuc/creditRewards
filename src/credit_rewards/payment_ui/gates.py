"""Payment UI gate checks — Monitor uses these to verify MVP alignment."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from credit_rewards.merchant_mapping import load_merchant_catalog, resolve_merchant_url
from credit_rewards.validation.dashboard import build_validation_dashboard

STATIC_INDEX = (
    Path(__file__).resolve().parents[1] / "web" / "static" / "index.html"
)
STATIC_WALLET_JS = (
    Path(__file__).resolve().parents[1] / "web" / "static" / "wallet-ui.js"
)
APP_PY = Path(__file__).resolve().parents[1] / "web" / "app.py"

MIN_MERCHANTS = 25


@dataclass
class PaymentUIGate:
    track: str
    gate_id: str
    name: str
    status: str  # pass | fail | skip
    detail: str = ""
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track": self.track,
            "id": self.gate_id,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "blockers": self.blockers,
        }


def check_validation_prerequisite() -> PaymentUIGate:
    dashboard = build_validation_dashboard(fetch_evidence=False)
    core_ready = bool(dashboard.get("core_ready"))
    return PaymentUIGate(
        track="V",
        gate_id="core_ready",
        name="Validation core_ready",
        status="pass" if core_ready else "fail",
        detail="Tracks A+B+C" if core_ready else "Fix validation before payment UI",
        blockers=[] if core_ready else list(dashboard.get("core_blockers") or ["core_ready false"]),
    )


def check_merchant_track() -> list[PaymentUIGate]:
    gates: list[PaymentUIGate] = []
    catalog = load_merchant_catalog()
    count = len(catalog)
    gates.append(
        PaymentUIGate(
            track="M",
            gate_id="catalog",
            name="Merchant catalog size",
            status="pass" if count >= MIN_MERCHANTS else "fail",
            detail=f"{count} merchants (min {MIN_MERCHANTS})",
            blockers=[] if count >= MIN_MERCHANTS else ["MerchantAgent: expand merchant_categories.yaml"],
        )
    )

    fuzzy_url = (
        "https://checkout.stripe.com/pay/cs_test_abc"
        "?return_url=https%3A%2F%2Fwww.chipotle.com%2Forder%2Fdone"
    )
    fuzzy = resolve_merchant_url(fuzzy_url)
    fuzzy_ok = fuzzy.best is not None and fuzzy.best.merchant_id == "chipotle"
    gates.append(
        PaymentUIGate(
            track="M",
            gate_id="fuzzy_url",
            name="Fuzzy checkout URL",
            status="pass" if fuzzy_ok else "fail",
            detail=fuzzy.best.merchant_name if fuzzy.best else "no match",
            blockers=[] if fuzzy_ok else ["MerchantAgent: fix resolve_merchant_url fuzzy scoring"],
        )
    )

    gates.append(
        PaymentUIGate(
            track="M",
            gate_id="confirm_flag",
            name="Resolve needs confirmation",
            status="pass" if fuzzy.needs_confirmation else "fail",
            detail=f"needsConfirmation={fuzzy.needs_confirmation}",
            blockers=[] if fuzzy.needs_confirmation else ["MerchantAgent: URL resolve must require confirm"],
        )
    )
    return gates


def check_page_track() -> list[PaymentUIGate]:
    gates: list[PaymentUIGate] = []
    if not STATIC_INDEX.exists():
        return [
            PaymentUIGate(
                track="P",
                gate_id="index",
                name="Homepage index.html",
                status="fail",
                blockers=["FrontendAgent: create static/index.html"],
            )
        ]

    html = STATIC_INDEX.read_text()
    js = STATIC_WALLET_JS.read_text() if STATIC_WALLET_JS.exists() else ""
    checks = {
        "confirm_modal": "confirmModal" in html and "api/merchant/resolve" in js,
        "merchant_id_recommend": "merchant_id" in js and "/api/recommend" in js,
        "full_rankings": "rankings" in js and "card_count" in js,
        "url_tab": 'data-tab="url"' in html or "panel-url" in html,
    }
    for gate_id, ok in checks.items():
        gates.append(
            PaymentUIGate(
                track="P",
                gate_id=gate_id,
                name=f"Page: {gate_id}",
                status="pass" if ok else "fail",
                blockers=[] if ok else [f"FrontendAgent: fix index.html ({gate_id})"],
            )
        )
    return gates


def check_recommend_track() -> list[PaymentUIGate]:
    gates: list[PaymentUIGate] = []
    if not APP_PY.exists():
        return [
            PaymentUIGate(
                track="R",
                gate_id="app",
                name="web/app.py",
                status="fail",
                blockers=["APIAgent: restore web/app.py"],
            )
        ]
    src = APP_PY.read_text()
    checks = {
        "merchant_resolve_route": '"/api/merchant/resolve"' in src,
        "merchant_id_field": "merchant_id" in src,
        "full_library_default": "_all_registry_card_keys" in src,
        "recommend_route": '"/api/recommend"' in src,
    }
    for gate_id, ok in checks.items():
        gates.append(
            PaymentUIGate(
                track="R",
                gate_id=gate_id,
                name=f"API: {gate_id}",
                status="pass" if ok else "fail",
                blockers=[] if ok else [f"APIAgent: fix app.py ({gate_id})"],
            )
        )
    return gates


def check_test_track(*, run_pytest: bool = True) -> PaymentUIGate:
    root = Path(__file__).resolve().parents[3]
    tests_dir = root / "tests"
    if not run_pytest or not tests_dir.is_dir():
        return PaymentUIGate(
            track="T",
            gate_id="pytest",
            name="Pay UI pytest",
            status="skip",
            detail="skipped (no tests dir or --skip-tests)",
        )

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_merchant_mapping.py",
        "tests/test_pay_web.py",
        "tests/test_payment_ui_e2e_smoke.py",
        "-q",
    ]
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    proc = subprocess.run(
        cmd,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    ok = proc.returncode == 0
    detail = (proc.stdout or proc.stderr or "").strip().splitlines()[-1:] or [""]
    return PaymentUIGate(
        track="T",
        gate_id="pytest",
        name="Pay UI pytest",
        status="pass" if ok else "fail",
        detail=detail[0][:120],
        blockers=[] if ok else ["QAAgent: fix tests/test_merchant_mapping.py or test_pay_web.py"],
    )


def run_all_gates(*, run_pytest: bool = True) -> dict[str, Any]:
    gates: list[PaymentUIGate] = []
    gates.append(check_validation_prerequisite())
    gates.extend(check_merchant_track())
    gates.extend(check_page_track())
    gates.extend(check_recommend_track())
    gates.append(check_test_track(run_pytest=run_pytest))

    blockers: list[str] = []
    for gate in gates:
        if gate.status == "fail":
            blockers.extend(gate.blockers)

    page_ready = not blockers and all(g.status != "fail" for g in gates)
    by_track: dict[str, list[dict[str, Any]]] = {}
    for gate in gates:
        by_track.setdefault(gate.track, []).append(gate.to_dict())

    return {
        "page_ready": page_ready,
        "blockers": blockers,
        "gates": [g.to_dict() for g in gates],
        "tracks": by_track,
    }
