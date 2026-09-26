"""Chatbot schemas - identical for the rules engine and any future LLM engine."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=2000,
        examples=["When is the next anime convention?"],
    )
    session_token: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Opaque conversation handle returned by the first call. Omit to start a "
            "new session; visitors can chat without authenticating."
        ),
    )
    include_history: bool = Field(
        default=True, description="Echo the last few turns back for chat UI rendering"
    )


class ChatMessageRead(ORMModel):
    id: int
    role: str
    message: str
    created_at: dt.datetime


class ChatResponse(BaseModel):
    session_token: str
    session_id: int
    reply: str
    matched_question: str | None = Field(
        default=None, description="FAQ entry that produced the reply, if any"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Rules-engine match score (0..1)"
    )
    suggestions: list[str] = Field(default_factory=list)
    history: list[ChatMessageRead] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    session_id: int
    session_token: str
    messages: list[ChatMessageRead]
    started_at: dt.datetime
    message_count: int
