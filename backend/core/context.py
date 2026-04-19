"""
Context assembly — the ONLY place that builds user messages for agents.

Architecture rule: if an agent needs new context, extend the corresponding
build_*_context function here. Never assemble prompts inside agent files.

Section 8 rules enforced here:
  1. Static system prompt always at position 0 (callers load it separately).
  2. Agents receive ONLY the fields they need (scoped injection).
  3. Dict iteration is sorted by key (deterministic ordering → stable cache key).
  4. Per-agent token budgets enforced via _truncate().
  5. research_context / execution_output > 6k tokens → summarise each entry to 500 tokens.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.state import NexusState, TaskNode

# ── Token budget constants (Section 8) ───────────────────────────────────────
# Approximation: 1 token ≈ 4 chars
_CHARS_PER_TOKEN = 4
_PLANNER_INPUT_BUDGET  = 4_000 * _CHARS_PER_TOKEN   # 16 000 chars
_EXECUTOR_INPUT_BUDGET = 8_000 * _CHARS_PER_TOKEN   # 32 000 chars
_VERIFIER_INPUT_BUDGET = 12_000 * _CHARS_PER_TOKEN  # 48 000 chars
_REFLECTOR_INPUT_BUDGET = 8_000 * _CHARS_PER_TOKEN  # 32 000 chars
_CONTEXT_SUMMARISE_THRESHOLD = 6_000 * _CHARS_PER_TOKEN  # 24 000 chars

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_prompt_cache: dict[str, str] = {}


def load_prompt(agent: str) -> str:
    """Load and cache the system prompt markdown for an agent."""
    if agent not in _prompt_cache:
        path = _PROMPTS_DIR / f"{agent}.md"
        _prompt_cache[agent] = path.read_text(encoding="utf-8")
    return _prompt_cache[agent]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate(text: str, max_chars: int, label: str = "") -> str:
    if len(text) <= max_chars:
        return text
    suffix = f"\n... [{label} truncated to {max_chars // _CHARS_PER_TOKEN} tokens]"
    return text[: max_chars - len(suffix)] + suffix


def _to_json(obj: Any) -> str:
    """Serialise with sorted keys for deterministic ordering."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _summarise_map(mapping: dict[str, str], entry_limit: int = 500 * _CHARS_PER_TOKEN) -> dict[str, str]:
    """Truncate each value to entry_limit chars. Used when total context exceeds threshold."""
    return {k: _truncate(v, entry_limit, label=k) for k, v in sorted(mapping.items())}


def _maybe_summarise(mapping: dict[str, str]) -> dict[str, str]:
    """Apply per-entry summarisation only if the total serialised size exceeds 6k tokens."""
    raw = _to_json(mapping)
    if len(raw) > _CONTEXT_SUMMARISE_THRESHOLD:
        return _summarise_map(mapping)
    return dict(sorted(mapping.items()))  # still sort keys for determinism


# ── Context builders ──────────────────────────────────────────────────────────

def build_planner_context(state: NexusState) -> str:
    """
    Section 8 — PLANNER CONTEXT.
    Token budget: 4 000 tokens input.
    """
    parts: list[str] = []

    parts.append(f"Goal: {state['user_goal']}")

    memory = state.get("session_memory") or []
    if memory:
        lines = ["", "Prior relevant work from your past sessions:"]
        for m in memory[:5]:
            score = round(m["quality_score"], 2)
            preview = m["content_preview"][:200]
            lines.append(f"- ({score}) {m['goal']} → {preview}")
        parts.append("\n".join(lines))

    iteration = state.get("iteration_count", 0)
    if iteration > 1:
        prev_score = state.get("quality_score", 0.0)
        feedback = state.get("reflection_feedback", "")
        parts.append(
            f"\nThis is iteration {iteration}. The previous attempt scored "
            f"{prev_score:.2f} and the Reflector flagged:\n{feedback}\n"
            "Produce a REVISED plan that addresses these issues."
        )

    context = "\n\n".join(parts)
    return _truncate(context, _PLANNER_INPUT_BUDGET, label="planner_context")


def build_executor_context(task: TaskNode, state: NexusState) -> str:
    """
    Section 8 — EXECUTOR CONTEXT (per-task).
    Token budget: 8 000 tokens input.
    """
    research_ctx = state.get("research_context") or {}
    exec_out = state.get("execution_output") or {}

    task_research = _truncate(
        research_ctx.get(task["id"], "No research context available."),
        max_chars=3_000 * _CHARS_PER_TOKEN,
        label="research_context",
    )

    dep_lines: list[str] = []
    for dep_id in sorted(task.get("depends_on") or []):
        dep_out = exec_out.get(dep_id, "(no output)")
        dep_lines.append(f"- {dep_id}: {_truncate(dep_out, 1_000 * _CHARS_PER_TOKEN, dep_id)}")

    parts = [
        f"Task ID: {task['id']}",
        f"Description: {task['description']}",
        f"Tool hints: {', '.join(task.get('tool_hints') or [])}",
        f"Research context for this task:\n{task_research}",
    ]
    if dep_lines:
        parts.append("Outputs from dependencies:\n" + "\n".join(dep_lines))
    parts.append("Generate a Python script. Use print() for captured output.")

    context = "\n\n".join(parts)
    return _truncate(context, _EXECUTOR_INPUT_BUDGET, label="executor_context")


def build_verifier_context(state: NexusState) -> str:
    """
    Section 8 — VERIFIER CONTEXT.
    Token budget: 12 000 tokens input.
    """
    research_ctx = state.get("research_context") or {}
    exec_out = state.get("execution_output") or {}

    summarised_research = _maybe_summarise(research_ctx)
    summarised_exec = _maybe_summarise(exec_out)

    parts = [
        f"Original goal: {state['user_goal']}",
        f"Task plan:\n{_to_json(state.get('task_plan') or [])}",
        f"Research context (summarised):\n{_to_json(summarised_research)}",
        "Execution outputs:\n"
        + _truncate(_to_json(summarised_exec), 8_000 * _CHARS_PER_TOKEN, "execution_output"),
        "Verify completeness, factual_grounding, and format_compliance.\n"
        "Output the verification report JSON.",
    ]

    context = "\n\n".join(parts)
    return _truncate(context, _VERIFIER_INPUT_BUDGET, label="verifier_context")


def build_reflector_context(state: NexusState) -> str:
    """
    Section 8 — REFLECTOR CONTEXT.
    Token budget: 8 000 tokens input.
    """
    exec_out = state.get("execution_output") or {}
    error_log = state.get("error_log") or []

    parts = [
        f"Original goal: {state['user_goal']}",
        f"Iteration: {state.get('iteration_count', 1)} of {state.get('max_iterations', 3)}",
        f"Verifier report:\n{_to_json(state.get('verification_report') or {})}",
        "Execution output (truncated preview):\n"
        + _truncate(_to_json(dict(sorted(exec_out.items()))), 4_000 * _CHARS_PER_TOKEN, "execution_output"),
        f"Error log (last 10):\n{_to_json(error_log[-10:])}",
    ]

    context = "\n\n".join(parts)
    return _truncate(context, _REFLECTOR_INPUT_BUDGET, label="reflector_context")
