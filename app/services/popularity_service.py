"""View/popularity counters: Redis INCR on the hot path, batched flush to Postgres.

Read path
    ``GET /content/{id}`` -> ``record_view`` (one Redis INCR, no DB write).

Flush path
    APScheduler job (see app.worker.scheduler) -> ``flush_all`` every
    ``POPULARITY_FLUSH_INTERVAL_SECONDS``:
      1. RENAME every pending counter to a ``:flushing`` key (atomic, so views
         arriving mid-flush land in a fresh counter instead of being lost);
      2. read the deltas and add them onto ``view_count`` in one transaction;
      3. recompute ``popularity_score`` (views + rating average + recency);
      4. delete the ``:flushing`` keys.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Literal, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging_config import get_logger
from app.core.redis_client import (
    cache_key,
    get_cache,
    stats_key,
    view_counter_key,
)
from app.db.models.character import Character
from app.db.models.content import Content
from app.db.models.merchandise import Merchandise
from app.db.models.rating import Rating, RatingScale

logger = get_logger(__name__)

ViewEntity = Literal["content", "character", "merchandise"]
_VIEW_PREFIXES: dict[str, str] = {
    "content": "content",
    "character": "character",
    "merchandise": "merchandise",
}

#: Full-text ranking weight constants (documented so scores are reproducible).
WEIGHT_VIEWS = 2.0
WEIGHT_RATING = 1.5
WEIGHT_RECENCY = 2.0
RECENCY_HALFLIFE_DAYS = 30.0


@dataclass
class FlushResult:
    """Outcome of one flush cycle, surfaced by the admin task endpoint."""

    entity: str
    keys_processed: int = 0
    rows_updated: int = 0
    views_applied: int = 0
    detail: dict[str, int] = field(default_factory=dict)
    finished_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


# ------------------------------------------------------------- write path
async def record_view(entity: ViewEntity, entity_id: int) -> int:
    """Bump the pending view counter; returns the un-flushed total."""
    cache = await get_cache()
    return await cache.incr(view_counter_key(entity, entity_id))


async def record_category_browse(category_slug: str) -> int:
    cache = await get_cache()
    return await cache.incr(stats_key("category", category_slug))


async def record_active_user(user_id: int) -> int:
    """Count one active user for today (DAU)."""
    cache = await get_cache()
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return await cache.incr(stats_key("active_users", today))


async def record_chatbot_interaction(session_count: int = 0, message_count: int = 2) -> None:
    """Track chatbot volume for the admin dashboard."""
    cache = await get_cache()
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    await cache.incr(stats_key("chatbot_messages", today), message_count)
    if session_count:
        await cache.incr(stats_key("chatbot_sessions", today), session_count)


# -------------------------------------------------------------- read path
async def pending_delta(entity: ViewEntity, entity_id: int) -> int:
    """Views not yet flushed to Postgres for one row."""
    cache = await get_cache()
    raw = await cache.get(view_counter_key(entity, entity_id))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


async def view_count_with_live_delta(entity: ViewEntity, entity_id: int, stored: int) -> int:
    """Stored Postgres value plus anything Redis has accumulated since the flush.

    Keeps the number on screen honest between scheduled flushes.
    """
    return stored + await pending_delta(entity, entity_id)


async def view_count_with_live_deltas(entity: ViewEntity, ids: list[int], stored: dict[int, int]) -> dict[int, int]:
    """Batched variant of :func:`view_count_with_live_delta` (one MGET)."""
    if not ids:
        return {}
    cache = await get_cache()
    keys = [view_counter_key(entity, item_id) for item_id in ids]
    values = await cache.mget(keys)
    result: dict[int, int] = {}
    for item_id, raw in zip(ids, values, strict=False):
        try:
            delta = int(raw or 0)
        except (TypeError, ValueError):
            delta = 0
        result[item_id] = stored.get(item_id, 0) + delta
    return result


# -------------------------------------------------------------- flush job
async def _drain_entity(entity: str) -> tuple[dict[int, int], int]:
    """Atomically claim pending counters and return ``{row_id: delta}``."""
    cache = await get_cache()
    prefix = cache_key("views", entity) + ":*"
    keys = await cache.scan_keys(prefix)
    if not keys:
        return {}, 0

    claimed: list[tuple[str, str]] = []
    for key in keys:
        # RENAME is atomic: new views land on the freshly created original key.
        staging = f"{key}:flushing"
        if await cache.rename(key, staging):
            claimed.append((staging, key))

    deltas: dict[int, int] = {}
    staging_keys = [staging for staging, _ in claimed]
    raw_values = await cache.mget(staging_keys)
    for (staging, _), raw in zip(claimed, raw_values, strict=False):
        try:
            value = int(raw or 0)
            row_id = int(staging.rsplit(":", 2)[1])
        except (TypeError, ValueError, IndexError):
            value, row_id = 0, 0
        if value > 0 and row_id > 0:
            deltas[row_id] = deltas.get(row_id, 0) + value
        await cache.delete(staging)
    return deltas, len(claimed)


def compute_popularity_score(
    view_count: int,
    average_rating: float,
    rating_count: int,
    release_date: Optional[dt.date],
    now: Optional[dt.datetime] = None,
) -> float:
    """Blend of log-scaled views, rating average and recency decay.

    Deterministic and cheap so it can be recomputed for every touched row on
    each flush instead of drifting between requests.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    view_component = WEIGHT_VIEWS * math.log10(max(0, view_count) + 1)
    rating_component = WEIGHT_RATING * (average_rating / 5.0) * math.log10(rating_count + 1)
    recency_component = 0.0
    if release_date:
        age_days = (now.date() - release_date).days
        if age_days >= 0:
            recency_component = WEIGHT_RECENCY * math.pow(0.5, age_days / RECENCY_HALFLIFE_DAYS)
    return round(view_component + rating_component + recency_component, 4)


async def _average_ratings(session: AsyncSession, content_ids: list[int]) -> dict[int, tuple[float, int]]:
    """Average star rating per content id (thumbs excluded from the average)."""
    if not content_ids:
        return {}
    stmt = (
        select(
            Rating.content_id.label("content_id"),
            func.avg(Rating.value).label("avg_value"),
            func.count(Rating.id).label("rating_count"),
        )
        .where(Rating.content_id.in_(content_ids), Rating.scale == RatingScale.STARS)
        .group_by(Rating.content_id)
    )
    rows = (await session.execute(stmt)).all()
    return {
        row.content_id: (float(row.avg_value or 0.0), int(row.rating_count or 0))
        for row in rows
    }


async def flush_all(session_factory: async_sessionmaker[AsyncSession]) -> list[FlushResult]:
    """Apply every pending Redis delta to Postgres. Called by APScheduler."""
    results: list[FlushResult] = []

    for entity in _VIEW_PREFIXES:
        async with session_factory() as session:
            deltas, keys_processed = await _drain_entity(entity)
            result = FlushResult(entity=entity, keys_processed=keys_processed)
            if not deltas:
                results.append(result)
                continue

            if entity == "content":
                rows = (
                    await session.execute(
                        select(Content.id, Content.view_count, Content.release_date).where(
                            Content.id.in_(list(deltas))
                        )
                    )
                ).all()
                ratings = await _average_ratings(session, list(deltas))
                for row in rows:
                    new_views = row.view_count + deltas[row.id]
                    avg, count = ratings.get(row.id, (0.0, 0))
                    score = compute_popularity_score(new_views, avg, count, row.release_date)
                    await session.execute(
                        update(Content)
                        .where(Content.id == row.id)
                        .values(view_count=new_views, popularity_score=score)
                    )
                    result.rows_updated += 1
                    result.views_applied += deltas[row.id]
            else:
                model = {"character": Character, "merchandise": Merchandise}[entity]
                for row_id, delta in deltas.items():
                    await session.execute(
                        update(model).where(model.id == row_id).values(view_count=model.view_count + delta)
                    )
                    result.rows_updated += 1
                    result.views_applied += delta

            await session.commit()
        logger.info(
            "popularity_flushed",
            extra={
                "entity": entity,
                "rows_updated": result.rows_updated,
                "views_applied": result.views_applied,
                "keys": result.keys_processed,
            },
        )
        results.append(result)

    return results
