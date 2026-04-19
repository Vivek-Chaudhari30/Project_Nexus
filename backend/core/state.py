"""
NexusState — the single shared state object for the entire agent pipeline.

Architecture rule: all agents read/write this object through LangGraph.
No agent holds private state between invocations.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict


class TaskNode(TypedDict):
    id: str
    description: str
    status: Literal["pending", "in_progress", "done", "failed"]
    depends_on: list[str]
    tool_hints: list[str]
    assigned_model: Literal["reasoning", "code", "extract"]
    output: str | None


class ToolResult(TypedDict):
    tool: str
    task_id: str
    ok: bool
    data: str
    error: str | None


class MemoryItem(TypedDict):
    session_id: str
    goal: str
    quality_score: float
    content_preview: str
    output_type: str


class NexusState(TypedDict, total=False):
    # Core identity — always set on init
    user_goal: str
    session_id: str
    user_id: str

    # Pipeline state
    task_plan: list[TaskNode]
    research_context: dict[str, str]          # task_id → gathered text
    execution_output: dict[str, str]           # task_id → stdout
    verification_report: dict[str, Any]

    # Reflection loop
    quality_score: float
    reflection_feedback: str
    iteration_count: int
    max_iterations: int

    # Cross-session memory (Pinecone recall, loaded at session start)
    session_memory: list[MemoryItem]

    # Error tracking
    error_log: list[str]

    # Set by output node when loop exits without meeting quality gate
    disclaimer: str | None


def initial_state(
    user_goal: str,
    session_id: str,
    user_id: str,
    session_memory: list[MemoryItem] | None = None,
) -> NexusState:
    """Return a fully-initialised NexusState for a new session."""
    return NexusState(
        user_goal=user_goal,
        session_id=session_id,
        user_id=user_id,
        task_plan=[],
        research_context={},
        execution_output={},
        verification_report={},
        quality_score=0.0,
        reflection_feedback="",
        iteration_count=0,
        max_iterations=3,
        session_memory=session_memory or [],
        error_log=[],
        disclaimer=None,
    )
