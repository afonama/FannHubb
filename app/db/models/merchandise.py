"""Merchandise catalogue - display only, no pricing/checkout per spec."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Merchandise(TimestampMixin, Base):
    __tablename__ = "merchandise"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    image_url: Mapped[Optional[str]] = mapped_column(String(512))
    tag: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    is_upcoming: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    release_date: Mapped[Optional[str]] = mapped_column(String(40))
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    category: Mapped["Category"] = relationship(back_populates="merchandise")  # noqa: F821

    __table_args__ = (
        Index("ix_merchandise_category_id", "category_id"),
        Index("ix_merchandise_category_id_is_upcoming", "category_id", "is_upcoming"),
    )
