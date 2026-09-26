"""Bookmark schemas (polymorphic across content / character / merchandise)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.db.models.bookmark import BookmarkTarget
from app.schemas.common import ORMModel


class BookmarkCreate(BaseModel):
    content_type: BookmarkTarget
    content_id: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)


class BookmarkRead(ORMModel):
    id: int
    user_id: int
    content_type: BookmarkTarget
    content_id: int
    note: str | None = None
    created_at: dt.datetime
    title: str | None = Field(
        default=None, description="Denormalised title of the saved item"
    )
    image_url: str | None = None
    category_slug: str | None = None


class BookmarkDeleteResult(BaseModel):
    id: int
    content_type: BookmarkTarget
    content_id: int
    deleted: bool = True
