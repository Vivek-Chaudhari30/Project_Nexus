"""
ModelRouter — the single gateway for all LLM calls in Nexus.

Architecture rule: NO other file may instantiate ChatAnthropic,
ChatOpenAI, or ChatGoogleGenerativeAI. All callers go through
ModelRouter.get(task_type).

Provider modes (PROVIDER_MODE env var or runtime toggle):
  "openai_only"  — all agents use OpenAI models (default)
                   reasoning → gpt-4o
                   code      → gpt-4o
                   extract   → gpt-4o-mini
  "multi"        — uses all three providers
                   reasoning → claude-sonnet-4-5  (Anthropic)
                   code      → gpt-4o             (OpenAI)
                   extract   → gemini-2.5-flash   (Google)

Providers are imported lazily inside __init__ so the server boots fine
in openai_only mode even when Anthropic/Google packages are not installed.

The active router can be hot-swapped at runtime via set_model_router()
without a server restart.
"""
from __future__ import annotations

from typing import Any, Literal

from backend.config import get_settings

TaskType = Literal["reasoning", "code", "extract"]

_CODE_KEYWORDS = {"code", "script", "program", "implement", "function", "debug"}
_EXTRACT_KEYWORDS = {"extract", "parse", "scrape", "summarize", "chunk"}

# Model names per mode — used by the config API to report current assignments
MODEL_NAMES: dict[str, dict[str, str]] = {
    "openai_only": {
        "reasoning": "gpt-4o",
        "code": "gpt-4o",
        "extraction": "gpt-4o-mini",
    },
    "multi": {
        "reasoning": "claude-sonnet-4-5",
        "code": "gpt-4o",
        "extraction": "gemini-2.5-flash-preview-04-17",
    },
}


class ModelRouter:
    """Returns the correct ChatModel instance for a given task_type keyword."""

    def __init__(self, mode: Literal["multi", "openai_only"] | None = None) -> None:
        cfg = get_settings()
        self.mode: Literal["multi", "openai_only"] = mode or cfg.provider_mode
        self.model_names: dict[str, str] = MODEL_NAMES[self.mode]

        from langchain_openai import ChatOpenAI  # always available

        if self.mode == "openai_only":
            self._reasoning: Any = ChatOpenAI(
                model="gpt-4o",
                api_key=cfg.openai_api_key,
                max_tokens=4096,
            )
            self._code: Any = ChatOpenAI(
                model="gpt-4o",
                api_key=cfg.openai_api_key,
                max_tokens=4096,
            )
            self._extract: Any = ChatOpenAI(
                model="gpt-4o-mini",
                api_key=cfg.openai_api_key,
                max_tokens=4096,
            )
        else:
            from langchain_anthropic import ChatAnthropic
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._reasoning = ChatAnthropic(  # type: ignore[call-arg]
                model="claude-sonnet-4-5",
                api_key=cfg.anthropic_api_key,
                max_tokens=4096,
            )
            self._code = ChatOpenAI(
                model="gpt-4o",
                api_key=cfg.openai_api_key,
                max_tokens=4096,
            )
            self._extract = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-preview-04-17",
                google_api_key=cfg.google_api_key,
                max_output_tokens=4096,
            )

    def get(self, task_type: str) -> Any:
        """Return the LLM for task_type. Accepts explicit names or free-text keywords."""
        normalised = task_type.lower().strip()

        if normalised == "code" or any(kw in normalised for kw in _CODE_KEYWORDS):
            return self._code

        if normalised == "extract" or any(kw in normalised for kw in _EXTRACT_KEYWORDS):
            return self._extract

        # "reasoning" and anything else → reasoning model (safe default)
        return self._reasoning

    # ── Named accessors ──────────────────────────────────────────────────────

    @property
    def reasoning(self) -> Any:
        return self._reasoning

    @property
    def code(self) -> Any:
        return self._code

    @property
    def extract(self) -> Any:
        return self._extract

    # Legacy aliases kept for backwards compat
    @property
    def claude(self) -> Any:
        return self._reasoning

    @property
    def gpt4o(self) -> Any:
        return self._code

    @property
    def gemini(self) -> Any:
        return self._extract


# ── Module-level mutable singleton (hot-swappable) ───────────────────────────

_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def set_model_router(router: ModelRouter) -> None:
    """Replace the active ModelRouter instance. Used by the config toggle API."""
    global _router
    _router = router
