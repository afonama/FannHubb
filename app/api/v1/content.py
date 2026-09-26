"""Public content browsing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import Field

from app.core.deps import DbSession, OptionalUser, Pagination
from app.schemas.common import Page
from app.schemas.content import ContentDetail, ContentFilters, ContentListItem
from app.services import content_service

router = APIRouter(prefix="/content", tags=["content"])


@router.get("", response_model=Page[ContentListItem], summary="Browse content")
async def list_content(
    db: DbSession,
    pagination: Pagination,
    filters: Annotated[ContentFilters, Query()],
) -> Page[ContentListItem]:
    """Visitor-accessible catalogue.

    Filters: ``category`` (slug), ``genre`` (tag), ``year``, ``type``, ``q``
    (full-text over title + description). ``sort`` is one of
    ``latest`` | ``popular`` | ``alpha`` | ``relevance``.
    """
    return await content_service.list_content(db, filters, pagination)


@router.get("/{content_id}", response_model=ContentDetail, summary="Content detail")
async def get_content(
    content_id: int,
    db: DbSession,
    user: OptionalUser,
) -> ContentDetail:
    """Increments the view counter through ``popularity_service`` (Redis INCR).

    When an optional JWT is supplied the response also carries the caller's
    ``bookmarked`` flag and own ``user_rating``.
    """
    return await content_service.get_content(db, content_id, user=user)
