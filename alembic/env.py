"""Alembic environment - async engine, DATABASE_URL sourced from app settings."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.models import Base
from app.db.session import build_engine, prepare_async_dsn

if context.config.config_file_name is not None and context.get_x_argument(as_dictionary=False) != ["-x", "no_logging"]:
    # Keep Alembic's own console logging; our structured logger owns the rest.
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)

configure_logging()

target_metadata = Base.metadata


def _offline_url() -> str:
    """Offline DDL needs a plain (non-asyncpg) driver URL.

    Reuse ``prepare_async_dsn`` so the scheme is normalised and driver-specific
    query parameters (``channel_binding`` and friends) are dropped exactly as they
    are for a real connection.
    """
    clean_url, _ = prepare_async_dsn(settings.database_url)
    return clean_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DB connection (``alembic upgrade head --sql``)."""
    context.configure(
        url=_offline_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: AsyncConnection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = build_engine()
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
