"""Fandom characters (display-only catalogue)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Character(TimestampMixin, Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(String(512))
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    category: Mapped["Category"] = relationship(back_populates="characters")  # noqa: F821

    __table_args__ = (
        Index("ix_characters_category_id", "category_id"),
        Index("ix_characters_name", "name"),
    )
