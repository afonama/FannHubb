"""Ratings: one row per (user, content) supporting both stars and thumbs."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.logging_config import get_logger
from app.db.models.content import Content, ContentStatus
from app.db.models.rating import Rating, RatingScale
from app.db.models.user import User
from app.schemas.rating import ContentRatingSummary, RatingCreate, RatingRead, RatingResponse

logger = get_logger(__name__)


async def rate_content(
    session: AsyncSession, user: User, content_id: int, payload: RatingCreate
) -> RatingResponse:
    """Create or update the caller's rating, returning the new aggregate.

    Design note: a single endpoint handles both scales. ``upsert`` semantics keep
    the ``uq_ratings_user_content`` constraint meaningful (one rating per user per
    item) and let a user switch from stars to thumbs without a second endpoint.
    """
    content = (
        await session.execute(
            select(Content).where(Content.id == content_id, Content.status == ContentStatus.PUBLISHED)
        )
    ).scalar_one_or_none()
    if content is None:
        raise NotFoundError(f"content {content_id} not found")

    rating = (
        await session.execute(
            select(Rating).where(Rating.user_id == user.id, Rating.content_id == content_id)
        )
    ).scalar_one_or_none()

    created = rating is None
    if created:
        rating = Rating(
            user_id=user.id, content_id=content_id, scale=payload.scale, value=payload.value
        )
    else:
        rating.scale = payload.scale
        rating.value = payload.value

    session.add(rating)
    await session.commit()
    await session.refresh(rating)

    logger.info(
        "rating_saved",
        extra={
            "user_id": user.id,
            "content_id": content_id,
            "scale": payload.scale.value,
            "value": payload.value,
            # NOT "created": that is a reserved LogRecord attribute, and passing
            # it through extra makes logging raise KeyError *after* the commit,
            # so the write lands but the caller is told 500.
            "rating_created": created,
        },
    )
    return RatingResponse(
        rating=RatingRead.model_validate(rating),
        summary=await content_rating_summary(session, content_id),
        created=created,
    )


async def content_rating_summary(session: AsyncSession, content_id: int) -> ContentRatingSummary:
    rows = (
        await session.execute(
            select(Rating.scale, Rating.value, func.count(Rating.id))
            .where(Rating.content_id == content_id)
            .group_by(Rating.scale, Rating.value)
        )
    ).all()

    star_total = star_votes = 0
    summary = ContentRatingSummary(average=0.0, count=0)
    for scale, value, votes in rows:
        votes = int(votes)
        if scale == RatingScale.STARS:
            star_total += value * votes
            star_votes += votes
            summary.count += votes
            summary.star_distribution[str(value)] = summary.star_distribution.get(str(value), 0) + votes
        elif value == 1:
            summary.thumbs_up += votes
        else:
            summary.thumbs_down += votes
    summary.average = round(star_total / star_votes, 2) if star_votes else 0.0
    return summary


async def get_user_rating(session: AsyncSession, user: User, content_id: int) -> Optional[Rating]:
    return (
        await session.execute(
            select(Rating).where(Rating.user_id == user.id, Rating.content_id == content_id)
        )
    ).scalar_one_or_none()


async def delete_rating(session: AsyncSession, user: User, content_id: int) -> int:
    result = await session.execute(
        delete(Rating).where(Rating.user_id == user.id, Rating.content_id == content_id)
    )
    await session.commit()
    if not result.rowcount:
        raise NotFoundError(
            "No rating to delete", details={"content_id": content_id}
        )
    return int(result.rowcount)
