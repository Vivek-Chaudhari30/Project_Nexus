"""
Unit tests for Phase 3: state types, prompt loading, and context assembly.

The spec (Phase 3) requires asserting:
  - Deterministic ordering (same input → same output, no dict key shuffle)
  - Token budgets are respected (output never exceeds the per-agent limit)
"""
from __future__ import annotations

import pytest

from backend.core.context import (
    _EXECUTOR_INPUT_BUDGET,
    _PLANNER_INPUT_BUDGET,
    _REFLECTOR_INPUT_BUDGET,
    _VERIFIER_INPUT_BUDGET,
    build_executor_context,
    build_planner_context,
    build_reflector_context,
    build_verifier_context,
    load_prompt,
)
from backend.core.state import NexusState, TaskNode, initial_state

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def base_state() -> NexusState:
    return initial_state(
        user_goal="Research the latest advances in transformer architectures",
        session_id="sess-001",
        user_id="user-001",
    )


@pytest.fixture()
def rich_state(base_state: NexusState) -> NexusState:
    base_state["task_plan"] = [
        TaskNode(
            id="t1",
            description="Search for recent transformer papers",
            status="done",
            depends_on=[],
            tool_hints=["web_search"],
            assigned_model="reasoning",
            output="Found 5 relevant papers.",
        ),
        TaskNode(
            id="t2",
            description="Summarise findings into a report",
            status="done",
            depends_on=["t1"],
            tool_hints=[],
            assigned_model="reasoning",
            output="Report: ...",
        ),
    ]
    base_state["research_context"] = {
        "t1": "Attention Is All You Need. Source: arxiv.org/abs/1706.03762",
        "t2": "Flash Attention 3 reduces memory by 50%. Source: arxiv.org",
    }
    base_state["execution_output"] = {"t1": "paper list printed", "t2": "report text"}
    base_state["verification_report"] = {
        "overall_pass": True,
        "completeness": {"pass": True, "score": 1.0},
        "factual_grounding": {"pass": True, "score": 0.95},
        "format_compliance": {"pass": True, "score": 1.0},
    }
    base_state["quality_score"] = 0.78
    base_state["reflection_feedback"] = "Add more depth on Flash Attention."
    base_state["iteration_count"] = 2
    base_state["error_log"] = ["t1: minor timeout warning"]
    return base_state


@pytest.fixture()
def sample_task(rich_state: NexusState) -> TaskNode:
    return rich_state["task_plan"][1]  # t2, depends on t1


# ── State type tests ──────────────────────────────────────────────────────────

class TestInitialState:
    def test_required_fields_present(self, base_state: NexusState) -> None:
        assert base_state["user_goal"] == "Research the latest advances in transformer architectures"
        assert base_state["session_id"] == "sess-001"
        assert base_state["iteration_count"] == 0
        assert base_state["max_iterations"] == 3

    def test_collections_empty(self, base_state: NexusState) -> None:
        assert base_state["task_plan"] == []
        assert base_state["research_context"] == {}
        assert base_state["execution_output"] == {}
        assert base_state["error_log"] == []

    def test_quality_score_zero(self, base_state: NexusState) -> None:
        assert base_state["quality_score"] == 0.0

    def test_disclaimer_none(self, base_state: NexusState) -> None:
        assert base_state["disclaimer"] is None


# ── Prompt loading tests ──────────────────────────────────────────────────────

class TestPromptLoading:
    @pytest.mark.parametrize("agent", ["planner", "researcher", "executor", "verifier", "reflector"])
    def test_prompt_loads_non_empty(self, agent: str) -> None:
        prompt = load_prompt(agent)
        assert len(prompt) > 100

    @pytest.mark.parametrize("agent", ["planner", "executor", "verifier", "reflector"])
    def test_prompt_ends_with_json_instruction(self, agent: str) -> None:
        prompt = load_prompt(agent)
        assert "Respond ONLY with valid JSON" in prompt

    def test_prompt_cached_same_object(self) -> None:
        p1 = load_prompt("planner")
        p2 = load_prompt("planner")
        assert p1 is p2  # lru-cache returns the identical string object


# ── Planner context tests ─────────────────────────────────────────────────────

class TestBuildPlannerContext:
    def test_contains_user_goal(self, base_state: NexusState) -> None:
        ctx = build_planner_context(base_state)
        assert base_state["user_goal"] in ctx

    def test_no_replan_section_on_first_iteration(self, base_state: NexusState) -> None:
        base_state["iteration_count"] = 1
        ctx = build_planner_context(base_state)
        assert "REVISED" not in ctx

    def test_replan_section_on_second_iteration(self, rich_state: NexusState) -> None:
        ctx = build_planner_context(rich_state)
        assert "REVISED" in ctx
        assert "0.78" in ctx
        assert "Flash Attention" in ctx

    def test_memory_injected_when_present(self, base_state: NexusState) -> None:
        base_state["session_memory"] = [
            {
                "session_id": "old-1",
                "goal": "Transformers overview",
                "quality_score": 0.91,
                "content_preview": "Key insight: attention heads...",
                "output_type": "research",
            }
        ]
        ctx = build_planner_context(base_state)
        assert "Prior relevant work" in ctx
        assert "0.91" in ctx

    def test_within_token_budget(self, rich_state: NexusState) -> None:
        ctx = build_planner_context(rich_state)
        assert len(ctx) <= _PLANNER_INPUT_BUDGET

    def test_deterministic(self, rich_state: NexusState) -> None:
        ctx1 = build_planner_context(rich_state)
        ctx2 = build_planner_context(rich_state)
        assert ctx1 == ctx2


# ── Executor context tests ────────────────────────────────────────────────────

class TestBuildExecutorContext:
    def test_contains_task_id_and_description(self, sample_task: TaskNode, rich_state: NexusState) -> None:
        ctx = build_executor_context(sample_task, rich_state)
        assert "t2" in ctx
        assert "Summarise findings" in ctx

    def test_contains_dependency_output(self, sample_task: TaskNode, rich_state: NexusState) -> None:
        ctx = build_executor_context(sample_task, rich_state)
        assert "t1" in ctx
        assert "paper list printed" in ctx

    def test_contains_research_context(self, sample_task: TaskNode, rich_state: NexusState) -> None:
        ctx = build_executor_context(sample_task, rich_state)
        assert "Flash Attention" in ctx

    def test_within_token_budget(self, sample_task: TaskNode, rich_state: NexusState) -> None:
        ctx = build_executor_context(sample_task, rich_state)
        assert len(ctx) <= _EXECUTOR_INPUT_BUDGET

    def test_deterministic(self, sample_task: TaskNode, rich_state: NexusState) -> None:
        ctx1 = build_executor_context(sample_task, rich_state)
        ctx2 = build_executor_context(sample_task, rich_state)
        assert ctx1 == ctx2

    def test_deps_sorted_for_determinism(self, rich_state: NexusState) -> None:
        # Task with multiple deps — order must be alphabetical
        task = TaskNode(
            id="t3",
            description="Aggregate results",
            status="pending",
            depends_on=["t2", "t1"],  # intentionally unsorted
            tool_hints=[],
            assigned_model="reasoning",
            output=None,
        )
        ctx1 = build_executor_context(task, rich_state)
        ctx2 = build_executor_context(task, rich_state)
        assert ctx1 == ctx2
        # t1 should appear before t2 (sorted order)
        assert ctx1.index("- t1:") < ctx1.index("- t2:")


# ── Verifier context tests ────────────────────────────────────────────────────

class TestBuildVerifierContext:
    def test_contains_goal_and_plan(self, rich_state: NexusState) -> None:
        ctx = build_verifier_context(rich_state)
        assert rich_state["user_goal"] in ctx
        assert "t1" in ctx

    def test_within_token_budget(self, rich_state: NexusState) -> None:
        ctx = build_verifier_context(rich_state)
        assert len(ctx) <= _VERIFIER_INPUT_BUDGET

    def test_deterministic(self, rich_state: NexusState) -> None:
        ctx1 = build_verifier_context(rich_state)
        ctx2 = build_verifier_context(rich_state)
        assert ctx1 == ctx2

    def test_research_context_sorted_by_key(self, rich_state: NexusState) -> None:
        ctx = build_verifier_context(rich_state)
        # JSON with sort_keys=True: "t1" comes before "t2"
        parsed_section = ctx[ctx.index("Research context"):]
        assert parsed_section.index('"t1"') < parsed_section.index('"t2"')


# ── Reflector context tests ───────────────────────────────────────────────────

class TestBuildReflectorContext:
    def test_contains_iteration_info(self, rich_state: NexusState) -> None:
        ctx = build_reflector_context(rich_state)
        assert "Iteration: 2 of 3" in ctx

    def test_contains_verifier_report(self, rich_state: NexusState) -> None:
        ctx = build_reflector_context(rich_state)
        assert "overall_pass" in ctx

    def test_error_log_limited_to_last_10(self, rich_state: NexusState) -> None:
        rich_state["error_log"] = [f"error {i}" for i in range(20)]
        ctx = build_reflector_context(rich_state)
        # Only last 10 appear — "error 10" through "error 19"
        assert "error 19" in ctx
        assert "error 0" not in ctx

    def test_within_token_budget(self, rich_state: NexusState) -> None:
        ctx = build_reflector_context(rich_state)
        assert len(ctx) <= _REFLECTOR_INPUT_BUDGET

    def test_deterministic(self, rich_state: NexusState) -> None:
        ctx1 = build_reflector_context(rich_state)
        ctx2 = build_reflector_context(rich_state)
        assert ctx1 == ctx2


# ── Token budget enforcement under large input ────────────────────────────────

class TestTokenBudgetEnforcement:
    def test_planner_truncates_huge_feedback(self, base_state: NexusState) -> None:
        base_state["iteration_count"] = 2
        base_state["reflection_feedback"] = "x" * (_PLANNER_INPUT_BUDGET * 2)
        ctx = build_planner_context(base_state)
        assert len(ctx) <= _PLANNER_INPUT_BUDGET

    def test_verifier_truncates_huge_execution_output(self, rich_state: NexusState) -> None:
        rich_state["execution_output"] = {f"t{i}": "y" * 5000 for i in range(20)}
        ctx = build_verifier_context(rich_state)
        assert len(ctx) <= _VERIFIER_INPUT_BUDGET

    def test_reflector_truncates_huge_exec_output(self, rich_state: NexusState) -> None:
        rich_state["execution_output"] = {"t1": "z" * 200_000}
        ctx = build_reflector_context(rich_state)
        assert len(ctx) <= _REFLECTOR_INPUT_BUDGET
