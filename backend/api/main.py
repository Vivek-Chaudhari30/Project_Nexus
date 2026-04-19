"""
FastAPI application — entry point for Project Nexus backend.

Lifespan: opens the Postgres connection pool on startup, closes on shutdown.
Middleware: CORS (all origins for dev; tighten via env in prod) + slowapi rate limiting.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.api.routes.health import router as health_router
from backend.api.routes.sessions import router as sessions_router
from backend.api.ws.run import router as ws_router
from backend.db.postgres import close_pool, get_pool
from backend.db.redis import close_redis

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("startup: initialising Postgres connection pool")
    await get_pool()
    logger.info("startup: ready")
    yield
    logger.info("shutdown: closing Postgres pool and Redis client")
    await close_pool()
    await close_redis()


app = FastAPI(
    title="Project Nexus",
    version="0.1.0",
    description="Multi-agent orchestration platform.",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# CORS — allow all origins in dev; restrict via env/nginx in prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# RFC 7807 error handler
@app.exception_handler(404)
async def not_found(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"type": "about:blank", "title": "Not Found", "status": 404, "detail": str(exc)},
    )


# Routers
app.include_router(health_router)
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(ws_router)
