"""Fan events, including the "near me" distance filter.

Geospatial simplification (documented in the README): instead of PostGIS we filter
with a latitude/longitude bounding box that rides the ``ix_events_lat_lng`` B-tree
index, then refine the survivors with the exact haversine formula in Python. That
is plenty for a city-scale demo and avoids a geography extension on serverless
Postgres.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Optional

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging_config import get_logger
from app.db.models.category import Category
from app.db.models.event import Event
from app.schemas.common import Page, PageParams
from app.schemas.event import EventQuery, EventRead

logger = get_logger(__name__)

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def _to_read(event: Event, origin: Optional[tuple[float, float]] = None) -> EventRead:
    return EventRead(
        id=event.id,
        name=event.name,
        city=event.city,
        lat=event.lat,
        lng=event.lng,
        start_date=event.start_date,
        end_date=event.end_date,
        ticket_url=event.ticket_url,
        description=event.description,
        category_id=event.category_id,
        category_slug=event.category.slug if event.category else None,
        category_name=event.category.name if event.category else None,
        distance_km=(
            round(haversine_km(origin[0], origin[1], event.lat, event.lng), 2) if origin else None
        ),
        created_at=event.created_at,
    )


def _build_query(filters: EventQuery) -> Select:
    stmt = select(Event).join(Category, Category.id == Event.category_id, isouter=True)

    if filters.city:
        stmt = stmt.where(func.lower(Event.city).ilike(f"%{filters.city.strip().lower()}%"))
    if filters.category:
        stmt = stmt.where(Category.slug == filters.category.strip().lower())
    if filters.from_date:
        stmt = stmt.where(Event.end_date.isnot(None), Event.end_date >= filters.from_date)
        stmt = stmt.where(Event.start_date <= filters.from_date)
    if filters.to_date:
        stmt = stmt.where(Event.start_date <= filters.to_date)
    if filters.upcoming_only:
        today = dt.date.today()
        stmt = stmt.where(Event.start_date >= today)

    box = filters.bounding_box()
    if box is not None:
        min_lat, max_lat, min_lng, max_lng = box
        stmt = stmt.where(
            Event.lat.between(min_lat, max_lat), Event.lng.between(min_lng, max_lng)
        )
    return stmt


async def list_events(session: AsyncSession, page: PageParams, filters: EventQuery) -> Page[EventRead]:
    stmt = _build_query(filters)

    total = int(
        (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar() or 0
    )
    rows = list(
        (
            await session.execute(
                stmt.options(selectinload(Event.category))
                .order_by(Event.start_date.asc(), Event.id.asc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .unique()
        .all()
    )

    origin = filters.coords
    items = [_to_read(event, origin) for event in rows]

    # Exact radius filter (the box is a cheap superset, this is the precise cut).
    if origin is not None and filters.near:
        items = [item for item in items if (item.distance_km or 0) <= filters.radius_km]
        # Recount so pagination metadata matches the refined result set.
        total = len(items) if page.page == 1 and page.offset == 0 else total

    return Page.build(items, total, page.page, page.page_size)


async def get_event(session: AsyncSession, event_id: int) -> EventRead:
    event = (
        await session.execute(
            select(Event).options(selectinload(Event.category)).where(Event.id == event_id)
        )
    ).scalar_one_or_none()
    if event is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"event {event_id} not found")
    return _to_read(event)
