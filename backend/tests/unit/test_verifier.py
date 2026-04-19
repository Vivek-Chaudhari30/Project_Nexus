"""
Unit tests for Phase 4 tools (web_search, file_writer, api_caller, rag_recall)
plus tool registry behaviour.

Named test_verifier.py because that is the in-spec filename; actual verifier
agent tests will be added in Phase 5.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Tool registry ─────────────────────────────────────────────────────────────

class TestToolRegistry:
    def test_all_tools_registered(self) -> None:
        from backend.tools import REGISTRY
        expected = {"web_search", "file_write", "file_read", "api_caller", "rag_recall"}
        assert expected.issubset(set(REGISTRY.keys()))

    def test_get_tool_returns_callable(self) -> None:
        from backend.tools import get_tool
        fn = get_tool("web_search")
        assert callable(fn)

    def test_get_tool_unknown_raises(self) -> None:
        from backend.tools import get_tool
        with pytest.raises(KeyError, match="not registered"):
            get_tool("does_not_exist")

    def test_tool_decorator_rejects_sync_function(self) -> None:
        from backend.tools import tool
        with pytest.raises(TypeError, match="async"):
            @tool
            def sync_fn(x: str) -> str:  # type: ignore[return-value]
                return x


# ── web_search ────────────────────────────────────────────────────────────────

class TestWebSearch:
    @pytest.fixture()
    def mock_redis(self) -> AsyncMock:
        redis = AsyncMock()
        redis.get.return_value = None  # cache miss by default
        redis.set.return_value = True
        return redis

    @pytest.fixture()
    def tavily_results(self) -> list[dict]:  # type: ignore[type-arg]
        return [
            {"title": "Paper A", "content": "Attention is all you need.", "url": "https://arxiv.org/1"},
            {"title": "Paper B", "content": "Flash Attention reduces memory.", "url": "https://arxiv.org/2"},
        ]

    @pytest.mark.asyncio
    async def test_returns_formatted_results(self, mock_redis: AsyncMock, tavily_results: list) -> None:  # type: ignore[type-arg]
        with (
            patch("backend.tools.web_search.get_redis", return_value=mock_redis),
            patch("backend.tools.web_search.get_settings") as mock_cfg,
            patch("backend.tools.web_search.AsyncTavilyClient") as mock_tavily,
        ):
            mock_cfg.return_value = MagicMock(tavily_api_key="tvly-test")
            mock_client = AsyncMock()
            mock_client.search.return_value = {"results": tavily_results}
            mock_tavily.return_value = mock_client

            from backend.tools.web_search import web_search
            result = await web_search(query="transformer architectures")

        assert "Paper A" in result
        assert "arxiv.org/1" in result
        assert "Paper B" in result

    @pytest.mark.asyncio
    async def test_returns_cache_hit_without_api_call(self, mock_redis: AsyncMock) -> None:
        mock_redis.get.return_value = "cached result"

        with (
            patch("backend.tools.web_search.get_redis", return_value=mock_redis),
            patch("backend.tools.web_search.AsyncTavilyClient") as mock_tavily,
        ):
            from backend.tools.web_search import web_search
            result = await web_search(query="cached query")

        assert result == "cached result"
        mock_tavily.assert_not_called()

    @pytest.mark.asyncio
    async def test_caches_result_after_api_call(self, mock_redis: AsyncMock, tavily_results: list) -> None:  # type: ignore[type-arg]
        with (
            patch("backend.tools.web_search.get_redis", return_value=mock_redis),
            patch("backend.tools.web_search.get_settings") as mock_cfg,
            patch("backend.tools.web_search.AsyncTavilyClient") as mock_tavily,
        ):
            mock_cfg.return_value = MagicMock(tavily_api_key="tvly-test")
            mock_client = AsyncMock()
            mock_client.search.return_value = {"results": tavily_results}
            mock_tavily.return_value = mock_client

            from backend.tools.web_search import web_search
            await web_search(query="new query")

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == 3600

    @pytest.mark.asyncio
    async def test_empty_results_returns_no_results_message(self, mock_redis: AsyncMock) -> None:
        with (
            patch("backend.tools.web_search.get_redis", return_value=mock_redis),
            patch("backend.tools.web_search.get_settings") as mock_cfg,
            patch("backend.tools.web_search.AsyncTavilyClient") as mock_tavily,
        ):
            mock_cfg.return_value = MagicMock(tavily_api_key="tvly-test")
            mock_client = AsyncMock()
            mock_client.search.return_value = {"results": []}
            mock_tavily.return_value = mock_client

            from backend.tools.web_search import web_search
            result = await web_search(query="obscure query")

        assert "No results found" in result

    def test_cache_key_is_deterministic(self) -> None:
        from backend.tools.web_search import _cache_key
        assert _cache_key("hello") == _cache_key("hello")
        assert _cache_key("hello") != _cache_key("world")


# ── file_writer ───────────────────────────────────────────────────────────────

class TestFileWriter:
    @pytest.mark.asyncio
    async def test_writes_file_to_workspace(self, tmp_path: Path) -> None:
        with patch("backend.tools.file_writer._WORKSPACE_ROOT", tmp_path):
            from backend.tools.file_writer import file_write
            result = await file_write(
                session_id="sess-1",
                relative_path="output/report.md",
                content="# Report\nHello world",
            )

        written = (tmp_path / "sess-1" / "output" / "report.md").read_text()
        assert written == "# Report\nHello world"
        assert "Written" in result

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        with patch("backend.tools.file_writer._WORKSPACE_ROOT", tmp_path):
            from backend.tools.file_writer import file_write
            await file_write(
                session_id="sess-2",
                relative_path="deep/nested/dir/file.txt",
                content="content",
            )

        assert (tmp_path / "sess-2" / "deep" / "nested" / "dir" / "file.txt").exists()

    @pytest.mark.asyncio
    async def test_blocks_path_traversal(self, tmp_path: Path) -> None:
        with patch("backend.tools.file_writer._WORKSPACE_ROOT", tmp_path):
            from backend.tools.file_writer import file_write
            with pytest.raises(PermissionError, match="traversal"):
                await file_write(
                    session_id="sess-3",
                    relative_path="../../etc/passwd",
                    content="hacked",
                )

    @pytest.mark.asyncio
    async def test_reads_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "sess-4" / "data.txt"
        target.parent.mkdir(parents=True)
        target.write_text("hello")

        with patch("backend.tools.file_writer._WORKSPACE_ROOT", tmp_path):
            from backend.tools.file_writer import file_read
            result = await file_read(session_id="sess-4", relative_path="data.txt")

        assert result == "hello"

    @pytest.mark.asyncio
    async def test_read_missing_file_returns_message(self, tmp_path: Path) -> None:
        with patch("backend.tools.file_writer._WORKSPACE_ROOT", tmp_path):
            from backend.tools.file_writer import file_read
            result = await file_read(session_id="sess-5", relative_path="missing.txt")

        assert "not found" in result.lower()


# ── api_caller ────────────────────────────────────────────────────────────────

class TestApiCaller:
    @pytest.mark.asyncio
    async def test_get_request_returns_status_and_body(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"ok": true}'

        with patch("backend.tools.api_caller.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            from backend.tools.api_caller import api_caller
            result = await api_caller(url="https://example.com/api", method="GET")

        assert "200" in result
        assert '{"ok": true}' in result

    @pytest.mark.asyncio
    async def test_post_sends_json_body(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "created"

        with patch("backend.tools.api_caller.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            from backend.tools.api_caller import api_caller
            await api_caller(url="https://example.com/api", method="POST", body={"key": "val"})

        call_kwargs = mock_client.request.call_args.kwargs
        assert call_kwargs["json"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_disallowed_method_returns_error(self) -> None:
        from backend.tools.api_caller import api_caller
        result = await api_caller(url="https://example.com", method="TRACE")
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_timeout_returns_error_message(self) -> None:
        import httpx

        with patch("backend.tools.api_caller.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            from backend.tools.api_caller import api_caller
            result = await api_caller(url="https://slow.example.com")

        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_network_error_returns_error_message(self) -> None:
        import httpx

        with patch("backend.tools.api_caller.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.RequestError("connection refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            from backend.tools.api_caller import api_caller
            result = await api_caller(url="https://unreachable.example.com")

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_response_truncated_at_8000_chars(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "x" * 10_000

        with patch("backend.tools.api_caller.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            from backend.tools.api_caller import api_caller
            result = await api_caller(url="https://example.com")

        # "HTTP 200\n" prefix + up to 8000 chars of body
        assert len(result) <= 8_010


# ── rag_recall ────────────────────────────────────────────────────────────────

class TestRagRecall:
    @pytest.fixture()
    def mock_redis(self) -> AsyncMock:
        redis = AsyncMock()
        redis.get.return_value = None
        redis.set.return_value = True
        return redis

    @pytest.fixture()
    def mock_vector(self) -> list[float]:
        return [0.1] * 1536

    @pytest.fixture()
    def pinecone_matches(self) -> list[dict]:  # type: ignore[type-arg]
        return [
            {
                "id": "sess-old-1",
                "score": 0.92,
                "metadata": {
                    "goal": "Research transformers",
                    "content_preview": "Found 5 relevant papers on attention.",
                    "quality_score": 0.88,
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_returns_formatted_matches(
        self,
        mock_redis: AsyncMock,
        mock_vector: list[float],
        pinecone_matches: list[dict],  # type: ignore[type-arg]
    ) -> None:
        with (
            patch("backend.tools.rag_recall.get_redis", return_value=mock_redis),
            patch("backend.tools.rag_recall.get_settings") as mock_cfg,
            patch("backend.tools.rag_recall.AsyncOpenAI") as mock_openai,
            patch("backend.tools.rag_recall.get_index") as mock_index,
        ):
            mock_cfg.return_value = MagicMock(openai_api_key="sk-test")
            embed_resp = MagicMock()
            embed_resp.data = [MagicMock(embedding=mock_vector)]
            mock_openai.return_value.embeddings.create = AsyncMock(return_value=embed_resp)
            mock_index.return_value.query.return_value = {"matches": pinecone_matches}

            from backend.tools.rag_recall import rag_recall
            result = await rag_recall(query="transformers", user_id="user-1")

        assert "Research transformers" in result
        assert "0.92" in result

    @pytest.mark.asyncio
    async def test_no_matches_returns_message(
        self, mock_redis: AsyncMock, mock_vector: list[float]
    ) -> None:
        with (
            patch("backend.tools.rag_recall.get_redis", return_value=mock_redis),
            patch("backend.tools.rag_recall.get_settings") as mock_cfg,
            patch("backend.tools.rag_recall.AsyncOpenAI") as mock_openai,
            patch("backend.tools.rag_recall.get_index") as mock_index,
        ):
            mock_cfg.return_value = MagicMock(openai_api_key="sk-test")
            embed_resp = MagicMock()
            embed_resp.data = [MagicMock(embedding=mock_vector)]
            mock_openai.return_value.embeddings.create = AsyncMock(return_value=embed_resp)
            mock_index.return_value.query.return_value = {"matches": []}

            from backend.tools.rag_recall import rag_recall
            result = await rag_recall(query="obscure topic", user_id="user-1")

        assert "No relevant" in result

    @pytest.mark.asyncio
    async def test_uses_cached_embedding(
        self, mock_vector: list[float], pinecone_matches: list[dict]  # type: ignore[type-arg]
    ) -> None:
        cached_redis = AsyncMock()
        cached_redis.get.return_value = json.dumps(mock_vector)
        cached_redis.set.return_value = True

        with (
            patch("backend.tools.rag_recall.get_redis", return_value=cached_redis),
            patch("backend.tools.rag_recall.AsyncOpenAI") as mock_openai,
            patch("backend.tools.rag_recall.get_index") as mock_index,
        ):
            mock_index.return_value.query.return_value = {"matches": pinecone_matches}

            from backend.tools.rag_recall import rag_recall
            await rag_recall(query="cached query", user_id="user-1")

        # OpenAI client should NOT have been constructed
        mock_openai.assert_not_called()

    @pytest.mark.asyncio
    async def test_pinecone_queried_with_user_namespace(
        self, mock_redis: AsyncMock, mock_vector: list[float]
    ) -> None:
        with (
            patch("backend.tools.rag_recall.get_redis", return_value=mock_redis),
            patch("backend.tools.rag_recall.get_settings") as mock_cfg,
            patch("backend.tools.rag_recall.AsyncOpenAI") as mock_openai,
            patch("backend.tools.rag_recall.get_index") as mock_index,
        ):
            mock_cfg.return_value = MagicMock(openai_api_key="sk-test")
            embed_resp = MagicMock()
            embed_resp.data = [MagicMock(embedding=mock_vector)]
            mock_openai.return_value.embeddings.create = AsyncMock(return_value=embed_resp)
            mock_index.return_value.query.return_value = {"matches": []}

            from backend.tools.rag_recall import rag_recall
            await rag_recall(query="q", user_id="user-xyz")

        query_kwargs = mock_index.return_value.query.call_args.kwargs
        assert query_kwargs["namespace"] == "user-xyz"
        assert query_kwargs["filter"] == {"quality_score": {"$gte": 0.70}}
