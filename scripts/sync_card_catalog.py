"""Build card_catalog_index.json from Rewards CC API (full category discovery)."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

from credit_rewards.card_catalog import catalog_coverage_stats, clear_catalog_cache  # noqa: E402
from credit_rewards.client import CardDataClient  # noqa: E402
from credit_rewards.ingest.card_catalog_sync import discover_catalog_rows, write_catalog_index  # noqa: E402
from credit_rewards.card_catalog import is_top_tier_issuer  # noqa: E402


def main() -> None:
    client = CardDataClient(use_local=False)
    if not client.is_configured:
        raise SystemExit("Set REWARDS_CC_API_KEY in .env before syncing card catalog.")

    print("Discovering cards from Rewards CC spend categories + transfer programs…")
    rows, errors = discover_catalog_rows(client)
    print(f"  Found {len(rows)} unique cards (all issuers)")

    top_rows = {k: v for k, v in rows.items() if is_top_tier_issuer(str(v.get("issuer") or ""))}
    print(f"  Keeping {len(top_rows)} cards from top-tier issuers for wallet picker")

    dest = write_catalog_index(top_rows, errors=errors, image_fetch_count=0)
    clear_catalog_cache()
    stats = catalog_coverage_stats()
    print(f"Wrote {stats['cardCount']} cards ({stats['issuerCount']} issuers) to {dest}")
    print("  Card images are fetched on demand when users pick a card (not during sync).")
    print(
        f"  Market coverage: {stats['marketShareCoveredPct']}% "
        f"of top-{len(stats['topIssuersMatched']) + len(stats['topIssuersMissing'])} issuers "
        f"(target {stats['marketShareTargetPct']}%)"
    )
    if stats["topIssuersMissing"]:
        print(f"  Missing issuers: {', '.join(stats['topIssuersMissing'][:5])}")
    if errors:
        print(f"  {len(errors)} non-fatal errors (see sync_errors in JSON)")


if __name__ == "__main__":
    main()
