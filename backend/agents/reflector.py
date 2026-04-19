"""
ReflectorAgent — quality scoring + improvement directives.

Scores 0.0–1.0 across 5 dimensions; overall_score = mean.
Pass threshold: >= 0.85 (CLAUDE.md Rule 8).
Section 7 STEP 5 implementation.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.agents.base import BaseAgent
from backend.core.context import build_reflector_context
from backend.core.state import NexusState

logger = logging.getLogger(__name__)

_QUALITY_THRESHOLD = 0.85
_DIMENSIONS = ("completeness", "accuracy", "quality", "efficiency", "format_score")


def _validate_reflection(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure required fields exist and scores are in [0, 1]."""
    raw.setdefault("quality_score", 0.0)
    raw.setdefault("improvement_directives", [])
    raw.setdefault("dimension_scores", {})
    raw.setdefault("pass", False)

    score = float(raw["quality_score"])
    raw["quality_score"] = max(0.0, min(1.0, score))

    dims = raw["dimension_scores"]
    for dim in _DIMENSIONS:
        dims.setdefault(dim, 0.0)
        dims[dim] = max(0.0, min(1.0, float(dims[dim])))

    # Recompute overall from dimensions to prevent prompt manipulation
    if any(dims[d] > 0 for d in _DIMENSIONS):
        raw["quality_score"] = round(sum(dims[d] for d in _DIMENSIONS) / len(_DIMENSIONS), 4)

    raw["pass"] = raw["quality_score"] >= _QUALITY_THRESHOLD
    return raw


class ReflectorAgent(BaseAgent):
    name = "reflector"

    async def run(self, state: NexusState) -> dict[str, Any]:
        iteration = state.get("iteration_count", 1)
        max_iter = state.get("max_iterations", 3)
        logger.info("reflector: iteration=%d/%d", iteration, max_iter)

        user_context = build_reflector_context(state)
        parsed = await self._invoke_json("reasoning", user_context, state)
        reflection = _validate_reflection(parsed)

        quality_score: float = reflection["quality_score"]
        directives: list[str] = reflection.get("improvement_directives") or []
        reflection_feedback = "\n".join(directives[:5])  # cap at 5 per spec

        logger.info(
            "reflector: quality_score=%.4f pass=%s directives=%d",
            quality_score,
            reflection["pass"],
            len(directives),
        )

        return {
            "quality_score": quality_score,
            "reflection_feedback": reflection_feedback,
        }
