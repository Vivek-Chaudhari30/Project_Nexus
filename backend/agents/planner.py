"""
PlannerAgent — decomposes a user goal into a TaskNode DAG.

Section 7 STEP 1 implementation.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.agents.base import AgentError, BaseAgent
from backend.core.context import build_planner_context
from backend.core.state import NexusState, TaskNode

logger = logging.getLogger(__name__)

_VALID_MODELS = {"reasoning", "code", "extract"}
_VALID_TOOLS = {"web_search", "code_exec", "file_write", "api_caller", "rag_recall"}
_MAX_TASKS = 10


def validate_task_dag(raw_tasks: list[dict[str, Any]]) -> list[TaskNode]:
    """
    Validate the planner's JSON output and return typed TaskNodes.
    Raises ValueError on schema violations or circular dependencies.
    """
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("task_plan must be a non-empty list")
    if len(raw_tasks) > _MAX_TASKS:
        raise ValueError(f"task_plan exceeds max {_MAX_TASKS} tasks ({len(raw_tasks)} given)")

    ids: set[str] = set()
    nodes: list[TaskNode] = []

    for i, raw in enumerate(raw_tasks):
        if not isinstance(raw, dict):
            raise ValueError(f"task[{i}] is not an object")
        for required in ("id", "description", "depends_on", "tool_hints", "assigned_model"):
            if required not in raw:
                raise ValueError(f"task[{i}] missing required field '{required}'")

        task_id: str = str(raw["id"])
        if task_id in ids:
            raise ValueError(f"Duplicate task id: {task_id!r}")
        ids.add(task_id)

        assigned = raw["assigned_model"]
        if assigned not in _VALID_MODELS:
            raise ValueError(f"task {task_id}: invalid assigned_model {assigned!r}")

        nodes.append(
            TaskNode(
                id=task_id,
                description=str(raw["description"]),
                status="pending",
                depends_on=[str(d) for d in (raw["depends_on"] or [])],
                tool_hints=[str(t) for t in (raw["tool_hints"] or []) if t in _VALID_TOOLS],
                assigned_model=assigned,
                output=None,
            )
        )

    # Validate that every depends_on reference exists
    for node in nodes:
        for dep in node["depends_on"]:
            if dep not in ids:
                raise ValueError(f"task {node['id']} depends on unknown id {dep!r}")

    # Detect cycles (DFS)
    _check_no_cycles(nodes)
    return nodes


def _check_no_cycles(nodes: list[TaskNode]) -> None:
    adj: dict[str, list[str]] = {n["id"]: n["depends_on"] for n in nodes}
    # 0 = unvisited, 1 = in-progress, 2 = done
    state: dict[str, int] = {n["id"]: 0 for n in nodes}

    def dfs(node_id: str) -> None:
        if state[node_id] == 1:
            raise ValueError(f"Circular dependency detected involving task {node_id!r}")
        if state[node_id] == 2:
            return
        state[node_id] = 1
        for dep in adj[node_id]:
            dfs(dep)
        state[node_id] = 2

    for nid in list(adj):
        dfs(nid)


class PlannerAgent(BaseAgent):
    name = "planner"

    async def run(self, state: NexusState) -> dict[str, Any]:
        logger.info("planner: iteration=%d", state.get("iteration_count", 1))
        user_context = build_planner_context(state)

        try:
            parsed = await self._invoke_json("reasoning", user_context, state)
        except AgentError:
            # Propagate — caller (graph) handles retry logic
            raise

        try:
            task_plan = validate_task_dag(parsed.get("tasks", []))
        except ValueError as exc:
            error_log = list(state.get("error_log") or [])
            error_log.append(f"planner validation: {exc}")
            logger.error("planner: validation failed — %s", exc)
            raise AgentError(f"planner: invalid task DAG — {exc}") from exc

        logger.info("planner: produced %d tasks", len(task_plan))
        return {"task_plan": task_plan}
