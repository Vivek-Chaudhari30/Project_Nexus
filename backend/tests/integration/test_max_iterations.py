"""
Integration test: max_iterations hard cap.

All three iterations produce quality_score = 0.43 (below 0.85 threshold).
The graph must exit after iteration 3 with disclaimer='max_iterations_reached'.
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


async def _planner_run(state: NexusState) -> dict[str, Any]:
    return {"task_plan": [_TASK], "error_log": []}


async def _researcher_run(state: NexusState) -> dict[str, Any]:
    return {"research_context": {"t1": ""}}


async def _executor_run(state: NexusState) -> dict[str, Any]:
    plan = list(state.get("task_plan") or [])
    for t in plan:
        t["status"] = "done"
    return {"task_plan": plan, "execution_output": {"t1": ""}}


async def _verifier_run(state: NexusState) -> dict[str, Any]:
    return {
        "verification_report": {
            "overall_pass": False,
            "completeness": {"pass": False, "score": 0.3, "notes": "poor"},
            "factual_grounding": {"pass": False, "score": 0.4, "notes": ""},
            "format_compliance": {"pass": True, "score": 0.6, "notes": ""},
        }
    }


async def _reflector_run_low(state: NexusState) -> dict[str, Any]:
    return {"quality_score": 0.43, "reflection_feedback": "needs much more detail"}


@pytest.mark.asyncio
async def test_max_iterations_sets_disclaimer() -> None:
    """3 iterations all score below 0.85 → disclaimer='max_iterations_reached'."""
    session_id = str(uuid.uuid4())
    state: NexusState = initial_state(
        user_goal="research X",
        session_id=session_id,
        user_id="user-test",
    )

    with (
        patch("backend.agents.base.get_model_router", return_value=MagicMock()),
        patch.object(PlannerAgent, "run", AsyncMock(side_effect=_planner_run)),
        patch.object(ResearcherAgent, "run", AsyncMock(side_effect=_researcher_run)),
        patch.object(ExecutorAgent, "run", AsyncMock(side_effect=_executor_run)),
        patch.object(VerifierAgent, "run", AsyncMock(side_effect=_verifier_run)),
        patch.object(ReflectorAgent, "run", AsyncMock(side_effect=_reflector_run_low)),
        patch(
            "backend.core.loop_detector.LoopDetector.check",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        graph = build_graph(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": session_id}}
        result = await graph.ainvoke(state, config=config)

    assert result["iteration_count"] == 3
    assert result["disclaimer"] == "max_iterations_reached"
    assert result["quality_score"] < 0.85


@pytest.mark.asyncio
async def test_loop_detected_sets_disclaimer() -> None:
    """Loop detector firing on first iteration → disclaimer='loop_detected'."""
    session_id = str(uuid.uuid4())
    state: NexusState = initial_state(
        user_goal="research X",
        session_id=session_id,
        user_id="user-test",
    )

    with (
        patch("backend.agents.base.get_model_router", return_value=MagicMock()),
        patch.object(PlannerAgent, "run", AsyncMock(side_effect=_planner_run)),
        patch.object(ResearcherAgent, "run", AsyncMock(side_effect=_researcher_run)),
        patch.object(ExecutorAgent, "run", AsyncMock(side_effect=_executor_run)),
        patch.object(VerifierAgent, "run", AsyncMock(side_effect=_verifier_run)),
        patch.object(ReflectorAgent, "run", AsyncMock(side_effect=_reflector_run_low)),
        patch(
            "backend.core.loop_detector.LoopDetector.check",
            new_callable=AsyncMock,
            return_value=True,  # immediate loop detection
        ),
    ):
        graph = build_graph(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": session_id}}
        result = await graph.ainvoke(state, config=config)

    assert result["disclaimer"] == "loop_detected"
    assert result["iteration_count"] == 1
