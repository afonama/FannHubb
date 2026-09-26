"""Cache abstraction used for rate limiting, token blacklisting and counters.

Redis (redis.asyncio) is the production backend. If ``REDIS_URL`` is unset or
unreachable the app transparently falls back to a process-local implementation
with the same semantics, so a demo laptop without Redis still boots. Which
backend is active is reported by ``GET /health`` and logged at startup.

Key layout (all prefixed with ``fanhub:``):
    rl:<scope>:<identity>            fixed-window rate-limit counter
    bl:jti:<token-id>                revoked access/refresh token marker
    views:content:<id>               pending view-count delta (INCR)
    views:character:<id>             pending view-count delta (INCR)
    views:merchandise:<id>           pending view-count delta (INCR)
    stats:active_users:<yyyy-mm-dd>  daily active-user counter
    stats:category:<slug>            category browse counter
    stats:chatbot:<yyyy-mm-dd>       chatbot interaction volume
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional, Protocol

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

KEY_PREFIX = "fanhub"


class CacheBackend(Protocol):
    """Minimal surface every backend implements."""

    kind: str

    async def ping(self) -> bool: ...
    async def get(self, key: str) -> Optional[str]: ...
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None: ...
    async def delete(self, *keys: str) -> int: ...
    async def exists(self, key: str) -> bool: ...
    async def incr(self, key: str, amount: int = 1, ex: Optional[int] = None) -> int: ...
    async def mget(self, keys: list[str]) -> list[Optional[str]]: ...
    async def ttl(self, key: str) -> int: ...
    async def scan_keys(self, pattern: str) -> list[str]: ...
    async def setnx(self, key: str, value: str, ex: Optional[int] = None) -> bool: ...
    async def rename(self, src: str, dst: str) -> bool: ...
    async def close(self) -> None: ...


class RedisCache:
    """Production backend: a single connection pool of Redis commands."""

    kind = "redis"

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: aioredis.Redis = aioredis.from_url(
            url,
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_connect_timeout,
            health_check_interval=30,
        )

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def get(self, key: str) -> Optional[str]:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        await self._client.set(key, value, ex=ex)

    async def delete(self, *keys: str) -> int:
        return int(await self._client.delete(*keys)) if keys else 0

    async def exists(self, key: str) -> bool:
        return bool(await self._client.exists(key))

    async def incr(self, key: str, amount: int = 1, ex: Optional[int] = None) -> int:
        pipe = self._client.pipeline()
        pipe.incrby(key, amount)
        if ex is not None:
            pipe.expire(key, ex, nx=True)
        results = await pipe.execute()
        return int(results[0])

    async def mget(self, keys: list[str]) -> list[Optional[str]]:
        if not keys:
            return []
        return list(await self._client.mget(keys))

    async def ttl(self, key: str) -> int:
        return int(await self._client.ttl(key))

    async def scan_keys(self, pattern: str) -> list[str]:
        found: list[str] = []
        cursor = 0
        while True:
            cursor, batch = await self._client.scan(cursor=cursor, match=pattern, count=500)
            found.extend(batch)
            if cursor == 0:
                break
        return found

    async def setnx(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        return bool(await self._client.set(key, value, ex=ex, nx=True))

    async def rename(self, src: str, dst: str) -> bool:
        """Atomically move a key; False when the source no longer exists.

        The flush job relies on this: views recorded while a flush is in flight
        create a brand-new counter and are picked up by the next cycle.
        """
        try:
            return bool(await self._client.rename(src, dst))
        except aioredis.ResponseError as exc:
            if "no such key" in str(exc).lower():
                return False
            raise

    async def close(self) -> None:
        await self._client.aclose()


class InMemoryCache:
    """Fallback backend with TTL semantics, used when Redis is unavailable.

    Not shared across processes/restarts - adequate for single-process dev and
    for the test suite, never for production (where REDIS_URL is required).
    """

    kind = "memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    def _sweep(self, now: float) -> None:
        expired = [k for k, (exp, _) in self._data.items() if exp and exp <= now]
        for key in expired:
            self._data.pop(key, None)

    def _read(self, key: str, now: float) -> Optional[str]:
        entry = self._data.get(key)
        if entry is None:
            return None
        exp, value = entry
        if exp and exp <= now:
            self._data.pop(key, None)
            return None
        return value

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            return self._read(key, time.monotonic())

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        async with self._lock:
            now = time.monotonic()
            self._sweep(now)
            self._data[key] = (now + ex if ex else 0.0, str(value))

    async def delete(self, *keys: str) -> int:
        async with self._lock:
            return sum(1 for key in keys if self._data.pop(key, None) is not None)

    async def exists(self, key: str) -> bool:
        async with self._lock:
            return self._read(key, time.monotonic()) is not None

    async def incr(self, key: str, amount: int = 1, ex: Optional[int] = None) -> int:
        async with self._lock:
            now = time.monotonic()
            self._sweep(now)
            current = int(self._read(key, now) or 0) + amount
            existing_expiry = self._data.get(key, (0.0, ""))[0]
            expiry = existing_expiry or (now + ex if ex else 0.0)
            self._data[key] = (expiry, str(current))
            return current

    async def mget(self, keys: list[str]) -> list[Optional[str]]:
        async with self._lock:
            now = time.monotonic()
            return [self._read(key, now) for key in keys]

    async def ttl(self, key: str) -> int:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return -2
            exp, _ = entry
            if not exp:
                return -1
            return max(0, int(exp - time.monotonic()))

    async def scan_keys(self, pattern: str) -> list[str]:
        prefix = pattern.rstrip("*")
        async with self._lock:
            self._sweep(time.monotonic())
            return [key for key in self._data if key.startswith(prefix)]

    async def setnx(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        async with self._lock:
            now = time.monotonic()
            self._sweep(now)
            if self._read(key, now) is not None:
                return False
            self._data[key] = (now + ex if ex else 0.0, str(value))
            return True

    async def rename(self, src: str, dst: str) -> bool:
        async with self._lock:
            now = time.monotonic()
            value = self._read(src, now)
            if value is None:
                return False
            expiry = self._data.get(src, (0.0, ""))[0]
            self._data.pop(src, None)
            self._data[dst] = (expiry, value)
            return True

    async def close(self) -> None:
        async with self._lock:
            self._data.clear()


_cache: Optional[CacheBackend] = None
_cache_lock = asyncio.Lock()


async def get_cache() -> CacheBackend:
    """Return the process-wide cache backend, choosing Redis when reachable."""
    global _cache
    if _cache is not None:
        return _cache
    async with _cache_lock:
        if _cache is not None:
            return _cache
        if settings.redis_configured:
            candidate = RedisCache(settings.redis_url.strip())
            try:
                if await candidate.ping():
                    _cache = candidate
                    logger.info("cache_backend_selected", extra={"backend": "redis"})
                    return _cache
                await candidate.close()
            except Exception as exc:  # noqa: BLE001 - degrade, never crash boot
                logger.warning(
                    "redis_unavailable_using_memory_fallback",
                    extra={"error": str(exc), "error_type": type(exc).__name__},
                )
        _cache = InMemoryCache()
        logger.info("cache_backend_selected", extra={"backend": "memory"})
        return _cache


def set_cache(backend: CacheBackend) -> None:
    """Override the backend (used by the test suite)."""
    global _cache
    _cache = backend


async def reset_cache() -> None:
    global _cache
    if _cache is not None:
        await _cache.close()
    _cache = None


def cache_key(*parts: object) -> str:
    """Build a namespaced key: ``fanhub:<part>:<part>``."""
    return ":".join([KEY_PREFIX, *(str(part) for part in parts)])


# ------------------------------------------------------- domain-level keys
def view_counter_key(entity: str, entity_id: int) -> str:
    return cache_key("views", entity, entity_id)


def blacklist_key(token_id: str) -> str:
    return cache_key("bl", "jti", token_id)


def rate_limit_key(scope: str, identity: str) -> str:
    return cache_key("rl", scope, identity)


def stats_key(name: str, *parts: object) -> str:
    return cache_key("stats", name, *parts) if parts else cache_key("stats", name)
