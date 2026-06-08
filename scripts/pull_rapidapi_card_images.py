#!/usr/bin/env python3
"""Download Rewards CC card art via RapidAPI into data/card_images/ (commit to git)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

from credit_rewards.card_image import CARD_IMAGES_DIR, local_image_path  # noqa: E402
from credit_rewards.client import CardDataClient, RewardsCCError, upstream_api_enabled  # noqa: E402
from credit_rewards.ingest.card_catalog_sync import discover_catalog_rows  # noqa: E402
from credit_rewards.ingest.card_image_fetch import download_image  # noqa: E402


def _rc_to_wallet() -> dict[str, str]:
    by_rc, _ = discover_catalog_rows(CardDataClient(use_upstream=True))
    return {rc: str(row["card_key"]) for rc, row in by_rc.items()}


def main() -> int:
    if not upstream_api_enabled():
        print(
            "Set CREDITREWARDS_USE_UPSTREAM_API=1 and REWARDS_CC_API_KEY in .env",
            file=sys.stderr,
        )
        return 1

    client = CardDataClient(use_upstream=True)
    if not client.is_configured:
        print("REWARDS_CC_API_KEY missing.", file=sys.stderr)
        return 1

    print("Discovering card keys from reference + spend categories…")
    rc_to_wallet = _rc_to_wallet()
    rc_keys = sorted(rc_to_wallet)
    print(f"Fetching images for {len(rc_keys)} Rewards CC card keys…")

    CARD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ok = skipped = no_url = failed = 0
    manifest: dict[str, str] = {}

    for i, rc_key in enumerate(rc_keys, 1):
        wallet_key = rc_to_wallet.get(rc_key, rc_key)
        if local_image_path(wallet_key):
            skipped += 1
            continue
        url = ""
        try:
            payload = client.get(f"creditcard-card-image/{rc_key}")
            if isinstance(payload, list) and payload:
                url = str(payload[0].get("cardImageUrl") or "")
        except RewardsCCError as exc:
            print(f"  API {rc_key}: {exc}", file=sys.stderr)
            failed += 1
            time.sleep(0.1)
            continue

        if not url.startswith(("http://", "https://")):
            no_url += 1
            continue

        path = download_image(wallet_key, url)
        if path:
            ok += 1
            manifest[wallet_key] = url
        else:
            failed += 1
        if i % 100 == 0:
            print(f"  … {i}/{len(rc_keys)} ({ok} saved, {skipped} skip)", flush=True)
        time.sleep(0.05)

    summary_path = CARD_IMAGES_DIR / "_rapidapi_manifest.json"
    summary_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    total = sum(
        1
        for p in CARD_IMAGES_DIR.iterdir()
        if p.is_file() and not p.name.startswith("_") and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    )
    print(
        f"Done: {ok} downloaded this run, {skipped} already present, "
        f"{no_url} without URL, {failed} failed. {total} image files in {CARD_IMAGES_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
