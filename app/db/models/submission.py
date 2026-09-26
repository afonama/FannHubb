"""Fan submissions submitted for moderator approval."""

from __future__ import annotations

import datetime as dt
import enum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SubmissionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


submission_status_enum = Enum(
    SubmissionStatus,
    name="submission_status",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)


class FanSubmission(Base):
    __tablename__ = "fan_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        submission_status_enum,
        nullable=False,
        default=SubmissionStatus.PENDING,
        server_default=SubmissionStatus.PENDING.value,
    )
    review_note: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Two FKs point at users, so both relationships declare their column.
    author: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys=[user_id], lazy="noload"
    )
    reviewer: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[reviewed_by], lazy="noload"
    )

    __table_args__ = (
        Index("ix_fan_submissions_status_created_at", "status", "created_at"),
        Index("ix_fan_submissions_user_id", "user_id"),
    )
