"""Uniform API error envelope + the exception types that produce it.

Every failure the API returns has the identical shape:

    {
      "status_code": 404,
      "code": "NOT_FOUND",
      "message": "content 42 not found",
      "details": {...} | null,
      "request_id": "0f3c...",
      "timestamp": "2026-09-25T10:00:00+00:00"
    }
"""

from __future__ import annotations

import enum
from typing import Any, Optional

from fastapi import status


class ErrorCode(str, enum.Enum):
    """Stable, machine-readable error identifiers for the frontend team."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    TOKEN_MISSING = "AUTH_TOKEN_MISSING"
    TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    EMAIL_NOT_VERIFIED = "AUTH_EMAIL_NOT_VERIFIED"
    UNAUTHENTICATED = "AUTH_REQUIRED"
    FORBIDDEN = "AUTH_FORBIDDEN"
    INSUFFICIENT_ROLE = "AUTH_INSUFFICIENT_ROLE"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_DISABLED = "SERVICE_DISABLED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for every expected (non-500) failure."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    default_message: str = "Unexpected server error"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        code: Optional[ErrorCode] = None,
        status_code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        self.headers = headers or {}
        super().__init__(self.message)


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = ErrorCode.VALIDATION_ERROR
    default_message = "Request payload failed validation"


class InvalidCredentialsError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.INVALID_CREDENTIALS
    default_message = "Incorrect email or password"


class TokenError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.TOKEN_INVALID
    default_message = "Invalid or malformed token"


class TokenExpiredError(TokenError):
    code = ErrorCode.TOKEN_EXPIRED
    default_message = "Token has expired"


class UnauthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.UNAUTHENTICATED
    default_message = "Authentication required"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = ErrorCode.FORBIDDEN
    default_message = "You do not have access to this resource"


class InsufficientRoleError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = ErrorCode.INSUFFICIENT_ROLE
    default_message = "This action requires a higher privilege level"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.NOT_FOUND
    default_message = "Resource not found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.CONFLICT
    default_message = "Resource conflict"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = ErrorCode.RATE_LIMITED
    default_message = "Too many requests"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        retry_after: int = 60,
        scope: Optional[str] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        headers = kwargs.pop("headers", None) or {}
        headers.setdefault("Retry-After", str(retry_after))
        details = kwargs.pop("details", None) or {}
        details.update({"retry_after": retry_after, "scope": scope, "limit": limit})
        super().__init__(message, headers=headers, details=details, **kwargs)


class ServiceDisabledError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = ErrorCode.SERVICE_DISABLED
    default_message = "This feature is currently disabled"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = ErrorCode.SERVICE_UNAVAILABLE
    default_message = "Upstream dependency unavailable"


#: Default code for non-AppError responses raised by Starlette/FastAPI.
HTTP_STATUS_TO_CODE: dict[int, ErrorCode] = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHENTICATED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.VALIDATION_ERROR,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: ErrorCode.PAYLOAD_TOO_LARGE,
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    status.HTTP_422_UNPROCESSABLE_ENTITY: ErrorCode.VALIDATION_ERROR,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}


def code_for_status(status_code: int) -> ErrorCode:
    return HTTP_STATUS_TO_CODE.get(status_code, ErrorCode.INTERNAL_ERROR)
