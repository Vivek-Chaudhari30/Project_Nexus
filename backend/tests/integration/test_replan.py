"""
Integration test: replan path.

First iteration returns quality 0.55 (below 0.85 threshold), triggering a
second planner run with reflection_feedback carried over. Second iteration
returns quality 0.90 and the graph exits cleanly.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from backend.agents.executor import ExecutorAgent
from backend.agents.planner import PlannerAgent
from backend.agents.reflector import ReflectorAgent
from backend.agents.researcher import ResearcherAgent
from backend.agents.verifier import VerifierAgent
from backend.core.graph import build_graph
from backend.core.state import NexusState, TaskNode, initial_state

_TASK: TaskNode = TaskNode(
    id="t1",
    description="Research topic X",
    status="pending",
    depends_on=[],
    tool_hints=[],
    assigned_model="reasoning",
    output=None,
)


def _planner_factory() -> AsyncMock:
    async def _run(state: NexusState) -> dict[str, Any]:
        return {"task_plan": [_TASK], "error_log": list(state.get("error_log") or [])}

    return AsyncMock(side_effect=_run)


def _researcher_factory() -> AsyncMock:
    async def _run(state: NexusState) -> dict[str, Any]:
        return {"research_context": {"t1": "research"}}

    return AsyncMock(side_effect=_run)


def _executor_factory() -> AsyncMock:
    async def _run(state: NexusState) -> dict[str, Any]:
        plan = list(state.get("task_plan") or [])
        for t in plan:
            t["status"] = "done"
        return {"task_plan": plan, "execution_output": {"t1": "output"}}

    return AsyncMock(side_effect=_run)


def _verifier_factory() -> AsyncMock:
    async def _run(state: NexusState) -> dict[str, Any]:
        return {
            "verification_report": {
                "overall_pass": True,
                "completeness": {"pass": True, "score": 0.8, "notes": ""},
                "factual_grounding": {"pass": True, "score": 0.8, "notes": ""},
                "format_compliance": {"pass": True, "score": 0.8, "notes": ""},
            }
        }

    return AsyncMock(side_effect=_run)


def _reflector_factory(scores: list[float]) -> AsyncMock:
    """Returns successive quality scores on each call."""
    counter = {"n": 0}

    async def _run(state: NexusState) -> dict[str, Any]:
        score = scores[min(counter["n"], len(scores) - 1)]
        counter["n"] += 1
        return {
            "quality_score": score,
            "reflection_feedback": "needs improvement" if score < 0.85 else "",
        }

    return AsyncMock(side_effect=_run)


@pytest.mark.asyncio
async def test_low_score_triggers_replan() -> None:
    """Iter 1 quality=0.55 → replan → iter 2 quality=0.90 → done."""
    session_id = str(uuid.uuid4())
    state: NexusState = initial_state(
        user_goal="research X",
        session_id=session_id,
        user_id="user-test",
    )

    mock_planner = _planner_factory()

    with (
        patch("backend.agents.base.get_model_router", return_value=MagicMock()),
        patch.object(PlannerAgent, "run", mock_planner),
        patch.object(ResearcherAgent, "run", _researcher_factory()),
        patch.object(ExecutorAgent, "run", _executor_factory()),
        patch.object(VerifierAgent, "run", _verifier_factory()),
        patch.object(ReflectorAgent, "run", _reflector_factory([0.55, 0.90])),
        patch(
            "backend.core.loop_detector.LoopDetector.check",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        graph = build_graph(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": session_id}}
        result = await graph.ainvoke(state, config=config)

    assert result["iteration_count"] == 2
    assert result["quality_score"] >= 0.85
    assert result.get("disclaimer") is None
    # Planner was invoked twice
    assert mock_planner.call_count == 2


@pytest.mark.asyncio
async def test_reflection_feedback_present_on_replan() -> None:
    """Verify that reflection_feedback is non-empty in state when replanning."""
    session_id = str(uuid.uuid4())
    state: NexusState = initial_state(
        user_goal="research X",
        session_id=session_id,
        user_id="user-test",
    )

    captured_states: list[NexusState] = []

    async def _planner_capturing(st: NexusState) -> dict[str, Any]:
        captured_states.append(dict(st))  # type: ignore[arg-type]
        return {"task_plan": [_TASK], "error_log": []}

    with (
        patch("backend.agents.base.get_model_router", return_value=MagicMock()),
        patch.object(PlannerAgent, "run", AsyncMock(side_effect=_planner_capturing)),
        patch.object(ResearcherAgent, "run", _researcher_factory()),
        patch.object(ExecutorAgent, "run", _executor_factory()),
        patch.object(VerifierAgent, "run", _verifier_factory()),
        patch.object(ReflectorAgent, "run", _reflector_factory([0.55, 0.90])),
        patch(
            "backend.core.loop_detector.LoopDetector.check",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        graph = build_graph(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": session_id}}
        await graph.ainvoke(state, config=config)

    # Second planner call should see the reflection feedback
    assert len(captured_states) == 2
    assert captured_states[1].get("reflection_feedback") == "needs improvement"
