"""User-facing routes: profile, avatar, preferences, dashboard, bookmarks."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, File, Query, UploadFile, status

from app.core.deps import CurrentUser, DbSession, OptionalUser, Pagination
from app.core.logging_config import get_logger
from app.db.models.bookmark import BookmarkTarget
from app.schemas.bookmark import BookmarkRead
from app.schemas.common import MessageResponse, Page
from app.schemas.user import (
    AvatarRead,
    DashboardResponse,
    PreferencesRead,
    PreferencesUpdate,
    UserRead,
    UserUpdate,
)
from app.schemas.auth import CurrentUserRead
from app.services import media_service, user_service
from app.services import bookmark_service as bookmarks

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, summary="My profile")
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead, summary="Update my profile")
async def update_me(payload: UserUpdate, db: DbSession, user: CurrentUser) -> UserRead:
    """Partial update - only the fields present in the body are written."""
    updated = await user_service.update_profile(db, user, payload)
    return UserRead.model_validate(updated)


@router.post(
    "/me/avatar",
    response_model=AvatarRead,
    status_code=status.HTTP_200_OK,
    summary="Upload my avatar",
)
async def upload_avatar(
    db: DbSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File(description="PNG, JPEG, WEBP or GIF (max 5 MB)")],
) -> AvatarRead:
    """Stores the image under ``MEDIA_ROOT/avatars`` and returns its public URL.

    The previous local file is deleted so a user cannot accumulate orphans.
    """
    public_url, written = await media_service.save_avatar(user.id, file)
    previous = user.avatar_url
    user.avatar_url = public_url
    db.add(user)
    await db.commit()
    if previous and previous != public_url:
        media_service.delete_local_media(previous)
    return AvatarRead(avatar_url=public_url, bytes_uploaded=written, message="Avatar updated")


@router.get("/me/preferences", response_model=PreferencesRead, summary="My preferences")
async def read_preferences(db: DbSession, user: CurrentUser) -> PreferencesRead:
    preference = await user_service.get_or_create_preferences(db, user)
    return PreferencesRead.model_validate(preference)


@router.patch("/me/preferences", response_model=PreferencesRead, summary="Update my preferences")
async def update_preferences(
    payload: PreferencesUpdate, db: DbSession, user: CurrentUser
) -> PreferencesRead:
    """``favorite_categories`` accepts category slugs; unknown slugs are a 404."""
    preference = await user_service.update_preferences(
        db, user, payload.favorite_categories, payload.display_prefs
    )
    return PreferencesRead.model_validate(preference)


@router.get(
    "/me/dashboard",
    response_model=DashboardResponse,
    summary="Personalised home payload",
)
async def dashboard(db: DbSession, user: CurrentUser) -> DashboardResponse:
    """Greeting + recent activity + favourite fandoms + recommended content.

    Registered tier: visitors calling this get a 401 from the dependency.
    """
    return await user_service.build_dashboard(db, user)


@router.get(
    "/me/bookmarks",
    response_model=Page[BookmarkRead],
    summary="My bookmarks",
)
async def my_bookmarks(
    db: DbSession,
    user: CurrentUser,
    pagination: Pagination,
    content_type: Annotated[
        Optional[BookmarkTarget], Query(description="Filter by target type")
    ] = None,
) -> Page[BookmarkRead]:
    return await bookmarks.paged_bookmarks(db, user, pagination, target=content_type)
