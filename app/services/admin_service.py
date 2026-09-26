"""Admin analytics: read from Redis counters first, Postgres as the fallback.

Deliberately avoids ``SELECT COUNT(*) FROM users`` style live aggregates for the
numbers that change constantly (DAU, category popularity, chatbot volume) - those
are INCR-ed in Redis on the hot path and read straight back here. Only slow-moving
totals (row counts, moderation queues) hit the database.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging_config import get_logger
from app.core.redis_client import cache_key, get_cache, stats_key
from app.db.models.bookmark import Bookmark
from app.db.models.category import Category
from app.db.models.character import Character
from app.db.models.content import Content, ContentStatus
from app.db.models.feedback import Feedback, FeedbackStatus
from app.db.models.merchandise import Merchandise
from app.db.models.rating import Rating
from app.db.models.submission import FanSubmission, SubmissionStatus
from app.db.models.user import User, UserRole
from app.schemas.admin import (
    ActiveUsersStat,
    AdminStats,
    ChatbotVolumeStat,
    PopularCategoryStat,
)

logger = get_logger(__name__)

_DAU_WINDOW_DAYS = 7
_CHATBOT_WINDOW_DAYS = 7


async def _cache_int(cache, key: str) -> Optional[int]:
    raw = await cache.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def _daily_series(cache, prefix: str, days: int) -> list[tuple[str, int]]:
    today = dt.datetime.now(dt.timezone.utc).date()
    keys = [stats_key(prefix, (today - dt.timedelta(days=offset)).isoformat()) for offset in range(days)]
    values = await cache.mget(keys)
    series: list[tuple[str, int]] = []
    for key, raw in zip(keys, values, strict=False):
        series.append((key.rsplit(":", 1)[-1], int(raw or 0)))
    series.reverse()
    return series


async def _active_users_window(cache, days: int = _DAU_WINDOW_DAYS) -> list[ActiveUsersStat]:
    series = await _daily_series(cache, "active_users", days)
    return [ActiveUsersStat(date=date, unique_logins=count, source="redis") for date, count in series]


async def _chatbot_volume(cache, days: int = _CHATBOT_WINDOW_DAYS) -> list[ChatbotVolumeStat]:
    today = dt.datetime.now(dt.timezone.utc).date()
    message_keys = [
        stats_key("chatbot_messages", (today - dt.timedelta(days=offset)).isoformat())
        for offset in range(days)
    ]
    session_keys = [
        stats_key("chatbot_sessions", (today - dt.timedelta(days=offset)).isoformat())
        for offset in range(days)
    ]
    messages = await cache.mget(message_keys)
    sessions = await cache.mget(session_keys)
    rows: list[ChatbotVolumeStat] = []
    for message_key, session_key, raw_messages, raw_sessions in zip(
        message_keys, session_keys, messages, sessions, strict=False
    ):
        rows.append(
            ChatbotVolumeStat(
                date=message_key.rsplit(":", 1)[-1],
                messages=int(raw_messages or 0),
                sessions=int(raw_sessions or 0),
            )
        )
    rows.reverse()
    return rows


async def _popular_categories(session: AsyncSession, cache) -> list[PopularCategoryStat]:
    """Merge Redis browse counters onto the category rows (0 when never viewed)."""
    categories = list((await session.execute(select(Category).order_by(Category.id))).scalars().all())
    slugs = [category.slug for category in categories]
    counters = await cache.mget([stats_key("category", slug) for slug in slugs])

    counts = dict(
        (
            await session.execute(
                select(Content.category_id, func.count(Content.id))
                .where(Content.status == ContentStatus.PUBLISHED)
                .group_by(Content.category_id)
            )
        ).all()
    )
    stats = [
        PopularCategoryStat(
            category_id=category.id,
            slug=category.slug,
            name=category.name,
            views=int(raw or 0),
            content_count=int(counts.get(category.id, 0)),
        )
        for category, raw in zip(categories, counters, strict=False)
    ]
    # Most-viewed first, ties broken by content volume then id for determinism.
    stats.sort(key=lambda item: (-item.views, -item.content_count, item.category_id))
    return stats


async def build_stats(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> AdminStats:
    cache = await get_cache()

    users_by_role = {
        role.value: int(count)
        for role, count in (
            await session.execute(select(User.role, func.count(User.id)).group_by(User.role))
        ).all()
    }
    content_by_status = {
        status.value: int(count)
        for status, count in (
            await session.execute(
                select(Content.status, func.count(Content.id)).group_by(Content.status)
            )
        ).all()
    }

    dau_series = await _active_users_window(cache)
    chatbot_series = await _chatbot_volume(cache)
    total_chatbot_messages = sum(item.messages for item in chatbot_series)
    total_chatbot_sessions = sum(item.sessions for item in chatbot_series)

    stats = AdminStats(
        generated_at=dt.datetime.now(dt.timezone.utc),
        cache_backend=cache.kind,
        total_users=sum(users_by_role.values()),
        users_by_role=users_by_role,
        active_users_today=sum(
            item.unique_logins for item in dau_series if item.date == dt.datetime.now(dt.timezone.utc).date().isoformat()
        ),
        active_users_window=dau_series,
        total_content=int(
            (await session.execute(select(func.count(Content.id)))).scalar() or 0
        ),
        content_by_status=content_by_status,
        total_characters=int((await session.execute(select(func.count(Character.id)))).scalar() or 0),
        total_merchandise=int((await session.execute(select(func.count(Merchandise.id)))).scalar() or 0),
        total_bookmarks=int((await session.execute(select(func.count(Bookmark.id)))).scalar() or 0),
        total_ratings=int((await session.execute(select(func.count(Rating.id)))).scalar() or 0),
        pending_submissions=int(
            (
                await session.execute(
                    select(func.count(FanSubmission.id)).where(
                        FanSubmission.status == SubmissionStatus.PENDING
                    )
                )
            ).scalar()
            or 0
        ),
        open_feedback=int(
            (
                await session.execute(
                    select(func.count(Feedback.id)).where(Feedback.status == FeedbackStatus.OPEN)
                )
            ).scalar()
            or 0
        ),
        popular_categories=await _popular_categories(session, cache),
        chatbot_volume=chatbot_series,
        chatbot_total_messages=total_chatbot_messages,
    )
    logger.info(
        "admin_stats_built",
        extra={
            "cache_backend": cache.kind,
            "active_users_today": stats.active_users_today,
            "chatbot_messages": total_chatbot_messages,
        },
    )
    return stats
