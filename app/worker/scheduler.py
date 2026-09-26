"""Scheduled Redis -> Postgres flush for view/popularity counters.

APScheduler's AsyncIOScheduler runs inside the FastAPI process, which keeps the
deployment story simple (one container, no beat worker). Point
``POPULARITY_FLUSH_INTERVAL_SECONDS`` at your cadence; the job is idempotent and
safe to run concurrently in more than one instance because counters are claimed
with an atomic RENAME.

For an out-of-process alternative (separate beat container, multiple web replicas)
run the same flush manually:

    python -m app.worker.flush_popularity
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.session import async_session_maker
from app.services import popularity_service

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None

JOB_ID_FLUSH_POPULARITY = "flush_popularity_counters"


async def flush_popularity_counters() -> None:
    """Job body: drain Redis counters into Postgres."""
    try:
        results = await popularity_service.flush_all(async_session_maker)
        logger.info(
            "popularity_flush_completed",
            extra={
                "entities": [result.entity for result in results],
                "rows_updated": sum(result.rows_updated for result in results),
                "views_applied": sum(result.views_applied for result in results),
            },
        )
    except Exception as exc:  # noqa: BLE001 - a failed job must not kill the app
        logger.error("popularity_flush_failed", extra={"error": str(exc), "error_type": type(exc).__name__})


def start_scheduler() -> AsyncIOScheduler | None:
    """Start the background scheduler unless SCHEDULER_ENABLED is false."""
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled", extra={"flag": "SCHEDULER_ENABLED"})
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        flush_popularity_counters,
        trigger=IntervalTrigger(seconds=settings.popularity_flush_interval_seconds),
        id=JOB_ID_FLUSH_POPULARITY,
        name="Flush Redis view counters into Postgres",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "scheduler_started",
        extra={"jobs": [job.id for job in scheduler.get_jobs()],
               "interval_seconds": settings.popularity_flush_interval_seconds},
    )
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler_stopped")
