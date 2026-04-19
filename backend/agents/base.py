"""
BaseAgent — shared scaffold for all Nexus agents.

Responsibilities:
  - Load system prompt from backend/prompts/{name}.md (cached, never reloaded)
  - Invoke the LLM with exponential-backoff retry (max 3 attempts, base 2s)
  - Parse JSON response; raise on malformed JSON
  - Emit structured log entries for token usage and latency
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.core.context import load_prompt
from backend.core.models import get_model_router
from backend.core.state import NexusState

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_SECONDS = 2.0
_RETRY_JITTER = 0.5


class AgentError(Exception):
    """Raised when an agent cannot recover from repeated failures."""


class BaseAgent(ABC):
    """Abstract base class for all five Nexus agents."""

    name: str  # must be set by subclasses — matches prompts/{name}.md

    def __init__(self) -> None:
        self._router = get_model_router()
        self._prompt = load_prompt(self.name)

    # ── Public interface ──────────────────────────────────────────────────────

    @abstractmethod
    async def run(self, state: NexusState) -> dict[str, Any]:
        """
        Execute the agent logic and return a dict of NexusState fields to update.
        LangGraph merges the returned dict into the shared state.
        """

    # ── Protected helpers ─────────────────────────────────────────────────────

    async def _invoke_json(
        self,
        model_task_type: str,
        user_context: str,
        state: NexusState,
    ) -> dict[str, Any]:
        """
        Call the appropriate LLM, expecting a JSON object back.
        Retries up to _MAX_RETRIES times with exponential backoff + jitter.
        On exhausted retries, appends to error_log and raises AgentError.
        """
        model = self._router.get(model_task_type)
        messages = [
            SystemMessage(
                content=self._prompt,
                additional_kwargs={"cache_control": {"type": "ephemeral"}},
            ),
            HumanMessage(content=user_context),
        ]

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            t0 = time.monotonic()
            try:
                response = await model.ainvoke(messages)
                latency_ms = int((time.monotonic() - t0) * 1000)
                raw = response.content
                if not isinstance(raw, str):
                    raw = str(raw)

                parsed = self._parse_json(raw)
                self._log_usage(response, latency_ms)
                return parsed

            except (json.JSONDecodeError, ValueError) as exc:
                # Malformed JSON — not worth retrying with the same prompt
                raise AgentError(
                    f"{self.name}: malformed JSON response — {exc}\n"
                    "Check backend/prompts/{self.name}.md: "
                    "'Respond ONLY with valid JSON' must be the final instruction."
                ) from exc

            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, _RETRY_JITTER)
                    logger.warning(
                        "%s: attempt %d/%d failed (%s) — retrying in %.1fs",
                        self.name, attempt, _MAX_RETRIES, exc, delay,
                    )
                    await asyncio.sleep(delay)

        error_msg = f"{self.name}: all {_MAX_RETRIES} retries exhausted — {last_exc}"
        logger.error(error_msg)
        error_log: list[str] = list(state.get("error_log") or [])
        error_log.append(error_msg)
        raise AgentError(error_msg)

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Extract JSON from the model response, stripping markdown fences if present."""
        text = raw.strip()
        # Strip ```json ... ``` fences
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)  # type: ignore[no-any-return]

    @staticmethod
    def _log_usage(response: Any, latency_ms: int) -> None:
        usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", {})
        logger.info(
            "agent_llm_call latency_ms=%d usage=%s",
            latency_ms,
            usage,
        )
