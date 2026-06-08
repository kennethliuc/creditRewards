from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from credit_rewards.paths import data_dir

DEFAULT_DB_PATH = data_dir() / "carddata.db"


def db_path() -> Path:
    raw = os.getenv("CREDITREWARDS_DB_PATH", "")
    return Path(raw) if raw else DEFAULT_DB_PATH


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path | None = None) -> Path:
    target = path or db_path()
    schema = Path(__file__).with_name("schema.sql").read_text()
    with session(target) as conn:
        conn.executescript(schema)
        _migrate_program_valuations(conn)
        _migrate_analytics(conn)
    return target


def _migrate_analytics(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS analytics_devices (
            device_id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            locale TEXT,
            user_agent TEXT,
            card_count INTEGER,
            meta_json TEXT
        );
        CREATE TABLE IF NOT EXISTS analytics_sessions (
            session_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_sec INTEGER
        );
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            properties_json TEXT NOT NULL DEFAULT '{}',
            received_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_analytics_events_device ON analytics_events(device_id);
        CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_analytics_events_occurred ON analytics_events(occurred_at);
        CREATE INDEX IF NOT EXISTS idx_analytics_devices_last_seen ON analytics_devices(last_seen_at);
        """
    )


def _migrate_program_valuations(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(program_valuations)")}
    if "official_cpp" not in cols:
        conn.execute("ALTER TABLE program_valuations ADD COLUMN official_cpp REAL")
    if "official_cpp_sources_json" not in cols:
        conn.execute("ALTER TABLE program_valuations ADD COLUMN official_cpp_sources_json TEXT")
    if "official_cpp_updated_at" not in cols:
        conn.execute("ALTER TABLE program_valuations ADD COLUMN official_cpp_updated_at TEXT")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def load_json(text: str) -> Any:
    return json.loads(text)
