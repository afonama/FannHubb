"""Character schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

Url = str


class CharacterRead(ORMModel):
    id: int
    name: str
    bio: str | None = None
    image_url: str | None = None
    category_id: int
    category_slug: str | None = None
    category_name: str | None = None
    view_count: int
    created_at: dt.datetime | None = None


class CharacterCreate(BaseModel):
    category_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    bio: str | None = None
    image_url: Url | None = Field(default=None, max_length=512)

    @field_validator("image_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("http://", "https://", "/media/")):
            raise ValueError("image_url must be an http(s) URL or a /media/ path")
        return value


class CharacterUpdate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    bio: str | None = None
    image_url: Url | None = Field(default=None, max_length=512)
