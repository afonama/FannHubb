"""Initial schema: 17 tables, 10 native enum types.

Generated offline from ``Base.metadata`` (see alembic/notes). Autogenerate needs a
live database, so this revision was written from the metadata and validated with
``alembic upgrade head --sql`` (offline mode) plus ``scripts/export_schema.py``.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    postgresql.ENUM('email_verify', 'password_reset', name='auth_token_purpose', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('content', 'character', 'merchandise', name='bookmark_target', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('draft', 'published', name='content_status', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('article', 'video', 'audio', 'image', name='content_type', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('open', 'reviewed', 'closed', name='feedback_status', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('bug', 'suggestion', 'query', name='feedback_type', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('user', 'bot', name='message_role', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('stars', 'thumbs', name='rating_scale', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('pending', 'approved', 'rejected', name='submission_status', create_type=False).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM('visitor', 'registered', 'admin', name='user_role', create_type=False).create(op.get_bind(), checkfirst=True)

    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('slug', sa.String(length=60), nullable=False),
        sa.Column('description', sa.String()),
        sa.Column('icon_url', sa.String(length=512)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_categories'),
    )
    op.create_index('ix_categories_slug', 'categories', ['slug'], unique=True)

    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default=sa.text("'0'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_tags'),
        sa.UniqueConstraint('name', name='uq_tags_name'),
    )
    op.create_index('ix_tags_name_lower', 'tags', [sa.text('lower(tags.name)')])

    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('avatar_url', sa.String(length=512)),
        sa.Column('role', postgresql.ENUM('visitor', 'registered', 'admin', name='user_role', create_type=False), nullable=False, server_default=sa.text("'registered'")),
        sa.Column('is_email_verified', sa.Boolean(), nullable=False, server_default=sa.text("'false'")),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_users'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_is_email_verified', 'users', ['is_email_verified'])
    op.create_index('ix_users_role_created_at', 'users', ['role', 'created_at'])

    op.create_table(
        'auth_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE', name='fk_auth_tokens_user_id_users'), nullable=False),
        sa.Column('purpose', postgresql.ENUM('email_verify', 'password_reset', name='auth_token_purpose', create_type=False), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("'now()'")),
        sa.PrimaryKeyConstraint('id', name='pk_auth_tokens'),
        sa.UniqueConstraint('token_hash', name='uq_auth_tokens_token_hash'),
    )
    op.create_index('ix_auth_tokens_expires_at', 'auth_tokens', ['expires_at'])
    op.create_index('ix_auth_tokens_user_purpose', 'auth_tokens', ['user_id', 'purpose'])

    op.create_table(
        'bookmarks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE', name='fk_bookmarks_user_id_users'), nullable=False),
        sa.Column('content_type', postgresql.ENUM('content', 'character', 'merchandise', name='bookmark_target', create_type=False), nullable=False),
        sa.Column('content_id', sa.Integer(), nullable=False),
        sa.Column('note', sa.String()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("'now()'")),
        sa.PrimaryKeyConstraint('id', name='pk_bookmarks'),
        sa.UniqueConstraint('user_id', 'content_type', 'content_id', name='uq_bookmarks_user_type_content'),
    )
    op.create_index('ix_bookmarks_content_type_content_id', 'bookmarks', ['content_type', 'content_id'])
    op.create_index('ix_bookmarks_user_id_created_at', 'bookmarks', ['user_id', 'created_at'])

    op.create_table(
        'characters',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id', ondelete='RESTRICT', name='fk_characters_category_id_categories'), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('bio', sa.String()),
        sa.Column('image_url', sa.String(length=512)),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default=sa.text("'0'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_characters'),
    )
    op.create_index('ix_characters_category_id', 'characters', ['category_id'])
    op.create_index('ix_characters_name', 'characters', ['name'])

    op.create_table(
        'chatbot_faqs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('question', sa.String(length=300), nullable=False),
        sa.Column('answer', sa.String(), nullable=False),
        sa.Column('keywords', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id', ondelete='SET NULL', name='fk_chatbot_faqs_category_id_categories')),
        sa.Column('priority', sa.Integer(), nullable=False, server_default=sa.text("'0'")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("'true'")),
        sa.Column('match_count', sa.Integer(), nullable=False, server_default=sa.text("'0'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_chatbot_faqs'),
    )
    op.create_index('ix_chatbot_faqs_is_active_priority', 'chatbot_faqs', ['is_active', 'priority'])

    op.create_table(
        'chatbot_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE', name='fk_chatbot_sessions_user_id_users')),
        sa.Column('session_token', sa.String(length=64), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_chatbot_sessions'),
    )
    op.create_index('ix_chatbot_sessions_session_token', 'chatbot_sessions', ['session_token'], unique=True)
    op.create_index('ix_chatbot_sessions_user_id', 'chatbot_sessions', ['user_id'])
    op.create_index('ix_chatbot_sessions_user_id_started_at', 'chatbot_sessions', ['user_id', 'started_at'])

    op.create_table(
        'content',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id', ondelete='RESTRICT', name='fk_content_category_id_categories'), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('type', postgresql.ENUM('article', 'video', 'audio', 'image', name='content_type', create_type=False), nullable=False),
        sa.Column('description', sa.String()),
        sa.Column('body_rich_text', sa.String()),
        sa.Column('media_url', sa.String(length=512)),
        sa.Column('release_date', sa.Date()),
        sa.Column('popularity_score', sa.Float(), nullable=False, server_default=sa.text("'0'")),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default=sa.text("'0'")),
        sa.Column('status', postgresql.ENUM('draft', 'published', name='content_status', create_type=False), nullable=False, server_default=sa.text("'published'")),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_content_created_by_users')),
        sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed(sa.text("to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))"), persisted=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_content'),
        sa.CheckConstraint(sa.text('view_count >= 0'), name='view_count_non_negative'),
    )
    op.create_index('ix_content_category_id_status', 'content', ['category_id', 'status'])
    op.create_index('ix_content_popularity_score', 'content', ['popularity_score'])
    op.create_index('ix_content_search_vector', 'content', ['search_vector'], postgresql_using='gin')
    op.create_index('ix_content_status_release_date', 'content', ['status', 'release_date'])
    op.create_index('ix_content_type', 'content', ['type'])

    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('city', sa.String(length=120), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date()),
        sa.Column('ticket_url', sa.String(length=512)),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id', ondelete='SET NULL', name='fk_events_category_id_categories')),
        sa.Column('description', sa.String(length=1000)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_events'),
    )
    op.create_index('ix_events_city', 'events', ['city'])
    op.create_index('ix_events_lat_lng', 'events', ['lat', 'lng'])
    op.create_index('ix_events_start_date', 'events', ['start_date'])

    op.create_table(
        'fan_submissions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE', name='fk_fan_submissions_user_id_users'), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id', ondelete='SET NULL', name='fk_fan_submissions_category_id_categories')),
        sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='submission_status', create_type=False), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('review_note', sa.String()),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_fan_submissions_reviewed_by_users')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_fan_submissions'),
    )
    op.create_index('ix_fan_submissions_status_created_at', 'fan_submissions', ['status', 'created_at'])
    op.create_index('ix_fan_submissions_user_id', 'fan_submissions', ['user_id'])

    op.create_table(
        'feedback',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_feedback_user_id_users')),
        sa.Column('type', postgresql.ENUM('bug', 'suggestion', 'query', name='feedback_type', create_type=False), nullable=False),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('status', postgresql.ENUM('open', 'reviewed', 'closed', name='feedback_status', create_type=False), nullable=False, server_default=sa.text("'open'")),
        sa.Column('admin_note', sa.String()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_feedback'),
    )
    op.create_index('ix_feedback_status_created_at', 'feedback', ['status', 'created_at'])
    op.create_index('ix_feedback_type', 'feedback', ['type'])
    op.create_index('ix_feedback_user_id', 'feedback', ['user_id'])

    op.create_table(
        'merchandise',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id', ondelete='RESTRICT', name='fk_merchandise_category_id_categories'), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('description', sa.String(length=500)),
        sa.Column('image_url', sa.String(length=512)),
        sa.Column('tag', sa.String(length=60)),
        sa.Column('is_upcoming', sa.Boolean(), nullable=False, server_default=sa.text("'false'")),
        sa.Column('release_date', sa.String(length=40)),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default=sa.text("'0'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_merchandise'),
    )
    op.create_index('ix_merchandise_category_id', 'merchandise', ['category_id'])
    op.create_index('ix_merchandise_category_id_is_upcoming', 'merchandise', ['category_id', 'is_upcoming'])
    op.create_index('ix_merchandise_tag', 'merchandise', ['tag'])

    op.create_table(
        'user_preferences',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE', name='fk_user_preferences_user_id_users'), autoincrement=True, nullable=False),
        sa.Column('favorite_categories', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('display_prefs', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('user_id', name='pk_user_preferences'),
    )

    op.create_table(
        'chatbot_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('chatbot_sessions.id', ondelete='CASCADE', name='fk_chatbot_messages_session_id_chatbot_sessions'), nullable=False),
        sa.Column('role', postgresql.ENUM('user', 'bot', name='message_role', create_type=False), nullable=False),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('matched_faq_id', sa.Integer(), sa.ForeignKey('chatbot_faqs.id', ondelete='SET NULL', name='fk_chatbot_messages_matched_faq_id_chatbot_faqs')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_chatbot_messages'),
    )
    op.create_index('ix_chatbot_messages_session_id_created_at', 'chatbot_messages', ['session_id', 'created_at'])

    op.create_table(
        'content_tags',
        sa.Column('content_id', sa.Integer(), sa.ForeignKey('content.id', ondelete='CASCADE', name='fk_content_tags_content_id_content'), nullable=False),
        sa.Column('tag_id', sa.Integer(), sa.ForeignKey('tags.id', ondelete='CASCADE', name='fk_content_tags_tag_id_tags'), nullable=False),
        sa.PrimaryKeyConstraint('content_id', 'tag_id', name='pk_content_tags'),
    )
    op.create_index('ix_content_tags_tag_id', 'content_tags', ['tag_id'])

    op.create_table(
        'ratings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE', name='fk_ratings_user_id_users'), nullable=False),
        sa.Column('content_id', sa.Integer(), sa.ForeignKey('content.id', ondelete='CASCADE', name='fk_ratings_content_id_content'), nullable=False),
        sa.Column('scale', postgresql.ENUM('stars', 'thumbs', name='rating_scale', create_type=False), nullable=False, server_default=sa.text("'stars'")),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint(sa.text("(scale = 'stars' AND value BETWEEN 1 AND 5) OR (scale = 'thumbs' AND value IN (-1, 1))"), name='rating_value_matches_scale'),
        sa.UniqueConstraint('user_id', 'content_id', name='uq_ratings_user_content'),
        sa.PrimaryKeyConstraint('id', name='pk_ratings'),
    )
    op.create_index('ix_ratings_content_id', 'ratings', ['content_id'])
    op.create_index('ix_ratings_user_id', 'ratings', ['user_id'])


def downgrade() -> None:
    op.drop_table('ratings')
    op.drop_table('content_tags')
    op.drop_table('chatbot_messages')
    op.drop_table('user_preferences')
    op.drop_table('merchandise')
    op.drop_table('feedback')
    op.drop_table('fan_submissions')
    op.drop_table('events')
    op.drop_table('content')
    op.drop_table('chatbot_sessions')
    op.drop_table('chatbot_faqs')
    op.drop_table('characters')
    op.drop_table('bookmarks')
    op.drop_table('auth_tokens')
    op.drop_table('users')
    op.drop_table('tags')
    op.drop_table('categories')
    for enum in ('user_role', 'submission_status', 'rating_scale', 'message_role', 'feedback_type', 'feedback_status', 'content_type', 'content_status', 'bookmark_target', 'auth_token_purpose',):
        postgresql.ENUM(name=enum).drop(op.get_bind(), checkfirst=True)
