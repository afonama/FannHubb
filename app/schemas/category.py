"""Category schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from app.schemas.common import ORMModel


class CategoryRead(ORMModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    icon_url: str | None = None
    content_count: int | None = Field(
        default=None, description="Published content count, included in list responses"
    )
    created_at: dt.datetime | None = None
