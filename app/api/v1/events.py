"""Fan event routes with the bounding-box "near me" filter."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import DbSession, Pagination
from app.schemas.common import Page
from app.schemas.event import EventQuery, EventRead
from app.services import event_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=Page[EventRead], summary="Browse events")
async def list_events(
    db: DbSession,
    pagination: Pagination,
    city: Annotated[str | None, Query(max_length=120)] = None,
    near: Annotated[
        str | None,
        Query(description="Reference point as 'lat,lng', e.g. 35.6812,139.7671"),
    ] = None,
    radius_km: Annotated[float, Query(gt=0, le=20_000, description="Search radius in km")] = 50.0,
    category: Annotated[str | None, Query(max_length=60, description="Category slug")] = None,
    from_date: Annotated[dt.date | None, Query(description="Events ending on/after this date")] = None,
    to_date: Annotated[dt.date | None, Query(description="Events starting on/before this date")] = None,
    upcoming_only: Annotated[bool, Query(description="Only events starting today or later")] = False,
) -> Page[EventRead]:
    """Filter by city substring, category, date window, or a lat/lng + radius.

    ``near`` + ``radius_km`` selects a latitude/longitude bounding box (indexed by
    ``ix_events_lat_lng``) and then refines it with an exact haversine distance,
    reported per event as ``distance_km``.
    """
    query = EventQuery(
        city=city,
        near=near,
        radius_km=radius_km,
        category=category,
        from_date=from_date,
        to_date=to_date,
        upcoming_only=upcoming_only,
    )
    return await event_service.list_events(db, pagination, query)


@router.get("/{event_id}", response_model=EventRead, summary="Event detail")
async def get_event(event_id: int, db: DbSession) -> EventRead:
    return await event_service.get_event(db, event_id)
