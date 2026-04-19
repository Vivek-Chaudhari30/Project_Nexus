"""
FastAPI dependency injection helpers.

get_current_user — verifies Bearer JWT and returns the user record from DB.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from backend.api.auth import decode_token
from backend.db.postgres import get_pool

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    """
    Validate the Bearer JWT and return the matching user row from Postgres.
    Raises HTTP 401 on invalid/expired token or unknown user_id.
    """
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub")

    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, created_at, is_active FROM users WHERE id = $1",
        UUID(user_id_str),
    )
    if row is None or not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return dict(row)
