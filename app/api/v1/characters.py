"""Public character catalogue."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query

from app.core.deps import DbSession, Pagination
from app.schemas.character import CharacterRead
from app.schemas.common import Page
from app.services import character_service

router = APIRouter(prefix="/characters", tags=["characters"])


@router.get("", response_model=Page[CharacterRead], summary="Browse characters")
async def list_characters(
    db: DbSession,
    pagination: Pagination,
    category: Annotated[Optional[str], Query(max_length=60, description="Category slug")] = None,
    search: Annotated[Optional[str], Query(max_length=120, description="Name contains")] = None,
) -> Page[CharacterRead]:
    return await character_service.list_characters(db, pagination, category=category, search=search)


@router.get("/{character_id}", response_model=CharacterRead, summary="Character detail")
async def get_character(character_id: int, db: DbSession) -> CharacterRead:
    """Bumps the character view counter in Redis (flushed on the scheduler)."""
    return await character_service.get_character(db, character_id)
