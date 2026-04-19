"""Unit tests for ModelRouter — both provider modes, no real API calls."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.core.models import ModelRouter


def _settings_mock(mode: str = "openai_only") -> MagicMock:
    m = MagicMock()
    m.provider_mode = mode
    m.openai_api_key = "sk-test"
    m.anthropic_api_key = "sk-ant-test"
    m.google_api_key = "AIza-test"
    return m


# ── openai_only mode ─────────────────────────────────────────────────────────


class TestOpenAIOnlyMode:
    @pytest.fixture()
    def router(self) -> ModelRouter:
        mock_openai_instance = MagicMock()
        mock_openai_cls = MagicMock(return_value=mock_openai_instance)

        with (
            patch("langchain_openai.ChatOpenAI", mock_openai_cls),
            patch("backend.core.models.get_settings", return_value=_settings_mock("openai_only")),
        ):
            return ModelRouter(mode="openai_only")

    def test_reasoning_returns_chat_openai(self, router: ModelRouter) -> None:
        from langchain_openai import ChatOpenAI  # noqa: F401 (import for spec reference)
        # All instances are ChatOpenAI mocks in openai_only mode
        result = router.get("reasoning")
        assert result is router._reasoning

    def test_code_returns_chat_openai(self, router: ModelRouter) -> None:
        assert router.get("code") is router._code

    def test_extract_returns_chat_openai(self, router: ModelRouter) -> None:
        assert router.get("extract") is router._extract

    def test_all_three_are_openai_instances(self, router: ModelRouter) -> None:
        """In openai_only mode, all three router.get() calls return a ChatOpenAI instance."""
        # All three should be the same mock type (ChatOpenAI), not Anthropic/Google
        r = router.get("reasoning")
        c = router.get("code")
        e = router.get("extract")
        # They are all MagicMock instances returned by the patched ChatOpenAI constructor
        assert r is not None
        assert c is not None
        assert e is not None
        # Anthropic and Google must NOT have been imported/called
        assert router.mode == "openai_only"

    def test_anthropic_not_instantiated(self) -> None:
        """Anthropic is never imported in openai_only mode."""
        mock_openai_cls = MagicMock(return_value=MagicMock())
        mock_anthropic_cls = MagicMock()
        mock_google_cls = MagicMock()

        with (
            patch("langchain_openai.ChatOpenAI", mock_openai_cls),
            patch("langchain_anthropic.ChatAnthropic", mock_anthropic_cls),
            patch("langchain_google_genai.ChatGoogleGenerativeAI", mock_google_cls),
            patch("backend.core.models.get_settings", return_value=_settings_mock("openai_only")),
        ):
            ModelRouter(mode="openai_only")

        mock_anthropic_cls.assert_not_called()
        mock_google_cls.assert_not_called()

    def test_model_names_are_openai(self, router: ModelRouter) -> None:
        assert router.model_names["reasoning"] == "gpt-4o"
        assert router.model_names["code"] == "gpt-4o"
        assert router.model_names["extraction"] == "gpt-4o-mini"

    @pytest.mark.parametrize("task_type", ["write a script", "implement sort", "debug this"])
    def test_code_keywords_route_to_code_model(self, router: ModelRouter, task_type: str) -> None:
        assert router.get(task_type) is router._code

    @pytest.mark.parametrize("task_type", ["extract fields", "parse html", "scrape page"])
    def test_extract_keywords_route_to_extract_model(self, router: ModelRouter, task_type: str) -> None:
        assert router.get(task_type) is router._extract

    @pytest.mark.parametrize("task_type", ["analyse market trends", "plan the tasks", "unknown"])
    def test_unrecognised_falls_back_to_reasoning(self, router: ModelRouter, task_type: str) -> None:
        assert router.get(task_type) is router._reasoning


# ── multi mode ───────────────────────────────────────────────────────────────


class TestMultiMode:
    @pytest.fixture()
    def mocks(self) -> dict[str, MagicMock]:
        return {
            "claude_instance": MagicMock(),
            "gpt4o_instance": MagicMock(),
            "gemini_instance": MagicMock(),
        }

    @pytest.fixture()
    def router(self, mocks: dict[str, MagicMock]) -> ModelRouter:
        mock_anthropic_cls = MagicMock(return_value=mocks["claude_instance"])
        mock_openai_cls = MagicMock(return_value=mocks["gpt4o_instance"])
        mock_google_cls = MagicMock(return_value=mocks["gemini_instance"])

        with (
            patch("langchain_anthropic.ChatAnthropic", mock_anthropic_cls),
            patch("langchain_openai.ChatOpenAI", mock_openai_cls),
            patch("langchain_google_genai.ChatGoogleGenerativeAI", mock_google_cls),
            patch("backend.core.models.get_settings", return_value=_settings_mock("multi")),
        ):
            return ModelRouter(mode="multi")

    def test_reasoning_returns_chat_anthropic(self, router: ModelRouter, mocks: dict[str, MagicMock]) -> None:
        """In multi mode, reasoning returns a ChatAnthropic instance."""
        assert router.get("reasoning") is mocks["claude_instance"]

    def test_code_returns_chat_openai(self, router: ModelRouter, mocks: dict[str, MagicMock]) -> None:
        assert router.get("code") is mocks["gpt4o_instance"]

    def test_extract_returns_chat_google(self, router: ModelRouter, mocks: dict[str, MagicMock]) -> None:
        """In multi mode, extraction returns a ChatGoogleGenerativeAI instance."""
        assert router.get("extract") is mocks["gemini_instance"]

    def test_model_names_are_multi(self, router: ModelRouter) -> None:
        assert router.model_names["reasoning"] == "claude-sonnet-4-5"
        assert router.model_names["code"] == "gpt-4o"
        assert router.model_names["extraction"] == "gemini-2.5-flash-preview-04-17"

    def test_reasoning_property_alias(self, router: ModelRouter, mocks: dict[str, MagicMock]) -> None:
        assert router.reasoning is mocks["claude_instance"]
        assert router.claude is mocks["claude_instance"]  # legacy alias

    def test_code_property_alias(self, router: ModelRouter, mocks: dict[str, MagicMock]) -> None:
        assert router.code is mocks["gpt4o_instance"]
        assert router.gpt4o is mocks["gpt4o_instance"]  # legacy alias

    def test_extract_property_alias(self, router: ModelRouter, mocks: dict[str, MagicMock]) -> None:
        assert router.extract is mocks["gemini_instance"]
        assert router.gemini is mocks["gemini_instance"]  # legacy alias


# ── keyword routing (mode-agnostic) ──────────────────────────────────────────


class TestKeywordRouting:
    @pytest.fixture()
    def router(self) -> ModelRouter:
        mock_openai_cls = MagicMock(return_value=MagicMock())
        with (
            patch("langchain_openai.ChatOpenAI", mock_openai_cls),
            patch("backend.core.models.get_settings", return_value=_settings_mock("openai_only")),
        ):
            return ModelRouter(mode="openai_only")

    def test_case_insensitive_code(self, router: ModelRouter) -> None:
        assert router.get("CODE") is router._code

    def test_case_insensitive_extract(self, router: ModelRouter) -> None:
        assert router.get("EXTRACT") is router._extract

    def test_case_insensitive_reasoning(self, router: ModelRouter) -> None:
        assert router.get("Reasoning") is router._reasoning
