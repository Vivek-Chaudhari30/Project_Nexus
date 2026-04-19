"""
All REST endpoints for Project Nexus per Section 6 of the build spec.

Auth endpoints:   POST /auth/register, POST /auth/login, GET /auth/me
Session endpoints: POST/GET /sessions, GET/DELETE /sessions/{id},
                   POST /sessions/{id}/abort, GET /sessions/{id}/events
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.auth import (
    create_access_token,
    hash_password,
    verify_password,
)
from backend.api.deps import get_current_user
from backend.api.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    EventList,
    EventRecord,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    SessionDetail,
    SessionList,
    SessionListItem,
    UserProfile,
)
from backend.db.postgres import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Auth ─────────────────────────────────────────────────────────────────────

@router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest) -> RegisterResponse:
    pool = await get_pool()
    existing = await pool.fetchval("SELECT id FROM users WHERE email = $1", body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    pw_hash = hash_password(body.password)
    user_id: UUID = await pool.fetchval(
        "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id",
        body.email,
        pw_hash,
    )
    token = create_access_token(str(user_id))
    return RegisterResponse(user_id=user_id, email=body.email, access_token=token)


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, password_hash, is_active FROM users WHERE email = $1", body.email
    )
    if row is None or not row["is_active"] or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    await pool.execute(
        "UPDATE users SET last_login_at = now() WHERE id = $1", row["id"]
    )
    token = create_access_token(str(row["id"]))
    return LoginResponse(access_token=token)


@router.get("/auth/me", response_model=UserProfile)
async def me(user: dict[str, Any] = Depends(get_current_user)) -> UserProfile:
    return UserProfile(
        user_id=user["id"],
        email=user["email"],
        created_at=user["created_at"],
    )


# ── Sessions ─────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> CreateSessionResponse:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO sessions (user_id, goal, status)
        VALUES ($1, $2, 'pending')
        RETURNING id, status, created_at
        """,
        user["id"],
        body.goal,
    )
    return CreateSessionResponse(
        session_id=row["id"],
        status=row["status"],
        created_at=row["created_at"],
    )


@router.get("/sessions", response_model=SessionList)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(get_current_user),
) -> SessionList:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, goal, status, final_quality, created_at
        FROM sessions
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        user["id"],
        limit,
        offset,
    )
    total: int = await pool.fetchval(
        "SELECT COUNT(*) FROM sessions WHERE user_id = $1", user["id"]
    )
    return SessionList(
        items=[
            SessionListItem(
                session_id=r["id"],
                goal=r["goal"],
                status=r["status"],
                final_quality=r["final_quality"],
                created_at=r["created_at"],
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
) -> SessionDetail:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, goal, status, iteration_count, final_quality, final_output,
               created_at, completed_at
        FROM sessions
        WHERE id = $1 AND user_id = $2
        """,
        session_id,
        user["id"],
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return SessionDetail(
        session_id=row["id"],
        goal=row["goal"],
        status=row["status"],
        iteration_count=row["iteration_count"],
        final_quality=row["final_quality"],
        final_output=row["final_output"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
) -> None:
    pool = await get_pool()
    result = await pool.execute(
        "UPDATE sessions SET status = 'aborted' WHERE id = $1 AND user_id = $2",
        session_id,
        user["id"],
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")


@router.post("/sessions/{session_id}/abort", status_code=status.HTTP_202_ACCEPTED)
async def abort_session(
    session_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT status FROM sessions WHERE id = $1 AND user_id = $2",
        session_id,
        user["id"],
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if row["status"] not in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already {row['status']}",
        )
    await pool.execute(
        "UPDATE sessions SET status = 'aborted' WHERE id = $1",
        session_id,
    )
    return {"detail": "abort requested"}


@router.get("/sessions/{session_id}/events", response_model=EventList)
async def session_events(
    session_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(get_current_user),
) -> EventList:
    pool = await get_pool()
    # Verify ownership
    owned = await pool.fetchval(
        "SELECT id FROM sessions WHERE id = $1 AND user_id = $2", session_id, user["id"]
    )
    if owned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    rows = await pool.fetch(
        """
        SELECT id, agent_name, iteration, model_used, tokens_in, tokens_out,
               latency_ms, error, created_at
        FROM audit_log
        WHERE session_id = $1
        ORDER BY created_at ASC
        LIMIT $2 OFFSET $3
        """,
        session_id,
        limit,
        offset,
    )
    total: int = await pool.fetchval(
        "SELECT COUNT(*) FROM audit_log WHERE session_id = $1", session_id
    )
    return EventList(
        items=[EventRecord(**dict(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
