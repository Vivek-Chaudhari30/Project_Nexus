"""Pydantic request/response models for the Project Nexus API."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=12, max_length=128)


class RegisterResponse(BaseModel):
    user_id: UUID
    email: str
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class UserProfile(BaseModel):
    user_id: UUID
    email: str
    created_at: datetime


# ── Sessions ─────────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=4000)


class CreateSessionResponse(BaseModel):
    session_id: UUID
    status: str
    created_at: datetime


class Citation(BaseModel):
    url: str
    title: str
    snippet: str


class SessionDetail(BaseModel):
    session_id: UUID
    goal: str
    status: str
    iteration_count: int
    final_quality: float | None
    final_output: dict[str, Any] | None
    citations: list[Citation] = []
    created_at: datetime
    completed_at: datetime | None


class SessionListItem(BaseModel):
    session_id: UUID
    goal: str
    status: str
    final_quality: float | None
    created_at: datetime


class SessionList(BaseModel):
    items: list[SessionListItem]
    total: int
    limit: int
    offset: int


# ── Audit / Events ───────────────────────────────────────────────────────────

class EventRecord(BaseModel):
    id: int
    agent_name: str
    iteration: int
    model_used: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    error: str | None
    created_at: datetime


class EventList(BaseModel):
    items: list[EventRecord]
    total: int
    limit: int
    offset: int


# ── Problem Details (RFC 7807) ────────────────────────────────────────────────

class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
