"""Bookmark routes (registered tier)."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession, Pagination
from app.db.models.bookmark import BookmarkTarget
from app.schemas.bookmark import BookmarkCreate, BookmarkDeleteResult, BookmarkRead
from app.schemas.common import MessageResponse, Page
from app.services import bookmark_service

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


@router.get("", response_model=Page[BookmarkRead], summary="My saved items")
async def list_bookmarks(
    db: DbSession,
    user: CurrentUser,
    pagination: Pagination,
    content_type: Annotated[
        Optional[BookmarkTarget], Query(description="Filter by target type")
    ] = None,
) -> Page[BookmarkRead]:
    """Paginated listing of the caller's own bookmarks, newest first."""
    return await bookmark_service.paged_bookmarks(
        db, user, pagination, target=content_type
    )


@router.post(
    "",
    response_model=BookmarkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save an item",
    responses={404: {"description": "Target does not exist"}, 409: {"description": "Already bookmarked"}},
)
async def create_bookmark(payload: BookmarkCreate, db: DbSession, user: CurrentUser) -> BookmarkRead:
    """Polymorphic save: ``content_type`` is content | character | merchandise.

    Duplicates are rejected by the ``uq_bookmarks_user_type_content`` unique
    constraint, surfaced as a 409.
    """
    return await bookmark_service.add_bookmark(db, user, payload)


@router.delete("", response_model=BookmarkDeleteResult, summary="Remove a saved item")
async def delete_bookmark(
    db: DbSession,
    user: CurrentUser,
    content_type: Annotated[BookmarkTarget, Query(description="Target type")],
    content_id: Annotated[int, Query(gt=0)],
) -> BookmarkDeleteResult:
    """Idempotent-style delete: removing something that is not saved is a 404."""
    await bookmark_service.remove_bookmark(db, user, content_type, content_id)
    return BookmarkDeleteResult(content_type=content_type, content_id=content_id, deleted=True)


@router.get("/{bookmark_id}", response_model=BookmarkRead, summary="One saved item")
async def get_bookmark(bookmark_id: int, db: DbSession, user: CurrentUser) -> BookmarkRead:
    """Scoped to the caller's own bookmarks: another user's id yields 404."""
    from app.db.models.bookmark import Bookmark

    bookmark = await db.get(Bookmark, bookmark_id)
    from app.core.errors import NotFoundError

    if bookmark is None or bookmark.user_id != user.id:
        raise NotFoundError(f"bookmark {bookmark_id} not found")
    return await bookmark_service._to_read(db, bookmark)


@router.delete(
    "/{bookmark_id}",
    response_model=MessageResponse,
    summary="Remove a saved item by id",
    responses={404: {"description": "Not saved by this user"}},
)
async def delete_bookmark_by_id(
    bookmark_id: int, db: DbSession, user: CurrentUser
) -> MessageResponse:
    """Delete by primary key, resolving the (type, content_id) triple first."""
    from app.db.models.bookmark import Bookmark

    from app.core.errors import NotFoundError

    bookmark = await db.get(Bookmark, bookmark_id)
    if bookmark is None or bookmark.user_id != user.id:
        raise NotFoundError(f"bookmark {bookmark_id} not found")

    await bookmark_service.remove_bookmark(
        db, user, bookmark.content_type, bookmark.content_id
    )
    return MessageResponse(message=f"Bookmark {bookmark_id} removed")
