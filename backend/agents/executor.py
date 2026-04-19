"""
ExecutorAgent — CodeAct pattern: generate Python → run in sandbox.

Phase 6: uses the real gRPC sandbox client (backend/tools/code_executor.py).
The Phase 5 subprocess stub has been removed per CLAUDE.md Rule 6.

Section 7 STEP 3 implementation.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.agents.base import AgentError, BaseAgent
from backend.agents.researcher import topological_sort
from backend.core.context import build_executor_context
from backend.core.state import NexusState, TaskNode
from backend.tools.code_executor import SandboxResult, execute_code

logger = logging.getLogger(__name__)

_SANDBOX_TIMEOUT = 30
_STDERR_MAX_CHARS = 500


class ExecutorAgent(BaseAgent):
    name = "executor"

    async def run(self, state: NexusState) -> dict[str, Any]:
        task_plan: list[TaskNode] = list(state.get("task_plan") or [])
        execution_output: dict[str, str] = dict(state.get("execution_output") or {})
        error_log: list[str] = list(state.get("error_log") or [])
        levels = topological_sort(task_plan)
        updated_plan: list[TaskNode] = list(task_plan)

        for level in levels:
            for task in level:
                task_model = task.get("assigned_model", "reasoning")
                model_type = "code" if task_model == "code" else "reasoning"

                user_context = build_executor_context(task, state)

                try:
                    parsed = await self._invoke_json(model_type, user_context, state)
                except AgentError as exc:
                    error_log.append(str(exc)[:500])
                    _mark_task(updated_plan, task["id"], "failed")
                    continue

                code = parsed.get("code", "")
                if not code or not isinstance(code, str):
                    error_log.append(f"executor task {task['id']}: LLM returned no code")
                    _mark_task(updated_plan, task["id"], "failed")
                    continue

                sandbox_result: SandboxResult = await execute_code(
                    code=code,
                    timeout=_SANDBOX_TIMEOUT,
                    task_id=task["id"],
                )

                if sandbox_result.success:
                    execution_output[task["id"]] = sandbox_result.stdout
                    _mark_task(updated_plan, task["id"], "done")
                    logger.info(
                        "executor: task=%s done wall_ms=%d", task["id"], sandbox_result.wall_ms
                    )
                else:
                    stderr_snippet = sandbox_result.stderr[:_STDERR_MAX_CHARS]
                    error_log.append(f"executor task {task['id']}: {stderr_snippet}")
                    _mark_task(updated_plan, task["id"], "failed")
                    logger.warning(
                        "executor: task=%s failed stderr=%r", task["id"], stderr_snippet
                    )

        return {
            "task_plan": updated_plan,
            "execution_output": execution_output,
            "error_log": error_log,
        }


def _mark_task(plan: list[TaskNode], task_id: str, status: str) -> None:
    for task in plan:
        if task["id"] == task_id:
            task["status"] = status  # type: ignore[typeddict-item]
            return
