"""
NexusGraph — LangGraph StateGraph implementing the canonical agent loop.

The pseudocode in Section 7 of the build spec is the authoritative spec.
This file MUST match it exactly; deviations require an ADR.

Node sequence per iteration:
  START → planner → [loop/maxiter check] → researcher → executor
        → verifier → reflector → [quality gate] → (planner | output)
        → END
"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agents.executor import ExecutorAgent
from backend.agents.planner import PlannerAgent
from backend.agents.reflector import ReflectorAgent
from backend.agents.researcher import ResearcherAgent
from backend.agents.verifier import VerifierAgent
from backend.core.loop_detector import LoopDetector
from backend.core.state import NexusState

logger = logging.getLogger(__name__)

_QUALITY_THRESHOLD = 0.85


# ──────────────────────────────────────────────────────────────────────────────
# Node implementations
# ──────────────────────────────────────────────────────────────────────────────

async def _planner_node(state: NexusState) -> dict:
    """
    Increment iteration_count, enforce hard cap, run PlannerAgent, then
    run loop detection — all as a single atomic node so checkpointing
    captures the post-planner state before any other agent runs.
    """
    new_count = (state.get("iteration_count") or 0) + 1
    max_iter = state.get("max_iterations") or 3
    base: dict = {"iteration_count": new_count}

    # Hard cap — must fire BEFORE the planner runs on this iteration.
    if new_count > max_iter:
        logger.info("graph: max_iterations_reached count=%d", new_count)
        return {**base, "disclaimer": "max_iterations_reached"}

    # Run the planner agent.
    try:
        merged = {**state, **base}
        planner_updates = await PlannerAgent().run(merged)  # type: ignore[arg-type]
    except Exception as exc:
        error_log = list(state.get("error_log") or [])
        error_log.append(f"planner error: {exc!s:.500}")
        return {**base, "error_log": error_log}

    task_plan = planner_updates.get("task_plan") or []

    # Loop detection — hash current plan against Redis SET for this session.
    try:
        detector = LoopDetector(state.get("session_id") or "unknown")
        if await detector.check(task_plan):
            error_log = list(planner_updates.get("error_log") or state.get("error_log") or [])
            error_log.append("loop detected — identical plan repeated")
            logger.warning("graph: loop_detected session=%s", state.get("session_id"))
            return {**base, **planner_updates, "error_log": error_log, "disclaimer": "loop_detected"}
    except Exception as exc:
        logger.error("graph: loop_detector failed: %s", exc)

    return {**base, **planner_updates}


async def _researcher_node(state: NexusState) -> dict:
    return await ResearcherAgent().run(state)  # type: ignore[arg-type]


async def _executor_node(state: NexusState) -> dict:
    return await ExecutorAgent().run(state)  # type: ignore[arg-type]


async def _verifier_node(state: NexusState) -> dict:
    return await VerifierAgent().run(state)  # type: ignore[arg-type]


async def _reflector_node(state: NexusState) -> dict:
    return await ReflectorAgent().run(state)  # type: ignore[arg-type]


async def _output_node(state: NexusState) -> dict:
    """Terminal node — sets max_iterations disclaimer if quality gate was never met."""
    quality = state.get("quality_score") or 0.0
    iteration = state.get("iteration_count") or 0
    max_iter = state.get("max_iterations") or 3
    updates: dict = {}

    if not state.get("disclaimer") and quality < _QUALITY_THRESHOLD and iteration >= max_iter:
        updates["disclaimer"] = "max_iterations_reached"

    logger.info(
        "graph: session=%s done quality=%.3f disclaimer=%s",
        state.get("session_id"),
        quality,
        updates.get("disclaimer") or state.get("disclaimer"),
    )
    return updates


# ──────────────────────────────────────────────────────────────────────────────
# Conditional edge routers
# ──────────────────────────────────────────────────────────────────────────────

def _route_after_planner(
    state: NexusState,
) -> Literal["researcher", "output"]:
    """After planner: if a disclaimer was set (max_iter or loop), go to output."""
    if state.get("disclaimer"):
        return "output"
    return "researcher"


def _route_after_reflector(
    state: NexusState,
) -> Literal["planner", "output"]:
    """Quality gate: pass threshold or exhausted iterations → output; else replan."""
    quality = state.get("quality_score") or 0.0
    iteration = state.get("iteration_count") or 0
    max_iter = state.get("max_iterations") or 3

    if quality >= _QUALITY_THRESHOLD:
        logger.info("graph: quality gate passed score=%.3f", quality)
        return "output"

    if iteration >= max_iter:
        return "output"

    logger.info(
        "graph: replanning iteration=%d quality=%.3f", iteration, quality
    )
    return "planner"


# ──────────────────────────────────────────────────────────────────────────────
# Graph builder
# ──────────────────────────────────────────────────────────────────────────────

def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> object:
    """
    Compile and return the Nexus StateGraph.

    Pass a checkpointer (AsyncPostgresSaver in production, MemorySaver in
    tests). If omitted a MemorySaver is used — suitable only for tests.
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    g: StateGraph = StateGraph(NexusState)

    g.add_node("planner", _planner_node)
    g.add_node("researcher", _researcher_node)
    g.add_node("executor", _executor_node)
    g.add_node("verifier", _verifier_node)
    g.add_node("reflector", _reflector_node)
    g.add_node("output", _output_node)

    g.add_edge(START, "planner")
    g.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"researcher": "researcher", "output": "output"},
    )
    g.add_edge("researcher", "executor")
    g.add_edge("executor", "verifier")
    g.add_edge("verifier", "reflector")
    g.add_conditional_edges(
        "reflector",
        _route_after_reflector,
        {"planner": "planner", "output": "output"},
    )
    g.add_edge("output", END)

    return g.compile(checkpointer=checkpointer)
