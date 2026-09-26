"""Feedback schemas (anonymous visitors welcome)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.db.models.feedback import FeedbackStatus, FeedbackType
from app.schemas.common import ORMModel


class FeedbackCreate(BaseModel):
    type: FeedbackType
    message: str = Field(min_length=10, max_length=4000)
    contact_email: str | None = Field(
        default=None,
        max_length=320,
        description="Optional so an anonymous visitor can be replied to",
    )


class FeedbackRead(ORMModel):
    id: int
    user_id: int | None = None
    type: FeedbackType
    message: str
    status: FeedbackStatus
    admin_note: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime | None = None


class FeedbackUpdate(BaseModel):
    status: FeedbackStatus | None = None
    admin_note: str | None = Field(default=None, max_length=2000)
