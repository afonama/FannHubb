"""Auth request/response schemas."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.db.models.user import UserRole
from app.schemas.common import ORMModel

Password = Annotated[str, Field(min_length=8, max_length=128)]


def _validate_password_strength(value: str) -> str:
    if not any(c.isalpha() for c in value):
        raise ValueError("password must contain at least one letter")
    if not any(c.isdigit() for c in value):
        raise ValueError("password must contain at least one digit")
    return value


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80, examples=["Yuki Tanaka"])
    email: EmailStr = Field(examples=["yuki@fanhubplus.dev"])
    password: Password = Field(examples=["User@12345"])
    favorite_categories: list[str] = Field(
        default_factory=list, max_length=8, description="Category slugs, e.g. ['anime','gaming']"
    )

    @field_validator("password")
    @classmethod
    def _strong_enough(cls, value: str) -> str:
        return _validate_password_strength(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenPair(BaseModel):
    """JWT pair returned by register / login / refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds")
    expires_at: dt.datetime
    role: UserRole


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: dt.datetime


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Always the same shape, whether or not the address exists (no enumeration)."""

    message: str
    delivery: Literal["log", "none"] = Field(
        description=(
            "How the link is delivered, from server config. Constant for every "
            "caller, so it cannot be used to probe whether an account exists."
        )
    )
    reset_url: str | None = Field(
        default=None,
        description="Populated only when DEBUG=true so local testers can follow the link",
    )


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: Password

    @field_validator("new_password")
    @classmethod
    def _strong_enough(cls, value: str) -> str:
        return _validate_password_strength(value)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(
        default=None, description="Optional: revoke this refresh token too"
    )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password

    @field_validator("new_password")
    @classmethod
    def _strong_enough(cls, value: str) -> str:
        return _validate_password_strength(value)


class EmailVerificationTokenResponse(BaseModel):
    token: str | None = Field(
        default=None, description="Only returned when DEBUG=true (no mail server in dev)"
    )
    verify_url: str | None = None
    message: str


class CurrentUserRead(ORMModel):
    id: int
    name: str
    email: EmailStr
    avatar_url: str | None
    role: UserRole
    is_email_verified: bool
    created_at: dt.datetime
