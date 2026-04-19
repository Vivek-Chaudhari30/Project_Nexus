"""
rag_recall — cross-session semantic recall via Pinecone.

Embedding model : OpenAI text-embedding-3-small (1536 dims)
Embedding cache : Redis  nexus:embed_cache:{sha256(text)}  TTL 7d
Pinecone query  : namespace = user_id, filter quality_score >= 0.70, top_k = 5
"""
from __future__ import annotations

import hashlib
import json
import struct

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.db.pinecone_client import get_index
from backend.db.redis import get_redis
from backend.tools import tool

_EMBED_TTL = 7 * 24 * 3600  # 7 days
_MIN_QUALITY = 0.70
_EMBED_MODEL = "text-embedding-3-small"


def _embed_cache_key(text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return f"nexus:embed_cache:{digest}"


def _pack_vector(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack_vector(data: bytes) -> list[float]:
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


async def _embed(text: str) -> list[float]:
    """Embed text using OpenAI, with Redis caching."""
    redis = get_redis()
    cache_key = _embed_cache_key(text)

    raw = await redis.get(cache_key)
    if raw:
        # Redis returns str when decode_responses=True; fall back to re-embed
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass

    cfg = get_settings()
    client = AsyncOpenAI(api_key=cfg.openai_api_key)
    response = await client.embeddings.create(model=_EMBED_MODEL, input=text[:8000])
    vector = response.data[0].embedding

    await redis.set(cache_key, json.dumps(vector), ex=_EMBED_TTL)
    return vector


@tool
async def rag_recall(
    query: str,
    user_id: str,
    top_k: int = 5,
    session_id: str = "",  # noqa: ARG001
) -> str:
    """
    Recall the most relevant past session outputs for the current user.
    Returns up to top_k results formatted as text with quality scores.
    """
    vector = await _embed(query)
    index = get_index()

    response = index.query(  # type: ignore[union-attr]
        vector=vector,
        top_k=top_k,
        namespace=user_id,
        filter={"quality_score": {"$gte": _MIN_QUALITY}},
        include_metadata=True,
    )

    matches = response.get("matches", [])
    if not matches:
        return "No relevant past sessions found."

    lines: list[str] = []
    for match in matches:
        meta = match.get("metadata", {})
        score = round(match.get("score", 0.0), 3)
        goal = meta.get("goal", "")[:200]
        preview = meta.get("content_preview", "")[:300]
        lines.append(f"[similarity={score}] Goal: {goal}\nPreview: {preview}")

    return "\n\n".join(lines)
