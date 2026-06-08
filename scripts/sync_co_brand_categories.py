#!/usr/bin/env python3
"""Sync Rewards CC category-card snapshots for merchant co-brand bonuses."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_rewards.ingest.co_brand_sync import sync_co_brand_categories  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Re-download even if snapshot exists")
    args = parser.parse_args()

    result = sync_co_brand_categories(only_missing=not args.all)
    print(f"Co-brand categories in merchant catalog: {result['category_count']}")
    print(f"Synced: {len(result['synced'])}")
    for line in result["synced"]:
        print(f"  + {line}")
    print(f"Skipped (already present): {len(result['skipped'])}")
    if result["errors"]:
        print("Errors:")
        for err in result["errors"]:
            print(f"  ! {err}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
