"""
ModelRouter — the single gateway for all LLM calls in Nexus.

Architecture rule: NO other file may instantiate ChatAnthropic,
ChatOpenAI, or ChatGoogleGenerativeAI. All callers go through
ModelRouter.get(task_type).

Routing logic (keyword-based with reasoning fallback):
  "code"      → GPT-4o   (langchain_openai)
  "extract"   → Gemini 2.5 Flash  (langchain_google_genai)
  "reasoning" → Claude Sonnet 4   (langchain_anthropic)  [default]
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from backend.config import get_settings

TaskType = Literal["reasoning", "code", "extract"]

_CODE_KEYWORDS = {"code", "script", "program", "implement", "function", "debug"}
_EXTRACT_KEYWORDS = {"extract", "parse", "scrape", "summarize", "chunk"}


class ModelRouter:
    """Returns the correct ChatModel instance for a given task_type keyword."""

    def __init__(self) -> None:
        cfg = get_settings()
        self._claude = ChatAnthropic(  # type: ignore[call-arg]
            model="claude-sonnet-4-5",
            api_key=cfg.anthropic_api_key,
            max_tokens=4096,
        )
        self._gpt4o = ChatOpenAI(
            model="gpt-4o",
            api_key=cfg.openai_api_key,
            max_tokens=4096,
        )
        self._gemini = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-preview-04-17",
            google_api_key=cfg.google_api_key,
            max_output_tokens=4096,
        )

    def get(self, task_type: str) -> ChatAnthropic | ChatOpenAI | ChatGoogleGenerativeAI:
        """
        Return the LLM for task_type. Accepts explicit task type names or
        free-text keywords (the router normalises them).
        """
        normalised = task_type.lower().strip()

        if normalised == "code" or any(kw in normalised for kw in _CODE_KEYWORDS):
            return self._gpt4o

        if normalised == "extract" or any(kw in normalised for kw in _EXTRACT_KEYWORDS):
            return self._gemini

        # "reasoning" and anything else → Claude (safe default)
        return self._claude

    @property
    def claude(self) -> ChatAnthropic:
        return self._claude

    @property
    def gpt4o(self) -> ChatOpenAI:
        return self._gpt4o

    @property
    def gemini(self) -> ChatGoogleGenerativeAI:
        return self._gemini


@lru_cache(maxsize=1)
def get_model_router() -> ModelRouter:
    """Process-level singleton. Safe because the router holds no mutable state."""
    return ModelRouter()
