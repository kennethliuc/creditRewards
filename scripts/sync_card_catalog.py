"""Build card_catalog_index.json from committed reference data (+ optional upstream refresh)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

from credit_rewards.card_catalog import catalog_coverage_stats, clear_catalog_cache, is_top_tier_issuer  # noqa: E402
from credit_rewards.client import CardDataClient, upstream_api_enabled  # noqa: E402
from credit_rewards.ingest.card_catalog_sync import (  # noqa: E402
    _registry_map,
    absorb_card_list_groups,
    apply_registry_card_keys,
    discover_catalog_rows,
    discover_catalog_rows_from_reference,
    fetch_card_list_rows,
    merge_manual_catalog_rows,
    normalize_bilt_catalog_rows,
    write_catalog_index,
)
from credit_rewards.card_image import apply_manifest_image_urls, manifest_image_count  # noqa: E402


def _merge_rows(
    base: dict[str, dict],
    extra: dict[str, dict],
) -> int:
    added = 0
    for key, row in extra.items():
        if key in base:
            existing = base[key]
            name = str(row.get("card_name") or "")
            if name and len(name) > len(str(existing.get("card_name") or "")):
                existing["card_name"] = name
            if row.get("issuer") and not str(existing.get("issuer") or "").strip():
                existing["issuer"] = row["issuer"]
        else:
            base[key] = row
            added += 1
    return added


def main() -> None:
    print("Discovering cards from committed reference snapshots…")
    rows, errors = discover_catalog_rows_from_reference()
    print(f"  Reference data: {len(rows)} unique cards")

    if upstream_api_enabled():
        client = CardDataClient(use_upstream=True)
        print("  Merging upstream Rewards CC discovery (CREDITREWARDS_USE_UPSTREAM_API=1)…")
        live_rows, live_errors = discover_catalog_rows(client)
        added = _merge_rows(rows, live_rows)
        errors.extend(live_errors)
        print(f"  Upstream added/updated {added} cards ({len(live_rows)} live keys)")
    else:
        local = CardDataClient(use_local=True)
        if local.is_configured:
            local_groups, local_src = fetch_card_list_rows(local)
            if local_groups:
                added = absorb_card_list_groups(local_groups, rows, reg_by_rc=_registry_map())
                errors.append(f"card_list:{local_src}:+{added}")
                print(f"  Local CardData API added {added} cards")

    merge_manual_catalog_rows(rows)
    apply_registry_card_keys(rows)
    normalize_bilt_catalog_rows(rows)

    top_rows = {k: v for k, v in rows.items() if is_top_tier_issuer(str(v.get("issuer") or ""))}
    image_count = apply_manifest_image_urls(top_rows)
    print(f"  Keeping {len(top_rows)} cards from top-tier issuers for wallet picker")
    if image_count:
        print(f"  Linked {image_count} manifest image URLs into catalog index")
    print(f"  Manifest has {manifest_image_count()} issuer CDN URLs (lazy load; ~{image_count} in index)")

    by_issuer: dict[str, int] = {}
    for row in top_rows.values():
        issuer = str(row.get("issuer") or "Unknown")
        by_issuer[issuer] = by_issuer.get(issuer, 0) + 1

    dest = write_catalog_index(
        top_rows,
        errors=errors,
        image_fetch_count=image_count,
        discovery_sources={"all_issuers": len(rows), "top_tier": len(top_rows), **by_issuer},
    )
    clear_catalog_cache()
    stats = catalog_coverage_stats()
    print(f"Wrote {stats['cardCount']} cards ({stats['issuerCount']} issuers) to {dest}")
    print("  Card images: card_image_urls.yaml + lazy CDN; SVG placeholder for the rest.")
    print(
        f"  Market coverage: {stats['marketShareCoveredPct']}% "
        f"of top-{len(stats['topIssuersMatched']) + len(stats['topIssuersMissing'])} issuers "
        f"(target {stats['marketShareTargetPct']}%)"
    )
    if stats["topIssuersMissing"]:
        print(f"  Missing issuers: {', '.join(stats['topIssuersMissing'][:5])}")
    if not upstream_api_enabled():
        print("  Upstream API off — catalog built from data/reference/ only.")
    if errors:
        print(f"  {len(errors)} notes (see sync_errors in JSON)")


if __name__ == "__main__":
    main()
