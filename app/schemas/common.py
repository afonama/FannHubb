"""Shared response envelopes: pagination, error shape, simple messages."""

from __future__ import annotations

import datetime as dt
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ErrorCode

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for schemas serialised from SQLAlchemy rows."""

    model_config = ConfigDict(from_attributes=True)


class PageParams(BaseModel):
    """Query-string pagination (``?page=1&page_size=20``)."""

    page: int = Field(default=1, ge=1, le=10_000, description="1-based page number")
    page_size: int = Field(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class Page(BaseModel, Generic[T]):
    """Uniform paginated list payload returned by every list endpoint."""

    items: list[T]
    total: int = Field(description="Total rows matching the filter, ignoring pagination")
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_prev: bool

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        )


class MessageResponse(BaseModel):
    """Simple ``{"message": "..."}`` acknowledgement."""

    message: str
    success: bool = True


class ErrorDetail(BaseModel):
    """The single error shape every failing request returns."""

    status_code: int = Field(description="HTTP status code")
    code: ErrorCode = Field(description="Stable machine-readable error code")
    message: str = Field(description="Human-readable explanation")
    details: dict[str, Any] | None = Field(
        default=None, description="Field-level errors, retry hints, etc."
    )
    request_id: str | None = None
    timestamp: dt.datetime | None = None


class IdResponse(BaseModel):
    id: int
