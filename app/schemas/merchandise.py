"""Merchandise schemas (display-only catalogue, no pricing/checkout)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class MerchandiseRead(ORMModel):
    id: int
    name: str
    description: str | None = None
    image_url: str | None = None
    category_id: int
    category_slug: str | None = None
    category_name: str | None = None
    tag: str | None = None
    is_upcoming: bool
    release_date: str | None = None
    view_count: int
    created_at: dt.datetime | None = None


class MerchandiseCreate(BaseModel):
    category_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=512)
    tag: str | None = Field(default=None, max_length=60)
    is_upcoming: bool = False
    release_date: str | None = Field(default=None, max_length=40)

    @field_validator("tag")
    @classmethod
    def _normalise_tag(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else value


class MerchandiseUpdate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=512)
    tag: str | None = Field(default=None, max_length=60)
    is_upcoming: bool | None = None
    release_date: str | None = Field(default=None, max_length=40)
