"""Admin routes. Every endpoint depends on ``require_admin`` (401/403 otherwise)."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import AdminUser, DbSession, Pagination
from app.core.logging_config import get_logger
from app.db.models.feedback import FeedbackStatus, FeedbackType
from app.db.models.submission import SubmissionStatus
from app.schemas.admin import AdminStats, TaskResult
from app.schemas.character import CharacterCreate, CharacterRead, CharacterUpdate
from app.schemas.common import MessageResponse, Page
from app.schemas.content import ContentCreate, ContentDetail, ContentFilters, ContentListItem, ContentUpdate
from app.schemas.feedback import FeedbackAdminRead, FeedbackUpdate
from app.schemas.merchandise import MerchandiseCreate, MerchandiseRead, MerchandiseUpdate
from app.schemas.submission import SubmissionListItem, SubmissionUpdate
from app.db.session import async_session_maker
from app.services import (
    admin_service,
    character_service,
    content_service,
    feedback_service,
    merchandise_service,
    submission_service,
)
from app.services.popularity_service import flush_all

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ------------------------------------------------------------------ content
@router.get("/content", response_model=Page[ContentListItem], summary="List all content (incl. drafts)")
async def list_all_content(
    db: DbSession,
    admin: AdminUser,
    pagination: Pagination,
    filters: Annotated[ContentFilters, Query()],
) -> Page[ContentListItem]:
    """Same filters as the public endpoint, but drafts are visible and
    ``status`` can be set explicitly."""
    return await content_service.list_content(db, filters, pagination, is_admin=True)


@router.post(
    "/content",
    response_model=ContentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create content",
)
async def create_content(payload: ContentCreate, db: DbSession, admin: AdminUser) -> ContentDetail:
    return await content_service.create_content(db, payload, admin)


@router.patch("/content/{content_id}", response_model=ContentDetail, summary="Update content")
async def update_content(
    content_id: int, payload: ContentUpdate, db: DbSession, admin: AdminUser
) -> ContentDetail:
    return await content_service.update_content(db, content_id, payload, admin)


@router.delete(
    "/content/{content_id}",
    response_model=MessageResponse,
    summary="Delete content",
)
async def delete_content(content_id: int, db: DbSession, admin: AdminUser) -> MessageResponse:
    await content_service.delete_content(db, content_id, admin)
    return MessageResponse(message=f"content {content_id} deleted")


# --------------------------------------------------------------- characters
@router.get(
    "/characters",
    response_model=Page[CharacterRead],
    summary="List characters",
)
async def list_characters(
    db: DbSession,
    admin: AdminUser,
    pagination: Pagination,
    category: Annotated[Optional[str], Query(description="Filter by category slug")] = None,
    search: Annotated[Optional[str], Query(description="Case-insensitive name match")] = None,
) -> Page[CharacterRead]:
    """Filterable listing backing the admin management table."""
    return await character_service.list_characters(
        db, pagination, category=category, search=search
    )


@router.post(
    "/characters",
    response_model=CharacterRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a character",
)
async def create_character(payload: CharacterCreate, db: DbSession, admin: AdminUser) -> CharacterRead:
    return await character_service.create_character(db, payload, admin)


@router.patch("/characters/{character_id}", response_model=CharacterRead, summary="Update a character")
async def update_character(
    character_id: int, payload: CharacterUpdate, db: DbSession, admin: AdminUser
) -> CharacterRead:
    return await character_service.update_character(db, character_id, payload, admin)


@router.delete("/characters/{character_id}", response_model=MessageResponse, summary="Delete a character")
async def delete_character(character_id: int, db: DbSession, admin: AdminUser) -> MessageResponse:
    await character_service.delete_character(db, character_id, admin)
    return MessageResponse(message=f"character {character_id} deleted")


# -------------------------------------------------------------- merchandise
@router.get(
    "/merchandise",
    response_model=Page[MerchandiseRead],
    summary="List merchandise",
)
async def list_merchandise(
    db: DbSession,
    admin: AdminUser,
    pagination: Pagination,
    category: Annotated[Optional[str], Query(description="Filter by category slug")] = None,
    tag: Annotated[Optional[str], Query(description="Filter by merchandise tag")] = None,
    upcoming: Annotated[Optional[bool], Query(description="Only upcoming releases")] = None,
) -> Page[MerchandiseRead]:
    """Filterable listing backing the admin management table."""
    return await merchandise_service.list_merchandise(
        db, pagination, category=category, tag=tag, upcoming=upcoming
    )


@router.post(
    "/merchandise",
    response_model=MerchandiseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create merchandise",
)
async def create_merchandise(
    payload: MerchandiseCreate, db: DbSession, admin: AdminUser
) -> MerchandiseRead:
    return await merchandise_service.create_merchandise(db, payload, admin)


@router.patch(
    "/merchandise/{item_id}", response_model=MerchandiseRead, summary="Update merchandise"
)
async def update_merchandise(
    item_id: int, payload: MerchandiseUpdate, db: DbSession, admin: AdminUser
) -> MerchandiseRead:
    return await merchandise_service.update_merchandise(db, item_id, payload, admin)


@router.delete("/merchandise/{item_id}", response_model=MessageResponse, summary="Delete merchandise")
async def delete_merchandise(item_id: int, db: DbSession, admin: AdminUser) -> MessageResponse:
    await merchandise_service.delete_merchandise(db, item_id, admin)
    return MessageResponse(message=f"merchandise {item_id} deleted")


# -------------------------------------------------------------- submissions
@router.get(
    "/submissions",
    response_model=Page[SubmissionListItem],
    summary="Moderation queue",
)
async def list_submissions(
    db: DbSession,
    admin: AdminUser,
    pagination: Pagination,
    status_filter: Annotated[
        Optional[SubmissionStatus],
        Query(alias="status", description="pending | approved | rejected"),
    ] = None,
) -> Page[SubmissionListItem]:
    return await submission_service.list_submissions(db, pagination, status=status_filter)


@router.get("/submissions/{submission_id}", response_model=SubmissionListItem, summary="Submission detail")
async def get_submission(
    submission_id: int, db: DbSession, admin: AdminUser
) -> SubmissionListItem:
    return await submission_service.get_submission(db, submission_id)


@router.patch("/submissions/{submission_id}", response_model=SubmissionListItem, summary="Approve or reject")
async def review_submission(
    submission_id: int, payload: SubmissionUpdate, db: DbSession, admin: AdminUser
) -> SubmissionListItem:
    """Sets ``status`` plus ``reviewed_by`` = the acting admin."""
    return await submission_service.review_submission(db, submission_id, payload, admin)


# ----------------------------------------------------------------- feedback
@router.get("/feedback", response_model=Page[FeedbackAdminRead], summary="List feedback")
async def list_feedback(
    db: DbSession,
    admin: AdminUser,
    pagination: Pagination,
    status_filter: Annotated[
        Optional[FeedbackStatus], Query(alias="status", description="open | reviewed | closed")
    ] = None,
    type_filter: Annotated[Optional[FeedbackType], Query(alias="type", description="bug | suggestion | query")] = None,
) -> Page[FeedbackAdminRead]:
    return await feedback_service.list_feedback(db, pagination, status=status_filter, type_=type_filter)


@router.get("/feedback/{feedback_id}", response_model=FeedbackAdminRead, summary="Feedback detail")
async def get_feedback_item(feedback_id: int, db: DbSession, admin: AdminUser) -> FeedbackAdminRead:
    from app.core.errors import NotFoundError
    from app.db.models.feedback import Feedback

    feedback = await db.get(Feedback, feedback_id)
    if feedback is None:
        raise NotFoundError(f"feedback {feedback_id} not found")
    return FeedbackAdminRead.model_validate(feedback)


@router.patch(
    "/feedback/{feedback_id}", response_model=FeedbackAdminRead, summary="Update feedback"
)
async def update_feedback_item(
    feedback_id: int, payload: FeedbackUpdate, db: DbSession, admin: AdminUser
) -> FeedbackAdminRead:
    return await feedback_service.update_feedback(db, feedback_id, payload, admin)


# ------------------------------------------------------------------- stats
@router.get("/stats", response_model=AdminStats, summary="Platform statistics")
async def stats(db: DbSession, admin: AdminUser) -> AdminStats:
    """Active users, popular categories and chatbot volume come from Redis
    counters; only slow-moving totals are counted in Postgres."""
    return await admin_service.build_stats(db, async_session_maker)


@router.post(
    "/tasks/flush-popularity",
    response_model=TaskResult,
    summary="Force the Redis -> Postgres counter flush",
)
async def force_flush(admin: AdminUser) -> TaskResult:
    """Manual trigger for the same job APScheduler runs every interval."""
    import datetime as dt

    results = await flush_all(async_session_maker)
    return TaskResult(
        task="flush_popularity_counters",
        updated_rows=sum(result.rows_updated for result in results),
        keys_processed=sum(result.keys_processed for result in results),
        finished_at=dt.datetime.now(dt.timezone.utc),
    )
