"""
JWT issue/verify and bcrypt password hashing.

Architecture rule: all auth logic lives here. Routes must not call jose or
bcrypt directly.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import jwt

from backend.config import get_settings

_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Return a bcrypt hash of password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(_BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if password matches the stored bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: str) -> str:
    """Create a signed JWT with exp = now + jwt_expiry_seconds."""
    cfg = get_settings()
    payload: dict[str, Any] = {
        "sub": user_id,
        "exp": datetime.now(UTC) + timedelta(seconds=cfg.jwt_expiry_seconds),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT. Raises jose.JWTError on invalid/expired tokens.
    Callers should convert JWTError to HTTP 401.
    """
    cfg = get_settings()
    return jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])  # type: ignore[return-value]
