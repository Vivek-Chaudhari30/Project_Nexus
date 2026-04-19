from __future__ import annotations

import redis.asyncio as aioredis

from backend.config import get_settings

_client: aioredis.Redis | None = None  # type: ignore[type-arg]


def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            str(settings.redis_url),
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
