"""
Integration test conftest — stubs the Postgres pool and Redis client so
the FastAPI lifespan does not attempt real network connections.

Individual tests that need specific DB behaviour override get_pool() in
their own patch context.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _stub_db_connections():
    """Prevent real Postgres/Redis connections during all integration tests."""
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=1)
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock(return_value="UPDATE 0")

    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)

    with (
        patch("backend.db.postgres.get_pool", AsyncMock(return_value=pool)),
        patch("backend.db.postgres._pool", pool),
        patch("backend.db.redis.get_redis", return_value=redis),
        patch("backend.db.redis._client", redis),
    ):
        yield
