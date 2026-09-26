"""Merchandise catalogue (display-only) + admin CRUD."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.core.logging_config import get_logger
from app.db.models.category import Category
from app.db.models.merchandise import Merchandise
from app.db.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.merchandise import MerchandiseCreate, MerchandiseRead, MerchandiseUpdate
from app.services import popularity_service

logger = get_logger(__name__)


def _to_read(item: Merchandise) -> MerchandiseRead:
    return MerchandiseRead(
        id=item.id,
        name=item.name,
        description=item.description,
        image_url=item.image_url,
        category_id=item.category_id,
        category_slug=item.category.slug if item.category else None,
        category_name=item.category.name if item.category else None,
        tag=item.tag,
        is_upcoming=item.is_upcoming,
        release_date=item.release_date,
        view_count=item.view_count,
        created_at=item.created_at,
    )


async def _to_reads(
    session: AsyncSession, items: list[Merchandise], *, live: bool = False
) -> list[MerchandiseRead]:
    result = [_to_read(item) for item in items]
    if live and items:
        stored = {item.id: item.view_count for item in items}
        live_counts = await popularity_service.view_count_with_live_deltas(
            "merchandise", list(stored), stored
        )
        for read in result:
            read.view_count = live_counts.get(read.id, read.view_count)
    return result


async def list_merchandise(
    session: AsyncSession,
    page: PageParams,
    *,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    upcoming: Optional[bool] = None,
) -> Page[MerchandiseRead]:
    stmt = select(Merchandise).join(Category, Category.id == Merchandise.category_id)
    if category:
        stmt = stmt.where(Category.slug == category.strip().lower())
    if tag:
        stmt = stmt.where(Merchandise.tag == tag.strip().lower())
    if upcoming is not None:
        stmt = stmt.where(Merchandise.is_upcoming == upcoming)

    total = int(
        (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar() or 0
    )
    ordering = Merchandise.release_date.asc().nullslast() if upcoming else Merchandise.created_at.desc()
    rows = list(
        (
            await session.execute(
                stmt.options(selectinload(Merchandise.category))
                .order_by(ordering, Merchandise.id.asc())
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


async def get_merchandise(
    session: AsyncSession, item_id: int, *, track_view: bool = True
) -> MerchandiseRead:
    item = (
        await session.execute(
            select(Merchandise)
            .options(selectinload(Merchandise.category))
            .where(Merchandise.id == item_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError(f"merchandise {item_id} not found")
    if track_view:
        await popularity_service.record_view("merchandise", item_id)
    read = _to_read(item)
    read.view_count = await popularity_service.view_count_with_live_delta(
        "merchandise", item.id, item.view_count
    )
    return read


async def create_merchandise(
    session: AsyncSession, payload: MerchandiseCreate, actor: Optional[User] = None
) -> MerchandiseRead:
    if await session.get(Category, payload.category_id) is None:
        raise NotFoundError(f"category {payload.category_id} not found")
    item = Merchandise(**payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    logger.info("merchandise_created", extra={"merchandise_id": item.id, "actor_id": getattr(actor, "id", None)})
    return await get_merchandise(session, item.id, track_view=False)


async def update_merchandise(
    session: AsyncSession, item_id: int, payload: MerchandiseUpdate, actor: Optional[User] = None
) -> MerchandiseRead:
    item = await session.get(Merchandise, item_id)
    if item is None:
        raise NotFoundError(f"merchandise {item_id} not found")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "category_id" in changes and await session.get(Category, int(changes["category_id"])) is None:
        raise NotFoundError(f"category {changes['category_id']} not found")
    for field, value in changes.items():
        setattr(item, field, value)
    session.add(item)
    await session.commit()
    logger.info("merchandise_updated", extra={"merchandise_id": item_id, "actor_id": getattr(actor, "id", None)})
    return await get_merchandise(session, item_id, track_view=False)


async def delete_merchandise(
    session: AsyncSession, item_id: int, actor: Optional[User] = None
) -> None:
    item = await session.get(Merchandise, item_id)
    if item is None:
        raise NotFoundError(f"merchandise {item_id} not found")
    await session.delete(item)
    await session.commit()
    logger.info("merchandise_deleted", extra={"merchandise_id": item_id, "actor_id": getattr(actor, "id", None)})
