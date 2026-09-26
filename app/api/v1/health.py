"""Liveness/readiness probes."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DbSession
from app.core.redis_client import get_cache

router = APIRouter(tags=["system"])


@router.get("/health", summary="Health check", tags=["system"])
async def health(db: DbSession) -> dict[str, Any]:
    """Reports DB reachability, which cache backend is live, and feature flags.

    Never returns 500 for a degraded dependency - a demo box without Redis should
    still show as ``"cache": {"backend": "memory", "degraded": true}``.
    """
    database_ok = True
    database_error: str | None = None
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health must not raise
        database_ok = False
        database_error = type(exc).__name__

    cache = await get_cache()
    return {
        "status": "ok" if database_ok else "degraded",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": {
            "connected": database_ok,
            "dialect": "postgresql+asyncpg",
            "pooled_endpoint": "-pooler" in (settings.database_url or ""),
            "error": database_error,
        },
        "cache": {
            "backend": cache.kind,
            "degraded": cache.kind != "redis",
            "redis_configured": settings.redis_configured,
        },
        "features": {
            "chatbot_enabled": settings.chatbot_enabled,
            "chatbot_provider": settings.chatbot_provider,
            "scheduler_enabled": settings.scheduler_enabled,
            "rate_limit_enabled": settings.rate_limit_enabled,
        },
    }


@router.get("/health/live", summary="Liveness probe", tags=["system"])
async def liveness() -> dict[str, str]:
    return {"status": "alive"}
