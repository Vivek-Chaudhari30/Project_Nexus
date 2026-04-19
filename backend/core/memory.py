"""
Memory layer — unified interface over Redis, Postgres, and Pinecone.

Two public functions:
  store_if_good(state, output) — upserts to Pinecone only if quality >= 0.70
  recall_for_user(user_id, goal, top_k=5) — semantic search, scoped by user

Embedding model: text-embedding-3-small (1536 dims, matches Pinecone index).
Embedding cache: Redis nexus:embed_cache:{sha256} TTL 7 days.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.core.state import MemoryItem, NexusState
from backend.db.pinecone_client import get_index
from backend.db.redis import get_redis

logger = logging.getLogger(__name__)

_QUALITY_WRITE_THRESHOLD = 0.70
_EMBED_MODEL = "text-embedding-3-small"
_EMBED_CACHE_TTL = 7 * 24 * 3600  # 7 days
_OUTPUT_KEYWORDS: dict[str, list[str]] = {
    "code": ["def ", "class ", "import ", "```python", "```js"],
    "research": ["according to", "study", "research", "found that", "evidence"],
    "analysis": ["analysis", "breakdown", "compare", "contrast", "evaluate"],
    "writing": ["introduction", "conclusion", "paragraph", "essay", "draft"],
}


def _classify_output_type(output: str) -> str:
    lower = output.lower()
    for output_type, keywords in _OUTPUT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return output_type
    return "mixed"


async def _embed(text: str) -> list[float]:
    """Return the embedding vector for text, using Redis as a 7-day cache."""
    cache_key = f"nexus:embed_cache:{hashlib.sha256(text.encode()).hexdigest()}"
    redis = get_redis()

    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("memory: redis embed cache read failed: %s", exc)

    cfg = get_settings()
    client = AsyncOpenAI(api_key=cfg.openai_api_key)
    response = await client.embeddings.create(model=_EMBED_MODEL, input=text)
    vector: list[float] = response.data[0].embedding

    try:
        await redis.set(cache_key, json.dumps(vector), ex=_EMBED_CACHE_TTL)
    except Exception as exc:
        logger.warning("memory: redis embed cache write failed: %s", exc)

    return vector


async def store_if_good(state: NexusState, output: str) -> None:
    """
    Upsert this session's output to Pinecone if final quality >= 0.70.

    Vector ID is the session_id (one vector per session, last-write-wins
    for retries). Namespace is user_id so recall is always user-scoped.
    """
    quality = state.get("quality_score") or 0.0
    if quality < _QUALITY_WRITE_THRESHOLD:
        logger.debug(
            "memory: skipping store quality=%.3f < threshold=%.2f",
            quality,
            _QUALITY_WRITE_THRESHOLD,
        )
        return

    session_id = state.get("session_id") or ""
    user_id = state.get("user_id") or ""
    goal = (state.get("user_goal") or "")[:500]
    content_preview = output[:300]
    output_type = _classify_output_type(output)

    embed_input = goal + "\n\n" + output[:2000]
    try:
        vector = await _embed(embed_input)
    except Exception as exc:
        logger.error("memory: embedding failed for session=%s: %s", session_id, exc)
        return

    metadata: dict[str, Any] = {
        "session_id": session_id,
        "user_id": user_id,
        "created_at": int(time.time()),
        "goal": goal,
        "output_type": output_type,
        "quality_score": quality,
        "content_preview": content_preview,
    }

    try:
        index = get_index()
        index.upsert(
            vectors=[{"id": session_id, "values": vector, "metadata": metadata}],
            namespace=user_id,
        )
        logger.info(
            "memory: stored session=%s quality=%.3f type=%s",
            session_id,
            quality,
            output_type,
        )
    except Exception as exc:
        logger.error("memory: Pinecone upsert failed session=%s: %s", session_id, exc)


async def recall_for_user(
    user_id: str,
    goal: str,
    top_k: int = 5,
) -> list[MemoryItem]:
    """
    Query Pinecone for the top_k most relevant past sessions for this user.

    Filters: namespace=user_id, metadata quality_score >= 0.70.
    Returns an empty list on any error so callers always get a safe result.
    """
    try:
        vector = await _embed(goal)
    except Exception as exc:
        logger.error("memory: embedding failed for recall user=%s: %s", user_id, exc)
        return []

    try:
        index = get_index()
        results = index.query(
            vector=vector,
            top_k=top_k,
            namespace=user_id,
            filter={"quality_score": {"$gte": _QUALITY_WRITE_THRESHOLD}},
            include_metadata=True,
        )
    except Exception as exc:
        logger.error("memory: Pinecone query failed user=%s: %s", user_id, exc)
        return []

    items: list[MemoryItem] = []
    for match in results.get("matches") or []:
        meta = match.get("metadata") or {}
        items.append(
            MemoryItem(
                session_id=meta.get("session_id", ""),
                goal=meta.get("goal", ""),
                quality_score=float(meta.get("quality_score", 0.0)),
                content_preview=meta.get("content_preview", ""),
                output_type=meta.get("output_type", "mixed"),
            )
        )

    logger.debug(
        "memory: recalled %d items for user=%s", len(items), user_id
    )
    return items
