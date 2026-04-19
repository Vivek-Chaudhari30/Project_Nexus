"""
Integration tests for the memory layer (Phase 8).

All external I/O (OpenAI embeddings, Redis, Pinecone) is mocked so the
tests run without any containers or API keys.

Scenario: two sessions with related goals. The second session should
receive a MemoryItem from the first via recall_for_user(), and that item
should be injected into the Planner context (via build_planner_context).
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.memory import recall_for_user, store_if_good
from backend.core.state import NexusState, initial_state

_DUMMY_VECTOR = [0.1] * 1536


def _make_redis_mock(cache_hit: bool = False) -> AsyncMock:
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=json.dumps(_DUMMY_VECTOR) if cache_hit else None)
    mock.set = AsyncMock(return_value=True)
    return mock


def _make_pinecone_index_mock(stored_items: list[dict] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.upsert = MagicMock()
    mock.query = MagicMock(
        return_value={
            "matches": [
                {
                    "id": item["session_id"],
                    "score": 0.95,
                    "metadata": item,
                }
                for item in (stored_items or [])
            ]
        }
    )
    return mock


def _make_openai_mock() -> AsyncMock:
    embedding_mock = MagicMock()
    embedding_mock.embedding = _DUMMY_VECTOR
    response_mock = MagicMock()
    response_mock.data = [embedding_mock]
    client_mock = AsyncMock()
    client_mock.embeddings.create = AsyncMock(return_value=response_mock)
    return client_mock


# ─────────────────────────────────────────────────────────────────────────────
# store_if_good
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_store_skipped_below_quality_threshold() -> None:
    """Quality 0.65 < 0.70 → Pinecone upsert must NOT be called."""
    state: NexusState = initial_state("goal", str(uuid.uuid4()), "user-1")
    state["quality_score"] = 0.65

    pinecone_index = _make_pinecone_index_mock()
    with patch("backend.core.memory.get_index", return_value=pinecone_index):
        await store_if_good(state, "some output")

    pinecone_index.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_store_upserts_above_quality_threshold() -> None:
    """Quality 0.85 >= 0.70 → Pinecone upsert called with correct metadata."""
    session_id = str(uuid.uuid4())
    user_id = "user-store"
    state: NexusState = initial_state("Build a recommendation engine", session_id, user_id)
    state["quality_score"] = 0.85

    pinecone_index = _make_pinecone_index_mock()
    redis_mock = _make_redis_mock(cache_hit=False)
    openai_mock = _make_openai_mock()

    with (
        patch("backend.core.memory.get_redis", return_value=redis_mock),
        patch("backend.core.memory.AsyncOpenAI", return_value=openai_mock),
        patch("backend.core.memory.get_index", return_value=pinecone_index),
        patch("backend.core.memory.get_settings") as mock_cfg,
    ):
        mock_cfg.return_value.openai_api_key = "test-key"
        await store_if_good(state, "Here is the recommendation system output...")

    pinecone_index.upsert.assert_called_once()
    call_args = pinecone_index.upsert.call_args
    vectors = call_args.kwargs.get("vectors") or call_args.args[0]
    assert len(vectors) == 1
    vec = vectors[0]
    assert vec["id"] == session_id
    meta = vec["metadata"]
    assert meta["user_id"] == user_id
    assert meta["quality_score"] == 0.85
    assert meta["session_id"] == session_id
    assert meta["goal"] == "Build a recommendation engine"
    assert len(meta["content_preview"]) <= 300


@pytest.mark.asyncio
async def test_store_uses_redis_cache_for_embedding() -> None:
    """Second store call with same text hits Redis cache, skips OpenAI."""
    session_id = str(uuid.uuid4())
    state: NexusState = initial_state("goal", session_id, "user-cache")
    state["quality_score"] = 0.80

    redis_mock = _make_redis_mock(cache_hit=True)  # cache returns vector
    openai_mock = _make_openai_mock()
    pinecone_index = _make_pinecone_index_mock()

    with (
        patch("backend.core.memory.get_redis", return_value=redis_mock),
        patch("backend.core.memory.AsyncOpenAI", return_value=openai_mock),
        patch("backend.core.memory.get_index", return_value=pinecone_index),
        patch("backend.core.memory.get_settings") as mock_cfg,
    ):
        mock_cfg.return_value.openai_api_key = "test-key"
        await store_if_good(state, "output text")

    # OpenAI embeddings should NOT have been called (cache hit)
    openai_mock.embeddings.create.assert_not_called()
    pinecone_index.upsert.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# recall_for_user
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recall_returns_memory_items() -> None:
    """recall_for_user returns MemoryItem list from Pinecone matches."""
    stored_session_id = str(uuid.uuid4())
    stored_items = [
        {
            "session_id": stored_session_id,
            "user_id": "user-recall",
            "created_at": 1_700_000_000,
            "goal": "Build a recommendation engine",
            "output_type": "code",
            "quality_score": 0.87,
            "content_preview": "def recommend(user_id): ...",
        }
    ]

    redis_mock = _make_redis_mock(cache_hit=False)
    openai_mock = _make_openai_mock()
    pinecone_index = _make_pinecone_index_mock(stored_items)

    with (
        patch("backend.core.memory.get_redis", return_value=redis_mock),
        patch("backend.core.memory.AsyncOpenAI", return_value=openai_mock),
        patch("backend.core.memory.get_index", return_value=pinecone_index),
        patch("backend.core.memory.get_settings") as mock_cfg,
    ):
        mock_cfg.return_value.openai_api_key = "test-key"
        items = await recall_for_user("user-recall", "recommendation system", top_k=5)

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, dict)
    assert item["session_id"] == stored_session_id
    assert item["quality_score"] == 0.87
    assert item["goal"] == "Build a recommendation engine"
    assert item["output_type"] == "code"


@pytest.mark.asyncio
async def test_recall_returns_empty_on_pinecone_error() -> None:
    """Pinecone failure → empty list, no exception raised."""
    redis_mock = _make_redis_mock(cache_hit=False)
    openai_mock = _make_openai_mock()
    pinecone_index = MagicMock()
    pinecone_index.query = MagicMock(side_effect=RuntimeError("Pinecone down"))

    with (
        patch("backend.core.memory.get_redis", return_value=redis_mock),
        patch("backend.core.memory.AsyncOpenAI", return_value=openai_mock),
        patch("backend.core.memory.get_index", return_value=pinecone_index),
        patch("backend.core.memory.get_settings") as mock_cfg,
    ):
        mock_cfg.return_value.openai_api_key = "test-key"
        items = await recall_for_user("user-err", "any goal")

    assert items == []


# ─────────────────────────────────────────────────────────────────────────────
# Two-session persistence scenario
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_second_session_receives_memory_from_first() -> None:
    """
    Session 1 stores output (quality 0.90). Session 2 calls recall and gets
    a MemoryItem from session 1 — which should appear in the Planner context.
    """
    from backend.core.context import build_planner_context

    session1_id = str(uuid.uuid4())
    session2_id = str(uuid.uuid4())
    user_id = "user-two-session"

    # --- Session 1: store a high-quality result ---
    state1: NexusState = initial_state("Build a recommendation engine", session1_id, user_id)
    state1["quality_score"] = 0.90

    stored_meta = {
        "session_id": session1_id,
        "user_id": user_id,
        "created_at": 1_700_000_000,
        "goal": "Build a recommendation engine",
        "output_type": "code",
        "quality_score": 0.90,
        "content_preview": "def recommend(user_id): return top_items",
    }

    pinecone_index = _make_pinecone_index_mock([stored_meta])
    redis_mock = _make_redis_mock(cache_hit=False)
    openai_mock = _make_openai_mock()

    with (
        patch("backend.core.memory.get_redis", return_value=redis_mock),
        patch("backend.core.memory.AsyncOpenAI", return_value=openai_mock),
        patch("backend.core.memory.get_index", return_value=pinecone_index),
        patch("backend.core.memory.get_settings") as mock_cfg,
    ):
        mock_cfg.return_value.openai_api_key = "test-key"
        await store_if_good(state1, "def recommend(user_id): return top_items")

    # --- Session 2: recall memory, inject into planner context ---
    with (
        patch("backend.core.memory.get_redis", return_value=redis_mock),
        patch("backend.core.memory.AsyncOpenAI", return_value=openai_mock),
        patch("backend.core.memory.get_index", return_value=pinecone_index),
        patch("backend.core.memory.get_settings") as mock_cfg,
    ):
        mock_cfg.return_value.openai_api_key = "test-key"
        memory_items = await recall_for_user(
            user_id, "Build a better recommendation system", top_k=5
        )

    assert len(memory_items) == 1
    assert memory_items[0]["session_id"] == session1_id

    # Build the planner context for session 2 with recalled memory
    state2: NexusState = initial_state(
        "Build a better recommendation system", session2_id, user_id
    )
    state2["session_memory"] = memory_items

    planner_context = build_planner_context(state2)

    # The recalled goal must appear in the planner context
    assert "Build a recommendation engine" in planner_context
