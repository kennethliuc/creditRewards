"""Admin routes for trial analytics dashboard."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from credit_rewards.analytics.service import (
    ADMIN_COOKIE,
    ADMIN_COOKIE_MAX_AGE,
    admin_password_configured,
    analytics_enabled,
    trial_summary,
    verify_admin_token,
    _admin_token,
)
from credit_rewards.analytics.service import ingest_events as ingest_analytics_events

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

router = APIRouter(tags=["analytics"])


class AnalyticsLoginRequest(BaseModel):
    password: str = Field(min_length=1)


class AnalyticsEventItem(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    occurred_at: str | None = None
    properties: dict[str, Any] | None = None


class AnalyticsIngestRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)
    session_id: str = Field(min_length=8, max_length=64)
    locale: str | None = None
    user_agent: str | None = None
    card_count: int | None = Field(default=None, ge=0, le=50)
    events: list[AnalyticsEventItem] = Field(min_length=1, max_length=100)


def _cookie_secure() -> bool:
    return os.getenv("CREDITREWARDS_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}


def _require_admin(request: Request) -> None:
    if not admin_password_configured():
        raise HTTPException(status_code=503, detail="Analytics admin password not configured")
    token = request.cookies.get(ADMIN_COOKIE)
    if not verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Admin login required")


@router.post("/api/analytics/events")
def analytics_ingest(body: AnalyticsIngestRequest) -> dict[str, Any]:
    if not analytics_enabled():
        return {"accepted": 0, "disabled": True}
    try:
        return ingest_analytics_events(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/analytics/status")
def analytics_status() -> dict[str, bool]:
    return {
        "enabled": analytics_enabled(),
        "admin_configured": admin_password_configured(),
    }


@router.post("/api/admin/analytics/login")
def admin_login(body: AnalyticsLoginRequest, response: Response) -> dict[str, str]:
    import hashlib
    import hmac

    if not admin_password_configured():
        raise HTTPException(status_code=503, detail="Set CREDITREWARDS_ANALYTICS_ADMIN_PASSWORD")
    expected = hmac.new(
        b"paycue-analytics-admin",
        body.password.encode(),
        hashlib.sha256,
    ).hexdigest()
    token = _admin_token()
    if not hmac.compare_digest(expected, token):
        raise HTTPException(status_code=401, detail="Invalid password")

    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=ADMIN_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
    )
    return {"status": "ok"}


@router.post("/api/admin/analytics/logout")
def admin_logout(response: Response) -> dict[str, str]:
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/api/admin/analytics/summary")
def admin_summary(request: Request, days: int = 7) -> dict[str, Any]:
    _require_admin(request)
    days = max(1, min(days, 90))
    return trial_summary(days=days)


@router.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))
