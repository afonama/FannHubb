"""Feedback from registered users *and* anonymous visitors (user_id nullable)."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.logging_config import get_logger
from app.db.models.feedback import Feedback, FeedbackStatus, FeedbackType
from app.db.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.feedback import FeedbackCreate, FeedbackRead, FeedbackUpdate

logger = get_logger(__name__)


async def create_feedback(
    session: AsyncSession, payload: FeedbackCreate, user: Optional[User] = None
) -> FeedbackRead:
    """Anonymous visitors get ``user_id = NULL``; the endpoint never requires auth."""
    feedback = Feedback(
        user_id=user.id if user is not None else None,
        type=payload.type,
        message=payload.message.strip(),
        status=FeedbackStatus.OPEN,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    logger.info(
        "feedback_created",
        extra={"feedback_id": feedback.id, "user_id": feedback.user_id, "type": payload.type.value,
               "anonymous": user is None},
    )
    return FeedbackRead.model_validate(feedback)


async def list_feedback(
    session: AsyncSession,
    page: PageParams,
    *,
    status: Optional[FeedbackStatus] = None,
    type_: Optional[FeedbackType] = None,
) -> Page[FeedbackRead]:
    stmt = select(Feedback)
    if status is not None:
        stmt = stmt.where(Feedback.status == status)
    if type_ is not None:
        stmt = stmt.where(Feedback.type == type_)

    total = int(
        (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar() or 0
    )
    rows = list(
        (
            await session.execute(
                stmt.order_by(Feedback.created_at.desc(), Feedback.id.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page.build(
        [FeedbackRead.model_validate(row) for row in rows], total, page.page, page.page_size
    )


async def list_user_feedback(
    session: AsyncSession, user: User, page: PageParams
) -> Page[FeedbackRead]:
    stmt = select(Feedback).where(Feedback.user_id == user.id)
    total = int(
        (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar() or 0
    )
    rows = list(
        (
            await session.execute(
                stmt.order_by(Feedback.created_at.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page.build(
        [FeedbackRead.model_validate(row) for row in rows], total, page.page, page.page_size
    )


async def update_feedback(
    session: AsyncSession, feedback_id: int, payload: FeedbackUpdate, actor: Optional[User] = None
) -> FeedbackRead:
    feedback = await session.get(Feedback, feedback_id)
    if feedback is None:
        raise NotFoundError(f"feedback {feedback_id} not found")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(feedback, field, value)
    feedback.updated_at = dt.datetime.now(dt.timezone.utc)
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    logger.info(
        "feedback_updated",
        extra={"feedback_id": feedback_id, "fields": sorted(changes), "actor_id": getattr(actor, "id", None)},
    )
    return FeedbackRead.model_validate(feedback)


async def moderation_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Feedback.status, func.count(Feedback.id)).group_by(Feedback.status)
        )
    ).all()
    return {status.value: int(count) for status, count in rows}
