"""Fan submission routes (registered tier submits, admin moderates)."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.submission import SubmissionCreate, SubmissionRead
from app.services import submission_service

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post(
    "",
    response_model=SubmissionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit fan content for review",
)
async def create_submission(payload: SubmissionCreate, db: DbSession, user: CurrentUser) -> SubmissionRead:
    """New submissions always start as ``status=pending`` - clients cannot set it."""
    return await submission_service.create_submission(db, user, payload)


@router.get("", response_model=Page[SubmissionRead], summary="My submissions")
async def my_submissions(db: DbSession, user: CurrentUser, pagination: Pagination) -> Page[SubmissionRead]:
    return await submission_service.list_user_submissions(db, user, pagination)
