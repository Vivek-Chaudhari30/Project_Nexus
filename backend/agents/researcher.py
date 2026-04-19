"""
ResearcherAgent — parallel tool dispatch in topological task order.

Section 7 STEP 2 implementation.
Does not call an LLM directly; orchestrates tool calls via the registry.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from typing import Any

from backend.core.state import NexusState, TaskNode
from backend.tools import get_tool

logger = logging.getLogger(__name__)

_RESULT_MAX_CHARS = 3_000


def topological_sort(tasks: list[TaskNode]) -> list[list[TaskNode]]:
    """
    Return tasks grouped into levels via Kahn's algorithm.
    Each level contains tasks whose dependencies are all satisfied by prior levels.
    Tasks within a level can run in parallel.
    """
    in_degree: dict[str, int] = {t["id"]: 0 for t in tasks}
    dependents: dict[str, list[str]] = defaultdict(list)

    for task in tasks:
        for dep in task["depends_on"]:
            in_degree[task["id"]] += 1
            dependents[dep].append(task["id"])

    by_id: dict[str, TaskNode] = {t["id"]: t for t in tasks}
    queue: deque[str] = deque(tid for tid, deg in in_degree.items() if deg == 0)
    levels: list[list[TaskNode]] = []

    while queue:
        level = list(queue)
        levels.append([by_id[tid] for tid in level])
        queue.clear()
        for tid in level:
            for dep_id in dependents[tid]:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

    return levels


async def _dispatch_task(task: TaskNode, research_context: dict[str, str]) -> tuple[str, str]:
    """Run all tool_hints for a task and merge results. Returns (task_id, result_text)."""
    results: list[str] = []

    for hint in task.get("tool_hints") or []:
        try:
            tool_fn = get_tool(hint)
        except KeyError:
            logger.warning("researcher: unknown tool hint %r for task %s", hint, task["id"])
            continue

        try:
            # Pass the task description as the query for search-type tools
            result = await tool_fn(
                query=task["description"],
                session_id="",   # populated by graph in later phases
                user_id="",
            )
            truncated = str(result)[:_RESULT_MAX_CHARS]
            results.append(truncated)
            logger.info("researcher: tool=%s task=%s ok", hint, task["id"])
        except Exception as exc:
            err = f"tool {hint} failed for task {task['id']}: {exc}"
            logger.error(err)
            results.append(f"No results found. ({err})")

    if not results:
        return task["id"], "No research tools specified for this task."

    return task["id"], "\n\n".join(results)


class ResearcherAgent:
    """Not a BaseAgent subclass — no LLM invocation, only tool dispatch."""

    name = "researcher"

    async def run(self, state: NexusState) -> dict[str, Any]:
        task_plan: list[TaskNode] = list(state.get("task_plan") or [])
        research_context: dict[str, str] = dict(state.get("research_context") or {})

        if not task_plan:
            logger.warning("researcher: task_plan is empty — nothing to research")
            return {"research_context": research_context}

        levels = topological_sort(task_plan)
        logger.info("researcher: %d tasks across %d levels", len(task_plan), len(levels))

        for level_idx, level in enumerate(levels):
            jobs = [_dispatch_task(task, research_context) for task in level]
            results = await asyncio.gather(*jobs, return_exceptions=True)

            for task, result in zip(level, results, strict=False):
                if isinstance(result, Exception):
                    logger.error("researcher: task %s raised %s", task["id"], result)
                    research_context[task["id"]] = f"No results found. ({result})"
                else:
                    task_id, text = result
                    research_context[task_id] = text

            logger.debug("researcher: level %d done", level_idx)

        return {"research_context": research_context}
