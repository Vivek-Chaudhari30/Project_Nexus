#!/usr/bin/env python3
"""
Accuracy evaluation script for Project Nexus.

Submits 6 representative goals to the running API, waits for completion via
WebSocket, and reports quality scores alongside pass/fail status.

Usage:
    python scripts/eval_accuracy.py [--base-url http://localhost] [--email eval@nexus.dev] [--password evalpassword123]

Exit code 0 if all cases pass (quality >= 0.85), 1 otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import websockets

_DEFAULT_BASE = "http://localhost"
_PASS_THRESHOLD = 0.85
_WS_TIMEOUT = 300  # seconds per case


@dataclass
class EvalCase:
    name: str
    goal: str
    category: str
    expected_output_type: str


@dataclass
class EvalResult:
    case: EvalCase
    quality_score: float = 0.0
    iterations: int = 0
    elapsed_s: float = 0.0
    disclaimer: str | None = None
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and self.quality_score >= _PASS_THRESHOLD


_CASES: list[EvalCase] = [
    EvalCase(
        name="research_llm_benchmarks",
        goal="Summarise the current state of LLM reasoning benchmarks (MMLU, MATH, HumanEval) and rank the top 5 models as of 2024.",
        category="research",
        expected_output_type="research",
    ),
    EvalCase(
        name="code_binary_search",
        goal="Write a well-tested Python implementation of binary search on a sorted list, including edge cases for empty lists and single elements.",
        category="code",
        expected_output_type="code",
    ),
    EvalCase(
        name="analysis_openai_vs_anthropic",
        goal="Compare OpenAI and Anthropic on safety approach, product strategy, and commercial traction. Provide a structured analysis with a recommendation.",
        category="analysis",
        expected_output_type="analysis",
    ),
    EvalCase(
        name="writing_cover_letter",
        goal="Write a professional cover letter for a Senior Software Engineer applying to a fintech startup that builds trading infrastructure.",
        category="writing",
        expected_output_type="writing",
    ),
    EvalCase(
        name="multi_step_data_pipeline",
        goal="Design and implement a Python data pipeline that reads a CSV of sales records, computes monthly revenue totals, and outputs a markdown report.",
        category="multi_step",
        expected_output_type="code",
    ),
    EvalCase(
        name="cross_session_memory",
        goal="Build a simple recommendation engine in Python that uses collaborative filtering on a user-item matrix.",
        category="cross_session_memory",
        expected_output_type="code",
    ),
]


async def _register_or_login(client: httpx.AsyncClient, base: str, email: str, password: str) -> str:
    resp = await client.post(f"{base}/api/v1/auth/register", json={"email": email, "password": password})
    if resp.status_code == 409:
        resp = await client.post(f"{base}/api/v1/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _create_session(client: httpx.AsyncClient, base: str, token: str, goal: str) -> str:
    resp = await client.post(
        f"{base}/api/v1/sessions",
        json={"goal": goal},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()["session_id"]


async def _run_via_ws(base: str, token: str, session_id: str, goal: str) -> dict[str, Any]:
    ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
    uri = f"{ws_base}/ws/run/{session_id}?token={token}"
    result: dict[str, Any] = {"quality_score": 0.0, "iterations": 0, "disclaimer": None}

    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "start", "goal": goal}))
        deadline = time.monotonic() + _WS_TIMEOUT
        async for raw in ws:
            if time.monotonic() > deadline:
                raise TimeoutError(f"WebSocket timed out after {_WS_TIMEOUT}s")
            frame: dict[str, Any] = json.loads(raw)
            ftype = frame.get("type", "")
            if ftype == "quality_score":
                result["quality_score"] = frame.get("score", 0.0)
            elif ftype == "replan":
                result["iterations"] = frame.get("iteration", result["iterations"])
            elif ftype == "done":
                result["iterations"] = frame.get("iteration", result["iterations"])
                result["disclaimer"] = frame.get("disclaimer")
                break
            elif ftype == "error":
                raise RuntimeError(frame.get("message", "unknown error"))

    return result


async def _eval_case(base: str, token: str, case: EvalCase) -> EvalResult:
    result = EvalResult(case=case)
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            session_id = await _create_session(client, base, token, case.goal)
        ws_result = await _run_via_ws(base, token, session_id, case.goal)
        result.quality_score = ws_result["quality_score"]
        result.iterations = ws_result["iterations"]
        result.disclaimer = ws_result["disclaimer"]
    except Exception as exc:
        result.error = str(exc)
    result.elapsed_s = time.monotonic() - t0
    return result


def _print_report(results: list[EvalResult]) -> None:
    col = {"name": 30, "cat": 18, "score": 7, "itr": 4, "time": 7, "status": 8}
    header = (
        f"{'Case':<{col['name']}} {'Category':<{col['cat']}} "
        f"{'Score':>{col['score']}} {'Itr':>{col['itr']}} "
        f"{'Time(s)':>{col['time']}} {'Status':>{col['status']}}"
    )
    sep = "-" * len(header)
    print("\n" + sep)
    print("  Project Nexus — Accuracy Evaluation Report")
    print(sep)
    print(header)
    print(sep)

    passed = 0
    for r in results:
        status = "PASS" if r.passed else ("ERROR" if r.error else "FAIL")
        score_str = f"{r.quality_score:.3f}" if not r.error else "  N/A"
        itr_str = str(r.iterations) if not r.error else "-"
        time_str = f"{r.elapsed_s:.1f}s"
        print(
            f"{r.case.name:<{col['name']}} {r.case.category:<{col['cat']}} "
            f"{score_str:>{col['score']}} {itr_str:>{col['itr']}} "
            f"{time_str:>{col['time']}} {status:>{col['status']}}"
        )
        if r.disclaimer:
            print(f"  {'':>{col['name']}} disclaimer: {r.disclaimer}")
        if r.error:
            print(f"  {'':>{col['name']}} error: {r.error}")
        if r.passed:
            passed += 1

    print(sep)
    total = len(results)
    print(f"  Result: {passed}/{total} passed  (threshold: quality >= {_PASS_THRESHOLD})")
    print(sep + "\n")


async def _main(base: str, email: str, password: str) -> int:
    print(f"Connecting to {base} …")
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _register_or_login(client, base, email, password)
    print(f"Authenticated as {email}\n")
    print(f"Running {len(_CASES)} eval cases (timeout {_WS_TIMEOUT}s each) …\n")

    results: list[EvalResult] = []
    for case in _CASES:
        print(f"  [{_CASES.index(case) + 1}/{len(_CASES)}] {case.name} …", end=" ", flush=True)
        result = await _eval_case(base, token, case)
        status = "PASS" if result.passed else ("ERROR" if result.error else "FAIL")
        print(status)
        results.append(result)

    _print_report(results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project Nexus accuracy evaluator")
    parser.add_argument("--base-url", default=_DEFAULT_BASE, help="Base URL of the Nexus API")
    parser.add_argument("--email", default="eval@nexus.dev")
    parser.add_argument("--password", default="evalpassword123!!")
    args = parser.parse_args()

    sys.exit(asyncio.run(_main(args.base_url, args.email, args.password)))
