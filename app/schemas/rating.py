"""Rating schemas.

Design decision (documented in README): a *single* endpoint ``POST /content/{id}/rate``
handles both supported scales. The request carries ``scale`` ("stars" | "thumbs") and
``value`` validated against that scale, so the client can offer a 5-star widget or a
thumbs up/down widget with the same route and the same table row (unique per
user+content, so re-rating overwrites).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, model_validator

from app.db.models.rating import RatingScale
from app.schemas.common import ORMModel


class RatingCreate(BaseModel):
    scale: RatingScale = RatingScale.STARS
    value: int = Field(description="1-5 for stars; +1 or -1 for thumbs")

    @model_validator(mode="after")
    def _value_matches_scale(self) -> "RatingCreate":
        if self.scale == RatingScale.STARS and not 1 <= self.value <= 5:
            raise ValueError("value must be between 1 and 5 when scale='stars'")
        if self.scale == RatingScale.THUMBS and self.value not in (-1, 1):
            raise ValueError("value must be +1 or -1 when scale='thumbs'")
        return self


class RatingRead(ORMModel):
    id: int
    user_id: int
    content_id: int
    scale: RatingScale
    value: int
    created_at: dt.datetime
    updated_at: dt.datetime | None = None


class RatingResponse(BaseModel):
    """Acknowledgement plus the content's aggregate after the write."""

    rating: RatingRead
    summary: "ContentRatingSummary"
    created: bool = Field(description="True when a new row was inserted, False on update")


class ContentRatingSummary(BaseModel):
    average: float
    count: int
    star_distribution: dict[str, int] = Field(default_factory=dict)
    thumbs_up: int = 0
    thumbs_down: int = 0


RatingResponse.model_rebuild()
