"""Chatbot sessions, transcript and the FAQ knowledge base."""

from __future__ import annotations

import datetime as dt
import enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class MessageRole(str, enum.Enum):
    USER = "user"
    BOT = "bot"


message_role_enum = Enum(
    MessageRole,
    name="message_role",
    native_enum=True,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda e: [m.value for m in e],
)


class ChatbotSession(Base):
    """A conversation thread; ``session_token`` is what anonymous visitors pass back."""

    __tablename__ = "chatbot_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    session_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_active_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    messages: Mapped[list["ChatbotMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ChatbotMessage.id",
    )

    __table_args__ = (Index("ix_chatbot_sessions_user_id_started_at", "user_id", "started_at"),)


class ChatbotMessage(Base):
    __tablename__ = "chatbot_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chatbot_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(message_role_enum, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    matched_faq_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chatbot_faqs.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[ChatbotSession] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_chatbot_messages_session_id_created_at", "session_id", "created_at"),
    )


class ChatbotFaq(TimestampMixin, Base):
    """Keyword -> answer rules. ``keywords`` is a JSONB list of trigger terms."""

    __tablename__ = "chatbot_faqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(String(300), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    match_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        Index("ix_chatbot_faqs_is_active_priority", "is_active", "priority"),
    )
