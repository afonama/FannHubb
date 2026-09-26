"""Async SQLAlchemy engine + session factory tuned for Neon serverless Postgres.

Neon specifics handled here:
  * the runtime DSN is the *pooled* endpoint (hostname contains ``-pooler``),
    i.e. a PgBouncer proxy - the asyncpg prepared-statement cache is disabled
    for that host because the proxy may route a session to another backend;
  * ``?sslmode=require`` (what Neon hands you in the console) is translated into
    the ``ssl=`` connect kwarg asyncpg understands;
  * the pool is deliberately small (5 + 5) because serverless Postgres scales
    compute on demand and bills idle connections.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

#: The exact set of ``ssl=`` values asyncpg accepts. Anything else would be a
#: hard connect error, so unknown values fall back to ``require`` - but every
#: mode asyncpg genuinely supports is passed through, including the stronger
#: ``verify-ca`` / ``verify-full`` (silently downgrading those to ``require``
#: would weaken TLS without telling anyone).
_ASYNC_SSL_MODES = {
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
}

#: Query parameters that belong to libpq (psycopg/``psql``) but are not valid
#: asyncpg connect arguments. asyncpg rejects unknown query parameters outright
#: with "invalid connect argument", so they must be dropped rather than passed
#: through. ``channel_binding`` is the one Neon now offers in its console.
_DROPPED_QUERY_PARAMS = {
    "channel_binding",
    "target_session_attrs",
    "sslcert",
    "sslkey",
    "sslrootcert",
    "sslcrl",
    "gssencmode",
    "keepalives",
    "keepalives_idle",
    "keepalives_interval",
    "keepalives_count",
    "replication",
    "options",
}


def prepare_async_dsn(url: str) -> tuple[str, dict[str, Any]]:
    """Normalise a Postgres DSN for the asyncpg driver.

    Returns the rewritten URL plus the connect kwargs that must be stripped out
    of the query string.
    """
    parsed = urlsplit(url)
    connect_args: dict[str, Any] = {}
    kept: list[tuple[str, str]] = []

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key == "sslmode":
            connect_args["ssl"] = value if value in _ASYNC_SSL_MODES else "require"
        elif key == "ssl":
            connect_args["ssl"] = value
        elif key == "application_name":
            connect_args["server_settings"] = {"application_name": value}
        elif key.lower() in _DROPPED_QUERY_PARAMS:
            logger.debug("dsn_query_param_dropped", extra={"param": key})
        else:
            kept.append((key, value))

    host = parsed.hostname or ""
    if "-pooler" in host or "pgbouncer" in host:
        # PgBouncer in transaction mode cannot guarantee a session-pinned
        # prepared statement, so disable client-side statement caching.
        connect_args["statement_cache_size"] = 0

    # ``create_async_engine`` needs the async driver named in the scheme. A
    # console-provided ``postgresql://`` DSN would otherwise resolve to the sync
    # psycopg2 driver and fail with "requires an async driver".
    scheme = parsed.scheme
    if scheme in ("postgresql", "postgres", ""):
        scheme = "postgresql+asyncpg"

    rewritten = urlunsplit(
        (scheme, parsed.netloc, parsed.path, urlencode(kept), parsed.fragment)
    )
    return rewritten, connect_args


def build_engine(
    url: Optional[str] = None,
    *,
    pool_size: Optional[int] = None,
    max_overflow: Optional[int] = None,
    search_path: Optional[str] = None,
    echo: Optional[bool] = None,
) -> AsyncEngine:
    """Create an AsyncEngine with the project's conservative pool settings."""
    dsn = url or settings.database_url
    clean_url, connect_args = prepare_async_dsn(dsn)

    schema = search_path if search_path is not None else settings.db_search_path
    if schema:
        connect_args.setdefault("server_settings", {})
        connect_args["server_settings"]["search_path"] = schema

    engine = create_async_engine(
        clean_url,
        echo=settings.db_echo if echo is None else echo,
        pool_size=settings.db_pool_size if pool_size is None else pool_size,
        max_overflow=settings.db_max_overflow if max_overflow is None else max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    logger.info(
        "engine_created",
        extra={
            "host": urlsplit(dsn).hostname,
            "pooled_endpoint": "-pooler" in (urlsplit(dsn).hostname or ""),
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "search_path": schema or "<default>",
        },
    )
    return engine


engine: AsyncEngine = build_engine()

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_session_maker


async def dispose_engine() -> None:
    await engine.dispose()
