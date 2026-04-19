"""
code_executor — gRPC client to the Nexus sandbox container.

Replaces the Phase 5 local subprocess stub in backend/agents/executor.py.

Architecture rule (CLAUDE.md #6): Never execute LLM-generated code outside
the sandbox container. This module is the ONLY path to code execution.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import grpc

from backend.config import get_settings

# Generated stubs (committed alongside executor.proto)
from backend.tools import executor_pb2, executor_pb2_grpc, tool

logger = logging.getLogger(__name__)

_HARD_TIMEOUT_SECONDS = 30
_STDOUT_MAX = 5_000
_STDERR_MAX = 2_000

# Module-level channel — reused across calls (gRPC channels are thread-safe)
_channel: grpc.Channel | None = None
_stub: executor_pb2_grpc.ExecutorStub | None = None


def _get_stub() -> executor_pb2_grpc.ExecutorStub:
    global _channel, _stub
    if _stub is None:
        cfg = get_settings()
        _channel = grpc.insecure_channel(cfg.sandbox_url)
        _stub = executor_pb2_grpc.ExecutorStub(_channel)
    return _stub


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    wall_ms: int


async def execute_code(
    code: str,
    timeout: int = _HARD_TIMEOUT_SECONDS,
    task_id: str = "",
) -> SandboxResult:
    """
    Send code to the sandbox gRPC server and await the result.

    Raises grpc.RpcError on transport failures (caller appends to error_log).
    """
    timeout = min(timeout, _HARD_TIMEOUT_SECONDS)
    stub = _get_stub()

    request = executor_pb2.ExecuteRequest(
        code=code,
        timeout_seconds=timeout,
        task_id=task_id,
    )

    t0 = time.monotonic()
    try:
        # gRPC unary call with a deadline slightly beyond the code timeout
        response: executor_pb2.ExecuteResponse = stub.Execute(
            request,
            timeout=timeout + 5,  # extra 5s for gRPC overhead
        )
        wall_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            "sandbox: task=%s success=%s exit=%d wall_ms=%d",
            task_id, response.success, response.exit_code, wall_ms,
        )
        return SandboxResult(
            success=response.success,
            stdout=response.stdout[:_STDOUT_MAX],
            stderr=response.stderr[:_STDERR_MAX],
            exit_code=response.exit_code,
            wall_ms=response.wall_ms or wall_ms,
        )

    except grpc.RpcError as exc:
        wall_ms = int((time.monotonic() - t0) * 1000)
        code_name = exc.code().name if hasattr(exc, "code") else "UNKNOWN"
        detail = exc.details() if hasattr(exc, "details") else str(exc)
        logger.error("sandbox gRPC error task=%s code=%s detail=%s", task_id, code_name, detail)
        return SandboxResult(
            success=False,
            stdout="",
            stderr=f"sandbox gRPC error [{code_name}]: {detail}"[:_STDERR_MAX],
            exit_code=-1,
            wall_ms=wall_ms,
        )


@tool
async def code_exec(code: str, task_id: str = "", session_id: str = "") -> str:  # noqa: ARG001
    """Execute Python code in the sandbox and return stdout (or error message)."""
    result = await execute_code(code=code, task_id=task_id)
    if result.success:
        return result.stdout
    return f"Error (exit {result.exit_code}): {result.stderr}"
