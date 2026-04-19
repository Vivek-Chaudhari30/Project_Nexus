"""
Tests for Settings startup validation (CHANGE 2).

ConfigurationError is raised when PROVIDER_MODE=multi and required
provider keys are absent. Tests control os.environ directly because
pydantic-settings reads from the process environment, not constructor kwargs.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from backend.config import ConfigurationError, Settings

# Complete minimal env that satisfies all non-optional fields
_BASE: dict[str, str] = {
    "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "OPENAI_API_KEY": "sk-test",
    "TAVILY_API_KEY": "tvly-test",
    "PINECONE_API_KEY": "pcsk-test",
    "JWT_SECRET": "test-jwt-secret-that-is-long-enough-for-hs256",
}


def _settings(extra: dict[str, str]) -> Settings:
    """Create Settings with a clean environment (ignores real .env)."""
    env = {**_BASE, **extra}
    with patch.dict(os.environ, env, clear=True):
        return Settings(_env_file=None)  # type: ignore[call-arg]


class TestOpenAIOnlyValidation:
    def test_boots_without_anthropic_key(self) -> None:
        _settings({"PROVIDER_MODE": "openai_only"})  # must not raise

    def test_boots_without_google_key(self) -> None:
        _settings({"PROVIDER_MODE": "openai_only"})  # must not raise

    def test_boots_with_only_openai_key(self) -> None:
        s = _settings({"PROVIDER_MODE": "openai_only"})
        assert s.provider_mode == "openai_only"
        assert s.anthropic_api_key is None
        assert s.google_api_key is None

    def test_default_mode_is_openai_only(self) -> None:
        # No PROVIDER_MODE in env → defaults to openai_only
        s = _settings({})
        assert s.provider_mode == "openai_only"


class TestMultiProviderValidation:
    def test_raises_when_anthropic_key_missing(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            _settings({"PROVIDER_MODE": "multi", "GOOGLE_API_KEY": "AIza-test"})

        msg = str(exc_info.value)
        assert "ANTHROPIC_API_KEY" in msg
        assert "PROVIDER_MODE" in msg
        assert "openai_only" in msg

    def test_raises_when_google_key_missing(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            _settings({"PROVIDER_MODE": "multi", "ANTHROPIC_API_KEY": "sk-ant-test"})

        assert "GOOGLE_API_KEY" in str(exc_info.value)

    def test_raises_when_both_keys_missing(self) -> None:
        with pytest.raises(ConfigurationError):
            _settings({"PROVIDER_MODE": "multi"})

    def test_boots_when_all_keys_present(self) -> None:
        s = _settings({
            "PROVIDER_MODE": "multi",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "GOOGLE_API_KEY": "AIza-test",
        })
        assert s.provider_mode == "multi"
        assert s.anthropic_api_key == "sk-ant-test"
        assert s.google_api_key == "AIza-test"

    def test_error_message_is_actionable(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            _settings({"PROVIDER_MODE": "multi", "ANTHROPIC_API_KEY": "sk-ant-test"})
        assert "Either set the key" in str(exc_info.value)
