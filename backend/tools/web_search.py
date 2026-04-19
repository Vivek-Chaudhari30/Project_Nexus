"""
web_search — Tavily wrapper with Redis result cache.

Redis key: nexus:tool_cache:web_search:{sha256(query)}  TTL 1h
Returns: newline-separated "title: snippet (source: url)" strings.
"""
from __future__ import annotations

import hashlib

from tavily import AsyncTavilyClient

from backend.config import get_settings
from backend.db.redis import get_redis
from backend.tools import tool

_TTL_SECONDS = 3600  # 1 hour


def _cache_key(query: str) -> str:
    digest = hashlib.sha256(query.encode()).hexdigest()
    return f"nexus:tool_cache:web_search:{digest}"


def _format_results(results: list[dict]) -> str:  # type: ignore[type-arg]
    lines: list[str] = []
    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")[:400]
        url = r.get("url", "")
        lines.append(f"{title}: {content} (source: {url})")
    return "\n".join(lines) if lines else "No results found."


@tool
async def web_search(query: str, session_id: str = "", max_results: int = 5) -> str:  # noqa: ARG001
    """Search the web via Tavily and return summarised results. Results are cached for 1 hour."""
    redis = get_redis()
    cache_key = _cache_key(query)

    cached = await redis.get(cache_key)
    if cached:
        return str(cached)

    cfg = get_settings()
    client = AsyncTavilyClient(api_key=cfg.tavily_api_key)
    response = await client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
        include_raw_content=False,
    )
    results: list[dict] = response.get("results", [])  # type: ignore[type-arg]
    formatted = _format_results(results)

    await redis.set(cache_key, formatted, ex=_TTL_SECONDS)
    return formatted
