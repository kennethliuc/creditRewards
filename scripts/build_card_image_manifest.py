#!/usr/bin/env python3
"""Build data/curated/card_image_urls.yaml from issuer product pages (text-only manifest)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

from credit_rewards.card_catalog import load_catalog_index_all  # noqa: E402
from credit_rewards.card_image import IMAGE_URLS_PATH, clear_image_url_manifest_cache, load_image_url_manifest  # noqa: E402
from credit_rewards.ingest.card_image_fetch import (  # noqa: E402
    product_url_for_card,
    resolve_official_image_url,
)
from credit_rewards.ingest.scrape.registry import load_card_registry  # noqa: E402


def _keys_for_args(args) -> list[str]:
    if args.card_keys:
        return list(dict.fromkeys(args.card_keys))
    keys: list[str] = []
    if args.registry or (not args.catalog and not args.card_keys):
        keys.extend(str(e["card_key"]) for e in load_card_registry())
    if args.catalog:
        keys.extend(str(r["card_key"]) for r in load_catalog_index_all() if r.get("card_key"))
    return list(dict.fromkeys(keys))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", action="store_true")
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("card_keys", nargs="*")
    args = parser.parse_args()

    manifest = dict(load_image_url_manifest())
    keys = _keys_for_args(args)
    fetched = skipped = no_url = failed = 0
    for key in keys:
        if manifest.get(key):
            skipped += 1
            continue
        if not product_url_for_card(key):
            no_url += 1
            continue
        url = resolve_official_image_url(key)
        if url.startswith(("http://", "https://")):
            manifest[key] = url
            fetched += 1
            if fetched % 25 == 0:
                print(f"  … {fetched} URLs", flush=True)
        else:
            failed += 1

    IMAGE_URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_URLS_PATH.write_text(
        yaml.safe_dump(
            {"urls": dict(sorted(manifest.items()))},
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    )
    clear_image_url_manifest_cache()
    print(
        f"Wrote {len(manifest)} URLs to {IMAGE_URLS_PATH} "
        f"(+{fetched} new, {skipped} kept, {no_url} no product page, {failed} scrape miss)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
