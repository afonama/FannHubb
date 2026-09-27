"""FastAPI dependencies: DB session, pagination, and the three auth tiers.

The tiers are deliberately three separate callables so a route's access level is
readable from its signature:

    get_current_user_optional   Visitor may call, JWT is a bonus  -> User | None
    get_current_user_required   Registered tier                -> User (401 otherwise)
    require_admin               Admin tier                      -> User (401/403 otherwise)
"""

from __future__ import annotations

from typing import Annotated, AsyncIterator, Optional

from fastapi import Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import InsufficientRoleError, UnauthenticatedError
from app.core.logging_config import get_logger
from app.db.models.user import User, UserRole
from app.db.session import async_session_maker
from app.schemas.common import PageParams
from app.core.security import TokenPayload
from app.services import auth_service

logger = get_logger(__name__)


# ------------------------------------------------------------------- db
async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request; services own their commits, errors roll back."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


DbSession = Annotated[AsyncSession, Depends(get_db)]


# ------------------------------------------------------------ pagination
def get_pagination(
    page: Annotated[int, Query(ge=1, le=10_000, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page (max 100)")] = 20,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


Pagination = Annotated[PageParams, Depends(get_pagination)]


# ------------------------------------------------------------------ auth
# The OAuth2 scheme is kept as a real dependency so /docs renders the Authorize
# button; the wrapper below adds an httpOnly-cookie fallback for browser clients.
bearer_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=False,
    description="JWT access token",
)


async def get_access_token(
    request: Request,
    header_token: Annotated[Optional[str], Depends(bearer_scheme)],
) -> Optional[str]:
    """Resolve the access token from the ``Authorization`` header or a cookie.

    Note this is a plain function rather than a callable class on purpose:
    FastAPI resolves annotation strings via ``call.__globals__``, which a class
    *instance* does not have.
    """
    if header_token:
        return header_token.strip()
    cookie = request.cookies.get("access_token")
    return cookie.strip() if cookie else None


AccessTokenStr = Annotated[Optional[str], Depends(get_access_token)]


async def _resolve_principal(
    request: Request, token: Optional[str], db: AsyncSession
) -> tuple[Optional[User], Optional[TokenPayload]]:
    """Decode + validate an access token, caching the result on ``request.state``.

    The cache matters when a route declares both ``CurrentUser`` and
    ``AccessPayload``: the token is verified (and its Redis blacklist checked)
    exactly once per request.
    """
    cached_user = getattr(request.state, "current_user", None)
    if cached_user is not None and hasattr(request.state, "access_payload"):
        return cached_user, request.state.access_payload

    from app.core.security import decode_token

    payload = decode_token(token, "access")
    user = await auth_service.authenticate_access_token(db, token)
    request.state.current_user = user
    # Snapshot the id as a plain int *now*, while the instance is still loaded.
    # ``get_db`` rolls the session back on any error, and ``Session.rollback()``
    # expires every instance in the identity map; re-reading ``user.id`` after
    # that point raises DetachedInstanceError. Anything that needs the id later
    # (access logs, rate-limit identities) must use this scalar instead.
    request.state.current_user_id = user.id
    request.state.access_payload = payload
    return user, payload


async def get_current_user_optional(
    request: Request,
    token: AccessTokenStr,
    db: DbSession,
) -> Optional[User]:
    """Visitor tier: ``None`` when unauthenticated, a ``User`` when a valid JWT is sent.

    A *present but invalid* token still raises 401 - silently downgrading to
    anonymous would hide client bugs and revoked-session mistakes.
    """
    if not token:
        return None
    user, _ = await _resolve_principal(request, token, db)
    return user


async def get_current_user_required(
    request: Request,
    token: AccessTokenStr,
    db: DbSession,
) -> User:
    """Registered tier: 401 when no valid access token is present."""
    if not token:
        raise UnauthenticatedError(
            "This endpoint requires a registered account. Send 'Authorization: Bearer <access_token>'."
        )
    user, _ = await _resolve_principal(request, token, db)
    return user


async def require_admin(
    request: Request,
    token: AccessTokenStr,
    db: DbSession,
) -> User:
    """Admin tier: 401 without a token, 403 without ``role=admin``."""
    if not token:
        raise UnauthenticatedError("Admin endpoints require authentication")
    user, _ = await _resolve_principal(request, token, db)
    if user.role != UserRole.ADMIN:
        logger.warning(
            "admin_access_denied",
            extra={"user_id": user.id, "role": user.role.value, "path": request.url.path},
        )
        raise InsufficientRoleError("This endpoint is restricted to administrators")
    return user


def get_access_payload(request: Request) -> TokenPayload:
    """The decoded access token for the current request (set by the auth deps)."""
    payload = getattr(request.state, "access_payload", None)
    if payload is None:
        raise UnauthenticatedError("No authenticated request context")
    return payload


async def require_verified_email(
    user: Annotated[User, Depends(get_current_user_required)],
) -> User:
    """Extra gate for actions that need a confirmed address."""
    from app.core.errors import AppError, ErrorCode

    if not user.is_email_verified:
        raise AppError(
            "Please verify your email address before using this feature",
            code=ErrorCode.EMAIL_NOT_VERIFIED,
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user_required)]
OptionalUser = Annotated[Optional[User], Depends(get_current_user_optional)]
AdminUser = Annotated[User, Depends(require_admin)]
AccessPayload = Annotated[TokenPayload, Depends(get_access_payload)]
