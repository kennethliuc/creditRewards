"""User accounts and server-side wallet (card_key + nickname + last4)."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from credit_rewards.card_catalog import catalog_card_keys, resolve_wallet_card_key
from credit_rewards.card_image import apply_local_image_urls, card_image_url_for_display
from credit_rewards.datastore.db import session, utc_now

SESSION_COOKIE = "cr_session"
SESSION_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountError(ValueError):
    pass


def _allowed_card_keys() -> set[str]:
    return catalog_card_keys()


def _card_label(card_key: str) -> str:
    return resolve_wallet_card_key(card_key)["card_name"]


def ensure_account_schema() -> None:
    with session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_wallet_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_key TEXT NOT NULL,
                nickname TEXT NOT NULL DEFAULT '',
                last4 TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, card_key)
            );

            CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_wallet_user ON user_wallet_cards(user_id);
            """
        )


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return secrets.compare_digest(digest.hex(), digest_hex)


def normalize_wallet_cards(cards: list[dict[str, Any]]) -> list[dict[str, str]]:
    allowed = _allowed_card_keys()
    if not cards:
        raise AccountError("Select at least one card")
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for idx, row in enumerate(cards):
        key = str(row.get("card_key") or row.get("cardKey") or "").strip()
        if not key or key not in allowed:
            raise AccountError(f"Unknown card: {key!r}")
        if key in seen:
            continue
        seen.add(key)
        nickname = str(row.get("nickname") or "").strip()[:40]
        last4 = re.sub(r"\D", "", str(row.get("last4") or ""))[:4]
        normalized.append(
            {
                "card_key": key,
                "card_name": _card_label(key),
                "nickname": nickname,
                "last4": last4,
                "sort_order": str(idx),
            }
        )
    return normalized


def register_user(email: str, password: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_account_schema()
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise AccountError("Invalid email")
    if len(password) < 8:
        raise AccountError("Password must be at least 8 characters")
    wallet = normalize_wallet_cards(cards)

    with session() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise AccountError("Email already registered")
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, _hash_password(password), utc_now()),
        )
        user_id = int(cur.lastrowid)
        _replace_wallet(conn, user_id, wallet)
    token = create_session(user_id)
    return {"user_id": user_id, "email": email, "session_token": token, "cards": wallet}


def create_session(user_id: int) -> str:
    ensure_account_schema()
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(UTC) + timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat()
    with session() as conn:
        conn.execute(
            "INSERT INTO user_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires),
        )
    return token


def login_user(email: str, password: str) -> dict[str, Any]:
    ensure_account_schema()
    email = email.strip().lower()
    with session() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if not row or not _verify_password(password, row["password_hash"]):
            raise AccountError("Invalid email or password")
        user_id = int(row["id"])
        wallet = _fetch_wallet(conn, user_id)
    token = create_session(user_id)
    return {"user_id": user_id, "email": email, "session_token": token, "cards": wallet}


def logout_session(token: str | None) -> None:
    if not token:
        return
    ensure_account_schema()
    with session() as conn:
        conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))


def user_id_from_session(token: str | None) -> int | None:
    if not token:
        return None
    ensure_account_schema()
    now = utc_now()
    with session() as conn:
        row = conn.execute(
            "SELECT user_id, expires_at FROM user_sessions WHERE token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        if row["expires_at"] < now:
            conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
            return None
        return int(row["user_id"])


def _fetch_wallet(conn, user_id: int) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT card_key, nickname, last4, sort_order
        FROM user_wallet_cards
        WHERE user_id = ?
        ORDER BY sort_order, card_key
        """,
        (user_id,),
    ).fetchall()
    return [
        {
            "card_key": row["card_key"],
            "card_name": _card_label(row["card_key"]),
            "nickname": row["nickname"] or "",
            "last4": row["last4"] or "",
            "image_url": card_image_url_for_display(row["card_key"]),
        }
        for row in rows
    ]


def _replace_wallet(conn, user_id: int, cards: list[dict[str, str]]) -> None:
    conn.execute("DELETE FROM user_wallet_cards WHERE user_id = ?", (user_id,))
    for idx, card in enumerate(cards):
        conn.execute(
            """
            INSERT INTO user_wallet_cards (user_id, card_key, nickname, last4, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, card["card_key"], card.get("nickname") or "", card.get("last4") or "", idx),
        )


def get_user_wallet(user_id: int) -> dict[str, Any]:
    ensure_account_schema()
    with session() as conn:
        user = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise AccountError("User not found")
        cards = _fetch_wallet(conn, user_id)
    return {"email": user["email"], "cards": cards}


def save_user_wallet(user_id: int, cards: list[dict[str, Any]]) -> dict[str, Any]:
    wallet = normalize_wallet_cards(cards)
    with session() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
            raise AccountError("User not found")
        _replace_wallet(conn, user_id, wallet)
    return {"cards": wallet}
