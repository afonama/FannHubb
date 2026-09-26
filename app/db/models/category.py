"""Fandom categories (Anime, Gaming, Movies, ...) - the top-level taxonomy."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon_url: Mapped[Optional[str]] = mapped_column(String(512))

    contents: Mapped[list["Content"]] = relationship(  # noqa: F821
        back_populates="category", lazy="noload"
    )
    characters: Mapped[list["Character"]] = relationship(  # noqa: F821
        back_populates="category", lazy="noload"
    )
    merchandise: Mapped[list["Merchandise"]] = relationship(  # noqa: F821
        back_populates="category", lazy="noload"
    )
    events: Mapped[list["Event"]] = relationship(  # noqa: F821
        back_populates="category", lazy="noload"
    )

    __table_args__ = ()
