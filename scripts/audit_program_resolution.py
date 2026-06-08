#!/usr/bin/env python3
"""Audit catalog program resolution — flags Cash mislabels and missing card detail."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from credit_rewards.card_catalog import load_catalog_index
from credit_rewards.ingest.reference_sync import assemble_card_from_category_snapshots, load_reference_card
from credit_rewards.official_cpp import (
    CASH_PROGRAM,
    load_official_cpp_config,
    resolve_program_name,
)


def audit_catalog(*, limit: int | None = None) -> dict:
    config = load_official_cpp_config()
    known_programs = set(config.programs.keys())
    catalog = load_catalog_index()
    if limit:
        catalog = catalog[:limit]

    resolved_counts: Counter[str] = Counter()
    unknown_programs: Counter[str] = Counter()
    no_detail: list[str] = []
    override_applied: list[str] = []
    suspicious_cash: list[dict] = []

    _POINTS_HINTS = (
        "mile",
        "miles",
        "bonvoy",
        "skymiles",
        "rapid",
        "aadvantage",
        "ultimate",
        "membership",
        "thankyou",
        "points",
        "rewards",
        "altitude",
        "flexpoint",
        "venture",
        "sapphire",
        "bilt",
    )

    for row in catalog:
        key = str(row["card_key"])
        ref = load_reference_card(key)
        if ref:
            detail = ref[0] if isinstance(ref, list) else ref
            source = "reference"
        else:
            detail = assemble_card_from_category_snapshots(key)
            source = "snapshot" if detail else "missing"

        if not detail:
            no_detail.append(key)
            continue

        program = resolve_program_name(key, detail, config)
        resolved_counts[program] += 1
        if program not in known_programs:
            unknown_programs[program] += 1

        if key in config.card_overrides:
            override_applied.append(key)

        if program == CASH_PROGRAM:
            earn = str(detail.get("baseSpendEarnType") or "").lower()
            key_l = key.lower()
            if earn and earn not in {"cash", "cash back", "cashback"} and any(
                h in earn for h in _POINTS_HINTS
            ):
                suspicious_cash.append(
                    {
                        "card_key": key,
                        "earn_type": detail.get("baseSpendEarnType"),
                        "source": source,
                        "issuer": detail.get("cardIssuer") or row.get("issuer"),
                    }
                )

    return {
        "catalog_count": len(catalog),
        "with_detail": len(catalog) - len(no_detail),
        "missing_detail": no_detail,
        "resolved_programs": dict(resolved_counts.most_common()),
        "unknown_programs": dict(unknown_programs.most_common()),
        "override_count": len(override_applied),
        "suspicious_cash_labels": suspicious_cash,
        "pass": not suspicious_cash,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Max catalog rows to scan")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/validation/program-resolution-latest.json"),
    )
    parser.add_argument("--fail-on-issues", action="store_true")
    args = parser.parse_args()

    report = audit_catalog(limit=args.limit or None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")

    print(f"Catalog: {report['catalog_count']} cards, {report['with_detail']} with detail")
    print(f"Missing detail: {len(report['missing_detail'])}")
    print(f"Unknown programs: {len(report['unknown_programs'])}")
    print(f"Suspicious Cash labels: {len(report['suspicious_cash_labels'])}")
    print(f"Wrote {args.out}")

    if args.fail_on_issues and not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
