"""
api_caller — generic async HTTP tool with basic schema validation.

Supports GET / POST / PUT / DELETE. Timeouts after 30s.
Response bodies are truncated to 8 000 chars before returning.
"""
from __future__ import annotations

from typing import Any

import httpx

from backend.tools import tool

_TIMEOUT = 30.0
_MAX_RESPONSE_CHARS = 8_000
_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


@tool
async def api_caller(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    session_id: str = "",  # noqa: ARG001  — for audit logging in future phases
) -> str:
    """Make an HTTP request and return the response as a string."""
    method = method.upper()
    if method not in _ALLOWED_METHODS:
        return f"Error: method {method!r} not allowed. Use one of {sorted(_ALLOWED_METHODS)}."

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers or {},
                json=body,
            )
        text = response.text[:_MAX_RESPONSE_CHARS]
        return f"HTTP {response.status_code}\n{text}"
    except httpx.TimeoutException:
        return f"Error: request to {url!r} timed out after {_TIMEOUT}s"
    except httpx.RequestError as exc:
        return f"Error: request failed — {exc}"
