"""Fan submission schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.db.models.submission import SubmissionStatus
from app.schemas.common import ORMModel


class SubmissionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=8000)
    category_id: int | None = Field(default=None, gt=0)


class SubmissionRead(ORMModel):
    id: int
    user_id: int
    title: str
    body: str
    category_id: int | None = None
    status: SubmissionStatus
    review_note: str | None = None
    reviewed_by: int | None = None
    created_at: dt.datetime
    updated_at: dt.datetime | None = None


class SubmissionUpdate(BaseModel):
    """Moderator action: approve or reject, optionally with a note."""

    status: SubmissionStatus
    review_note: str | None = Field(default=None, max_length=2000)


class SubmissionListItem(SubmissionRead):
    author_name: str | None = None
    author_email: str | None = None
