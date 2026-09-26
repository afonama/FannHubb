"""Admin-only schemas: dashboard stats and moderation payloads."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.db.models.feedback import FeedbackStatus
from app.db.models.submission import SubmissionStatus
from app.schemas.common import ORMModel


class PopularCategoryStat(BaseModel):
    category_id: int
    slug: str
    name: str
    views: int = Field(description="Redis browse counter for the category")
    content_count: int = 0


class ActiveUsersStat(BaseModel):
    date: str
    unique_logins: int
    source: str = Field(description="redis | database")


class ChatbotVolumeStat(BaseModel):
    date: str
    messages: int
    sessions: int


class AdminStats(BaseModel):
    """Aggregated platform stats; served from Redis counters where available."""

    generated_at: dt.datetime
    cache_backend: str
    total_users: int
    users_by_role: dict[str, int]
    active_users_today: int
    active_users_window: list[ActiveUsersStat]
    total_content: int
    content_by_status: dict[str, int]
    total_characters: int
    total_merchandise: int
    total_bookmarks: int
    total_ratings: int
    pending_submissions: int
    open_feedback: int
    popular_categories: list[PopularCategoryStat]
    chatbot_volume: list[ChatbotVolumeStat]
    chatbot_total_messages: int


class ModerationCounts(BaseModel):
    pending_submissions: int
    approved_submissions: int
    rejected_submissions: int
    open_feedback: int
    reviewed_feedback: int
    closed_feedback: int


class TaskResult(BaseModel):
    task: str
    updated_rows: int
    keys_processed: int
    finished_at: dt.datetime
