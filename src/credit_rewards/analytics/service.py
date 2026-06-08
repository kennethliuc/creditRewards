"""Analytics ingest and admin summary."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from credit_rewards.analytics.repository import AnalyticsRepository
from credit_rewards.datastore.db import session, utc_now

ADMIN_COOKIE = "cr_analytics_admin"
ADMIN_COOKIE_MAX_AGE = 60 * 60 * 12  # 12 hours


def analytics_enabled() -> bool:
    return os.getenv("CREDITREWARDS_ANALYTICS_ENABLED", "1").lower() not in {
        "0",
        "false",
        "no",
    }


def admin_password_configured() -> bool:
    return bool((os.getenv("CREDITREWARDS_ANALYTICS_ADMIN_PASSWORD") or "").strip())


def _admin_token() -> str:
    import hashlib
    import hmac

    password = (os.getenv("CREDITREWARDS_ANALYTICS_ADMIN_PASSWORD") or "").strip()
    if not password:
        return ""
    return hmac.new(b"paycue-analytics-admin", password.encode(), hashlib.sha256).hexdigest()


def verify_admin_token(token: str | None) -> bool:
    expected = _admin_token()
    if not expected or not token:
        return False
    import hmac as hm

    return hm.compare_digest(expected, token)


def ingest_events(payload: dict[str, Any]) -> dict[str, Any]:
    if not analytics_enabled():
        return {"accepted": 0, "disabled": True}

    device_id = str(payload.get("device_id") or "").strip()
    session_id = str(payload.get("session_id") or "").strip()
    events = payload.get("events") or []
    if not device_id or not session_id:
        raise ValueError("device_id and session_id are required")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a non-empty list")

    received_at = utc_now()
    locale = str(payload.get("locale") or "") or None
    user_agent = str(payload.get("user_agent") or "") or None
    card_count = payload.get("card_count")
    if card_count is not None:
        card_count = int(card_count)

    rows: list[tuple[str, str, str, str, str, str]] = []
    first_occurred = received_at
    last_occurred = received_at

    for raw in events[:100]:
        if not isinstance(raw, dict):
            continue
        event_type = str(raw.get("event_type") or "").strip()
        if not event_type or len(event_type) > 64:
            continue
        occurred_at = str(raw.get("occurred_at") or received_at).strip()
        props = raw.get("properties") or {}
        if not isinstance(props, dict):
            props = {}
        props_json = json.dumps(props, ensure_ascii=False)
        rows.append((device_id, session_id, event_type, occurred_at, props_json, received_at))
        if occurred_at < first_occurred:
            first_occurred = occurred_at
        if occurred_at > last_occurred:
            last_occurred = occurred_at

    if not rows:
        raise ValueError("no valid events")

    with session() as conn:
        repo = AnalyticsRepository(conn)
        repo.upsert_device(
            device_id=device_id,
            seen_at=last_occurred,
            locale=locale,
            user_agent=user_agent,
            card_count=card_count,
            meta={"last_session_id": session_id},
        )
        repo.upsert_session_start(
            session_id=session_id,
            device_id=device_id,
            started_at=first_occurred,
        )
        for raw in events:
            if not isinstance(raw, dict):
                continue
            if raw.get("event_type") == "app_close":
                duration = raw.get("properties", {}).get("duration_sec")
                try:
                    duration_sec = int(duration) if duration is not None else None
                except (TypeError, ValueError):
                    duration_sec = None
                repo.close_session(
                    session_id=session_id,
                    ended_at=str(raw.get("occurred_at") or received_at),
                    duration_sec=duration_sec,
                )
                break
        accepted = repo.insert_events(rows)

    return {"accepted": accepted, "disabled": False}


def trial_summary(*, days: int = 7) -> dict[str, Any]:
    since_dt = datetime.now(UTC) - timedelta(days=days)
    since = since_dt.replace(microsecond=0).isoformat()

    with session() as conn:
        repo = AnalyticsRepository(conn)
        counts = repo.summary_counts(since=since)
        by_type = repo.events_by_type(since=since)
        devices = repo.recent_devices(limit=50)
        events = repo.recent_events(limit=100)

    return {
        "window_days": days,
        "since": since,
        "counts": counts,
        "events_by_type": by_type,
        "recent_devices": devices,
        "recent_events": events,
        "generated_at": utc_now(),
    }
