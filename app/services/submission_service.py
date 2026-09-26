"""Fan submissions and their moderation lifecycle."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.core.logging_config import get_logger
from app.db.models.category import Category
from app.db.models.submission import FanSubmission, SubmissionStatus
from app.db.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.submission import SubmissionCreate, SubmissionListItem, SubmissionRead, SubmissionUpdate

logger = get_logger(__name__)


async def create_submission(
    session: AsyncSession, user: User, payload: SubmissionCreate
) -> SubmissionRead:
    if payload.category_id is not None and await session.get(Category, payload.category_id) is None:
        raise NotFoundError(f"category {payload.category_id} not found")

    submission = FanSubmission(
        user_id=user.id,
        title=payload.title.strip(),
        body=payload.body.strip(),
        category_id=payload.category_id,
        status=SubmissionStatus.PENDING,
    )
    session.add(submission)
    await session.commit()
    await session.refresh(submission)
    logger.info("submission_created", extra={"submission_id": submission.id, "user_id": user.id})
    return SubmissionRead.model_validate(submission)


async def _to_list_item(submission: FanSubmission, author: Optional[User]) -> SubmissionListItem:
    base = SubmissionRead.model_validate(submission)
    return SubmissionListItem(
        **base.model_dump(),
        author_name=author.name if author else None,
        author_email=author.email if author else None,
    )


async def list_user_submissions(
    session: AsyncSession, user: User, page: PageParams
) -> Page[SubmissionRead]:
    stmt = select(FanSubmission).where(FanSubmission.user_id == user.id)
    total = int(
        (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar() or 0
    )
    rows = list(
        (
            await session.execute(
                stmt.order_by(FanSubmission.created_at.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page.build(
        [SubmissionRead.model_validate(row) for row in rows], total, page.page, page.page_size
    )


async def list_submissions(
    session: AsyncSession, page: PageParams, *, status: Optional[SubmissionStatus] = None
) -> Page[SubmissionListItem]:
    stmt = select(FanSubmission).options(selectinload(FanSubmission.user))
    if status is not None:
        stmt = stmt.where(FanSubmission.status == status)

    total = int(
        (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar() or 0
    )
    rows = list(
        (
            await session.execute(
                stmt.order_by(FanSubmission.created_at.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    items = [await _to_list_item(row, getattr(row, "user", None)) for row in rows]
    return Page.build(items, total, page.page, page.page_size)


async def get_submission(session: AsyncSession, submission_id: int) -> SubmissionListItem:
    submission = (
        await session.execute(
            select(FanSubmission)
            .options(selectinload(FanSubmission.user))
            .where(FanSubmission.id == submission_id)
        )
    ).scalar_one_or_none()
    if submission is None:
        raise NotFoundError(f"submission {submission_id} not found")
    return await _to_list_item(submission, submission.user)


async def review_submission(
    session: AsyncSession, submission_id: int, payload: SubmissionUpdate, reviewer: User
) -> SubmissionListItem:
    """Approve or reject a submission; the review is attributed to ``reviewer``."""
    submission = await session.get(FanSubmission, submission_id)
    if submission is None:
        raise NotFoundError(f"submission {submission_id} not found")

    submission.status = payload.status
    submission.reviewed_by = reviewer.id
    if payload.review_note is not None:
        submission.review_note = payload.review_note
    submission.updated_at = dt.datetime.now(dt.timezone.utc)

    session.add(submission)
    await session.commit()
    logger.info(
        "submission_reviewed",
        extra={"submission_id": submission_id, "status": payload.status.value, "reviewer_id": reviewer.id},
    )
    return await get_submission(session, submission_id)


async def status_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(FanSubmission.status, func.count(FanSubmission.id)).group_by(FanSubmission.status)
        )
    ).all()
    return {status.value: int(count) for status, count in rows}
