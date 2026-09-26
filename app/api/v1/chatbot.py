"""Chatbot routes.

Works for visitors too: sessions are identified by an opaque ``session_token``
rather than requiring a JWT. The engine behind these routes is chosen by
``CHATBOT_PROVIDER``; when ``CHATBOT_ENABLED=false`` the service raises 503
``SERVICE_DISABLED`` and the rest of the API is unaffected.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.deps import DbSession, OptionalUser
from app.core.rate_limit import for_endpoint as rate_limit_for
from app.schemas.chatbot import ChatHistoryResponse, ChatRequest, ChatResponse
from app.schemas.chatbot import ChatMessageRead
from app.services import chatbot_service

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

rate_limit_chatbot = rate_limit_for("chatbot")


@router.post(
    "/message",
    response_model=ChatResponse,
    summary="Send a message to the fan assistant",
    responses={429: {"description": "Rate limit exceeded"}, 503: {"description": "Chatbot disabled"}},
)
async def post_message(
    payload: ChatRequest,
    db: DbSession,
    user: OptionalUser,
    _limit: Annotated[None, Depends(rate_limit_chatbot)],
) -> ChatResponse:
    """Omit ``session_token`` to start a conversation; pass it back to continue.

    The response schema is identical whichever engine answers, so swapping in an
    LLM later requires no client change.
    """
    return await chatbot_service.handle_message(db, payload, user_id=user.id if user else None)


@router.get(
    "/history/{session_id}",
    response_model=ChatHistoryResponse,
    summary="Transcript for a session",
)
async def get_history(
    session_id: int,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200, description="Max messages to return")] = 50,
) -> ChatHistoryResponse:
    if not settings.chatbot_enabled:
        from app.core.errors import ServiceDisabledError

        raise ServiceDisabledError(
            "The Fan Hub assistant is disabled on this deployment",
            details={"flag": "CHATBOT_ENABLED"},
        )

    thread, messages = await chatbot_service.get_history(db, session_id, limit=limit)
    return ChatHistoryResponse(
        session_id=thread.id,
        session_token=thread.session_token,
        messages=[ChatMessageRead.model_validate(item) for item in messages],
        started_at=thread.started_at,
        message_count=len(messages),
    )
