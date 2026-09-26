"""Aggregated model imports - keeps ``Base.metadata`` complete for Alembic."""

from app.db.base import Base
from app.db.models.bookmark import Bookmark, BookmarkTarget
from app.db.models.category import Category
from app.db.models.character import Character
from app.db.models.chatbot import ChatbotFaq, ChatbotMessage, ChatbotSession, MessageRole
from app.db.models.content import Content, ContentStatus, ContentType, Tag, content_tags
from app.db.models.event import Event
from app.db.models.feedback import Feedback, FeedbackStatus, FeedbackType
from app.db.models.merchandise import Merchandise
from app.db.models.rating import Rating, RatingScale
from app.db.models.submission import FanSubmission, SubmissionStatus
from app.db.models.user import AuthToken, AuthTokenPurpose, User, UserPreference, UserRole

__all__ = [
    "Base",
    "AuthToken",
    "AuthTokenPurpose",
    "Bookmark",
    "BookmarkTarget",
    "Category",
    "Character",
    "ChatbotFaq",
    "ChatbotMessage",
    "ChatbotSession",
    "Content",
    "ContentStatus",
    "ContentType",
    "Event",
    "FanSubmission",
    "Feedback",
    "FeedbackStatus",
    "FeedbackType",
    "Merchandise",
    "MessageRole",
    "Rating",
    "RatingScale",
    "SubmissionStatus",
    "Tag",
    "User",
    "UserPreference",
    "UserRole",
    "content_tags",
]
