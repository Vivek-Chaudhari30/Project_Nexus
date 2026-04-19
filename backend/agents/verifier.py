"""
VerifierAgent — 3-dimension pass/fail report.

Dimensions: completeness, factual_grounding, format_compliance.
Section 7 STEP 4 implementation.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.agents.base import BaseAgent
from backend.core.context import build_verifier_context
from backend.core.state import NexusState

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = {"overall_pass", "completeness", "factual_grounding", "format_compliance"}


def _validate_report(report: dict[str, Any]) -> dict[str, Any]:
    """Ensure the verifier returned all required keys; fill defaults if minor fields missing."""
    missing = _REQUIRED_KEYS - set(report.keys())
    if missing:
        raise ValueError(f"Verifier report missing keys: {missing}")

    # Normalise each dimension to always have 'pass' and 'score'
    for dim in ("completeness", "factual_grounding", "format_compliance"):
        entry = report.get(dim)
        if not isinstance(entry, dict):
            report[dim] = {"pass": False, "score": 0.0, "notes": "missing dimension"}
        else:
            entry.setdefault("pass", False)
            entry.setdefault("score", 0.0)
            entry.setdefault("notes", "")

    report.setdefault("ungrounded_claims", [])
    report.setdefault("missing_tasks", [])
    return report


class VerifierAgent(BaseAgent):
    name = "verifier"

    async def run(self, state: NexusState) -> dict[str, Any]:
        logger.info("verifier: iteration=%d", state.get("iteration_count", 1))
        user_context = build_verifier_context(state)
        parsed = await self._invoke_json("reasoning", user_context, state)

        try:
            report = _validate_report(parsed)
        except ValueError as exc:
            logger.error("verifier: invalid report — %s", exc)
            # Return a failing report rather than crashing the session
            report = {
                "overall_pass": False,
                "completeness": {"pass": False, "score": 0.0, "notes": str(exc)},
                "factual_grounding": {"pass": False, "score": 0.0, "notes": ""},
                "format_compliance": {"pass": False, "score": 0.0, "notes": ""},
                "ungrounded_claims": [],
                "missing_tasks": [],
            }

        logger.info("verifier: overall_pass=%s", report.get("overall_pass"))
        return {"verification_report": report}
