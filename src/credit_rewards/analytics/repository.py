"""SQLite persistence for product analytics."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class AnalyticsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_device(
        self,
        *,
        device_id: str,
        seen_at: str,
        locale: str | None = None,
        user_agent: str | None = None,
        card_count: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        self.conn.execute(
            """
            INSERT INTO analytics_devices (
                device_id, first_seen_at, last_seen_at, locale, user_agent, card_count, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                locale = COALESCE(excluded.locale, analytics_devices.locale),
                user_agent = COALESCE(excluded.user_agent, analytics_devices.user_agent),
                card_count = COALESCE(excluded.card_count, analytics_devices.card_count),
                meta_json = excluded.meta_json
            """,
            (device_id, seen_at, seen_at, locale, user_agent, card_count, meta_json),
        )

    def upsert_session_start(
        self,
        *,
        session_id: str,
        device_id: str,
        started_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO analytics_sessions (session_id, device_id, started_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO NOTHING
            """,
            (session_id, device_id, started_at),
        )

    def close_session(
        self,
        *,
        session_id: str,
        ended_at: str,
        duration_sec: int | None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE analytics_sessions
            SET ended_at = ?, duration_sec = ?
            WHERE session_id = ?
            """,
            (ended_at, duration_sec, session_id),
        )

    def insert_events(
        self,
        rows: list[tuple[str, str, str, str, str, str]],
    ) -> int:
        if not rows:
            return 0
        self.conn.executemany(
            """
            INSERT INTO analytics_events (
                device_id, session_id, event_type, occurred_at, properties_json, received_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return len(rows)

    def summary_counts(self, *, since: str) -> dict[str, Any]:
        devices_total = self.conn.execute(
            "SELECT COUNT(*) AS c FROM analytics_devices"
        ).fetchone()["c"]
        devices_active = self.conn.execute(
            "SELECT COUNT(*) AS c FROM analytics_devices WHERE last_seen_at >= ?",
            (since,),
        ).fetchone()["c"]
        sessions_total = self.conn.execute(
            "SELECT COUNT(*) AS c FROM analytics_sessions"
        ).fetchone()["c"]
        sessions_recent = self.conn.execute(
            "SELECT COUNT(*) AS c FROM analytics_sessions WHERE started_at >= ?",
            (since,),
        ).fetchone()["c"]
        events_total = self.conn.execute(
            "SELECT COUNT(*) AS c FROM analytics_events"
        ).fetchone()["c"]
        events_recent = self.conn.execute(
            "SELECT COUNT(*) AS c FROM analytics_events WHERE occurred_at >= ?",
            (since,),
        ).fetchone()["c"]
        return {
            "devices_total": devices_total,
            "devices_active": devices_active,
            "sessions_total": sessions_total,
            "sessions_recent": sessions_recent,
            "events_total": events_total,
            "events_recent": events_recent,
        }

    def events_by_type(self, *, since: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT event_type, COUNT(*) AS count
            FROM analytics_events
            WHERE occurred_at >= ?
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
        return [{"event_type": r["event_type"], "count": r["count"]} for r in rows]

    def recent_devices(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT device_id, first_seen_at, last_seen_at, locale, card_count, user_agent
            FROM analytics_devices
            ORDER BY last_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, device_id, session_id, event_type, occurred_at, properties_json, received_at
            FROM analytics_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["properties"] = json.loads(item.pop("properties_json") or "{}")
            except json.JSONDecodeError:
                item["properties"] = {}
            out.append(item)
        return out

    def device_timeline(self, device_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT event_type, occurred_at, properties_json, session_id
            FROM analytics_events
            WHERE device_id = ?
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (device_id, limit),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = {
                "event_type": row["event_type"],
                "occurred_at": row["occurred_at"],
                "session_id": row["session_id"],
            }
            try:
                item["properties"] = json.loads(row["properties_json"] or "{}")
            except json.JSONDecodeError:
                item["properties"] = {}
            out.append(item)
        return out
