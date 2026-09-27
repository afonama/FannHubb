"""Chatbot routes.

Starting a conversation works for visitors too: ``POST /message`` accepts an
omitted JWT. Continuing one is stricter - ``GET /history/{session_id}`` requires
both a valid access token and the opaque ``session_token``, because a sequential
``session_id`` is guessable and must never act as a credential on its own.

The engine behind these routes is chosen by ``CHATBOT_PROVIDER``; when
``CHATBOT_ENABLED=false`` the service raises 503 ``SERVICE_DISABLED`` and the
rest of the API is unaffected.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, OptionalUser
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
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Session belongs to another account"},
        404: {"description": "No such session"},
    },
)
async def get_history(
    session_id: int,
    db: DbSession,
    user: CurrentUser,
    session_token: Annotated[
        str,
        Query(
            min_length=1,
            max_length=200,
            description="Opaque token issued when the session was created",
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=200, description="Max messages to return")] = 50,
) -> ChatHistoryResponse:
    """Return a transcript, but only to the account that owns the thread.

    Both the session id and the opaque ``session_token`` are required: the id on
    its own is a guessable integer, so neither it nor the pair may substitute
    for authentication.
    """
    if not settings.chatbot_enabled:
        from app.core.errors import ServiceDisabledError

        raise ServiceDisabledError(
            "The Fan Hub assistant is disabled on this deployment",
            details={"flag": "CHATBOT_ENABLED"},
        )

    thread, messages = await chatbot_service.get_history(
        db,
        session_id,
        session_token=session_token,
        user_id=user.id,
        limit=limit,
    )
    return ChatHistoryResponse(
        session_id=thread.id,
        session_token=thread.session_token,
        messages=[ChatMessageRead.model_validate(item) for item in messages],
        started_at=thread.started_at,
        message_count=len(messages),
    )
