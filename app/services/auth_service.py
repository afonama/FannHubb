"""Authentication: registration, login, refresh rotation, logout, email/password flows."""

from __future__ import annotations

import datetime as dt
from typing import Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ConflictError,
    ErrorCode,
    InvalidCredentialsError,
    NotFoundError,
    TokenError,
    UnauthenticatedError,
)
from app.core.logging_config import get_logger
from app.core.redis_client import blacklist_key, get_cache
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    password_needs_rehash,
    token_expiry,
    verify_password,
)
from app.db.models.user import AuthToken, AuthTokenPurpose, User, UserPreference, UserRole
from app.schemas.auth import (
    AccessToken,
    ChangePasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
)
from app.services import popularity_service
from app.services.user_service import fetch_user_by_email, fetch_user_by_id, get_or_create_preferences

logger = get_logger(__name__)

#: Why a password reset email was (not) sent - kept out of the HTTP response.
#: Both are constant regardless of whether the address is registered.
_FORGOT_PASSWORD_GENERIC_MESSAGE = (
    "If that email is registered, a password reset link has been generated. "
    "It was written to the server log rather than emailed; follow it from there."
)
_FORGOT_PASSWORD_NO_DELIVERY_MESSAGE = (
    "If that email is registered, the request was accepted. This deployment has "
    "no reset delivery channel configured, so no link was generated. "
    "Contact an administrator to have your password reset."
)


# ------------------------------------------------------------- token pair
async def _issue_token_pair(user: User) -> TokenPair:
    access_token, access_expires, _ = create_access_token(user.id, user.role.value)
    refresh_token, _, _ = create_refresh_token(user.id, user.role.value)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        expires_at=access_expires,
        role=user.role,
    )


async def _revoke_token_id(token_id: str, expires_at: dt.datetime) -> None:
    """Blacklist a token id in Redis for exactly its remaining lifetime."""
    cache = await get_cache()
    ttl = int((expires_at - dt.datetime.now(dt.timezone.utc)).total_seconds())
    if ttl > 0:
        await cache.set(blacklist_key(token_id), "1", ex=ttl)
        logger.info("token_revoked", extra={"jti": token_id, "ttl_seconds": ttl})


async def is_token_revoked(token_id: str) -> bool:
    cache = await get_cache()
    return await cache.exists(blacklist_key(token_id))


# ------------------------------------------------------------ registration
async def register(session: AsyncSession, payload: RegisterRequest) -> Tuple[User, TokenPair]:
    """Create a registered account and issue the first token pair."""
    email = payload.email.strip().lower()
    if await fetch_user_by_email(session, email) is not None:
        raise ConflictError("An account with that email already exists", details={"email": email})

    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role=UserRole.REGISTERED,
        is_email_verified=False,
    )
    session.add(user)
    await session.flush()

    session.add(
        UserPreference(
            user_id=user.id,
            favorite_categories=sorted({slug.strip().lower() for slug in payload.favorite_categories if slug.strip()}),
            display_prefs={},
        )
    )
    await session.commit()
    await session.refresh(user)

    await _create_auth_token(session, user.id, AuthTokenPurpose.EMAIL_VERIFY)
    await popularity_service.record_active_user(user.id)

    logger.info("user_registered", extra={"user_id": user.id, "email": email})
    return user, await _issue_token_pair(user)


# ------------------------------------------------------------------ login
async def login(session: AsyncSession, payload: LoginRequest) -> Tuple[User, TokenPair]:
    email = payload.email.strip().lower()
    user = await fetch_user_by_email(session, email)

    # Always run a hash comparison so a missing account and a wrong password
    # take a comparable amount of time (no user enumeration via timing).
    stored_hash = user.password_hash if user else hash_password("timing-equaliser")
    password_ok = verify_password(stored_hash, payload.password)

    if user is None or not password_ok:
        logger.warning("login_failed", extra={"email": email, "user_exists": user is not None})
        raise InvalidCredentialsError()

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        logger.info("password_hash_upgraded", extra={"user_id": user.id})

    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    session.add(user)
    await session.commit()

    await popularity_service.record_active_user(user.id)
    logger.info("login_succeeded", extra={"user_id": user.id, "role": user.role.value})
    return user, await _issue_token_pair(user)


# ---------------------------------------------------------------- refresh
async def refresh_tokens(session: AsyncSession, payload: RefreshRequest) -> TokenPair:
    """Rotate a refresh token: issue a new pair and revoke the presented one."""
    token_payload = decode_token(payload.refresh_token, "refresh")
    if await is_token_revoked(token_payload.token_id):
        raise TokenError("Refresh token has been revoked", code=ErrorCode.TOKEN_INVALID)

    try:
        user_id = int(token_payload.subject)
    except (TypeError, ValueError) as exc:
        raise TokenError() from exc

    user = await fetch_user_by_id(session, user_id)
    if user is None:
        raise UnauthenticatedError("Account no longer exists", code=ErrorCode.TOKEN_INVALID)

    pair = await _issue_token_pair(user)
    await _revoke_token_id(token_payload.token_id, token_payload.expires_at)
    logger.info("tokens_refreshed", extra={"user_id": user.id})
    return pair


# ----------------------------------------------------------------- logout
async def logout(
    session: AsyncSession, user: Optional[User], access_payload, refresh_token: Optional[str]
) -> int:
    """Revoke the current access token and, when supplied, a refresh token."""
    revoked = 0
    if access_payload is not None:
        await _revoke_token_id(access_payload.token_id, access_payload.expires_at)
        revoked += 1
    if refresh_token:
        try:
            refresh_payload = decode_token(refresh_token, "refresh")
        except TokenError:
            refresh_payload = None
        if refresh_payload is not None and not await is_token_revoked(refresh_payload.token_id):
            await _revoke_token_id(refresh_payload.token_id, refresh_payload.expires_at)
            revoked += 1
    logger.info("logout", extra={"user_id": getattr(user, "id", None), "revoked": revoked})
    return revoked


# ------------------------------------------------------- token validation
async def authenticate_access_token(session: AsyncSession, token: str) -> User:
    """Resolve a bearer access token to a live, non-revoked user."""
    payload = decode_token(token, "access")
    if await is_token_revoked(payload.token_id):
        raise UnauthenticatedError("Session has been revoked", code=ErrorCode.TOKEN_INVALID)

    try:
        user_id = int(payload.subject)
    except (TypeError, ValueError) as exc:
        raise TokenError() from exc

    user = await fetch_user_by_id(session, user_id)
    if user is None:
        raise UnauthenticatedError("Account no longer exists", code=ErrorCode.TOKEN_INVALID)
    return user


# ------------------------------------------------ email / password resets
async def _create_auth_token(
    session: AsyncSession,
    user_id: int,
    purpose: AuthTokenPurpose,
    expires_delta: Optional[dt.timedelta] = None,
) -> tuple[str, dt.datetime]:
    """Mint a single-use token, superseding any unconsumed token of the same purpose."""
    if purpose == AuthTokenPurpose.EMAIL_VERIFY:
        expires_delta = expires_delta or dt.timedelta(hours=settings.email_verify_token_expire_hours)
    else:
        expires_delta = expires_delta or dt.timedelta(minutes=settings.password_reset_token_expire_minutes)

    await session.execute(
        delete(AuthToken).where(AuthToken.user_id == user_id, AuthToken.purpose == purpose)
    )
    raw_token = generate_opaque_token()
    expires_at = token_expiry(expires_delta)
    session.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_opaque_token(raw_token),
            expires_at=expires_at,
        )
    )
    await session.commit()
    return raw_token, expires_at


async def issue_email_verification_token(session: AsyncSession, user: User) -> tuple[str, dt.datetime]:
    return await _create_auth_token(session, user.id, AuthTokenPurpose.EMAIL_VERIFY)


async def issue_password_reset_token(session: AsyncSession, user: User) -> tuple[str, dt.datetime]:
    return await _create_auth_token(session, user.id, AuthTokenPurpose.PASSWORD_RESET)


async def _consume_auth_token(
    session: AsyncSession, raw_token: str, purpose: AuthTokenPurpose
) -> tuple[Optional[User], Optional[AuthToken]]:
    now = dt.datetime.now(dt.timezone.utc)
    stmt = (
        select(AuthToken)
        .where(
            AuthToken.token_hash == hash_opaque_token(raw_token),
            AuthToken.purpose == purpose,
        )
        .limit(1)
    )
    token_row = (await session.execute(stmt)).scalar_one_or_none()
    if token_row is None:
        return None, None
    if token_row.used_at is not None:
        return None, None
    if token_row.expires_at < now:
        return None, token_row
    user = await fetch_user_by_id(session, token_row.user_id, with_preference=False)
    return user, token_row


async def verify_email(session: AsyncSession, raw_token: str) -> User:
    """Consume an email-verification token and flip the flag."""
    user, token_row = await _consume_auth_token(session, raw_token, AuthTokenPurpose.EMAIL_VERIFY)
    if token_row is None:
        raise NotFoundError("Verification link is invalid or has already been used")
    if user is None:
        raise NotFoundError("Verification link is invalid or has already been used")

    now = dt.datetime.now(dt.timezone.utc)
    user.is_email_verified = True
    token_row.used_at = now
    session.add_all([user, token_row])
    await session.commit()
    logger.info("email_verified", extra={"user_id": user.id})
    return user


async def forgot_password(session: AsyncSession, email: str) -> ForgotPasswordResponse:
    """Always return the same envelope so accounts cannot be enumerated.

    ``message`` and ``delivery`` come from server configuration, never from
    whether the address exists, so neither leaks account existence. When
    delivery is ``none`` no token is minted at all - returning "a link has been
    generated" while generating nothing was the original defect.
    """
    delivery = settings.password_reset_delivery
    message = (
        _FORGOT_PASSWORD_GENERIC_MESSAGE
        if delivery == "log"
        else _FORGOT_PASSWORD_NO_DELIVERY_MESSAGE
    )

    if delivery == "none":
        # Do not create a token that can never be delivered: it would leave
        # unusable rows in auth_tokens and imply a working flow that does not exist.
        logger.info("password_reset_skipped_no_delivery", extra={"delivery": delivery})
        return ForgotPasswordResponse(message=message, delivery=delivery, reset_url=None)

    user = await fetch_user_by_email(session, email)
    reset_url: Optional[str] = None

    if user is not None:
        raw_token, expires_at = await issue_password_reset_token(session, user)
        reset_url = f"{settings.public_base_url.rstrip('/')}/reset-password?token={raw_token}"
        logger.info(
            "password_reset_link_issued",
            extra={
                "user_id": user.id,
                "expires_at": expires_at.isoformat(),
                "delivery": delivery,
                "reset_url": reset_url,
            },
        )

    return ForgotPasswordResponse(
        message=message,
        delivery=delivery,
        reset_url=reset_url if settings.debug else None,
    )


async def reset_password(session: AsyncSession, payload: ResetPasswordRequest) -> User:
    """Consume a reset token, store the new hash and drop every other reset token."""
    user, token_row = await _consume_auth_token(session, payload.token, AuthTokenPurpose.PASSWORD_RESET)
    if token_row is None or user is None:
        raise NotFoundError("Reset link is invalid, expired or already used")

    now = dt.datetime.now(dt.timezone.utc)
    user.password_hash = hash_password(payload.new_password)
    token_row.used_at = now
    session.add_all([user, token_row])
    await session.execute(
        delete(AuthToken).where(
            AuthToken.user_id == user.id, AuthToken.purpose == AuthTokenPurpose.EMAIL_VERIFY
        )
    )
    await session.commit()
    logger.info("password_reset_completed", extra={"user_id": user.id})
    return user


async def change_password(session: AsyncSession, user: User, payload: ChangePasswordRequest) -> None:
    if not verify_password(user.password_hash, payload.current_password):
        raise InvalidCredentialsError("Current password is incorrect")
    if verify_password(user.password_hash, payload.new_password):
        raise ConflictError("New password must be different from the current one")

    user.password_hash = hash_password(payload.new_password)
    session.add(user)
    await session.commit()
    logger.info("password_changed", extra={"user_id": user.id})
