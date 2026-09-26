"""Content schemas: catalogue list/detail plus admin create/update payloads."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models.content import ContentStatus, ContentType
from app.schemas.common import ORMModel

ContentSort = Literal["latest", "popular", "alpha", "relevance"]

Url = Annotated[str, Field(max_length=512)]


class RatingSummary(BaseModel):
    average: float = Field(description="Mean rating, 0.0 when unrated")
    count: int = 0
    star_distribution: dict[str, int] = Field(default_factory=dict)
    thumbs_up: int = 0
    thumbs_down: int = 0


class ContentListItem(ORMModel):
    id: int
    title: str
    type: ContentType
    description: str | None = None
    media_url: str | None = None
    release_date: dt.date | None = None
    popularity_score: float
    view_count: int
    status: ContentStatus
    category_id: int
    category_slug: str | None = None
    category_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    rating: RatingSummary | None = None
    created_at: dt.datetime | None = None


class ContentDetail(ContentListItem):
    body_rich_text: str | None = None
    category_description: str | None = None
    bookmarked: bool = Field(
        default=False, description="True when the caller has bookmarked this item"
    )
    user_rating: dict | None = Field(
        default=None, description="The caller's own rating, when authenticated"
    )
    updated_at: dt.datetime | None = None


class ContentCreate(BaseModel):
    category_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=200)
    type: ContentType = ContentType.ARTICLE
    description: str | None = Field(default=None, max_length=2000)
    body_rich_text: str | None = None
    media_url: Url | None = None
    release_date: dt.date | None = None
    status: ContentStatus = ContentStatus.PUBLISHED
    popularity_score: float = Field(default=0.0, ge=0, le=10_000)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return sorted({tag.strip().lower() for tag in value if tag.strip()})

    @field_validator("media_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("http://", "https://", "/media/")):
            raise ValueError("media_url must be an http(s) URL or a /media/ path")
        return value

    @model_validator(mode="after")
    def _media_required_for_rich_types(self) -> "ContentCreate":
        if self.type in {ContentType.VIDEO, ContentType.AUDIO, ContentType.IMAGE} and not self.media_url:
            raise ValueError(f"media_url is required for type '{self.type.value}'")
        return self


class ContentUpdate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=2, max_length=200)
    type: ContentType | None = None
    description: str | None = Field(default=None, max_length=2000)
    body_rich_text: str | None = None
    media_url: Url | None = None
    release_date: dt.date | None = None
    status: ContentStatus | None = None
    popularity_score: float | None = Field(default=None, ge=0, le=10_000)
    tags: list[str] | None = Field(default=None, max_length=20)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return sorted({tag.strip().lower() for tag in value if tag.strip()})

    @field_validator("media_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("http://", "https://", "/media/")):
            raise ValueError("media_url must be an http(s) URL or a /media/ path")
        return value


class ContentFilters(BaseModel):
    """Query model for ``GET /content`` (bound with ``Annotated[..., Query()]``)."""

    model_config = ConfigDict(extra="forbid")

    category: str | None = Field(
        default=None, max_length=60, description="Category slug, e.g. 'anime'"
    )
    genre: str | None = Field(
        default=None, max_length=50, description="Tag to filter on, e.g. 'shounen'"
    )
    year: int | None = Field(default=None, ge=1900, le=2100, description="release_date year")
    type: ContentType | None = None
    q: str | None = Field(
        default=None, max_length=120, description="Full-text search over title + description"
    )
    sort: ContentSort = Field(
        default="latest", description="latest | popular | alpha | relevance"
    )
    status: ContentStatus | None = Field(
        default=None, description="Admin-only override; visitors always see published"
    )

    @field_validator("category", "genre", "q", mode="before")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        """Normalise at the edge so services never see padded input."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("category", "genre", mode="after")
    @classmethod
    def _lower(cls, value: str | None) -> str | None:
        return value.lower() if value else value
