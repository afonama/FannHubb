"""Character catalogue: public listing with view tracking + admin CRUD."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.core.logging_config import get_logger
from app.db.models.category import Category
from app.db.models.character import Character
from app.db.models.user import User
from app.schemas.character import CharacterCreate, CharacterRead, CharacterUpdate
from app.schemas.common import Page, PageParams
from app.services import popularity_service

logger = get_logger(__name__)


async def _to_read(item: Character) -> CharacterRead:
    return CharacterRead(
        id=item.id,
        name=item.name,
        bio=item.bio,
        image_url=item.image_url,
        category_id=item.category_id,
        category_slug=item.category.slug if item.category else None,
        category_name=item.category.name if item.category else None,
        view_count=item.view_count,
        created_at=item.created_at,
    )


async def _to_reads(session: AsyncSession, items: list[Character], *, live: bool = False) -> list[CharacterRead]:
    result = [await _to_read(item) for item in items]
    if live and items:
        stored = {item.id: item.view_count for item in items}
        live_counts = await popularity_service.view_count_with_live_deltas(
            "character", list(stored), stored
        )
        for read in result:
            read.view_count = live_counts.get(read.id, read.view_count)
    return result


async def list_characters(
    session: AsyncSession,
    page: PageParams,
    *,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> Page[CharacterRead]:
    stmt = select(Character).join(Category, Category.id == Character.category_id)
    if category:
        stmt = stmt.where(Category.slug == category.strip().lower())
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(Character.name.ilike(pattern))

    total = int(
        (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar() or 0
    )
    rows = list(
        (
            await session.execute(
                stmt.options(selectinload(Character.category))
                .order_by(Character.name.asc(), Character.id.asc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    items = await _to_reads(session, rows, live=True)
    return Page.build(items, total, page.page, page.page_size)


async def get_character(
    session: AsyncSession, character_id: int, *, track_view: bool = True
) -> CharacterRead:
    item = (
        await session.execute(
            select(Character)
            .options(selectinload(Character.category))
            .where(Character.id == character_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError(f"character {character_id} not found")
    if track_view:
        await popularity_service.record_view("character", character_id)
    read = await _to_read(item)
    read.view_count = await popularity_service.view_count_with_live_delta(
        "character", item.id, item.view_count
    )
    return read


async def create_character(
    session: AsyncSession, payload: CharacterCreate, actor: Optional[User] = None
) -> CharacterRead:
    if await session.get(Category, payload.category_id) is None:
        raise NotFoundError(f"category {payload.category_id} not found")
    item = Character(**payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    logger.info("character_created", extra={"character_id": item.id, "actor_id": getattr(actor, "id", None)})
    return await get_character(session, item.id, track_view=False)


async def update_character(
    session: AsyncSession, character_id: int, payload: CharacterUpdate, actor: Optional[User] = None
) -> CharacterRead:
    item = await session.get(Character, character_id)
    if item is None:
        raise NotFoundError(f"character {character_id} not found")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "category_id" in changes and await session.get(Category, int(changes["category_id"])) is None:
        raise NotFoundError(f"category {changes['category_id']} not found")
    for field, value in changes.items():
        setattr(item, field, value)
    session.add(item)
    await session.commit()
    logger.info("character_updated", extra={"character_id": character_id, "actor_id": getattr(actor, "id", None)})
    return await get_character(session, character_id, track_view=False)


async def delete_character(
    session: AsyncSession, character_id: int, actor: Optional[User] = None
) -> None:
    item = await session.get(Character, character_id)
    if item is None:
        raise NotFoundError(f"character {character_id} not found")
    await session.delete(item)
    await session.commit()
    logger.info("character_deleted", extra={"character_id": character_id, "actor_id": getattr(actor, "id", None)})
