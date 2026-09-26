"""Bookmarks: polymorphic saves for content / characters / merchandise.

A bookmark row is a (user, target_type, target_id) triple; the referenced row is
resolved lazily per page so the listing can show titles, images and category
slugs without N+1 queries.
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.logging_config import get_logger
from app.db.models.bookmark import Bookmark, BookmarkTarget
from app.db.models.category import Category
from app.db.models.character import Character
from app.db.models.content import Content, ContentStatus
from app.db.models.merchandise import Merchandise
from app.db.models.user import User
from app.schemas.bookmark import BookmarkCreate, BookmarkRead
from app.schemas.common import Page, PageParams
from app.schemas.user import BookmarkPreview

logger = get_logger(__name__)

_TARGET_MODELS: dict[BookmarkTarget, type] = {
    BookmarkTarget.CONTENT: Content,
    BookmarkTarget.CHARACTER: Character,
    BookmarkTarget.MERCHANDISE: Merchandise,
}


async def _target_exists(session: AsyncSession, target: BookmarkTarget, target_id: int) -> None:
    """Reject saves of rows that do not exist (or, for content, are not published)."""
    model = _TARGET_MODELS[target]
    stmt = select(model.id).where(model.id == target_id)
    if target == BookmarkTarget.CONTENT:
        stmt = stmt.where(Content.status == ContentStatus.PUBLISHED)
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise NotFoundError(f"{target.value} {target_id} not found")


async def add_bookmark(session: AsyncSession, user: User, payload: BookmarkCreate) -> BookmarkRead:
    """Idempotent-ish create: an existing triple is reported as a 409 conflict."""
    await _target_exists(session, payload.content_type, payload.content_id)

    existing = (
        await session.execute(
            select(Bookmark).where(
                Bookmark.user_id == user.id,
                Bookmark.content_type == payload.content_type,
                Bookmark.content_id == payload.content_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            "This item is already bookmarked",
            details={"bookmark_id": existing.id, "content_type": payload.content_type.value,
                     "content_id": payload.content_id},
        )

    bookmark = Bookmark(
        user_id=user.id,
        content_type=payload.content_type,
        content_id=payload.content_id,
        note=payload.note,
    )
    session.add(bookmark)
    await session.commit()
    await session.refresh(bookmark)
    logger.info(
        "bookmark_added",
        extra={"user_id": user.id, "bookmark_id": bookmark.id, "target": payload.content_type.value,
               "target_id": payload.content_id},
    )
    return await _to_read(session, bookmark)


async def remove_bookmark(
    session: AsyncSession, user: User, target: BookmarkTarget, target_id: int
) -> int:
    result = await session.execute(
        delete(Bookmark).where(
            Bookmark.user_id == user.id,
            Bookmark.content_type == target,
            Bookmark.content_id == target_id,
        )
    )
    await session.commit()
    deleted = int(result.rowcount or 0)
    if deleted == 0:
        raise NotFoundError(
            "Bookmark not found",
            details={"content_type": target.value, "content_id": target_id},
        )
    logger.info(
        "bookmark_removed",
        extra={"user_id": user.id, "target": target.value, "target_id": target_id},
    )
    return deleted


async def list_bookmarks(
    session: AsyncSession,
    user: User,
    page: PageParams,
    *,
    target: Optional[BookmarkTarget] = None,
) -> list[Bookmark]:
    stmt = select(Bookmark).where(Bookmark.user_id == user.id)
    if target is not None:
        stmt = stmt.where(Bookmark.content_type == target)
    return list(
        (
            await session.execute(
                stmt.order_by(Bookmark.created_at.desc(), Bookmark.id.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .all()
    )


async def count_bookmarks(session: AsyncSession, user: User, target: Optional[BookmarkTarget] = None) -> int:
    stmt = select(func.count(Bookmark.id)).where(Bookmark.user_id == user.id)
    if target is not None:
        stmt = stmt.where(Bookmark.content_type == target)
    return int((await session.execute(stmt)).scalar() or 0)


async def paged_bookmarks(
    session: AsyncSession,
    user: User,
    page: PageParams,
    *,
    target: Optional[BookmarkTarget] = None,
) -> Page[BookmarkRead]:
    total = await count_bookmarks(session, user, target)
    rows = await list_bookmarks(session, user, page, target=target)
    items = [await _to_read(session, row) for row in rows]
    return Page.build(items, total, page.page, page.page_size)


async def _target_metadata(
    session: AsyncSession, target: BookmarkTarget, ids: Sequence[int]
) -> dict[int, tuple[str, str | None, str | None]]:
    """Return ``{id: (title, image_url, category_slug)}`` for a page of bookmarks."""
    if not ids:
        return {}
    if target == BookmarkTarget.CONTENT:
        rows = (
            await session.execute(
                select(Content.id, Content.title, Content.media_url, Category.slug)
                .join(Category, Category.id == Content.category_id)
                .where(Content.id.in_(list(ids)))
            )
        ).all()
    elif target == BookmarkTarget.CHARACTER:
        rows = (
            await session.execute(
                select(Character.id, Character.name, Character.image_url, Category.slug)
                .join(Category, Category.id == Character.category_id)
                .where(Character.id.in_(list(ids)))
            )
        ).all()
    else:
        rows = (
            await session.execute(
                select(Merchandise.id, Merchandise.name, Merchandise.image_url, Category.slug)
                .join(Category, Category.id == Merchandise.category_id)
                .where(Merchandise.id.in_(list(ids)))
            )
        ).all()
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


async def _to_read(session: AsyncSession, bookmark: Bookmark) -> BookmarkRead:
    metadata = await _target_metadata(session, bookmark.content_type, [bookmark.content_id])
    title, image_url, category_slug = metadata.get(bookmark.content_id, (None, None, None))
    return BookmarkRead(
        id=bookmark.id,
        user_id=bookmark.user_id,
        content_type=bookmark.content_type,
        content_id=bookmark.content_id,
        note=bookmark.note,
        created_at=bookmark.created_at,
        title=title,
        image_url=image_url,
        category_slug=category_slug,
    )


def to_preview(bookmark: Bookmark) -> BookmarkPreview:
    """Cheap projection used by the dashboard (no title resolution)."""
    return BookmarkPreview(
        id=bookmark.id,
        content_type=bookmark.content_type.value,
        content_id=bookmark.content_id,
        title=f"{bookmark.content_type.value} #{bookmark.content_id}",
        created_at=bookmark.created_at,
    )


async def is_bookmarked(session: AsyncSession, user: User, target: BookmarkTarget, target_id: int) -> bool:
    return bool(
        await session.scalar(
            select(Bookmark.id).where(
                Bookmark.user_id == user.id,
                Bookmark.content_type == target,
                Bookmark.content_id == target_id,
            )
        )
    )
