from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from scraper.config import get_settings
from scraper.logging import get_logger

logger = get_logger("scraper.redis")

_pool: ConnectionPool | None = None
_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _pool, _redis
    if _redis is None:
        settings = get_settings().redis
        _pool = ConnectionPool.from_url(
            settings.url,
            socket_timeout=settings.socket_timeout,
            socket_connect_timeout=settings.socket_connect_timeout,
            retry_on_timeout=settings.retry_on_timeout,
            max_connections=settings.max_connections,
            health_check_interval=settings.health_check_interval,
            decode_responses=True,
        )
        _redis = aioredis.Redis(connection_pool=_pool)
        logger.info(
            "redis_client_created",
            url=settings.url.split("@")[-1] if "@" in settings.url else "local",
        )
    return _redis


async def check_redis_health() -> dict[str, Any]:
    try:
        r = get_redis()
        pong = await r.ping()
        info = await r.info("server")
        return {
            "status": "ok" if pong else "error",
            "redis_version": info.get("redis_version", "unknown"),
        }
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        return {"status": "error", "error": str(e)}


async def dispose() -> None:
    global _pool, _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None
    logger.info("redis_client_disposed")


async def set_cache(key: str, value: str, ttl: int = 300) -> None:
    r = get_redis()
    await r.setex(key, ttl, value)


async def get_cache(key: str) -> str | None:
    r = get_redis()
    return await r.get(key)


async def delete_cache(key: str) -> None:
    r = get_redis()
    await r.delete(key)
