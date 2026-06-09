from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from credit_rewards.benchmarks import DEFAULT_UTILIZATION_WEIGHTS, load_program_benchmarks, typical_utilization_cpp

if TYPE_CHECKING:
    from credit_rewards.models import CardProfile

from credit_rewards.paths import data_dir

OFFICIAL_CPP_PATH = data_dir() / "curated" / "official_cpp.yaml"
CASH_PROGRAM = "Cash"


@dataclass
class OfficialCppConfig:
    version: str
    aggregation: str
    sanity_cap_cpp: float
    programs: dict[str, dict[str, Any]]
    card_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_official_cpp_config(path: Path | None = None) -> OfficialCppConfig:
    target = path or OFFICIAL_CPP_PATH
    payload = yaml.safe_load(target.read_text()) or {}
    return OfficialCppConfig(
        version=str(payload.get("version") or ""),
        aggregation=str(payload.get("aggregation") or "max"),
        sanity_cap_cpp=float(payload.get("sanity_cap_cpp") or 3.5),
        programs=dict(payload.get("programs") or {}),
        card_overrides=dict(payload.get("card_overrides") or {}),
    )


_CASH_EARN_ALIASES = frozenset(
    {
        "cash",
        "cash back",
        "cashback",
        "sam's cash",
        "sams cash",
    }
)

_ISSUER_PROGRAM_HINTS: tuple[tuple[str, str], ...] = (
    ("american express", "American Express Membership Rewards"),
    ("amex", "American Express Membership Rewards"),
    ("chase", "Chase Ultimate Rewards"),
    ("citi", "Citi ThankYou Rewards"),
    ("capital one", "Capital One Miles"),
    ("wells fargo", "Wells Fargo Go Far Rewards"),
    ("bilt", "Bilt Points"),
)

_CASH_KEY_HINTS = (
    "cash",
    "secured",
    "customizedcash",
    "activecash",
    "double-cash",
    "doublecash",
    "savorone",
    "savor",
    "discover-it",
    "blue-cash",
)


def normalize_earn_type(raw: str) -> str:
    """Map Rewards CC / snapshot spend labels to canonical program names."""
    text = (raw or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if lower in _CASH_EARN_ALIASES or lower.startswith("cash"):
        return CASH_PROGRAM
    return text


def _looks_like_cash_card(card_key: str, earn_type: str) -> bool:
    key = card_key.lower()
    earn = earn_type.lower()
    if earn == CASH_PROGRAM.lower() or "cash" in earn:
        return True
    return any(hint in key for hint in _CASH_KEY_HINTS)


def infer_program_from_metadata(
    card_key: str,
    detail: dict[str, Any],
) -> str | None:
    """Best-effort program when upstream spendType is missing or generic."""
    earn = normalize_earn_type(str(detail.get("baseSpendEarnType") or ""))
    if earn and earn not in {CASH_PROGRAM, "Points", "points"}:
        return earn

    issuer = str(detail.get("cardIssuer") or "").lower()
    key = card_key.lower()
    if _looks_like_cash_card(card_key, earn):
        return CASH_PROGRAM

    for needle, program in _ISSUER_PROGRAM_HINTS:
        if needle in issuer or needle.replace(" ", "") in key:
            return program
    return None


def resolve_program_name(
    card_key: str,
    detail: dict[str, Any],
    config: OfficialCppConfig | None = None,
) -> str:
    config = config or load_official_cpp_config()
    override = config.card_overrides.get(card_key) or {}
    use_program = override.get("use_program")
    if use_program:
        return str(use_program)

    currency = str(detail.get("baseSpendEarnCurrency") or "").lower()
    if currency in {"cash", "cashback"}:
        return CASH_PROGRAM

    earn_type = normalize_earn_type(str(detail.get("baseSpendEarnType") or ""))
    if earn_type == CASH_PROGRAM:
        return CASH_PROGRAM
    if earn_type:
        return earn_type

    inferred = infer_program_from_metadata(card_key, detail)
    if inferred:
        return inferred

    return CASH_PROGRAM


def valuate_as_points(resolved_program: str) -> bool:
    return resolved_program != CASH_PROGRAM


def enrich_card_profile(
    card: "CardProfile",
    *,
    official_cpp: float,
    resolved_program: str,
) -> "CardProfile":
    from credit_rewards.models import CardProfile as Profile

    return Profile(
        **{
            **card.model_dump(),
            "official_cpp": official_cpp,
            "resolved_program": resolved_program,
            "valuate_as_points": valuate_as_points(resolved_program),
        }
    )


def aggregate_official_cpp(candidates: list[float], *, sanity_cap: float) -> float:
    """Legacy max aggregation (kept for tests and audit comparisons)."""
    if not candidates:
        return 1.0
    return min(max(candidates), sanity_cap)


def resolve_official_cpp_from_benchmark_row(
    program_name: str,
    bench: dict[str, Any] | None,
    *,
    config: OfficialCppConfig | None = None,
) -> tuple[float, dict[str, Any]]:
    """Compute display CPP from program benchmark row."""
    config = config or load_official_cpp_config()
    if program_name == CASH_PROGRAM or not bench:
        return 1.0, {"fixed": 1.0}

    if config.aggregation == "typical_utilization":
        typical = typical_utilization_cpp(bench)
        sources = {
            "typical_utilization": typical,
            "benchmark_cap": float(bench.get("cpp_default") or typical),
            "cpp_cash_floor": float(bench.get("cpp_cash_floor") or 1.0),
            "cpp_portal": float(bench.get("cpp_portal") or bench.get("cpp_default") or 1.0),
            "cpp_transfer": float(
                bench.get("cpp_transfer") or bench.get("cpp_portal") or bench.get("cpp_default") or 1.0
            ),
            "utilization_weights": bench.get("utilization_weights") or list(DEFAULT_UTILIZATION_WEIGHTS),
        }
        return typical, sources

    candidates = [float(bench.get("cpp_default") or 1.0)]
    official = aggregate_official_cpp(candidates, sanity_cap=config.sanity_cap_cpp)
    return official, {"benchmark": official}


def compute_program_official_cpp(
    program_name: str,
    *,
    rewards_cc_values: list[float],
    benchmark_cpp: float | None = None,
    awardwallet_values: list[float] | None = None,
    manual_cpp: float | None = None,
    config: OfficialCppConfig | None = None,
) -> tuple[float, dict[str, Any]]:
    """Return (official_cpp, sources audit dict)."""
    config = config or load_official_cpp_config()
    program_cfg = config.programs.get(program_name) or {}

    if program_name == CASH_PROGRAM or program_cfg.get("official_cpp") is not None:
        fixed = float(program_cfg.get("official_cpp") or 1.0)
        return fixed, {"fixed": fixed}

    bench_row = load_program_benchmarks().get(program_name)
    if config.aggregation == "typical_utilization" and bench_row:
        typical, sources = resolve_official_cpp_from_benchmark_row(
            program_name,
            bench_row,
            config=config,
        )
        if rewards_cc_values:
            sources["rewards_cc_max"] = max(rewards_cc_values)
        if benchmark_cpp is not None:
            sources["upgraded_points"] = benchmark_cpp
        if awardwallet_values:
            sources["awardwallet_max"] = max(awardwallet_values)
        if manual_cpp is not None:
            sources["manual"] = manual_cpp
        sources["official_cpp"] = typical
        return typical, sources

    candidates: list[float] = []
    sources: dict[str, Any] = {}

    if rewards_cc_values:
        rc_max = max(rewards_cc_values)
        candidates.append(rc_max)
        sources["rewards_cc_max"] = rc_max

    if benchmark_cpp is not None:
        candidates.append(benchmark_cpp)
        sources["upgraded_points"] = benchmark_cpp

    for value in awardwallet_values or []:
        candidates.append(value)
    if awardwallet_values:
        sources["awardwallet_max"] = max(awardwallet_values)

    if manual_cpp is not None:
        candidates.append(manual_cpp)
        sources["manual"] = manual_cpp

    official = aggregate_official_cpp(candidates, sanity_cap=config.sanity_cap_cpp)
    sources["official_cpp"] = official
    return official, sources


def lookup_official_cpp_from_table(
    program_name: str,
    program_table: dict[str, float],
    config: OfficialCppConfig | None = None,
) -> float:
    config = config or load_official_cpp_config()
    if program_name == CASH_PROGRAM:
        return 1.0
    if program_name in program_table:
        return program_table[program_name]
    program_cfg = config.programs.get(program_name) or {}
    if program_cfg.get("official_cpp") is not None:
        return float(program_cfg["official_cpp"])
    bench = load_program_benchmarks().get(program_name)
    if bench and config.aggregation == "typical_utilization":
        return typical_utilization_cpp(bench)
    if bench:
        return float(bench["cpp_default"])
    return 1.0


def resolve_card_official_cpp(
    card_key: str,
    detail: dict[str, Any],
    program_table: dict[str, float],
    config: OfficialCppConfig | None = None,
) -> tuple[float, str]:
    config = config or load_official_cpp_config()
    program = resolve_program_name(card_key, detail, config)
    cpp = lookup_official_cpp_from_table(program, program_table, config)
    return cpp, program


def fallback_program_table() -> dict[str, float]:
    """Static Phase-1 official CPP when DB refresh has not run (tests/CLI)."""
    config = load_official_cpp_config()
    benchmarks = load_program_benchmarks()
    table: dict[str, float] = {"Cash": 1.0}
    for program_name, cfg in config.programs.items():
        if program_name == CASH_PROGRAM:
            table[CASH_PROGRAM] = float(cfg.get("official_cpp") or 1.0)
            continue
        bench = benchmarks.get(program_name)
        if bench and config.aggregation == "typical_utilization":
            table[program_name] = typical_utilization_cpp(bench)
            continue
        candidates: list[float] = []
        if bench:
            candidates.append(float(bench["cpp_default"]))
        if cfg.get("manual_cpp") is not None:
            candidates.append(float(cfg["manual_cpp"]))
        table[program_name] = aggregate_official_cpp(candidates, sanity_cap=config.sanity_cap_cpp)
    return table
