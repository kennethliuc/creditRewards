from __future__ import annotations

import json
from pathlib import Path

from credit_rewards.datastore.db import init_db, session
from credit_rewards.datastore.repository import CardDataRepository

from credit_rewards.paths import data_dir

SEED_DIR = data_dir() / "seed"


def seed_database(db_path: Path | None = None) -> dict[str, int]:
    """Load static taxonomy only. Card rewards come from issuer scrape (refresh-all)."""
    init_db(db_path)
    counts = {"cards": 0, "transfer_partners": 0, "transfer_rules": 0}

    with session(db_path) as conn:
        repo = CardDataRepository(conn)

        category_list = json.loads((SEED_DIR / "category_list.json").read_text())
        repo.set_category_list_payload(category_list)

        partners = json.loads((SEED_DIR / "transfer_partners.json").read_text())
        for partner in partners:
            repo.upsert_transfer_partner(
                int(partner["transferPartnerId"]),
                partner["transferPartnerName"],
            )
            counts["transfer_partners"] += 1

        partner_cards_path = SEED_DIR / "transfer_partner_cards.json"
        if partner_cards_path.exists():
            conn.execute("DELETE FROM transfer_partner_cards")
            for rule in json.loads(partner_cards_path.read_text()):
                repo.upsert_transfer_partner_card(int(rule["transferPartnerId"]), rule)
                counts["transfer_rules"] += 1

    return counts
