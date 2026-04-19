"""Unit tests for ModelRouter — no real API calls made."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from backend.core.models import ModelRouter


@pytest.fixture()
def router() -> ModelRouter:
    """ModelRouter with all LLM constructors mocked to avoid real API calls."""
    with (
        patch("backend.core.models.ChatAnthropic", return_value=MagicMock(spec=ChatAnthropic)),
        patch("backend.core.models.ChatOpenAI", return_value=MagicMock(spec=ChatOpenAI)),
        patch(
            "backend.core.models.ChatGoogleGenerativeAI",
            return_value=MagicMock(spec=ChatGoogleGenerativeAI),
        ),
        patch("backend.core.models.get_settings") as mock_cfg,
    ):
        mock_cfg.return_value = MagicMock(
            anthropic_api_key="sk-ant-test",
            openai_api_key="sk-test",
            google_api_key="AIza-test",
        )
        yield ModelRouter()


class TestModelRouterExplicitTypes:
    def test_reasoning_returns_claude(self, router: ModelRouter) -> None:
        model = router.get("reasoning")
        assert isinstance(model, MagicMock)
        assert model is router.claude

    def test_code_returns_gpt4o(self, router: ModelRouter) -> None:
        model = router.get("code")
        assert model is router.gpt4o

    def test_extract_returns_gemini(self, router: ModelRouter) -> None:
        model = router.get("extract")
        assert model is router.gemini


class TestModelRouterKeywordFallthrough:
    @pytest.mark.parametrize("task_type", ["write a script", "implement sort", "debug this"])
    def test_code_keywords_route_to_gpt4o(self, router: ModelRouter, task_type: str) -> None:
        assert router.get(task_type) is router.gpt4o

    @pytest.mark.parametrize("task_type", ["extract fields", "parse html", "scrape page"])
    def test_extract_keywords_route_to_gemini(self, router: ModelRouter, task_type: str) -> None:
        assert router.get(task_type) is router.gemini

    @pytest.mark.parametrize("task_type", ["analyse market trends", "plan the tasks", "unknown"])
    def test_unrecognised_falls_back_to_claude(self, router: ModelRouter, task_type: str) -> None:
        assert router.get(task_type) is router.claude


class TestModelRouterCaseInsensitive:
    def test_uppercase_code(self, router: ModelRouter) -> None:
        assert router.get("CODE") is router.gpt4o

    def test_mixed_case_reasoning(self, router: ModelRouter) -> None:
        assert router.get("Reasoning") is router.claude

    def test_mixed_case_extract(self, router: ModelRouter) -> None:
        assert router.get("EXTRACT") is router.gemini
