"""Public merchandise catalogue (display-only, no checkout)."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query

from app.core.deps import DbSession, Pagination
from app.schemas.common import Page
from app.schemas.merchandise import MerchandiseRead
from app.services import merchandise_service

router = APIRouter(prefix="/merchandise", tags=["merchandise"])


@router.get("", response_model=Page[MerchandiseRead], summary="Browse merchandise")
async def list_merchandise(
    db: DbSession,
    pagination: Pagination,
    category: Annotated[Optional[str], Query(max_length=60, description="Category slug")] = None,
    tag: Annotated[Optional[str], Query(max_length=60)] = None,
    upcoming: Annotated[Optional[bool], Query(description="Filter upcoming releases")] = None,
) -> Page[MerchandiseRead]:
    return await merchandise_service.list_merchandise(
        db, pagination, category=category, tag=tag, upcoming=upcoming
    )


@router.get("/{item_id}", response_model=MerchandiseRead, summary="Merchandise detail")
async def get_merchandise(item_id: int, db: DbSession) -> MerchandiseRead:
    return await merchandise_service.get_merchandise(db, item_id)
