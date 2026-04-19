"""
Integration test: full pipeline runs end-to-end with mocked agents.

Tests the graph wiring — routing, iteration counting, and state propagation.
Agents' run() methods are patched so this exercises only graph logic.
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
    tool_hints=["web_search"],
    assigned_model="reasoning",
    output=None,
)

_VERIFICATION = {
    "overall_pass": True,
    "completeness": {"pass": True, "score": 0.9, "notes": ""},
    "factual_grounding": {"pass": True, "score": 0.85, "notes": ""},
    "format_compliance": {"pass": True, "score": 1.0, "notes": ""},
}

_REFLECTION = {
    "quality_score": 0.88,
    "dimension_scores": {
        "completeness": 0.9,
        "factual_grounding": 0.85,
        "format_compliance": 1.0,
    },
    "improvement_directives": [],
    "overall_pass": True,
}


async def _planner_run(state: NexusState) -> dict[str, Any]:
    return {"task_plan": [_TASK], "error_log": []}


async def _researcher_run(state: NexusState) -> dict[str, Any]:
    return {"research_context": {"t1": "Some research."}}


async def _executor_run(state: NexusState) -> dict[str, Any]:
    plan = list(state.get("task_plan") or [])
    for t in plan:
        t["status"] = "done"
    return {"task_plan": plan, "execution_output": {"t1": "done\n"}}


async def _verifier_run(state: NexusState) -> dict[str, Any]:
    return {"verification_report": _VERIFICATION}


async def _reflector_run(state: NexusState) -> dict[str, Any]:
    return {
        "quality_score": _REFLECTION["quality_score"],
        "reflection_feedback": "",
    }


@pytest.mark.asyncio
async def test_full_pipeline_quality_above_threshold() -> None:
    """Full pipeline: all agents mocked, assert quality_score >= 0.70 on exit."""
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
        patch.object(ReflectorAgent, "run", AsyncMock(side_effect=_reflector_run)),
        patch(
            "backend.core.loop_detector.LoopDetector.check",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        graph = build_graph(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": session_id}}
        result = await graph.ainvoke(state, config=config)

    assert result["quality_score"] >= 0.70
    assert result.get("disclaimer") is None
    assert result["iteration_count"] == 1
