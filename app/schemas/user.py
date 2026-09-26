"""User profile, preferences, avatar and dashboard schemas."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.db.models.user import UserRole
from app.schemas.auth import CurrentUserRead
from app.schemas.common import ORMModel
from app.schemas.content import ContentListItem


class UserRead(CurrentUserRead):
    """Full profile - includes email (self only, never for other users)."""

    last_login_at: dt.datetime | None = None


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=512)

    @field_validator("avatar_url")
    @classmethod
    def _valid_url(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not value.startswith(("http://", "https://", "/media/")):
            raise ValueError("avatar_url must be an http(s) URL or a /media/ path")
        return value


class PreferencesRead(ORMModel):
    user_id: int
    favorite_categories: list[str] = Field(default_factory=list)
    display_prefs: dict[str, Any] = Field(default_factory=dict)
    updated_at: dt.datetime | None = None


class PreferencesUpdate(BaseModel):
    favorite_categories: list[str] | None = Field(default=None, max_length=8)
    display_prefs: dict[str, Any] | None = None

    @field_validator("favorite_categories")
    @classmethod
    def _normalise(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return sorted({item.strip().lower() for item in value if item.strip()})


class AvatarRead(BaseModel):
    avatar_url: str
    bytes_uploaded: int
    message: str


class FavoriteFandom(ORMModel):
    slug: str
    name: str
    content_count: int
    bookmark_count: int


class RecentActivity(ORMModel):
    kind: str = Field(description="bookmark | rating | submission | feedback | login")
    label: str
    occurred_at: dt.datetime
    content_id: int | None = None


class DashboardStats(BaseModel):
    total_bookmarks: int
    total_ratings: int
    total_submissions: int
    pending_submissions: int
    favorite_fandom_count: int


class DashboardResponse(BaseModel):
    """Personalised home payload: greeting + activity + fandoms + bookmarks."""

    greeting: str
    user: UserRead
    stats: DashboardStats
    recent_activity: list[RecentActivity]
    favorite_fandoms: list[FavoriteFandom]
    recommended_content: list[ContentListItem]
    bookmarks_preview: list["BookmarkPreview"]
    featured_categories: list[dict[str, Any]]


class BookmarkPreview(BaseModel):
    id: int
    content_type: str
    content_id: int
    title: str
    image_url: str | None = None
    category_slug: str | None = None
    created_at: dt.datetime


DashboardResponse.model_rebuild()
