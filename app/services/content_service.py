"""Content catalogue: filtering, sorting, full-text search, admin CRUD."""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.core.logging_config import get_logger
from app.db.models.bookmark import Bookmark, BookmarkTarget
from app.db.models.category import Category
from app.db.models.content import Content, ContentStatus, Tag
from app.db.models.rating import Rating, RatingScale
from app.db.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.content import (
    ContentCreate,
    ContentDetail,
    ContentFilters,
    ContentListItem,
    ContentUpdate,
    RatingSummary,
)
from app.services import popularity_service

logger = get_logger(__name__)


def _tag_names(item: Content) -> list[str]:
    """API shape stays ``list[str]`` even though the ORM holds ``Tag`` rows."""
    return [tag.name for tag in (item.tags or [])]


async def _resolve_tags(session: AsyncSession, names: Sequence[str]) -> list[Tag]:
    """Get-or-create Tag rows for a list of tag names (lowercased, deduped)."""
    wanted = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    if not wanted:
        return []

    existing = (
        (
            await session.execute(select(Tag).where(Tag.name.in_(wanted)))
        )
        .scalars()
        .all()
    )
    by_name = {tag.name: tag for tag in existing}
    for name in wanted:
        if name not in by_name:
            tag = Tag(name=name)
            session.add(tag)
            by_name[name] = tag
    # Flush so the association rows written by the caller have real tag_id values.
    await session.flush()
    return [by_name[name] for name in wanted]


# ---------------------------------------------------------------- queries
def _base_query(filters: ContentFilters, *, is_admin: bool) -> Select:
    """Filter/sort builder shared by the list endpoint and the count query."""
    stmt: Select = select(Content).join(Category, Category.id == Content.category_id)

    if not is_admin or filters.status is None:
        # Visitors may only ever see published rows.
        stmt = stmt.where(Content.status == ContentStatus.PUBLISHED)
    else:
        stmt = stmt.where(Content.status == filters.status)

    if filters.category:
        stmt = stmt.where(Category.slug == filters.category.strip().lower())
    if filters.year:
        stmt = stmt.where(func.extract("year", Content.release_date) == filters.year)
    if filters.type:
        stmt = stmt.where(Content.type == filters.type)
    if filters.genre:
        tag = filters.genre.strip().lower()
        stmt = stmt.where(Content.tags.any(Tag.name == tag))
    if filters.q:
        # websearch_to_tsquery never raises on odd user input, unlike to_tsquery.
        query = func.websearch_to_tsquery("english", filters.q.strip())
        stmt = stmt.where(Content.search_vector.op("@@")(query))

    return stmt


def _apply_sort(stmt: Select, filters: ContentFilters) -> Select:
    if filters.q and filters.sort == "relevance":
        query = func.websearch_to_tsquery("english", filters.q.strip())
        rank = func.ts_rank_cd(Content.search_vector, query)
        return stmt.order_by(rank.desc(), Content.popularity_score.desc(), Content.id.desc())
    if filters.sort == "popular":
        return stmt.order_by(Content.popularity_score.desc(), Content.view_count.desc(), Content.id.desc())
    if filters.sort == "alpha":
        return stmt.order_by(Content.title.asc(), Content.id.asc())
    return stmt.order_by(Content.created_at.desc(), Content.id.desc())


async def list_content(
    session: AsyncSession,
    filters: ContentFilters,
    page: PageParams,
    *,
    is_admin: bool = False,
) -> Page[ContentListItem]:
    """Paginated, filtered, sorted content list with batched rating aggregates."""
    if filters.category:
        await popularity_service.record_category_browse(filters.category.strip().lower())

    base = _base_query(filters, is_admin=is_admin)
    total = int(
        (await session.execute(select(func.count()).select_from(base.order_by(None).subquery()))).scalar()
        or 0
    )

    stmt = (
        _apply_sort(base, filters)
        .options(selectinload(Content.category), selectinload(Content.tags))
        .limit(page.limit)
        .offset(page.offset)
    )
    rows = list((await session.execute(stmt)).scalars().unique().all())
    items = await to_list_items(session, rows)
    return Page.build(items, total, page.page, page.page_size)


# ------------------------------------------------------------- rendering
async def _rating_summaries(
    session: AsyncSession, content_ids: Sequence[int]
) -> dict[int, RatingSummary]:
    """Aggregate every rating for a whole page in one grouped query (no N+1)."""
    if not content_ids:
        return {}
    rows = (
        await session.execute(
            select(
                Rating.content_id,
                Rating.scale,
                Rating.value,
                func.count(Rating.id).label("votes"),
            )
            .where(Rating.content_id.in_(list(content_ids)))
            .group_by(Rating.content_id, Rating.scale, Rating.value)
        )
    ).all()

    star_totals: dict[int, int] = {}
    star_votes: dict[int, int] = {}
    summaries: dict[int, RatingSummary] = {}

    for content_id, scale, value, votes in rows:
        summary = summaries.setdefault(content_id, RatingSummary(average=0.0, count=0))
        votes = int(votes)
        if scale == RatingScale.STARS:
            summary.count += votes
            star_totals[content_id] = star_totals.get(content_id, 0) + value * votes
            star_votes[content_id] = star_votes.get(content_id, 0) + votes
            summary.star_distribution[str(value)] = summary.star_distribution.get(str(value), 0) + votes
        elif value == 1:
            summary.thumbs_up += votes
        else:
            summary.thumbs_down += votes

    for content_id, summary in summaries.items():
        votes = star_votes.get(content_id, 0)
        summary.average = round(star_totals.get(content_id, 0) / votes, 2) if votes else 0.0
    return summaries


async def to_list_items(
    session: AsyncSession,
    contents: Sequence[Content],
    *,
    with_live_views: bool = False,
) -> list[ContentListItem]:
    """Convert Content rows into list items, batching rating and view lookups."""
    if not contents:
        return []
    ids = [item.id for item in contents]
    summaries = await _rating_summaries(session, ids)

    if with_live_views:
        stored = {item.id: item.view_count for item in contents}
        live = await popularity_service.view_count_with_live_deltas("content", ids, stored)
    else:
        live = {item.id: item.view_count for item in contents}

    return [
        ContentListItem(
            id=item.id,
            title=item.title,
            type=item.type,
            description=item.description,
            media_url=item.media_url,
            release_date=item.release_date,
            popularity_score=item.popularity_score,
            view_count=live.get(item.id, item.view_count),
            status=item.status,
            category_id=item.category_id,
            category_slug=item.category.slug if item.category else None,
            category_name=item.category.name if item.category else None,
            tags=_tag_names(item),
            rating=summaries.get(item.id),
            created_at=item.created_at,
        )
        for item in contents
    ]


async def get_content(
    session: AsyncSession,
    content_id: int,
    *,
    user: Optional[User] = None,
    is_admin: bool = False,
    track_view: bool = True,
) -> ContentDetail:
    """Fetch one content item, bumping the Redis view counter as a side effect."""
    stmt = (
        select(Content)
        .options(selectinload(Content.category), selectinload(Content.tags))
        .where(Content.id == content_id)
    )
    if not is_admin:
        stmt = stmt.where(Content.status == ContentStatus.PUBLISHED)

    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise NotFoundError(f"content {content_id} not found")

    if track_view:
        # Hot path stays in Redis; app.worker.scheduler flushes to Postgres.
        await popularity_service.record_view("content", content_id)

    live_views = await popularity_service.view_count_with_live_delta(
        "content", item.id, item.view_count
    )
    summary = (await _rating_summaries(session, [item.id])).get(item.id)

    bookmarked = False
    user_rating: Optional[dict] = None
    if user is not None:
        bookmarked = bool(
            await session.scalar(
                select(
                    Bookmark.id
                ).where(
                    Bookmark.user_id == user.id,
                    Bookmark.content_type == BookmarkTarget.CONTENT,
                    Bookmark.content_id == item.id,
                )
            )
        )
        rating_row = (
            await session.execute(
                select(Rating).where(Rating.user_id == user.id, Rating.content_id == item.id)
            )
        ).scalar_one_or_none()
        if rating_row is not None:
            user_rating = {"scale": rating_row.scale.value, "value": rating_row.value}

    return ContentDetail(
        id=item.id,
        title=item.title,
        type=item.type,
        description=item.description,
        media_url=item.media_url,
        release_date=item.release_date,
        popularity_score=item.popularity_score,
        view_count=live_views,
        status=item.status,
        category_id=item.category_id,
        category_slug=item.category.slug if item.category else None,
        category_name=item.category.name if item.category else None,
        tags=_tag_names(item),
        rating=summary,
        created_at=item.created_at,
        body_rich_text=item.body_rich_text,
        category_description=item.category.description if item.category else None,
        bookmarked=bookmarked,
        user_rating=user_rating,
        updated_at=item.updated_at,
    )


# ------------------------------------------------------------- admin CRUD
async def _assert_category_exists(session: AsyncSession, category_id: int) -> Category:
    category = await session.get(Category, category_id)
    if category is None:
        raise NotFoundError(f"category {category_id} not found", details={"category_id": category_id})
    return category


async def create_content(
    session: AsyncSession, payload: ContentCreate, actor: Optional[User] = None
) -> ContentDetail:
    await _assert_category_exists(session, payload.category_id)
    data = payload.model_dump(exclude={"tags"})
    item = Content(**data, created_by=actor.id if actor else None)
    item.tags = await _resolve_tags(session, payload.tags)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    logger.info(
        "content_created",
        extra={"content_id": item.id, "actor_id": getattr(actor, "id", None)},
    )
    return await get_content(session, item.id, is_admin=True, track_view=False)


async def update_content(
    session: AsyncSession, content_id: int, payload: ContentUpdate, actor: Optional[User] = None
) -> ContentDetail:
    item = await session.get(Content, content_id)
    if item is None:
        raise NotFoundError(f"content {content_id} not found")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    tags = changes.pop("tags", None)

    if "category_id" in changes:
        await _assert_category_exists(session, int(changes["category_id"]))
    if "status" in changes and changes["status"] == ContentStatus.PUBLISHED and item.status != ContentStatus.PUBLISHED:
        logger.info("content_published", extra={"content_id": content_id})

    for field, value in changes.items():
        setattr(item, field, value)
    if tags is not None:
        item.tags = await _resolve_tags(session, tags)

    session.add(item)
    await session.commit()
    logger.info(
        "content_updated",
        extra={"content_id": content_id, "fields": sorted(changes), "actor_id": getattr(actor, "id", None)},
    )
    return await get_content(session, content_id, is_admin=True, track_view=False)


async def delete_content(session: AsyncSession, content_id: int, actor: Optional[User] = None) -> None:
    item = await session.get(Content, content_id)
    if item is None:
        raise NotFoundError(f"content {content_id} not found")
    await session.delete(item)
    await session.commit()
    logger.info("content_deleted", extra={"content_id": content_id, "actor_id": getattr(actor, "id", None)})
