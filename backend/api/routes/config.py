"""
Provider mode toggle API.

GET  /api/v1/config/provider-mode  — returns current mode + model assignments
POST /api/v1/config/provider-mode  — hot-swaps the ModelRouter; persists to Redis
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.core.models import MODEL_NAMES, ModelRouter, get_model_router, set_model_router
from backend.db.redis import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])

_REDIS_KEY = "nexus:config:provider_mode"


class ProviderModeResponse(BaseModel):
    mode: Literal["multi", "openai_only"]
    models: dict[str, str]


class ProviderModeRequest(BaseModel):
    mode: Literal["multi", "openai_only"]


@router.get("/config/provider-mode", response_model=ProviderModeResponse)
async def get_provider_mode() -> ProviderModeResponse:
    r = get_model_router()
    return ProviderModeResponse(mode=r.mode, models=r.model_names)


@router.post("/config/provider-mode", response_model=ProviderModeResponse)
async def update_provider_mode(body: ProviderModeRequest) -> ProviderModeResponse:
    from backend.config import ConfigurationError

    try:
        new_router = ModelRouter(mode=body.mode)
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.error("Failed to build ModelRouter for mode=%s: %s", body.mode, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    set_model_router(new_router)

    try:
        redis = get_redis()
        await redis.set(_REDIS_KEY, body.mode)
    except Exception as exc:
        logger.warning("Failed to persist provider_mode to Redis: %s", exc)

    logger.info("provider_mode switched to %s", body.mode)
    return ProviderModeResponse(mode=new_router.mode, models=new_router.model_names)
