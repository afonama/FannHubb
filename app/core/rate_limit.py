"""Redis-backed fixed-window rate limiting for abuse-prone public endpoints.

Used as a FastAPI dependency:  ``dependencies=[RateLimiter.for_endpoint("login")]``

The counter is an ``INCR`` on ``fanhub:rl:<scope>:<identity>`` with the window TTL
applied on first hit, which keeps the operation to a single round trip. Identities
combine client IP with the authenticated user id (when present) so a shared NAT
does not punish unrelated visitors, while a single abusive client is still capped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
from fastapi import Request

from app.core.config import settings
from app.core.errors import RateLimitedError
from app.core.logging_config import get_logger
from app.core.redis_client import get_cache, rate_limit_key

logger = get_logger(__name__)


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    limit: int
    window_seconds: int

    @classmethod
    def for_endpoint(cls, endpoint: str) -> "RateLimitRule":
        return cls(
            scope=endpoint,
            limit=getattr(settings, f"rate_limit_{endpoint}"),
            window_seconds=getattr(settings, f"rate_limit_{endpoint}_window"),
        )


def client_ip(request: Request) -> str:
    """Best-effort client IP, honouring a single proxy hop when present."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _identity(request: Request) -> str:
    """Client IP plus the authenticated user id when there is one."""
    user = getattr(request.state, "current_user", None)
    user_id = getattr(user, "id", None)
    return f"{client_ip(request)}|u{user_id}" if user_id else client_ip(request)


class RateLimiter:
    """Fixed-window quota checker for one endpoint scope."""

    def __init__(self, rule: RateLimitRule) -> None:
        self.rule = rule

    @classmethod
    def for_endpoint(cls, endpoint: str) -> "RateLimiter":
        return cls(RateLimitRule.for_endpoint(endpoint))

    async def check(self, identity: str) -> Optional[int]:
        """Consume one unit of quota; return ``None`` when allowed, else retry-after."""
        cache = await get_cache()
        key = rate_limit_key(self.rule.scope, identity)
        count = await cache.incr(key, 1, ex=self.rule.window_seconds)
        if count > self.rule.limit:
            ttl = await cache.ttl(key)
            return max(1, ttl if ttl and ttl > 0 else self.rule.window_seconds)
        return None

    async def enforce(self, identity: str) -> None:
        """Raise :class:`RateLimitedError` when ``identity`` is over quota."""
        if not settings.rate_limit_enabled:
            return
        retry_after = await self.check(identity)
        if retry_after is not None:
            logger.warning(
                "rate_limit_exceeded",
                extra={"scope": self.rule.scope, "identity": identity, "limit": self.rule.limit},
            )
            raise RateLimitedError(
                f"Too many {self.rule.scope.replace('_', ' ')} attempts. Try again in {retry_after}s.",
                retry_after=retry_after,
                scope=self.rule.scope,
                limit=self.rule.limit,
            )

    async def __call__(self, request: Request) -> None:
        await self.enforce(client_ip(request))


def for_endpoint(endpoint: str) -> Callable[[Request], Awaitable[None]]:
    """Build a FastAPI dependency enforcing ``endpoint``'s quota per client IP.

    Returns a plain function rather than the class instance on purpose: FastAPI
    resolves *string* annotations through ``call.__globals__``, which a class
    instance does not expose (and this module uses PEP 563 annotations).
    """

    async def _rate_limit_dependency(request: Request) -> None:
        await RateLimiter(RateLimitRule.for_endpoint(endpoint)).enforce(client_ip(request))

    _rate_limit_dependency.__name__ = f"rate_limit_{endpoint}"
    return _rate_limit_dependency


async def enforce_rate_limit(scope: str, identity: str) -> None:
    """One-shot helper for endpoints that need a custom identity (e.g. IP + email)."""
    await RateLimiter(RateLimitRule.for_endpoint(scope)).enforce(identity)
