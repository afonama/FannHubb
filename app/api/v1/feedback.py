"""Feedback routes - open to anonymous visitors and registered users alike."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, DbSession, OptionalUser, Pagination
from app.core.rate_limit import for_endpoint as rate_limit_for
from app.schemas.common import MessageResponse, Page
from app.schemas.feedback import FeedbackCreate, FeedbackRead
from app.services import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])

# Visitors are the abuse vector here, so the limit is per IP and generous in time.
rate_limit_feedback = rate_limit_for("feedback")


@router.post(
    "",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send feedback (anonymous allowed)",
    responses={429: {"description": "Rate limit exceeded"}},
)
async def create_feedback(
    payload: FeedbackCreate,
    db: DbSession,
    user: OptionalUser,
    _limit: Annotated[None, Depends(rate_limit_feedback)],
) -> FeedbackRead:
    """Works without a token: ``user_id`` is stored as NULL for visitors."""
    return await feedback_service.create_feedback(db, payload, user=user)


@router.get(
    "",
    response_model=Page[FeedbackRead],
    summary="Feedback I have sent",
)
async def my_feedback(db: DbSession, user: CurrentUser, pagination: Pagination) -> Page[FeedbackRead]:
    """The caller's own feedback, so a user can track what they reported."""
    return await feedback_service.list_user_feedback(db, user, pagination)
