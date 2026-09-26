"""Fan events with coordinates for a "near me" bounding-box filter."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    ticket_url: Mapped[Optional[str]] = mapped_column(String(512))
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    description: Mapped[Optional[str]] = mapped_column(String(1000))

    category: Mapped[Optional["Category"]] = relationship(back_populates="events")  # noqa: F821

    __table_args__ = (
        Index("ix_events_lat_lng", "lat", "lng"),
        Index("ix_events_city", "city"),
        Index("ix_events_start_date", "start_date"),
    )
