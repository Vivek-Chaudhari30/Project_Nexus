"""Shared pytest fixtures — Phase 2 baseline (db/redis mocked until Phase 7)."""
from __future__ import annotations

import os

# Inject minimal env vars so Settings() validates in unit/integration tests
# that don't boot real containers.
_TEST_ENV = {
    "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "ANTHROPIC_API_KEY": "test-anthropic",
    "OPENAI_API_KEY": "test-openai",
    "GOOGLE_API_KEY": "test-google",
    "TAVILY_API_KEY": "test-tavily",
    "PINECONE_API_KEY": "test-pinecone",
    "JWT_SECRET": "test-jwt-secret-that-is-long-enough-for-hs256",
}

for _k, _v in _TEST_ENV.items():
    os.environ.setdefault(_k, _v)

# Clear lru_cache so Settings() re-reads the vars we just set above.
from backend.config import get_settings  # noqa: E402

get_settings.cache_clear()
