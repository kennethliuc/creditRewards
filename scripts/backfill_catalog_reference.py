"""One-time: save upstream card-detail JSON for catalog cards missing offline reference."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

from credit_rewards.ingest.reference_sync import backfill_catalog_reference_cards  # noqa: E402


def main() -> None:
    result = backfill_catalog_reference_cards()
    print(
        f"Saved {result['saved_count']}/{result['missing_before']} cards "
        f"→ {result['output_dir']}/cards/"
    )
    if result["errors"]:
        print(f"{len(result['errors'])} errors:")
        for err in result["errors"][:10]:
            print(f"  {err}")


if __name__ == "__main__":
    main()
