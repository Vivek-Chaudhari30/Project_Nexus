"""
Nexus sandbox gRPC server.

Receives Python source over gRPC, executes in an isolated subprocess
with hard resource limits, returns stdout/stderr/exit_code.

Security layers (enforced by the container, not here):
  - iptables egress allowlist (see iptables-setup.sh)
  - read-only root filesystem, 128MB /tmp tmpfs
  - non-root user (uid 1000)
  - no pip / build tools in the image
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
import time
from concurrent import futures

import grpc

# Proto-generated stubs (co-located in this container's /app)
sys.path.insert(0, "/app")
import executor_pb2
import executor_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_STDOUT_MAX = 5_000
_STDERR_MAX = 2_000
_HARD_TIMEOUT = 30  # seconds, absolute ceiling regardless of request value


class ExecutorServicer(executor_pb2_grpc.ExecutorServicer):
    def Execute(
        self,
        request: executor_pb2.ExecuteRequest,
        context: grpc.ServicerContext,
    ) -> executor_pb2.ExecuteResponse:
        timeout = min(request.timeout_seconds or _HARD_TIMEOUT, _HARD_TIMEOUT)
        task_id = request.task_id or "unknown"
        code = request.code

        logger.info("execute task_id=%s timeout=%ds len(code)=%d", task_id, timeout, len(code))

        result = _run_code(code, timeout)

        logger.info(
            "execute task_id=%s success=%s exit=%d wall_ms=%d",
            task_id, result["success"], result["exit_code"], result["wall_ms"],
        )
        return executor_pb2.ExecuteResponse(
            success=result["success"],
            stdout=result["stdout"][:_STDOUT_MAX],
            stderr=result["stderr"][:_STDERR_MAX],
            exit_code=result["exit_code"],
            wall_ms=result["wall_ms"],
        )


def _run_code(code: str, timeout: int) -> dict:  # type: ignore[type-arg]
    """Execute code in a subprocess. Returns a result dict."""
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", dir="/tmp", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        script_path = f.name

    t0 = time.monotonic()
    try:
        import subprocess
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = proc.communicate(timeout=timeout)
            success = proc.returncode == 0
            exit_code = proc.returncode
            stderr_text = stderr_b.decode(errors="replace")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"timeout after {timeout}s",
                "exit_code": -1,
                "wall_ms": int((time.monotonic() - t0) * 1000),
            }
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc)[:_STDERR_MAX],
            "exit_code": -1,
            "wall_ms": int((time.monotonic() - t0) * 1000),
        }

    return {
        "success": success,
        "stdout": stdout_b.decode(errors="replace"),
        "stderr": stderr_text,
        "exit_code": exit_code,
        "wall_ms": int((time.monotonic() - t0) * 1000),
    }


def serve() -> None:
    port = int(os.environ.get("SANDBOX_GRPC_PORT", "50051"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    executor_pb2_grpc.add_ExecutorServicer_to_server(ExecutorServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("sandbox gRPC server listening on :%d", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
