from __future__ import annotations

import json
import sqlite3
from typing import Any

from credit_rewards.datastore.db import load_json, utc_now
from credit_rewards.benchmarks import load_program_benchmarks
from credit_rewards.program_valuation import (
    build_card_valuation_summary,
    extract_valuation_fields,
    merge_benchmark,
)
from credit_rewards.official_cpp import resolve_card_official_cpp, load_official_cpp_config


class CardDataRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def log_call(self, skey: str, path: str, status_code: int = 200) -> None:
        self.conn.execute(
            "INSERT INTO api_call_log (skey, path, status_code, called_at) VALUES (?, ?, ?, ?)",
            (skey, path, status_code, utc_now()),
        )

    def upsert_card(self, detail: dict[str, Any], source_url: str = "", source_type: str = "manual") -> None:
        card_key = detail["cardKey"]
        self.conn.execute(
            """
            INSERT INTO cards (card_key, card_issuer, card_name, is_active, detail_json, source_url, source_type, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_key) DO UPDATE SET
              card_issuer=excluded.card_issuer,
              card_name=excluded.card_name,
              is_active=excluded.is_active,
              detail_json=excluded.detail_json,
              source_url=excluded.source_url,
              source_type=excluded.source_type,
              updated_at=excluded.updated_at
            """,
            (
                card_key,
                detail.get("cardIssuer") or "",
                detail.get("cardName") or "",
                int(detail.get("isActive", 1)),
                json.dumps(detail),
                source_url,
                source_type,
                utc_now(),
            ),
        )
        self._sync_category_rules_from_card(detail)
        self.sync_program_valuation_from_detail(detail)

    def sync_program_valuation_from_detail(self, detail: dict[str, Any]) -> None:
        row = merge_benchmark(extract_valuation_fields(detail), load_program_benchmarks())
        program = row["program_name"]
        if not program:
            return
        self.conn.execute(
            """
            INSERT INTO program_valuations (
              program_name, earn_currency, cpp_default, cpp_cash_floor,
              is_cash_redeemable, source, benchmark_cpp_default, benchmark_cpp_cash_floor,
              benchmark_source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(program_name) DO UPDATE SET
              earn_currency=excluded.earn_currency,
              cpp_default=excluded.cpp_default,
              cpp_cash_floor=excluded.cpp_cash_floor,
              is_cash_redeemable=excluded.is_cash_redeemable,
              source=excluded.source,
              benchmark_cpp_default=excluded.benchmark_cpp_default,
              benchmark_cpp_cash_floor=excluded.benchmark_cpp_cash_floor,
              benchmark_source=excluded.benchmark_source,
              updated_at=excluded.updated_at
            """,
            (
                program,
                row["earn_currency"],
                row["cpp_default"],
                row["cpp_cash_floor"],
                int(row["is_cash_redeemable"]),
                row["source"],
                row.get("benchmark_cpp_default"),
                row.get("benchmark_cpp_cash_floor"),
                row.get("benchmark_source"),
                utc_now(),
            ),
        )

    def _sync_category_rules_from_card(self, detail: dict[str, Any]) -> None:
        card_key = detail["cardKey"]
        self.conn.execute("DELETE FROM category_card_rules WHERE card_key = ?", (card_key,))
        for rule in detail.get("spendBonusCategory") or []:
            category_id = rule.get("spendBonusCategoryId")
            if category_id is None:
                continue
            self.conn.execute(
                """
                INSERT INTO spend_categories (category_id, category_name, category_group, subcategory_group, is_all)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(category_id) DO UPDATE SET
                  category_name=excluded.category_name,
                  category_group=COALESCE(excluded.category_group, spend_categories.category_group),
                  subcategory_group=COALESCE(excluded.subcategory_group, spend_categories.subcategory_group)
                """,
                (
                    int(category_id),
                    rule.get("spendBonusCategoryName") or "",
                    rule.get("spendBonusCategoryGroup"),
                    rule.get("spendBonusSubcategoryGroup"),
                ),
            )
            payload = {
                "cardKey": card_key,
                "cardName": detail.get("cardName"),
                "cardIssuer": detail.get("cardIssuer"),
                "cardNetwork": detail.get("cardNetwork"),
                "categoryType": rule.get("spendBonusCategoryType"),
                "spendBonusCategoryName": rule.get("spendBonusCategoryName"),
                "spendBonusCategoryId": category_id,
                "spendBonusDesc": rule.get("spendBonusDesc"),
                "earnMultiplier": rule.get("earnMultiplier"),
                "spendType": detail.get("baseSpendEarnType"),
                "isDateLimit": rule.get("isDateLimit", 0),
                "limitBeginDate": rule.get("limitBeginDate") or "",
                "limitEndDate": rule.get("limitEndDate") or "",
                "isSpendLimit": rule.get("isSpendLimit", 0),
                "spendLimit": rule.get("spendLimit", 0),
                "spendLimitResetPeriod": rule.get("spendLimitResetPeriod") or "",
            }
            self.conn.execute(
                "INSERT INTO category_card_rules (category_id, card_key, rule_json) VALUES (?, ?, ?)",
                (int(category_id), card_key, json.dumps(payload)),
            )

    def set_category_list_payload(self, payload: list[dict[str, Any]]) -> None:
        self.conn.execute(
            """
            INSERT INTO category_list_json (id, payload) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET payload=excluded.payload
            """,
            (json.dumps(payload),),
        )

    def get_card_list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT card_issuer, card_key, card_name, is_active FROM cards ORDER BY card_issuer, card_name"
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["card_issuer"], []).append(
                {
                    "cardKey": row["card_key"],
                    "cardName": row["card_name"],
                    "isActive": row["is_active"],
                }
            )
        return [{"cardIssuer": issuer, "card": cards} for issuer, cards in grouped.items()]

    def get_card_detail(self, card_key: str) -> list[dict[str, Any]] | None:
        row = self.conn.execute(
            "SELECT detail_json FROM cards WHERE card_key = ?", (card_key,)
        ).fetchone()
        if not row:
            return None
        return [load_json(row["detail_json"])]

    def get_all_card_details(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT detail_json FROM cards ORDER BY card_name").fetchall()
        return [load_json(r["detail_json"]) for r in rows]

    def search_cards(self, name: str, limit: int = 10) -> list[dict[str, Any]]:
        if len(name.strip()) < 4:
            return []
        pattern = f"%{name.strip()}%"
        rows = self.conn.execute(
            """
            SELECT card_key, card_issuer, card_name FROM cards
            WHERE lower(card_name) LIKE lower(?)
            ORDER BY card_name LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()
        return [
            {"cardKey": r["card_key"], "cardIssuer": r["card_issuer"], "cardName": r["card_name"]}
            for r in rows
        ]

    def get_category_list(self) -> list[dict[str, Any]]:
        row = self.conn.execute("SELECT payload FROM category_list_json WHERE id = 1").fetchone()
        if row:
            return load_json(row["payload"])
        return []

    def get_category_cards(self, category_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT rule_json FROM category_card_rules WHERE category_id = ? ORDER BY card_key",
            (category_id,),
        ).fetchall()
        return [load_json(r["rule_json"]) for r in rows]

    def upsert_transfer_partner(self, partner_id: int, name: str) -> None:
        self.conn.execute(
            """
            INSERT INTO transfer_partners (transfer_partner_id, transfer_partner_name)
            VALUES (?, ?)
            ON CONFLICT(transfer_partner_id) DO UPDATE SET transfer_partner_name=excluded.transfer_partner_name
            """,
            (partner_id, name),
        )

    def upsert_transfer_partner_card(self, partner_id: int, rule: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO transfer_partner_cards (transfer_partner_id, rule_json) VALUES (?, ?)",
            (partner_id, json.dumps(rule)),
        )

    def get_transfer_program_list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT transfer_partner_id, transfer_partner_name FROM transfer_partners ORDER BY transfer_partner_name"
        ).fetchall()
        return [
            {
                "transferPartnerName": r["transfer_partner_name"],
                "transferPartnerId": r["transfer_partner_id"],
            }
            for r in rows
        ]

    def get_transfer_program_cards(self, partner_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT rule_json FROM transfer_partner_cards WHERE transfer_partner_id = ?",
            (partner_id,),
        ).fetchall()
        return [load_json(r["rule_json"]) for r in rows]

    def upsert_official_program_cpp(
        self,
        *,
        program_name: str,
        earn_currency: str,
        official_cpp: float,
        sources: dict[str, Any],
    ) -> None:
        now = utc_now()
        existing = self.conn.execute(
            "SELECT cpp_default, cpp_cash_floor, is_cash_redeemable, source FROM program_valuations WHERE program_name = ?",
            (program_name,),
        ).fetchone()
        cpp_default = float(existing["cpp_default"]) if existing else official_cpp
        cpp_floor = float(existing["cpp_cash_floor"]) if existing else 1.0
        is_cash = int(existing["is_cash_redeemable"]) if existing else int(program_name == "Cash")
        source = existing["source"] if existing else "official_cpp"
        self.conn.execute(
            """
            INSERT INTO program_valuations (
              program_name, earn_currency, cpp_default, cpp_cash_floor, is_cash_redeemable,
              source, official_cpp, official_cpp_sources_json, official_cpp_updated_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(program_name) DO UPDATE SET
              official_cpp=excluded.official_cpp,
              official_cpp_sources_json=excluded.official_cpp_sources_json,
              official_cpp_updated_at=excluded.official_cpp_updated_at,
              updated_at=excluded.updated_at
            """,
            (
                program_name,
                earn_currency,
                cpp_default,
                cpp_floor,
                is_cash,
                source,
                official_cpp,
                json.dumps(sources),
                now,
                now,
            ),
        )

    def get_official_cpp_table(self) -> dict[str, float]:
        rows = self.conn.execute(
            "SELECT program_name, official_cpp FROM program_valuations WHERE official_cpp IS NOT NULL"
        ).fetchall()
        table = {row["program_name"]: float(row["official_cpp"]) for row in rows}
        config = load_official_cpp_config()
        if "Cash" not in table:
            table["Cash"] = float(config.programs.get("Cash", {}).get("official_cpp") or 1.0)
        return table

    def get_program_valuation_list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT program_name, earn_currency, official_cpp, official_cpp_sources_json
            FROM program_valuations
            WHERE official_cpp IS NOT NULL
            ORDER BY program_name
            """
        ).fetchall()
        return [
            {
                "rewardProgram": r["program_name"],
                "earnCurrency": r["earn_currency"],
                "officialCpp": r["official_cpp"],
                "dollarPerPoint": round(float(r["official_cpp"]) / 100.0, 4),
                "sources": load_json(r["official_cpp_sources_json"])
                if r["official_cpp_sources_json"]
                else {},
            }
            for r in rows
        ]

    def get_card_valuation(self, card_key: str) -> dict[str, Any] | None:
        detail = self.get_card_detail(card_key)
        if not detail:
            return None
        program_table = self.get_official_cpp_table()
        return build_card_valuation_summary(
            detail[0],
            card_key=card_key,
            program_table=program_table,
        )

    def get_api_usage(self, skey: str, monthly_limit: int = 2500) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT strftime('%Y-%m', called_at) AS ym,
                   status_code,
                   COUNT(*) AS cnt
            FROM api_call_log
            WHERE skey = ?
            GROUP BY ym, status_code
            ORDER BY ym DESC
            """,
            (skey,),
        ).fetchall()

        if not rows:
            now = utc_now()
            month_label = now[:7]
            return [
                {
                    "yearMonth": month_label,
                    "statusCode": [
                        {
                            "statusCode": 200,
                            "apiCalls": 0,
                            "apiCallsLimit": monthly_limit,
                            "apiCallsRemaining": monthly_limit,
                            "lastUpdated": now,
                        }
                    ],
                }
            ]

        by_month: dict[str, dict[int, int]] = {}
        for row in rows:
            by_month.setdefault(row["ym"], {})[row["status_code"]] = row["cnt"]

        result = []
        for ym, counts in sorted(by_month.items(), reverse=True):
            success = counts.get(200, 0)
            status_codes = [
                {
                    "statusCode": 200,
                    "apiCalls": success,
                    "apiCallsLimit": monthly_limit,
                    "apiCallsRemaining": max(monthly_limit - success, 0),
                    "lastUpdated": utc_now(),
                }
            ]
            for code in (404, 429, 500):
                if code in counts:
                    status_codes.append(
                        {
                            "statusCode": code,
                            "apiCalls": counts[code],
                            "apiCallsLimit": 0,
                            "apiCallsRemaining": 0,
                            "lastUpdated": utc_now(),
                        }
                    )
            result.append({"yearMonth": ym, "statusCode": status_codes})
        return result
