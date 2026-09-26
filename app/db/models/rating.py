"""Ratings: 5-star and thumbs up/down share one table via ``scale``."""

from __future__ import annotations

import datetime as dt
import enum
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RatingScale(str, enum.Enum):
    """Supported rating scales.

    ``STARS`` -> value 1..5, ``THUMBS`` -> value +1 / -1. A user has exactly one
    rating per content item (unique on user_id + content_id); re-rating or
    switching scale updates the existing row.
    """

    STARS = "stars"
    THUMBS = "thumbs"


rating_scale_enum = Enum(
    RatingScale,
    name="rating_scale",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)


class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[int] = mapped_column(
        ForeignKey("content.id", ondelete="CASCADE"), nullable=False
    )
    scale: Mapped[RatingScale] = mapped_column(
        rating_scale_enum, nullable=False, default=RatingScale.STARS, server_default=RatingScale.STARS.value
    )
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(lazy="noload")  # noqa: F821
    content: Mapped["Content"] = relationship(back_populates="ratings")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("user_id", "content_id", name="uq_ratings_user_content"),
        CheckConstraint(
            "(scale = 'stars' AND value BETWEEN 1 AND 5) OR (scale = 'thumbs' AND value IN (-1, 1))",
            name="rating_value_matches_scale",
        ),
        Index("ix_ratings_content_id", "content_id"),
        Index("ix_ratings_user_id", "user_id"),
    )
