"""
Loop detector — prevents the orchestrator from replanning in circles.

Uses a Redis SET per session (TTL 1h) to track SHA-256 hashes of the
task_plan produced by each Planner invocation. If the same plan hash
appears twice the session is marked loop_detected and exits.

Redis key: nexus:loop_detector:{session_id}
"""
from __future__ import annotations

import hashlib
import json
import logging

import redis.asyncio as redis

from backend.config import get_settings
from backend.core.state import TaskNode

logger = logging.getLogger(__name__)

_TTL_SECONDS = 3600  # 1 hour


def _plan_hash(task_plan: list[TaskNode]) -> str:
    """Stable SHA-256 of the task plan, order-independent by task id."""
    normalised = sorted(
        (
            {
                "id": t["id"],
                "description": t["description"],
                "depends_on": sorted(t.get("depends_on") or []),
                "assigned_model": t.get("assigned_model", ""),
            }
        )
        for t in task_plan
    ),
    payload = json.dumps(normalised, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


class LoopDetector:
    """
    Per-session loop detector backed by Redis.

    check(task_plan) returns True if this plan was seen before (loop),
    False if it is new (adds the hash to the set).
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._key = f"nexus:loop_detector:{session_id}"

    async def check(self, task_plan: list[TaskNode]) -> bool:
        """Return True if loop detected, False (and record hash) otherwise."""
        plan_hash = _plan_hash(task_plan)
        cfg = get_settings()
        client: redis.Redis = redis.from_url(str(cfg.redis_url), decode_responses=True)
        try:
            async with client:
                # SADD returns 0 if the member already existed
                added = await client.sadd(self._key, plan_hash)
                await client.expire(self._key, _TTL_SECONDS)
                if added == 0:
                    logger.warning(
                        "loop_detector: duplicate plan hash=%s session=%s",
                        plan_hash[:12],
                        self._session_id,
                    )
                    return True
                return False
        except Exception as exc:
            # Redis failure → log and allow the pipeline to continue; a
            # missed loop detection is less harmful than aborting a session.
            logger.error("loop_detector: Redis error: %s", exc)
            return False
