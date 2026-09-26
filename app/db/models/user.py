"""User accounts, preferences and one-time auth tokens."""

from __future__ import annotations

import datetime as dt
import enum
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    """Three access tiers required by the spec."""

    VISITOR = "visitor"
    REGISTERED = "registered"
    ADMIN = "admin"


class AuthTokenPurpose(str, enum.Enum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"


user_role_enum = Enum(
    UserRole,
    name="user_role",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)
auth_token_purpose_enum = Enum(
    AuthTokenPurpose,
    name="auth_token_purpose",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512))
    role: Mapped[UserRole] = mapped_column(
        user_role_enum, nullable=False, default=UserRole.REGISTERED, server_default=UserRole.REGISTERED.value
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_login_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    preference: Mapped[Optional["UserPreference"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    bookmarks: Mapped[list["Bookmark"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    tokens: Mapped[list["AuthToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )

    __table_args__ = (
        Index("ix_users_role_created_at", "role", "created_at"),
        Index("ix_users_is_email_verified", "is_email_verified"),
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


class UserPreference(Base):
    """Per-user UI/interest settings (JSONB keeps this schema-free)."""

    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    favorite_categories: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    display_prefs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="preference")


class AuthToken(Base):
    """Single-use, expiring tokens backing verify-email and reset-password links.

    Only the SHA-256 digest is stored, so a database leak cannot be replayed.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[AuthTokenPurpose] = mapped_column(auth_token_purpose_enum, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    user: Mapped[User] = relationship(back_populates="tokens")

    __table_args__ = (
        Index("ix_auth_tokens_user_purpose", "user_id", "purpose"),
        Index("ix_auth_tokens_expires_at", "expires_at"),
    )
