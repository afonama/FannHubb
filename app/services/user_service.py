"""User profile, preferences, avatar metadata and the personalised dashboard."""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.core.logging_config import get_logger
from app.db.models.bookmark import Bookmark, BookmarkTarget
from app.db.models.category import Category
from app.db.models.character import Character
from app.db.models.content import Content, ContentStatus
from app.db.models.feedback import Feedback, FeedbackStatus, FeedbackType
from app.db.models.merchandise import Merchandise
from app.db.models.rating import Rating
from app.db.models.submission import FanSubmission, SubmissionStatus
from app.db.models.user import User, UserPreference, UserRole
from app.schemas.content import ContentListItem
from app.schemas.user import (
    AvatarRead,
    BookmarkPreview,
    DashboardResponse,
    DashboardStats,
    FavoriteFandom,
    PreferencesRead,
    RecentActivity,
    UserRead,
    UserUpdate,
)

logger = get_logger(__name__)

_DASHBOARD_CONTENT_LIMIT = 6
_DASHBOARD_BOOKMARK_LIMIT = 5
_ACTIVITY_LIMIT = 8


# ------------------------------------------------------------- fetchers
def user_load_options(*, with_preference: bool = True) -> tuple:
    options = []
    if with_preference:
        options.append(selectinload(User.preference))
    return tuple(options)


async def fetch_user_by_id(
    session: AsyncSession, user_id: int, *, with_preference: bool = True
) -> Optional[User]:
    stmt = select(User).where(User.id == user_id).options(*user_load_options(with_preference=with_preference))
    return (await session.execute(stmt)).scalar_one_or_none()


async def fetch_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    stmt = (
        select(User)
        .where(func.lower(User.email) == email.strip().lower())
        .options(*user_load_options())
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_user_or_404(session: AsyncSession, user_id: int) -> User:
    user = await fetch_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError(f"user {user_id} not found")
    return user


# -------------------------------------------------------------- profile
async def update_profile(session: AsyncSession, user: User, payload: UserUpdate) -> User:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return user
    for field, value in changes.items():
        setattr(user, field, value)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("profile_updated", extra={"user_id": user.id, "fields": sorted(changes)})
    return user


async def get_or_create_preferences(session: AsyncSession, user: User) -> UserPreference:
    if user.preference is not None:
        return user.preference
    preference = UserPreference(user_id=user.id, favorite_categories=[], display_prefs={})
    session.add(preference)
    await session.flush()
    await session.refresh(preference)
    return preference


async def update_preferences(
    session: AsyncSession, user: User, favorite_categories: Optional[list[str]], display_prefs: Optional[dict[str, Any]]
) -> UserPreference:
    preference = await get_or_create_preferences(session, user)
    if favorite_categories is not None:
        known = await _known_category_slugs(session)
        unknown = [slug for slug in favorite_categories if slug not in known]
        if unknown:
            raise NotFoundError(
                f"unknown categor{'y' if len(unknown) == 1 else 'ies'}: {', '.join(sorted(unknown))}",
                details={"unknown_slugs": sorted(unknown)},
            )
        preference.favorite_categories = favorite_categories
    if display_prefs is not None:
        preference.display_prefs = display_prefs
    preference.updated_at = dt.datetime.now(dt.timezone.utc)
    session.add(preference)
    await session.commit()
    await session.refresh(preference)
    return preference


async def _known_category_slugs(session: AsyncSession) -> set[str]:
    rows = await session.execute(select(Category.slug))
    return {row for row in rows.scalars().all()}


# ------------------------------------------------------------ dashboard
def build_greeting(user: User, now: dt.datetime | None = None) -> str:
    """Time-of-day greeting, trimmed by time of day and the user's first name."""
    now = now or dt.datetime.now(dt.timezone.utc)
    hour = now.hour
    if hour < 5:
        part = "Burning the midnight oil"
    elif hour < 12:
        part = "Good morning"
    elif hour < 18:
        part = "Good afternoon"
    else:
        part = "Good evening"
    first_name = user.name.strip().split(" ")[0] if user.name.strip() else "fan"
    suffix = ", admin" if user.role == UserRole.ADMIN else ""
    return f"{part}, {first_name}{suffix}! Ready for some fandom?"


async def _dashboard_stats(session: AsyncSession, user: User) -> DashboardStats:
    total_bookmarks = await session.scalar(
        select(func.count(Bookmark.id)).where(Bookmark.user_id == user.id)
    )
    total_ratings = await session.scalar(
        select(func.count(Rating.id)).where(Rating.user_id == user.id)
    )
    total_submissions = await session.scalar(
        select(func.count(FanSubmission.id)).where(FanSubmission.user_id == user.id)
    )
    pending = await session.scalar(
        select(func.count(FanSubmission.id)).where(
            FanSubmission.user_id == user.id, FanSubmission.status == SubmissionStatus.PENDING
        )
    )
    preference = await get_or_create_preferences(session, user)
    return DashboardStats(
        total_bookmarks=int(total_bookmarks or 0),
        total_ratings=int(total_ratings or 0),
        total_submissions=int(total_submissions or 0),
        pending_submissions=int(pending or 0),
        favorite_fandom_count=len(preference.favorite_categories),
    )


async def _recent_activity(session: AsyncSession, user: User, limit: int = _ACTIVITY_LIMIT) -> list[RecentActivity]:
    """Merge the newest rows from the four activity tables."""
    bookmark_rows = (
        await session.execute(
            select(Bookmark.content_type, Bookmark.content_id, Bookmark.created_at)
            .where(Bookmark.user_id == user.id)
            .order_by(Bookmark.created_at.desc())
            .limit(limit)
        )
    ).all()
    rating_rows = (
        await session.execute(
            select(Rating.content_id, Rating.value, Rating.created_at)
            .where(Rating.user_id == user.id)
            .order_by(Rating.created_at.desc())
            .limit(limit)
        )
    ).all()
    submission_rows = (
        await session.execute(
            select(FanSubmission.title, FanSubmission.status, FanSubmission.created_at)
            .where(FanSubmission.user_id == user.id)
            .order_by(FanSubmission.created_at.desc())
            .limit(limit)
        )
    ).all()
    feedback_rows = (
        await session.execute(
            select(Feedback.type, Feedback.status, Feedback.created_at)
            .where(Feedback.user_id == user.id)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        )
    ).all()

    activity: list[RecentActivity] = []
    for target, content_id, created_at in bookmark_rows:
        activity.append(
            RecentActivity(
                kind="bookmark",
                label=f"Saved a {target.value} (#{content_id})",
                occurred_at=created_at,
                content_id=content_id if target == BookmarkTarget.CONTENT else None,
            )
        )
    for content_id, value, created_at in rating_rows:
        activity.append(
            RecentActivity(
                kind="rating",
                label=f"Rated #{content_id} ({value}/5)" if value > 0 else f"Thumbed down #{content_id}",
                occurred_at=created_at,
                content_id=content_id,
            )
        )
    for title, status, created_at in submission_rows:
        activity.append(
            RecentActivity(kind="submission", label=f"Submission '{title}' is {status.value}", occurred_at=created_at)
        )
    for fb_type, status, created_at in feedback_rows:
        activity.append(
            RecentActivity(
                kind="feedback",
                label=f"{fb_type.value.capitalize()} feedback is {status.value}",
                occurred_at=created_at,
            )
        )

    activity.sort(key=lambda item: item.occurred_at, reverse=True)
    return activity[:limit]


async def _favorite_fandoms(session: AsyncSession, user: User) -> list[FavoriteFandom]:
    """Preference slugs first, then categories the user actually saved from."""
    preference = await get_or_create_preferences(session, user)
    saved_rows = (
        await session.execute(
            select(Content.category_id, func.count(Content.id))
            .join(Bookmark, Bookmark.content_id == Content.id)
            .where(
                Bookmark.user_id == user.id,
                Bookmark.content_type == BookmarkTarget.CONTENT,
                Content.status == ContentStatus.PUBLISHED,
            )
            .group_by(Content.category_id)
        )
    ).all()
    saved_by_category = {row[0]: int(row[1]) for row in saved_rows}

    slug_rows = await session.execute(select(Category.id, Category.slug, Category.name))
    categories = {row.id: (row.slug, row.name) for row in slug_rows}

    content_counts = dict(
        (
            await session.execute(
                select(Content.category_id, func.count(Content.id))
                .where(Content.status == ContentStatus.PUBLISHED)
                .group_by(Content.category_id)
            )
        ).all()
    )

    ordered_slugs = list(preference.favorite_categories)
    for category_id in saved_by_category:
        slug = categories.get(category_id, (None, None))[0]
        if slug and slug not in ordered_slugs:
            ordered_slugs.append(slug)

    fandoms: list[FavoriteFandom] = []
    for slug in ordered_slugs:
        match = next((cid for cid, meta in categories.items() if meta[0] == slug), None)
        if match is None:
            continue
        fandoms.append(
            FavoriteFandom(
                slug=slug,
                name=categories[match][1],
                content_count=int(content_counts.get(match, 0)),
                bookmark_count=saved_by_category.get(match, 0),
            )
        )
    return fandoms[:6]


async def _recommended_content(
    session: AsyncSession, user: User, limit: int = _DASHBOARD_CONTENT_LIMIT
) -> list[ContentListItem]:
    """Popular published content, biased towards the user's favourite fandoms."""
    preference = await get_or_create_preferences(session, user)
    stmt = (
        select(Content)
        .join(Category, Category.id == Content.category_id)
        .where(Content.status == ContentStatus.PUBLISHED)
        .options(selectinload(Content.category), selectinload(Content.tags))
    )
    if preference.favorite_categories:
        stmt = stmt.where(Category.slug.in_(preference.favorite_categories))
    stmt = stmt.order_by(Content.popularity_score.desc(), Content.id.desc()).limit(limit)
    rows = list((await session.execute(stmt)).scalars().unique().all())
    if not rows:
        stmt = (
            select(Content)
            .join(Category, Category.id == Content.category_id)
            .where(Content.status == ContentStatus.PUBLISHED)
            .options(selectinload(Content.category), selectinload(Content.tags))
            .order_by(Content.popularity_score.desc(), Content.id.desc())
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).scalars().unique().all())

    from app.services import content_service  # local import avoids a cycle

    return await content_service.to_list_items(session, rows, with_live_views=True)


async def _bookmark_previews(session: AsyncSession, user: User, limit: int = _DASHBOARD_BOOKMARK_LIMIT) -> list[BookmarkPreview]:
    from app.services import bookmark_service

    bookmarks = await bookmark_service.list_bookmarks(session, user, limit=limit, offset=0)
    return [bookmark_service.to_preview(bookmark) for bookmark in bookmarks]


async def _featured_categories(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Category.slug, Category.name, func.count(Content.id))
            .outerjoin(Content, (Content.category_id == Category.id) & (Content.status == ContentStatus.PUBLISHED))
            .group_by(Category.id, Category.slug, Category.name)
            .order_by(Category.id)
        )
    ).all()
    return [{"slug": slug, "name": name, "content_count": int(count)} for slug, name, count in rows]


async def build_dashboard(session: AsyncSession, user: User) -> DashboardResponse:
    """Assemble the personalised home payload.

    The sub-queries run sequentially on purpose: SQLAlchemy's AsyncSession is
    explicitly *not* concurrency-safe, so fanning out with asyncio.gather over a
    shared session would corrupt the identity map / connection.
    """
    stats = await _dashboard_stats(session, user)
    activity = await _recent_activity(session, user)
    fandoms = await _favorite_fandoms(session, user)
    recommended = await _recommended_content(session, user)
    previews = await _bookmark_previews(session, user)
    categories = await _featured_categories(session)

    return DashboardResponse(
        greeting=build_greeting(user),
        user=UserRead.model_validate(user),
        stats=stats,
        recent_activity=activity,
        favorite_fandoms=fandoms,
        recommended_content=recommended,
        bookmarks_preview=previews,
        featured_categories=categories,
    )
