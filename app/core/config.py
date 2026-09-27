"""Application settings, loaded strictly from the environment / .env file.

Every knob the app needs (database DSN, JWT secret, CORS allow-list, Redis,
chatbot toggle, rate limits, scheduler cadence) lives here. Nothing in this
module contains a hardcoded credential or environment-specific URL.
"""

from __future__ import annotations

import functools
from typing import Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration (12-factor style)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ app
    app_name: str = "Fan Hub Plus"
    app_version: str = "1.0.0"
    app_env: Literal["local", "dev", "staging", "prod"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True
    log_level: str = "INFO"
    log_json: bool = True

    # ------------------------------------------------------------- database
    # Neon serverless Postgres. Use the *pooled* connection string (hostname
    # contains "-pooler") for runtime traffic. Never commit this value.
    database_url: str = Field(
        ...,
        description="SQLAlchemy async DSN, e.g. postgresql+asyncpg://user:pw@ep-x-pooler.region.neon.tech/db?sslmode=require",
    )
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 900
    db_echo: bool = False
    db_search_path: str = Field(
        default="",
        description="Optional schema search_path override (used by the test suite).",
    )

    # ---------------------------------------------------------------- redis
    redis_url: str = Field(
        default="",
        description="redis:// or rediss:// URL. Empty => in-process fallback cache.",
    )
    redis_enabled: bool = True
    redis_socket_timeout: float = 1.0
    redis_connect_timeout: float = 1.0

    # ------------------------------------------------------------------ jwt
    jwt_secret_key: SecretStr = Field(
        ..., description="Signing secret for access/refresh tokens (min 32 chars in prod)."
    )
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "fan-hub-plus"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    email_verify_token_expire_hours: int = 48
    password_reset_token_expire_minutes: int = 30
    # How a reset link reaches the user. "log" writes it to the application log
    # (development only - the operator hands it over); "none" generates nothing and
    # the API says so, instead of implying a link was sent. No mail transport is
    # wired up yet; see README "Password reset".
    password_reset_delivery: Literal["log", "none"] = "log"

    # ----------------------------------------------------------------- cors
    # Comma-separated list, e.g. "http://localhost:5173,https://fanhub.example.com"
    cors_origins: str = ""
    cors_allow_credentials: bool = True

    # ------------------------------------------------------------- chatbot
    chatbot_enabled: bool = True
    chatbot_provider: Literal["rules", "llm"] = "rules"
    chatbot_llm_api_key: SecretStr = SecretStr("")
    chatbot_llm_base_url: str = "https://api.openai.com/v1"
    chatbot_llm_model: str = "gpt-4o-mini"
    chatbot_max_message_length: int = 2000
    chatbot_session_ttl_hours: int = 24

    # --------------------------------------------------------- rate limits
    rate_limit_enabled: bool = True
    rate_limit_register: int = 5
    rate_limit_register_window: int = 900
    rate_limit_login: int = 5
    rate_limit_login_window: int = 300
    rate_limit_forgot_password: int = 3
    rate_limit_forgot_password_window: int = 900
    rate_limit_feedback: int = 5
    rate_limit_feedback_window: int = 3600
    rate_limit_chatbot: int = 20
    rate_limit_chatbot_window: int = 300

    # ---------------------------------------------------------------- media
    media_root: str = "media"
    media_max_upload_bytes: int = 5 * 1024 * 1024
    public_base_url: str = "http://localhost:8000"

    # ------------------------------------------------------------ scheduler
    # APScheduler flushes Redis view/popularity deltas into Postgres.
    scheduler_enabled: bool = True
    popularity_flush_interval_seconds: int = 60

    # ----------------------------------------------------------------- seed
    seed_admin_email: str = "admin@fanhubplus.dev"
    seed_admin_password: str = "Admin@12345"
    seed_user_emails: str = "yuki@fanhubplus.dev,marcus@fanhubplus.dev,priya@fanhubplus.dev"
    seed_user_password: str = "User@12345"

    # ---------------------------------------------------------- validators
    @field_validator("database_url")
    @classmethod
    def _require_async_pg(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("DATABASE_URL is empty")
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql://", 1)
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the asyncpg driver "
                "(postgresql+asyncpg://user:pass@host/db?sslmode=require)"
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    # --------------------------------------------------------- properties
    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins parsed from the comma-separated env value."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def redis_configured(self) -> bool:
        return bool(self.redis_enabled and self.redis_url.strip())

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    @property
    def seed_user_email_list(self) -> list[str]:
        return [item.strip() for item in self.seed_user_emails.split(",") if item.strip()]

    def validate_runtime(self) -> None:
        """Fail fast on insecure production configuration."""
        if not self.is_production:
            return
        if len(self.jwt_secret_key.get_secret_value()) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters in production")
        if "*" in self.cors_origin_list:
            raise RuntimeError("CORS_ORIGINS must not be '*' in production")
        if self.password_reset_delivery == "log":
            # Not fatal - a demo may still need to boot - but reset tokens are
            # single-use credentials, and writing them to production logs is how
            # they end up in a log aggregator. Wire a real transport and set
            # PASSWORD_RESET_DELIVERY=none before going live.
            import logging

            logging.getLogger(__name__).warning(
                "password_reset_delivery_is_log_in_production",
                extra={"hint": "set PASSWORD_RESET_DELIVERY=none once a mail transport exists"},
            )


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton (env is read once per process)."""
    settings = Settings()
    settings.validate_runtime()
    return settings


settings = get_settings()
