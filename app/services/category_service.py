"""Category listing with published-content counts."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.category import Category
from app.db.models.content import Content, ContentStatus
from app.schemas.category import CategoryRead


async def list_categories(session: AsyncSession) -> list[CategoryRead]:
    """All categories ordered by display id, each with a published-content count."""
    rows = (
        await session.execute(
            select(Category, func.count(Content.id))
            .outerjoin(
                Content,
                (Content.category_id == Category.id) & (Content.status == ContentStatus.PUBLISHED),
            )
            .group_by(Category.id, Category.slug, Category.name, Category.description, Category.icon_url, Category.created_at, Category.updated_at)
            .order_by(Category.id)
        )
    ).all()
    return [
        CategoryRead(
            id=category.id,
            name=category.name,
            slug=category.slug,
            description=category.description,
            icon_url=category.icon_url,
            content_count=int(count),
            created_at=category.created_at,
        )
        for category, count in rows
    ]


async def get_category_by_slug(session: AsyncSession, slug: str) -> Category | None:
    return (
        await session.execute(select(Category).where(Category.slug == slug.strip().lower()))
    ).scalar_one_or_none()


async def get_category(session: AsyncSession, slug: str) -> CategoryRead:
    """One category with its published-content count, or 404."""
    from app.core.errors import NotFoundError

    normalised = slug.strip().lower()
    row = (
        await session.execute(
            select(Category, func.count(Content.id))
            .outerjoin(
                Content,
                (Content.category_id == Category.id)
                & (Content.status == ContentStatus.PUBLISHED),
            )
            .where(Category.slug == normalised)
            .group_by(
                Category.id,
                Category.slug,
                Category.name,
                Category.description,
                Category.icon_url,
                Category.created_at,
                Category.updated_at,
            )
        )
    ).first()
    if row is None:
        raise NotFoundError(
            "Category not found",
            details={"slug": normalised},
        )
    category, count = row
    return CategoryRead(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        icon_url=category.icon_url,
        content_count=int(count),
        created_at=category.created_at,
    )
