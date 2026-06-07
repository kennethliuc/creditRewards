#!/usr/bin/env python3
"""Download card art for registry (popular) cards and optional wallet keys."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_rewards.card_image import (  # noqa: E402
    local_image_path,
    registry_card_keys_for_images,
    warm_card_images,
)
from credit_rewards.client import CardDataClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        action="store_true",
        help="Prefetch Phase-1 registry / popular cards (default when no keys given)",
    )
    parser.add_argument("card_keys", nargs="*", help="Additional card_key values to prefetch")
    args = parser.parse_args()

    client = CardDataClient(use_local=False)
    if not client.is_configured:
        print("REWARDS_CC_API_KEY not set; skipping remote image fetch.", file=sys.stderr)
        return 1

    keys = list(args.card_keys)
    if args.registry or not keys:
        keys = list(dict.fromkeys(registry_card_keys_for_images() + keys))

    before = sum(1 for k in keys if local_image_path(k))
    results = warm_card_images(keys, client=client)
    after = sum(1 for k in keys if local_image_path(k))
    ok = sum(1 for url in results.values() if url.startswith("/api/cards/image/file"))
    print(f"Prefetched {ok} local images ({after}/{len(keys)} on disk, was {before}).")
    return 0 if after >= before else 1


if __name__ == "__main__":
    raise SystemExit(main())
