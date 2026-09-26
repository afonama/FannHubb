"""User feedback: bugs, suggestions and general queries (visitors allowed)."""

from __future__ import annotations

import datetime as dt
import enum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FeedbackType(str, enum.Enum):
    BUG = "bug"
    SUGGESTION = "suggestion"
    QUERY = "query"


class FeedbackStatus(str, enum.Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    CLOSED = "closed"


feedback_type_enum = Enum(
    FeedbackType,
    name="feedback_type",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)
feedback_status_enum = Enum(
    FeedbackStatus,
    name="feedback_status",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[FeedbackType] = mapped_column(feedback_type_enum, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[FeedbackStatus] = mapped_column(
        feedback_status_enum, nullable=False, default=FeedbackStatus.OPEN,
        server_default=FeedbackStatus.OPEN.value,
    )
    admin_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_feedback_status_created_at", "status", "created_at"),
        Index("ix_feedback_type", "type"),
        Index("ix_feedback_user_id", "user_id"),
    )
