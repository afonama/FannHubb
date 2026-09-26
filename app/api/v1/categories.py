"""Category listing (public)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import DbSession
from app.schemas.category import CategoryRead
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead], summary="List all fandoms")
async def list_categories(db: DbSession) -> list[CategoryRead]:
    """The eight fandom categories with their published-content counts.

    Not paginated: the taxonomy is small and fixed, and the frontend renders it
    as a nav bar.
    """
    return await category_service.list_categories(db)


@router.get(
    "/{slug}",
    response_model=CategoryRead,
    summary="One fandom category",
    responses={404: {"description": "No such category"}},
)
async def get_category(slug: str, db: DbSession) -> CategoryRead:
    """Single category by slug, with its published-content count."""
    return await category_service.get_category(db, slug)
