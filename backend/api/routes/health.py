"""Health, readiness, and metrics endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from backend.db.postgres import get_pool
from backend.db.redis import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> JSONResponse:
    """Liveness probe — always 200 if the process is up."""
    return JSONResponse({"status": "ok"})


@router.get("/ready")
async def ready() -> JSONResponse:
    """
    Readiness probe — checks Postgres and Redis connectivity.
    Returns 503 if either is unreachable.
    """
    checks: dict[str, str] = {}
    ok = True

    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.error("ready: postgres check failed: %s", exc)
        checks["postgres"] = "error"
        ok = False

    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error("ready: redis check failed: %s", exc)
        checks["redis"] = "error"
        ok = False

    status_code = 200 if ok else 503
    return JSONResponse({"status": "ready" if ok else "degraded", "checks": checks}, status_code=status_code)


@router.get("/metrics")
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint — restrict at ingress in production."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
