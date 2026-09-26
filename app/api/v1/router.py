"""Aggregate router for API v1 - one include per resource."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    bookmarks,
    categories,
    characters,
    chatbot,
    content,
    events,
    feedback,
    health,
    merchandise,
    ratings,
    submissions,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(categories.router)
api_router.include_router(content.router)
api_router.include_router(characters.router)
api_router.include_router(merchandise.router)
api_router.include_router(bookmarks.router)
api_router.include_router(ratings.router)
api_router.include_router(submissions.router)
api_router.include_router(feedback.router)
api_router.include_router(events.router)
api_router.include_router(chatbot.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
