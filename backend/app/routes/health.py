"""Health and readiness endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/ping")
def ping() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.app_env,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/")
def root() -> dict:
    return {"service": "gridgreen-backend", "docs": "/docs", "ping": "/ping"}
