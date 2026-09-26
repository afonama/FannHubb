"""Auth routes: register, login, refresh, logout, password reset, email verify."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.deps import AccessPayload, CurrentUser, DbSession
from app.core.logging_config import get_logger
from app.core.rate_limit import RateLimiter, client_ip, enforce_rate_limit
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUserRead,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
)
from app.schemas.common import MessageResponse as CommonMessage
from app.services import auth_service

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


async def limit_register(request: Request, payload: RegisterRequest) -> None:
    """Cap signups per IP and per target address."""
    await enforce_rate_limit("register", f"{client_ip(request)}|{payload.email.strip().lower()}")


async def limit_login(request: Request, payload: LoginRequest) -> None:
    """Credential-stuffing guard: per IP *and* per account."""
    await enforce_rate_limit("login", f"{client_ip(request)}|{payload.email.strip().lower()}")


async def limit_forgot_password(request: Request, payload: ForgotPasswordRequest) -> None:
    """Reset emails are the classic enumeration/abuse vector - keep it tight."""
    await enforce_rate_limit("forgot_password", f"{client_ip(request)}|{payload.email.strip().lower()}")


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Create a registered account",
    responses={409: {"description": "Email already registered"}},
)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: DbSession,
    _limit: Annotated[None, Depends(limit_register)],
) -> TokenPair:
    """Self-service signup. New accounts start as ``role=registered`` with an
    unverified email; the response already contains a usable token pair."""
    _user, tokens = await auth_service.register(db, payload)
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        max_age=60 * 60 * 24,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return tokens


@router.post("/login", response_model=TokenPair, summary="Exchange credentials for JWTs")
async def login(
    payload: LoginRequest,
    response: Response,
    db: DbSession,
    _limit: Annotated[None, Depends(limit_login)],
) -> TokenPair:
    """Returns an access token (short-lived) and a refresh token (long-lived).

    The access token is also set as an httpOnly cookie for browser clients.
    """
    _user, tokens = await auth_service.login(db, payload)
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        max_age=60 * 60 * 24,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return tokens


@router.post("/refresh", response_model=TokenPair, summary="Rotate a refresh token")
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    """Issues a new pair and revokes the presented refresh token (rotation)."""
    return await auth_service.refresh_tokens(db, payload)


@router.post("/logout", response_model=CommonMessage, summary="Revoke the current session")
async def logout(
    payload: LogoutRequest,
    db: DbSession,
    user: CurrentUser,
    access_payload: AccessPayload,
) -> CommonMessage:
    """Blacklists the access token (and optionally the refresh token) in Redis."""
    revoked = await auth_service.logout(db, user, access_payload, payload.refresh_token)
    return CommonMessage(message=f"Signed out ({revoked} token(s) revoked)")


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password reset link",
    responses={429: {"description": "Too many reset requests"}},
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: DbSession,
    _limit: Annotated[None, Depends(limit_forgot_password)],
) -> ForgotPasswordResponse:
    """Always returns 200 with an identical message, so accounts cannot be probed.

    The raw reset link is logged server-side; it is echoed in the response only
    when ``DEBUG=true`` so a demo without a mail server still works.
    """
    return await auth_service.forgot_password(db, payload.email)


@router.post("/reset-password", response_model=CommonMessage, summary="Consume a reset token")
async def reset_password(payload: ResetPasswordRequest, db: DbSession) -> CommonMessage:
    """Single-use, expiring token from the ``forgot-password`` link."""
    await auth_service.reset_password(db, payload)
    return CommonMessage(message="Password updated. You can now sign in with the new password.")


@router.post("/change-password", response_model=CommonMessage, summary="Change your own password")
async def change_password(payload: ChangePasswordRequest, db: DbSession, user: CurrentUser) -> CommonMessage:
    await auth_service.change_password(db, user, payload)
    return CommonMessage(message="Password changed")


@router.get("/verify-email/{token}", response_model=CurrentUserRead, summary="Verify an email address")
async def verify_email(token: str, db: DbSession) -> CurrentUserRead:
    """Consumes the emailed token and flips ``users.is_email_verified``."""
    user = await auth_service.verify_email(db, token)
    return CurrentUserRead.model_validate(user)


@router.post("/resend-verification", response_model=CommonMessage, summary="Resend the verification email")
async def resend_verification(db: DbSession, user: CurrentUser) -> CommonMessage:
    """Mints a fresh single-use verification token (the old one is superseded)."""
    if user.is_email_verified:
        return CommonMessage(message="Email address is already verified")
    _token, expires_at = await auth_service.issue_email_verification_token(db, user)
    logger.info("verification_email_queued", extra={"user_id": user.id, "expires_at": expires_at.isoformat()})
    return CommonMessage(message=f"Verification link generated; valid until {expires_at.isoformat()}")


@router.get("/me", response_model=CurrentUserRead, summary="Who am I?")
async def current_user(user: CurrentUser) -> CurrentUserRead:
    return CurrentUserRead.model_validate(user)
