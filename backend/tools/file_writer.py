"""
file_writer — scoped filesystem writes for sandbox-generated artefacts.

All writes are confined to /tmp/nexus/workspace/{session_id}/.
Path traversal attempts raise PermissionError.
"""
from __future__ import annotations

from pathlib import Path

from backend.tools import tool

_WORKSPACE_ROOT = Path("/tmp/nexus/workspace")


def _safe_path(session_id: str, relative_path: str) -> Path:
    """Resolve and validate that the target path stays within the session workspace."""
    workspace = (_WORKSPACE_ROOT / session_id).resolve()
    target = (workspace / relative_path).resolve()
    if not str(target).startswith(str(workspace)):
        raise PermissionError(
            f"Path traversal blocked: {relative_path!r} escapes workspace {workspace}"
        )
    return target


@tool
async def file_write(session_id: str, relative_path: str, content: str) -> str:
    """Write content to a file inside the session workspace. Creates parent dirs as needed."""
    target = _safe_path(session_id, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {target}"


@tool
async def file_read(session_id: str, relative_path: str) -> str:
    """Read a file from the session workspace."""
    target = _safe_path(session_id, relative_path)
    if not target.exists():
        return f"File not found: {relative_path}"
    return target.read_text(encoding="utf-8")
