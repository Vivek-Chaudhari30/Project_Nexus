"""
Integration tests for the gRPC sandbox (Phase 6).

Requires the sandbox container to be running:
    docker compose -f infra/docker-compose.yml --profile full up -d sandbox

These tests are skipped automatically if the sandbox is unreachable.
"""
from __future__ import annotations

import os

import grpc
import pytest

from backend.tools.code_executor import SandboxResult, execute_code

_SANDBOX_URL = os.getenv("SANDBOX_URL", "localhost:50051")


def _sandbox_available() -> bool:
    try:
        channel = grpc.insecure_channel(_SANDBOX_URL)
        grpc.channel_ready_future(channel).result(timeout=2)
        return True
    except grpc.FutureTimeoutError:
        return False


pytestmark = pytest.mark.skipif(
    not _sandbox_available(),
    reason="Sandbox container not reachable at SANDBOX_URL",
)


@pytest.mark.asyncio
async def test_simple_print_returns_stdout() -> None:
    result: SandboxResult = await execute_code(
        code="print(1 + 1)",
        timeout=10,
        task_id="integration-add",
    )
    assert result.success is True
    assert result.stdout.strip() == "2"
    assert result.exit_code == 0
    assert result.wall_ms >= 0


@pytest.mark.asyncio
async def test_infinite_loop_times_out() -> None:
    result: SandboxResult = await execute_code(
        code="while True: pass",
        timeout=5,
        task_id="integration-timeout",
    )
    assert result.success is False
    assert result.exit_code != 0
