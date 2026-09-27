"""Chatbot: a rules/FAQ-matching engine behind a swappable engine interface.

The route and the Pydantic schemas know nothing about *how* a reply is produced.
``CHATBOT_PROVIDER`` selects the implementation:

  ``rules`` (default) - :class:`FaqRulesEngine`, scores user input against the
      ``chatbot_faqs`` keyword index. Deterministic, offline, zero cost.
  ``llm``            - :class:`LlmChatbotEngine`, an OpenAI-compatible call site
      that is wired but inert until ``CHATBOT_LLM_API_KEY`` is provided.

To add a provider: implement :class:`ChatbotEngine`, register it in
:func:`build_engine`, and set ``CHATBOT_PROVIDER=<name>``. No route or schema
change required. Setting ``CHATBOT_ENABLED=false`` disables the feature outright
(the router returns 503 ``SERVICE_DISABLED``) and the rest of the app is unaffected.
"""

from __future__ import annotations

import datetime as dt
import re
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Protocol, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ErrorCode, ForbiddenError, NotFoundError, ServiceDisabledError
from app.core.logging_config import get_logger
from app.core.redis_client import get_cache
from app.db.models.chatbot import ChatbotFaq, ChatbotMessage, ChatbotSession, MessageRole
from app.schemas.chatbot import ChatMessageRead, ChatRequest, ChatResponse

logger = get_logger(__name__)

_WORD_RE = re.compile(r"[a-z0-9']+")

#: Reply used when nothing matches - still helpful, never a dead end.
FALLBACK_ANSWER = (
    "I did not catch that one. I can help with browsing fandoms, finding events near you, "
    "rating content, or tracking upcoming merchandise. Try asking about a category, an "
    "event in your city, or how bookmarks work."
)

STOP_WORDS = frozenset(
    {
        "a", "an", "and", "are", "do", "does", "for", "how", "i", "in", "is", "it", "me",
        "my", "of", "on", "the", "to", "was", "what", "when", "where", "which", "who",
        "why", "you", "your", "can", "with", "about", "get", "tell", "please", "s",
    }
)


@dataclass
class ChatbotReply:
    """Engine-agnostic result; mapped straight onto :class:`ChatResponse`."""

    reply: str
    confidence: float = 0.0
    matched_question: Optional[str] = None
    matched_faq_id: Optional[int] = None
    suggestions: list[str] = field(default_factory=list)


class ChatbotEngine(Protocol):
    """The contract every backend implements."""

    name: str

    async def respond(
        self, session: AsyncSession, message: str, history: Sequence[ChatbotMessage]
    ) -> ChatbotReply: ...


# ----------------------------------------------------------------- helpers
def tokenize(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if word not in STOP_WORDS}


def score_faq(message_tokens: set[str], faq: ChatbotFaq) -> float:
    """Keyword-overlap score in ``0..1``.

    Multi-word phrases score higher than single words (all parts must be present),
    so "anime convention" beats a stray "anime". Question-token overlap acts as a
    softer secondary signal, and ``priority`` breaks ties in :func:`_ranked_faqs`.
    """
    if not message_tokens:
        return 0.0
    best = 0.0
    for keyword in faq.keywords or []:
        keyword_lower = str(keyword).strip().lower()
        if not keyword_lower:
            continue
        if " " in keyword_lower:
            parts = set(_WORD_RE.findall(keyword_lower))
            if parts and parts <= message_tokens:
                best = max(best, 1.0)
            continue
        if keyword_lower in message_tokens:
            best = max(best, 0.75)
    question_tokens = tokenize(faq.question)
    if question_tokens:
        overlap = len(message_tokens & question_tokens) / len(question_tokens)
        best = max(best, round(overlap * 0.6, 4))
    return round(min(best, 1.0), 4)


async def _ranked_faqs(session: AsyncSession, limit: int = 3) -> list[ChatbotFaq]:
    """Active FAQs ordered by priority (highest first) - the whole table is tiny."""
    return list(
        (
            await session.execute(
                select(ChatbotFaq)
                .where(ChatbotFaq.is_active.is_(True))
                .order_by(ChatbotFaq.priority.desc(), ChatbotFaq.id.asc())
                .limit(limit * 3)
            )
        )
        .scalars()
        .all()
    )


# ------------------------------------------------------------------ engines
class FaqRulesEngine:
    """Default provider: deterministic keyword matching against ``chatbot_faqs``."""

    name = "rules"

    def __init__(self, match_threshold: float = 0.35) -> None:
        self.match_threshold = match_threshold

    async def respond(
        self, session: AsyncSession, message: str, history: Sequence[ChatbotMessage]
    ) -> ChatbotReply:
        message_tokens = tokenize(message)
        faqs = await _ranked_faqs(session)
        scored = sorted(
            ((score_faq(message_tokens, faq), faq) for faq in faqs),
            key=lambda pair: (pair[0], pair[1].priority, -pair[1].id),
            reverse=True,
        )

        if not scored or scored[0][0] < self.match_threshold:
            await self._record_miss(session, message)
            return ChatbotReply(
                reply=FALLBACK_ANSWER,
                confidence=round(scored[0][0], 3) if scored else 0.0,
                suggestions=[faq.question for _, faq in scored[:3]] or ["What fandoms do you cover?"],
            )

        best_score, best_faq = scored[0]
        best_faq.match_count = (best_faq.match_count or 0) + 1
        session.add(best_faq)
        await session.flush()

        suggestions = [faq.question for score, faq in scored[1:3] if score > 0]
        return ChatbotReply(
            reply=best_faq.answer,
            confidence=round(best_score, 3),
            matched_question=best_faq.question,
            matched_faq_id=best_faq.id,
            suggestions=suggestions,
        )

    async def _record_miss(self, session: AsyncSession, message: str) -> None:
        """Log unanswered questions so an admin can turn them into FAQs."""
        logger.info("chatbot_no_match", extra={"message_preview": message[:120]})


class LlmChatbotEngine:
    """Drop-in OpenAI-compatible provider.

    Intentionally not a hard dependency: httpx is already in the project, and the
    call is only attempted when an API key is configured. To wire a different
    vendor, replace ``_complete`` - the rest of the app is unchanged.
    """

    name = "llm"

    def __init__(self, fallback: Optional[ChatbotEngine] = None) -> None:
        self.fallback_engine = fallback or FaqRulesEngine()

    @property
    def configured(self) -> bool:
        return bool(settings.chatbot_llm_api_key.get_secret_value().strip())

    async def respond(
        self, session: AsyncSession, message: str, history: Sequence[ChatbotMessage]
    ) -> ChatbotReply:
        if not self.configured:
            logger.warning("chatbot_llm_not_configured_using_rules")
            return await self.fallback_engine.respond(session, message, history)

        try:
            answer = await self._complete(message, history)
        except Exception as exc:  # noqa: BLE001 - degrade to rules, never 500
            logger.error("chatbot_llm_failed", extra={"error": str(exc), "error_type": type(exc).__name__})
            return await self.fallback_engine.respond(session, message, history)

        return ChatbotReply(reply=answer, confidence=1.0, matched_question=None, suggestions=[])

    async def _complete(self, message: str, history: Sequence[ChatbotMessage]) -> str:
        import httpx

        transcript = [
            {"role": "user" if item.role == MessageRole.USER else "assistant", "content": item.message}
            for item in history[-10:]
        ]
        transcript.append({"role": "user", "content": message})

        url = f"{settings.chatbot_llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.chatbot_llm_api_key.get_secret_value()}"}
        payload = {
            "model": settings.chatbot_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the Fan Hub Plus assistant. You help fans discover anime, gaming, "
                        "movies, TV, K-Pop, comics, manga and cosplay content, find events and "
                        "merchandise. Be brief and friendly. Never invent events or merchandise."
                    ),
                },
                *transcript,
            ],
            "temperature": 0.4,
            "max_tokens": 220,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()


def build_engine() -> ChatbotEngine:
    """Factory driven by ``CHATBOT_PROVIDER``."""
    if settings.chatbot_provider == "llm":
        return LlmChatbotEngine()
    return FaqRulesEngine()


# ------------------------------------------------------------- session I/O
async def resolve_session(
    session: AsyncSession, session_token: Optional[str], user_id: Optional[int]
) -> ChatbotSession:
    """Load an existing thread or open a new one (anonymous visitors included)."""
    if session_token:
        existing = (
            await session.execute(
                select(ChatbotSession).where(ChatbotSession.session_token == session_token)
            )
        ).scalar_one_or_none()
        if existing is not None:
            if user_id is not None and existing.user_id is None:
                existing.user_id = user_id
                session.add(existing)
            existing.last_active_at = dt.datetime.now(dt.timezone.utc)
            session.add(existing)
            await session.commit()
            await session.refresh(existing)
            return existing

    thread = ChatbotSession(
        user_id=user_id,
        session_token=secrets.token_urlsafe(24),
        started_at=dt.datetime.now(dt.timezone.utc),
        last_active_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    logger.info("chatbot_session_created", extra={"session_id": thread.id, "user_id": user_id})
    return thread


async def _append_message(
    session: AsyncSession,
    thread: ChatbotSession,
    role: MessageRole,
    message: str,
    faq_id: Optional[int] = None,
) -> ChatbotMessage:
    row = ChatbotMessage(
        session_id=thread.id, role=role, message=message, matched_faq_id=faq_id
    )
    session.add(row)
    await session.flush()
    return row


async def _recent_messages(
    session: AsyncSession, thread: ChatbotSession, limit: int = 20
) -> list[ChatbotMessage]:
    rows = list(
        (
            await session.execute(
                select(ChatbotMessage)
                .where(ChatbotMessage.session_id == thread.id)
                .order_by(ChatbotMessage.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


async def handle_message(
    session: AsyncSession, payload: ChatRequest, user_id: Optional[int] = None
) -> ChatResponse:
    """Full chatbot turn: resolve session, ask the engine, persist the transcript."""
    if not settings.chatbot_enabled:
        raise ServiceDisabledError(
            "The Fan Hub assistant is disabled on this deployment",
            details={"flag": "CHATBOT_ENABLED"},
        )

    engine = build_engine()
    thread = await resolve_session(session, payload.session_token, user_id)
    history = await _recent_messages(session, thread)

    user_row = await _append_message(session, thread, MessageRole.USER, payload.message.strip())
    result = await engine.respond(session, payload.message.strip(), history)
    await _append_message(
        session, thread, MessageRole.BOT, result.reply, result.matched_faq_id
    )
    await session.commit()

    from app.services import popularity_service

    await popularity_service.record_chatbot_interaction(
        session_count=1 if not payload.session_token else 0,
        message_count=2,
    )

    transcript = await _recent_messages(session, thread, limit=20)
    logger.info(
        "chatbot_turn",
        extra={
            "session_id": thread.id,
            "user_id": user_id,
            "engine": engine.name,
            "confidence": result.confidence,
            "matched_faq_id": result.matched_faq_id,
        },
    )
    return ChatResponse(
        session_token=thread.session_token,
        session_id=thread.id,
        reply=result.reply,
        matched_question=result.matched_question,
        confidence=result.confidence,
        suggestions=result.suggestions,
        history=[ChatMessageRead.model_validate(item) for item in transcript]
        if payload.include_history
        else [ChatMessageRead.model_validate(user_row)],
    )


async def get_history(
    session: AsyncSession,
    session_id: int,
    *,
    session_token: str,
    user_id: int,
    limit: int = 50,
) -> tuple[ChatbotSession, list[ChatbotMessage]]:
    """Load a transcript, but only for the caller who owns the thread.

    A bare ``session_id`` is not a credential: ids are small sequential integers
    and therefore trivially enumerable. Two independent checks are required -
    the opaque ``session_token`` must match, and the thread must not already
    belong to a different account.
    """
    thread = await session.get(ChatbotSession, session_id)
    if thread is None:
        raise NotFoundError(f"chatbot session {session_id} not found")

    if not secrets.compare_digest(thread.session_token, session_token):
        raise ForbiddenError("This chatbot session does not belong to you")

    if thread.user_id is not None and thread.user_id != user_id:
        raise ForbiddenError("This chatbot session belongs to another account")

    # An anonymous thread claimed by a signed-in user is adopted here, mirroring
    # ``resolve_session`` so the two paths cannot disagree about ownership.
    if thread.user_id is None:
        thread.user_id = user_id
        session.add(thread)
        await session.commit()
        await session.refresh(thread)

    rows = list(
        (
            await session.execute(
                select(ChatbotMessage)
                .where(ChatbotMessage.session_id == thread.id)
                .order_by(ChatbotMessage.id.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return thread, rows


async def chatbot_enabled() -> bool:
    """Flag exposed on /health so the frontend can hide the widget."""
    return settings.chatbot_enabled
