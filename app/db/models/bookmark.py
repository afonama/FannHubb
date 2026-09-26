"""Polymorphic bookmarks: a user may save content, characters or merchandise."""

from __future__ import annotations

import enum
import datetime as dt

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BookmarkTarget(str, enum.Enum):
    """Which catalogue a bookmark row points at (polymorphic by design)."""

    CONTENT = "content"
    CHARACTER = "character"
    MERCHANDISE = "merchandise"


bookmark_target_enum = Enum(
    BookmarkTarget,
    name="bookmark_target",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content_type: Mapped[BookmarkTarget] = mapped_column(bookmark_target_enum, nullable=False)
    content_id: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    user: Mapped["User"] = relationship(back_populates="bookmarks")  # noqa: F821

    __table_args__ = (
        UniqueConstraint(
            "user_id", "content_type", "content_id", name="uq_bookmarks_user_type_content"
        ),
        Index("ix_bookmarks_user_id_created_at", "user_id", "created_at"),
        Index("ix_bookmarks_content_type_content_id", "content_type", "content_id"),
    )
