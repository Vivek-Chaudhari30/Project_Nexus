"""
Integration tests for the REST API (Phase 9).

Uses httpx.AsyncClient with FastAPI's ASGI transport so no real server is
needed. Postgres and Redis are mocked at the dependency layer so the tests
run without any containers.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.auth import create_access_token, hash_password
from backend.api.main import app

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_USER_ID = uuid4()
_SESSION_ID = uuid4()
_EMAIL = "test@nexus.dev"
_PASSWORD = "supersecretpassword123"
_PW_HASH = hash_password(_PASSWORD)


def _make_pool_mock(
    register_row: Any = None,
    login_row: Any = None,
    session_row: Any = None,
    session_list: list[Any] | None = None,
    event_list: list[Any] | None = None,
    total: int = 0,
) -> AsyncMock:
    pool = AsyncMock()

    async def _fetchrow(query: str, *args: Any) -> Any:
        q = query.strip().lower()
        if "insert into users" in q:
            return {"id": _USER_ID, "status": "pending"}
        if "select id from users where email" in q:
            return register_row
        if "select id, password_hash" in q:
            return login_row
        if "select id, email, created_at" in q:
            # me endpoint
            import datetime
            return {"id": _USER_ID, "email": _EMAIL, "created_at": datetime.datetime.now(), "is_active": True}
        if "insert into sessions" in q:
            import datetime
            return {"id": _SESSION_ID, "status": "pending", "created_at": datetime.datetime.now()}
        if "select id, goal, status" in q and "user_id" in q:
            return session_row
        return None

    async def _fetchval(query: str, *args: Any) -> Any:
        q = query.strip().lower()
        if "select 1" in q:
            return 1
        if "insert into users" in q:
            return _USER_ID
        if "select id from users where email" in q:
            return register_row
        if "select count" in q and "sessions" in q:
            return total
        if "select count" in q and "audit_log" in q:
            return total
        if "select id from sessions" in q:
            return _SESSION_ID
        return None

    async def _fetch(query: str, *args: Any) -> list[Any]:
        q = query.strip().lower()
        if "from sessions" in q:
            return session_list or []
        if "from audit_log" in q:
            return event_list or []
        return []

    pool.fetchrow = AsyncMock(side_effect=_fetchrow)
    pool.fetchval = AsyncMock(side_effect=_fetchval)
    pool.fetch = AsyncMock(side_effect=_fetch)
    pool.execute = AsyncMock(return_value="UPDATE 1")
    return pool


def _auth_headers(user_id: str | None = None) -> dict[str, str]:
    token = create_access_token(str(user_id or _USER_ID))
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Health endpoints
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_ok_when_deps_up() -> None:
    pool_mock = _make_pool_mock()
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)

    with (
        patch("backend.api.routes.health.get_pool", AsyncMock(return_value=pool_mock)),
        patch("backend.api.routes.health.get_redis", return_value=redis_mock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_ready_503_when_postgres_down() -> None:
    pool_mock = AsyncMock()
    pool_mock.fetchval = AsyncMock(side_effect=ConnectionError("db down"))
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)

    with (
        patch("backend.api.routes.health.get_pool", AsyncMock(return_value=pool_mock)),
        patch("backend.api.routes.health.get_redis", return_value=redis_mock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["postgres"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# Auth: register
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_creates_user() -> None:
    pool_mock = _make_pool_mock(register_row=None)  # email not taken

    with patch("backend.api.routes.sessions.get_pool", AsyncMock(return_value=pool_mock)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/register",
                json={"email": _EMAIL, "password": _PASSWORD},
            )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_short_password_rejected() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": _EMAIL, "password": "short"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_duplicate_email_409() -> None:
    pool_mock = _make_pool_mock(register_row={"id": _USER_ID})  # email already taken

    with patch("backend.api.routes.sessions.get_pool", AsyncMock(return_value=pool_mock)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/register",
                json={"email": _EMAIL, "password": _PASSWORD},
            )
    assert resp.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# Auth: login
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_returns_token() -> None:
    login_row = {"id": _USER_ID, "password_hash": _PW_HASH, "is_active": True}
    pool_mock = _make_pool_mock(login_row=login_row)

    with patch("backend.api.routes.sessions.get_pool", AsyncMock(return_value=pool_mock)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": _EMAIL, "password": _PASSWORD},
            )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password_401() -> None:
    login_row = {"id": _USER_ID, "password_hash": _PW_HASH, "is_active": True}
    pool_mock = _make_pool_mock(login_row=login_row)

    with patch("backend.api.routes.sessions.get_pool", AsyncMock(return_value=pool_mock)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": _EMAIL, "password": "wrongpassword999"},
            )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Auth: /me
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_returns_profile() -> None:
    pool_mock = _make_pool_mock()

    with (
        patch("backend.api.routes.sessions.get_pool", AsyncMock(return_value=pool_mock)),
        patch("backend.api.deps.get_pool", AsyncMock(return_value=pool_mock)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/me", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["email"] == _EMAIL


@pytest.mark.asyncio
async def test_me_without_token_401() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401  # HTTPBearer returns 401 when no credentials


# ─────────────────────────────────────────────────────────────────────────────
# Sessions: create + get
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session_returns_session_id() -> None:
    pool_mock = _make_pool_mock()

    with (
        patch("backend.api.routes.sessions.get_pool", AsyncMock(return_value=pool_mock)),
        patch("backend.api.deps.get_pool", AsyncMock(return_value=pool_mock)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/sessions",
                json={"goal": "Research the latest LLM benchmarks"},
                headers=_auth_headers(),
            )
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_session_goal_too_long_422() -> None:
    pool_mock = _make_pool_mock()
    with patch("backend.api.deps.get_pool", AsyncMock(return_value=pool_mock)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/sessions",
                json={"goal": "x" * 4001},
                headers=_auth_headers(),
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_session_not_found_404() -> None:
    pool_mock = _make_pool_mock(session_row=None)

    with (
        patch("backend.api.routes.sessions.get_pool", AsyncMock(return_value=pool_mock)),
        patch("backend.api.deps.get_pool", AsyncMock(return_value=pool_mock)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/sessions/{uuid4()}",
                headers=_auth_headers(),
            )
    assert resp.status_code == 404
