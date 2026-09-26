"""Password hashing (argon2id) and JWT issuing/verification (PyJWT)."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import TokenError, TokenExpiredError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

TokenType = Literal["access", "refresh", "email_verify", "password_reset"]

# OWASP-recommended argon2id parameters: 64 MiB memory, 3 iterations, 4 lanes.
_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


# --------------------------------------------------------------- passwords
def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _password_hasher.hash(plain_password)


def verify_password(password_hash: str, plain_password: str) -> bool:
    """Constant-time-ish verification; never raises on malformed input."""
    if not password_hash or not plain_password:
        return False
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when a stored hash was produced with weaker parameters."""
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, VerificationError):
        return True


# -------------------------------------------------------------------- JWT
@dataclass(frozen=True)
class TokenPayload:
    subject: str
    token_id: str
    token_type: str
    issued_at: datetime
    expires_at: datetime
    role: Optional[str] = None
    raw_claims: dict[str, Any] | None = None


def _build_claims(
    subject: str | int,
    token_type: TokenType,
    expires_delta: timedelta,
    role: Optional[str] = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": str(subject),
        "jti": uuid.uuid4().hex,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "iss": settings.jwt_issuer,
    }
    if role:
        claims["role"] = role
    return claims


def create_token(
    subject: str | int,
    token_type: TokenType,
    expires_delta: timedelta,
    role: Optional[str] = None,
) -> tuple[str, datetime, str]:
    """Return ``(encoded_jwt, expires_at, jti)`` for the given token type."""
    claims = _build_claims(subject, token_type, expires_delta, role)
    encoded = jwt.encode(
        claims,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return encoded, datetime.fromtimestamp(claims["exp"], tz=timezone.utc), claims["jti"]


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    """Verify signature/expiry/type and return the payload.

    Raises :class:`TokenExpiredError` or :class:`TokenError`; never leaks the
    underlying jwt exception internals to the client.
    """
    if not token or not token.strip():
        raise TokenError("Token is empty")
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "jti", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.InvalidTokenError as exc:
        logger.warning("token_rejected", extra={"reason": type(exc).__name__})
        raise TokenError() from exc

    if claims.get("typ") != expected_type:
        raise TokenError(f"Expected a {expected_type} token")

    return TokenPayload(
        subject=str(claims["sub"]),
        token_id=claims["jti"],
        token_type=claims["typ"],
        issued_at=datetime.fromtimestamp(claims["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        role=claims.get("role"),
        raw_claims=claims,
    )


def create_access_token(subject: str | int, role: str) -> tuple[str, datetime, str]:
    return create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        role=role,
    )


def create_refresh_token(subject: str | int, role: str) -> tuple[str, datetime, str]:
    return create_token(
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        role=role,
    )


# ------------------------------------------------- opaque one-time tokens
def generate_opaque_token(nbytes: int = 32) -> str:
    """URL-safe random token for email-verification / password-reset links."""
    return secrets.token_urlsafe(nbytes)


def hash_opaque_token(token: str) -> str:
    """Deterministic digest so a stolen DB dump cannot reset anyone's account."""
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiry(expires_delta: timedelta) -> datetime:
    return datetime.now(timezone.utc) + expires_delta
