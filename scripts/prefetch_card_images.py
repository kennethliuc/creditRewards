#!/usr/bin/env python3
"""Download bundled card art from issuer product pages (replaces RapidAPI prefetch)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_rewards.card_image import local_image_path  # noqa: E402
from credit_rewards.ingest.card_image_fetch import fetch_official_card_image  # noqa: E402
from credit_rewards.ingest.scrape.registry import load_card_registry  # noqa: E402


def main() -> int:
    keys = [str(entry["card_key"]) for entry in load_card_registry()]
    ok = skipped = failed = 0
    for key in keys:
        if local_image_path(key):
            skipped += 1
            continue
        path = fetch_official_card_image(key)
        if path:
            ok += 1
            print(f"  ✓ {key} → {path.name}")
        else:
            failed += 1
            print(f"  ✗ {key}", file=sys.stderr)
    print(f"Done: {ok} downloaded, {skipped} already present, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
