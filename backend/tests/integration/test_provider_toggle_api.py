"""
Integration tests for GET/POST /api/v1/config/provider-mode.

ModelRouter construction and Redis are mocked so no real LLM calls or
Redis connections are made.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.main import app
from backend.core.models import MODEL_NAMES


def _make_mock_router(mode: str = "openai_only") -> MagicMock:
    r = MagicMock()
    r.mode = mode
    r.model_names = MODEL_NAMES[mode]
    return r


# ── GET /api/v1/config/provider-mode ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_provider_mode_returns_current_mode() -> None:
    mock_router = _make_mock_router("openai_only")

    with patch("backend.core.models._router", mock_router):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/config/provider-mode")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "openai_only"
    assert data["models"]["reasoning"] == "gpt-4o"
    assert data["models"]["code"] == "gpt-4o"
    assert data["models"]["extraction"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_get_provider_mode_multi() -> None:
    mock_router = _make_mock_router("multi")

    with patch("backend.core.models._router", mock_router):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/config/provider-mode")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "multi"
    assert data["models"]["reasoning"] == "claude-sonnet-4-5"
    assert data["models"]["extraction"] == "gemini-2.5-flash-preview-04-17"


# ── POST /api/v1/config/provider-mode ────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_switches_to_multi() -> None:
    new_router = _make_mock_router("multi")
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)

    with (
        patch("backend.api.routes.config.ModelRouter", return_value=new_router),
        patch("backend.api.routes.config.set_model_router") as mock_set,
        patch("backend.api.routes.config.get_redis", return_value=redis_mock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/config/provider-mode",
                json={"mode": "multi"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "multi"
    assert data["models"]["reasoning"] == "claude-sonnet-4-5"
    mock_set.assert_called_once_with(new_router)


@pytest.mark.asyncio
async def test_post_persists_mode_to_redis() -> None:
    new_router = _make_mock_router("openai_only")
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)

    with (
        patch("backend.api.routes.config.ModelRouter", return_value=new_router),
        patch("backend.api.routes.config.set_model_router"),
        patch("backend.api.routes.config.get_redis", return_value=redis_mock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/config/provider-mode", json={"mode": "openai_only"})

    redis_mock.set.assert_called_once_with("nexus:config:provider_mode", "openai_only")


@pytest.mark.asyncio
async def test_post_invalid_mode_422() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/config/provider-mode",
            json={"mode": "grok_only"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_multi_missing_keys_returns_422() -> None:
    from backend.config import ConfigurationError

    with patch(
        "backend.api.routes.config.ModelRouter",
        side_effect=ConfigurationError(
            "PROVIDER_MODE is 'multi' but ANTHROPIC_API_KEY is not set."
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/config/provider-mode", json={"mode": "multi"})

    assert resp.status_code == 422
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_post_get_roundtrip() -> None:
    """POST to switch to multi, then GET to confirm the mode was applied."""
    new_router = _make_mock_router("multi")
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)

    with (
        patch("backend.api.routes.config.ModelRouter", return_value=new_router),
        patch("backend.api.routes.config.set_model_router"),
        patch("backend.api.routes.config.get_redis", return_value=redis_mock),
        patch("backend.core.models._router", new_router),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            post_resp = await client.post("/api/v1/config/provider-mode", json={"mode": "multi"})
            get_resp = await client.get("/api/v1/config/provider-mode")

    assert post_resp.json()["mode"] == "multi"
    assert get_resp.json()["mode"] == "multi"
