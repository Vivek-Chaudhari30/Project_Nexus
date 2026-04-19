"""
Unit tests for all five agents (Phase 5).

Covers: PlannerAgent, ResearcherAgent, ExecutorAgent, VerifierAgent, ReflectorAgent.
All LLM and tool calls are mocked — no real API calls made.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.executor import ExecutorAgent, SandboxResult
from backend.agents.planner import PlannerAgent, validate_task_dag
from backend.agents.reflector import ReflectorAgent, _validate_reflection
from backend.agents.researcher import ResearcherAgent, topological_sort
from backend.agents.verifier import VerifierAgent, _validate_report
from backend.core.state import NexusState, TaskNode, initial_state

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def base_state() -> NexusState:
    return initial_state(
        user_goal="Analyse the impact of LLMs on software engineering",
        session_id="sess-test",
        user_id="user-test",
    )


@pytest.fixture()
def two_task_plan() -> list[TaskNode]:
    return [
        TaskNode(id="t1", description="Search for papers", status="pending",
                 depends_on=[], tool_hints=["web_search"], assigned_model="reasoning", output=None),
        TaskNode(id="t2", description="Summarise findings", status="pending",
                 depends_on=["t1"], tool_hints=[], assigned_model="reasoning", output=None),
    ]


def _mock_llm_response(content: dict[str, Any]) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(content)
    msg.usage_metadata = {}
    return msg


def _make_agent(agent_class: type, llm_response: dict[str, Any]) -> Any:
    """
    Construct an agent with get_model_router patched to avoid Settings validation,
    then wire in a mock model returning llm_response.
    """
    mock_router = MagicMock()
    with patch("backend.agents.base.get_model_router", return_value=mock_router):
        agent = agent_class()

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=_mock_llm_response(llm_response))
    agent._router = MagicMock()
    agent._router.get.return_value = mock_model
    return agent


# ══════════════════════════════════════════════════════════════════════════════
# validate_task_dag
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateTaskDag:
    def test_valid_dag_returns_task_nodes(self) -> None:
        raw = [
            {"id": "t1", "description": "Do A", "depends_on": [],
             "tool_hints": ["web_search"], "assigned_model": "reasoning"},
            {"id": "t2", "description": "Do B", "depends_on": ["t1"],
             "tool_hints": [], "assigned_model": "code"},
        ]
        nodes = validate_task_dag(raw)
        assert len(nodes) == 2
        assert nodes[0]["id"] == "t1"
        assert nodes[1]["status"] == "pending"
        assert nodes[1]["output"] is None

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            validate_task_dag([])

    def test_exceeds_max_tasks_raises(self) -> None:
        tasks = [{"id": f"t{i}", "description": "x", "depends_on": [],
                  "tool_hints": [], "assigned_model": "reasoning"} for i in range(11)]
        with pytest.raises(ValueError, match="max"):
            validate_task_dag(tasks)

    def test_duplicate_id_raises(self) -> None:
        raw = [
            {"id": "t1", "description": "A", "depends_on": [], "tool_hints": [], "assigned_model": "reasoning"},
            {"id": "t1", "description": "B", "depends_on": [], "tool_hints": [], "assigned_model": "reasoning"},
        ]
        with pytest.raises(ValueError, match="Duplicate"):
            validate_task_dag(raw)

    def test_unknown_depends_on_raises(self) -> None:
        raw = [{"id": "t1", "description": "A", "depends_on": ["t99"],
                "tool_hints": [], "assigned_model": "reasoning"}]
        with pytest.raises(ValueError, match="unknown id"):
            validate_task_dag(raw)

    def test_invalid_model_raises(self) -> None:
        raw = [{"id": "t1", "description": "A", "depends_on": [],
                "tool_hints": [], "assigned_model": "gpt-magic"}]
        with pytest.raises(ValueError, match="assigned_model"):
            validate_task_dag(raw)

    def test_missing_required_field_raises(self) -> None:
        raw = [{"id": "t1", "description": "A", "depends_on": [], "tool_hints": []}]  # no assigned_model
        with pytest.raises(ValueError, match="assigned_model"):
            validate_task_dag(raw)

    def test_unknown_tool_hints_filtered(self) -> None:
        raw = [{"id": "t1", "description": "A", "depends_on": [],
                "tool_hints": ["web_search", "totally_fake_tool"], "assigned_model": "reasoning"}]
        nodes = validate_task_dag(raw)
        assert nodes[0]["tool_hints"] == ["web_search"]

    def test_cycle_raises(self) -> None:
        raw = [
            {"id": "t1", "description": "A", "depends_on": ["t2"], "tool_hints": [], "assigned_model": "reasoning"},
            {"id": "t2", "description": "B", "depends_on": ["t1"], "tool_hints": [], "assigned_model": "reasoning"},
        ]
        with pytest.raises(ValueError, match="Circular"):
            validate_task_dag(raw)


# ══════════════════════════════════════════════════════════════════════════════
# PlannerAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestPlannerAgent:
    @pytest.mark.asyncio
    async def test_happy_path_updates_task_plan(self, base_state: NexusState) -> None:
        agent = _make_agent(PlannerAgent, {
            "tasks": [
                {"id": "t1", "description": "Search", "depends_on": [],
                 "tool_hints": ["web_search"], "assigned_model": "reasoning"},
            ]
        })
        updates = await agent.run(base_state)
        assert len(updates["task_plan"]) == 1
        assert updates["task_plan"][0]["id"] == "t1"

    @pytest.mark.asyncio
    async def test_planner_raises_on_invalid_dag(self, base_state: NexusState) -> None:
        from backend.agents.base import AgentError
        agent = _make_agent(PlannerAgent, {"tasks": []})  # empty → invalid
        with pytest.raises(AgentError):
            await agent.run(base_state)

    @pytest.mark.asyncio
    async def test_planner_uses_reasoning_model(self, base_state: NexusState) -> None:
        agent = _make_agent(PlannerAgent, {
            "tasks": [{"id": "t1", "description": "x", "depends_on": [],
                       "tool_hints": [], "assigned_model": "reasoning"}]
        })
        await agent.run(base_state)
        agent._router.get.assert_called_with("reasoning")

    @pytest.mark.asyncio
    async def test_planner_strips_markdown_fence(self, base_state: NexusState) -> None:
        raw_json = json.dumps({
            "tasks": [{"id": "t1", "description": "Search", "depends_on": [],
                       "tool_hints": [], "assigned_model": "reasoning"}]
        })
        mock_router = MagicMock()
        with patch("backend.agents.base.get_model_router", return_value=mock_router):
            agent = PlannerAgent()

        response = MagicMock()
        response.content = f"```json\n{raw_json}\n```"
        response.usage_metadata = {}
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=response)
        agent._router = MagicMock()
        agent._router.get.return_value = mock_model

        updates = await agent.run(base_state)
        assert len(updates["task_plan"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# ResearcherAgent + topological_sort
# ══════════════════════════════════════════════════════════════════════════════

class TestTopologicalSort:
    def test_single_root(self, two_task_plan: list[TaskNode]) -> None:
        levels = topological_sort(two_task_plan)
        assert len(levels) == 2
        assert levels[0][0]["id"] == "t1"
        assert levels[1][0]["id"] == "t2"

    def test_two_independent_roots(self) -> None:
        tasks = [
            TaskNode(id="t1", description="A", status="pending", depends_on=[],
                     tool_hints=[], assigned_model="reasoning", output=None),
            TaskNode(id="t2", description="B", status="pending", depends_on=[],
                     tool_hints=[], assigned_model="reasoning", output=None),
        ]
        levels = topological_sort(tasks)
        assert len(levels) == 1
        assert {t["id"] for t in levels[0]} == {"t1", "t2"}

    def test_empty_plan(self) -> None:
        assert topological_sort([]) == []


class TestResearcherAgent:
    @pytest.mark.asyncio
    async def test_calls_tool_and_writes_context(
        self, base_state: NexusState, two_task_plan: list[TaskNode]
    ) -> None:
        base_state["task_plan"] = two_task_plan
        agent = ResearcherAgent()

        with patch("backend.agents.researcher.get_tool") as mock_get_tool:
            mock_fn = AsyncMock(return_value="LLM research result from web")
            mock_get_tool.return_value = mock_fn

            updates = await agent.run(base_state)

        assert "t1" in updates["research_context"]
        assert "LLM research result" in updates["research_context"]["t1"]

    @pytest.mark.asyncio
    async def test_tool_failure_writes_no_results(
        self, base_state: NexusState, two_task_plan: list[TaskNode]
    ) -> None:
        base_state["task_plan"] = two_task_plan
        agent = ResearcherAgent()

        with patch("backend.agents.researcher.get_tool") as mock_get_tool:
            mock_fn = AsyncMock(side_effect=RuntimeError("API down"))
            mock_get_tool.return_value = mock_fn

            updates = await agent.run(base_state)

        assert "No results found" in updates["research_context"]["t1"]

    @pytest.mark.asyncio
    async def test_empty_task_plan_returns_unchanged_context(self, base_state: NexusState) -> None:
        agent = ResearcherAgent()
        updates = await agent.run(base_state)
        assert updates["research_context"] == {}

    @pytest.mark.asyncio
    async def test_tasks_without_tool_hints_get_default_message(
        self, base_state: NexusState
    ) -> None:
        task = TaskNode(id="t1", description="Write summary", status="pending",
                        depends_on=[], tool_hints=[], assigned_model="reasoning", output=None)
        base_state["task_plan"] = [task]
        agent = ResearcherAgent()

        updates = await agent.run(base_state)
        assert "No research tools" in updates["research_context"]["t1"]


# ══════════════════════════════════════════════════════════════════════════════
# ExecutorAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestExecutorAgent:
    @pytest.mark.asyncio
    async def test_successful_execution_writes_output(
        self, base_state: NexusState, two_task_plan: list[TaskNode]
    ) -> None:
        base_state["task_plan"] = two_task_plan
        agent = _make_agent(ExecutorAgent, {"code": "print('hello')"})

        with patch("backend.agents.executor.execute_code", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SandboxResult(
                success=True, stdout="hello\n", stderr="", exit_code=0, wall_ms=50
            )
            updates = await agent.run(base_state)

        assert "hello" in updates["execution_output"].get("t1", "")

    @pytest.mark.asyncio
    async def test_failed_task_marked_failed_in_plan(
        self, base_state: NexusState, two_task_plan: list[TaskNode]
    ) -> None:
        base_state["task_plan"] = two_task_plan
        agent = _make_agent(ExecutorAgent, {"code": "raise SystemExit(1)"})

        with patch("backend.agents.executor.execute_code", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SandboxResult(
                success=False, stdout="", stderr="error", exit_code=1, wall_ms=10
            )
            updates = await agent.run(base_state)

        statuses = {t["id"]: t["status"] for t in updates["task_plan"]}
        assert statuses["t1"] == "failed"

    @pytest.mark.asyncio
    async def test_sandbox_error_appended_to_error_log(
        self, base_state: NexusState, two_task_plan: list[TaskNode]
    ) -> None:
        base_state["task_plan"] = two_task_plan
        agent = _make_agent(ExecutorAgent, {"code": "1/0"})

        with patch("backend.agents.executor.execute_code", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SandboxResult(
                success=False, stdout="", stderr="ZeroDivisionError", exit_code=1, wall_ms=5
            )
            updates = await agent.run(base_state)

        assert any("ZeroDivisionError" in e for e in updates["error_log"])

    @pytest.mark.asyncio
    async def test_code_model_used_for_code_tasks(
        self, base_state: NexusState
    ) -> None:
        task = TaskNode(id="t1", description="Write a sort", status="pending",
                        depends_on=[], tool_hints=[], assigned_model="code", output=None)
        base_state["task_plan"] = [task]
        agent = _make_agent(ExecutorAgent, {"code": "print(sorted([3,1,2]))"})

        with patch("backend.agents.executor.execute_code", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SandboxResult(
                success=True, stdout="[1, 2, 3]", stderr="", exit_code=0, wall_ms=20
            )
            await agent.run(base_state)

        agent._router.get.assert_called_with("code")

    @pytest.mark.asyncio
    async def test_empty_code_response_marks_task_failed(
        self, base_state: NexusState, two_task_plan: list[TaskNode]
    ) -> None:
        base_state["task_plan"] = two_task_plan
        agent = _make_agent(ExecutorAgent, {"code": ""})  # empty code

        with patch("backend.agents.executor.execute_code", new_callable=AsyncMock) as mock_run:
            updates = await agent.run(base_state)

        mock_run.assert_not_called()
        statuses = {t["id"]: t["status"] for t in updates["task_plan"]}
        assert statuses["t1"] == "failed"


# ══════════════════════════════════════════════════════════════════════════════
# VerifierAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestVerifierAgent:
    _PASSING_REPORT = {
        "overall_pass": True,
        "completeness": {"pass": True, "score": 1.0, "notes": ""},
        "factual_grounding": {"pass": True, "score": 0.95, "notes": ""},
        "format_compliance": {"pass": True, "score": 1.0, "notes": ""},
        "ungrounded_claims": [],
        "missing_tasks": [],
    }

    @pytest.mark.asyncio
    async def test_happy_path_writes_verification_report(self, base_state: NexusState) -> None:
        agent = _make_agent(VerifierAgent, self._PASSING_REPORT)
        updates = await agent.run(base_state)
        assert updates["verification_report"]["overall_pass"] is True

    @pytest.mark.asyncio
    async def test_invalid_report_returns_failing_report(self, base_state: NexusState) -> None:
        # Missing required keys — verifier should return a safe failing report
        agent = _make_agent(VerifierAgent, {"overall_pass": True})
        updates = await agent.run(base_state)
        assert updates["verification_report"]["overall_pass"] is False

    def test_validate_report_fills_missing_dimension_defaults(self) -> None:
        raw: dict[str, Any] = {
            "overall_pass": True,
            "completeness": {"pass": True},
            "factual_grounding": {},
            "format_compliance": {"score": 0.9},
        }
        report = _validate_report(raw)
        assert report["completeness"]["score"] == 0.0
        assert report["factual_grounding"]["pass"] is False
        assert report["format_compliance"]["notes"] == ""

    def test_validate_report_raises_on_missing_required_key(self) -> None:
        with pytest.raises(ValueError, match="missing keys"):
            _validate_report({"overall_pass": True})  # missing dimensions


# ══════════════════════════════════════════════════════════════════════════════
# ReflectorAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestReflectorAgent:
    _HIGH_SCORE_REFLECTION = {
        "quality_score": 0.90,
        "dimension_scores": {
            "completeness": 0.95, "accuracy": 0.90,
            "quality": 0.88, "efficiency": 0.85, "format_score": 0.92,
        },
        "improvement_directives": [],
        "pass": True,
    }
    _LOW_SCORE_REFLECTION = {
        "quality_score": 0.60,
        "dimension_scores": {
            "completeness": 0.70, "accuracy": 0.55,
            "quality": 0.60, "efficiency": 0.65, "format_score": 0.50,
        },
        "improvement_directives": ["Improve accuracy", "Add citations"],
        "pass": False,
    }

    @pytest.mark.asyncio
    async def test_high_score_writes_quality_score(self, base_state: NexusState) -> None:
        agent = _make_agent(ReflectorAgent, self._HIGH_SCORE_REFLECTION)
        updates = await agent.run(base_state)
        assert updates["quality_score"] >= 0.85

    @pytest.mark.asyncio
    async def test_low_score_writes_feedback(self, base_state: NexusState) -> None:
        agent = _make_agent(ReflectorAgent, self._LOW_SCORE_REFLECTION)
        updates = await agent.run(base_state)
        assert updates["quality_score"] < 0.85
        assert "Improve accuracy" in updates["reflection_feedback"]

    @pytest.mark.asyncio
    async def test_directives_capped_at_5(self, base_state: NexusState) -> None:
        many_directives = {**self._LOW_SCORE_REFLECTION,
                           "improvement_directives": [f"fix {i}" for i in range(10)]}
        agent = _make_agent(ReflectorAgent, many_directives)
        updates = await agent.run(base_state)
        assert updates["reflection_feedback"].count("\n") < 5

    def test_validate_reflection_clamps_scores(self) -> None:
        raw: dict[str, Any] = {
            "quality_score": 1.5,  # > 1.0
            "dimension_scores": {
                "completeness": -0.1, "accuracy": 2.0,
                "quality": 0.8, "efficiency": 0.8, "format_score": 0.8,
            },
            "improvement_directives": [],
            "pass": True,
        }
        result = _validate_reflection(raw)
        assert 0.0 <= result["quality_score"] <= 1.0
        assert all(0.0 <= result["dimension_scores"][d] <= 1.0
                   for d in ("completeness", "accuracy", "quality", "efficiency", "format_score"))

    def test_validate_reflection_recomputes_overall_from_dims(self) -> None:
        raw: dict[str, Any] = {
            "quality_score": 0.99,  # manipulated high value
            "dimension_scores": {
                "completeness": 0.5, "accuracy": 0.5,
                "quality": 0.5, "efficiency": 0.5, "format_score": 0.5,
            },
            "improvement_directives": [],
            "pass": True,
        }
        result = _validate_reflection(raw)
        assert abs(result["quality_score"] - 0.5) < 0.01
        assert result["pass"] is False  # 0.5 < 0.85
