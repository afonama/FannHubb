"""Content items (articles / video / audio / image) and their tag join table."""

from __future__ import annotations

import datetime as dt
import enum
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ContentType(str, enum.Enum):
    ARTICLE = "article"
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"


class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


content_type_enum = Enum(
    ContentType,
    name="content_type",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)
content_status_enum = Enum(
    ContentStatus,
    name="content_status",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)

#: Tags are a real entity (not a bare string column) so that
#: ``Content.tags`` can be an ordinary many-to-many relationship.
class Tag(TimestampMixin, Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    usage_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (Index("ix_tags_name_lower", func.lower(name)),)


#: Pure association table: both sides are foreign keys, so the relationship
#: is a standard many-to-many and ORM traversal/filtering works.
content_tags = Table(
    "content_tags",
    Base.metadata,
    Column("content_id", ForeignKey("content.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_content_tags_tag_id", "tag_id"),
)


class Content(TimestampMixin, Base):
    __tablename__ = "content"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[ContentType] = mapped_column(
        content_type_enum, nullable=False, default=ContentType.ARTICLE
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    body_rich_text: Mapped[Optional[str]] = mapped_column(Text)
    media_url: Mapped[Optional[str]] = mapped_column(String(512))
    release_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    popularity_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[ContentStatus] = mapped_column(
        content_status_enum,
        nullable=False,
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
    )
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Persisted full-text vector, kept in sync by Postgres itself.
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR(),
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))",
            persisted=True,
        ),
    )

    category: Mapped["Category"] = relationship(back_populates="contents")  # noqa: F821
    ratings: Mapped[list["Rating"]] = relationship(  # noqa: F821
        back_populates="content", cascade="all, delete-orphan", lazy="noload"
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary=content_tags, lazy="selectin", order_by=Tag.name
    )

    __table_args__ = (
        CheckConstraint("view_count >= 0", name="view_count_non_negative"),
        Index("ix_content_category_id_status", "category_id", "status"),
        Index("ix_content_status_release_date", "status", "release_date"),
        Index("ix_content_popularity_score", "popularity_score"),
        Index("ix_content_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_content_type", "type"),
    )
