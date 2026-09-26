"""Rating routes.

Single endpoint for both scales (documented in README + app/schemas/rating.py):
``scale=stars`` takes value 1-5, ``scale=thumbs`` takes value +1/-1.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession
from app.schemas.common import MessageResponse
from app.schemas.rating import ContentRatingSummary, RatingCreate, RatingRead, RatingResponse
from app.services import rating_service

router = APIRouter(tags=["ratings"])


@router.post(
    "/content/{content_id}/rate",
    response_model=RatingResponse,
    status_code=status.HTTP_200_OK,
    summary="Rate a content item (5-star or thumbs up/down)",
    responses={404: {"description": "Content not found"}, 422: {"description": "Invalid value for the scale"}},
)
async def rate_content(
    content_id: int, payload: RatingCreate, db: DbSession, user: CurrentUser
) -> RatingResponse:
    """Upsert: one rating per user per item.

    Returns ``created=true`` for a first rating and ``created=false`` when an
    existing rating was updated (including switching between scales).
    """
    return await rating_service.rate_content(db, user, content_id, payload)


@router.get(
    "/content/{content_id}/rating",
    response_model=ContentRatingSummary,
    summary="Aggregate rating for a content item",
)
async def content_rating(content_id: int, db: DbSession) -> ContentRatingSummary:
    """Public aggregate: average + star distribution + thumbs totals."""
    return await rating_service.content_rating_summary(db, content_id)


@router.get(
    "/content/{content_id}/rating/me",
    response_model=RatingRead,
    summary="My own rating",
)
async def my_rating(content_id: int, db: DbSession, user: CurrentUser) -> RatingRead:
    from app.core.errors import NotFoundError

    rating = await rating_service.get_user_rating(db, user, content_id)
    if rating is None:
        raise NotFoundError("You have not rated this item", details={"content_id": content_id})
    return RatingRead.model_validate(rating)


@router.delete(
    "/content/{content_id}/rating",
    response_model=MessageResponse,
    summary="Remove my rating",
    responses={404: {"description": "No rating to delete"}},
)
async def delete_rating(content_id: int, db: DbSession, user: CurrentUser) -> MessageResponse:
    await rating_service.delete_rating(db, user, content_id)
    return MessageResponse(message=f"Rating on content {content_id} removed")
