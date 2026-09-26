"""Event schemas, including the lat/lng "near me" query."""

from __future__ import annotations

import datetime as dt
import math

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class EventRead(ORMModel):
    id: int
    name: str
    city: str
    lat: float
    lng: float
    start_date: dt.date
    end_date: dt.date | None = None
    ticket_url: str | None = None
    description: str | None = None
    category_id: int | None = None
    category_slug: str | None = None
    category_name: str | None = None
    distance_km: float | None = Field(
        default=None, description="Set when the request supplied near=lat,lng"
    )
    created_at: dt.datetime | None = None


class EventQuery(BaseModel):
    """Query model for ``GET /events``.

    ``near`` + ``radius_km`` produce a latitude/longitude bounding box (see the
    README simplification note: no PostGIS, plain B-tree index on (lat, lng)).
    """

    city: str | None = Field(default=None, max_length=120)
    near: str | None = Field(
        default=None, description="Reference point as 'lat,lng', e.g. 35.6812,139.7671"
    )
    radius_km: float = Field(default=50.0, gt=0, le=20_000)
    category: str | None = Field(default=None, max_length=60, description="Category slug")
    from_date: dt.date | None = None
    to_date: dt.date | None = None
    upcoming_only: bool = False

    @model_validator(mode="after")
    def _validate_near(self) -> "EventQuery":
        if not self.near:
            return self
        parts = [part.strip() for part in self.near.split(",")]
        if len(parts) != 2:
            raise ValueError("near must be formatted as 'lat,lng'")
        try:
            lat, lng = float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise ValueError("near must contain two numeric values: 'lat,lng'") from exc
        if not -90 <= lat <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= lng <= 180:
            raise ValueError("longitude must be between -180 and 180")
        object.__setattr__(self, "_coords", (lat, lng))
        return self

    @property
    def coords(self) -> tuple[float, float] | None:
        return getattr(self, "_coords", None)

    def bounding_box(self) -> tuple[float, float, float, float] | None:
        """Return ``(min_lat, max_lat, min_lng, max_lng)`` for the radius.

        Uses the haversine degree approximations: 1 deg latitude ~= 111.32 km,
        1 deg longitude ~= 111.32 km * cos(latitude). The box is deliberately a
        little generous (see README "no PostGIS" note); distance_km is still
        computed exactly with the haversine formula in the response.
        """
        if not self.coords:
            return None
        lat, lng = self.coords
        lat_delta = self.radius_km / 111.32
        cos_lat = math.cos(math.radians(lat))
        # Near the poles longitude degrees shrink, so clamp the divisor to keep
        # the box from collapsing to zero width (and dividing by zero).
        lng_delta = self.radius_km / (111.32 * max(abs(cos_lat), 1e-6))
        return (
            max(-90.0, lat - lat_delta),
            min(90.0, lat + lat_delta),
            max(-180.0, lng - lng_delta),
            min(180.0, lng + lng_delta),
        )
