"""
WebSocket handler: /ws/run/{session_id}

Auth: JWT passed as ?token= query param (browsers can't set custom headers on WS).

Frame sequence (server → client):
  connected → agent_start/complete/progress → quality_score → (replan →) done
  or error on failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError

from backend.api.auth import decode_token
from backend.core.graph import build_graph
from backend.core.state import NexusState, initial_state
from backend.db.postgres import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()

_AGENT_NODES = {"planner", "researcher", "executor", "verifier", "reflector"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _send(ws: WebSocket, frame: dict[str, Any]) -> None:
    import contextlib
    with contextlib.suppress(Exception):
        await ws.send_text(json.dumps(frame))


async def _run_graph(
    ws: WebSocket,
    session_id: str,
    user_id: str,
    goal: str,
) -> None:
    """Execute the LangGraph pipeline and stream events to the WebSocket."""
    pool = await get_pool()

    # Mark session as running
    await pool.execute(
        "UPDATE sessions SET status = 'running' WHERE id = $1",
        UUID(session_id),
    )

    state: NexusState = initial_state(
        user_goal=goal,
        session_id=session_id,
        user_id=user_id,
    )

    # Recall cross-session memory at start
    try:
        from backend.core.memory import recall_for_user
        state["session_memory"] = await recall_for_user(user_id, goal, top_k=5)
    except Exception as exc:
        logger.warning("ws: memory recall failed: %s", exc)

    graph = build_graph()  # uses MemorySaver; checkpointer swap in Phase 11
    config = {"configurable": {"thread_id": session_id}}

    final_state: NexusState | None = None
    current_iteration = 0

    try:
        async for event in graph.astream_events(state, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name", "")

            if kind == "on_chain_start" and name in _AGENT_NODES:
                if name == "planner":
                    current_iteration += 1
                await _send(ws, {
                    "type": "agent_start",
                    "agent": name,
                    "iteration": current_iteration,
                    "ts": _now(),
                })

            elif kind == "on_chain_end" and name in _AGENT_NODES:
                output = event.get("data", {}).get("output") or {}
                preview = ""
                if name == "reflector":
                    quality = (output.get("quality_score") or 0.0)
                    await _send(ws, {
                        "type": "quality_score",
                        "score": quality,
                        "iteration": current_iteration,
                        "breakdown": output.get("dimension_scores") or {},
                    })
                elif name == "planner" and current_iteration > 1:
                    await _send(ws, {
                        "type": "replan",
                        "iteration": current_iteration,
                        "feedback": (output.get("reflection_feedback") or "")[:200],
                    })
                await _send(ws, {
                    "type": "agent_complete",
                    "agent": name,
                    "output_preview": str(preview)[:400],
                    "ts": _now(),
                })

            elif kind == "on_chain_end" and name == "output":
                final_state = event.get("data", {}).get("output")

    except Exception as exc:
        logger.error("ws: graph error session=%s: %s", session_id, exc)
        await _send(ws, {"type": "error", "code": "graph_error", "message": str(exc)[:300], "agent": None})
        await pool.execute(
            "UPDATE sessions SET status = 'failed' WHERE id = $1", UUID(session_id)
        )
        return

    # Finalise session in DB
    quality = (final_state or {}).get("quality_score") or 0.0
    disclaimer = (final_state or {}).get("disclaimer")
    iter_count = (final_state or {}).get("iteration_count") or 0

    await pool.execute(
        """
        UPDATE sessions
        SET status = 'completed', final_quality = $2,
            final_output = $3, iteration_count = $4, completed_at = now()
        WHERE id = $1
        """,
        UUID(session_id),
        quality,
        json.dumps({"disclaimer": disclaimer}),
        iter_count,
    )

    # Store to memory if quality meets threshold
    try:
        from backend.core.memory import store_if_good
        if final_state:
            output_text = json.dumps(final_state.get("execution_output") or {})
            await store_if_good(final_state, output_text)
    except Exception as exc:
        logger.warning("ws: memory store failed: %s", exc)

    await _send(ws, {
        "type": "done",
        "output": (final_state or {}).get("execution_output") or {},
        "citations": [],
        "final_score": quality,
        "disclaimer": disclaimer,
    })


@router.websocket("/ws/run/{session_id}")
async def ws_run(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(..., description="Bearer JWT"),
) -> None:
    # Validate JWT
    try:
        payload = decode_token(token)
        user_id: str = payload["sub"]
    except (JWTError, KeyError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify session ownership
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT goal, status, user_id FROM sessions WHERE id = $1",
        UUID(session_id),
    )
    if row is None or str(row["user_id"]) != user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if row["status"] not in ("pending",):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await _send(websocket, {"type": "connected", "session_id": session_id})

    goal = row["goal"]
    started = False

    try:
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            frame = json.loads(raw)
            frame_type = frame.get("type")

            if frame_type == "ping":
                await _send(websocket, {"type": "pong"})

            elif frame_type == "start":
                if started:
                    await _send(websocket, {"type": "error", "code": "already_started", "message": "Session already running", "agent": None})
                    continue
                started = True
                goal = frame.get("goal") or goal
                asyncio.create_task(_run_graph(websocket, session_id, user_id, goal))

            elif frame_type == "abort":
                await pool.execute(
                    "UPDATE sessions SET status = 'aborted' WHERE id = $1", UUID(session_id)
                )
                break

    except TimeoutError:
        pass  # client idle — close cleanly
    except WebSocketDisconnect:
        logger.info("ws: client disconnected session=%s", session_id)
    except Exception as exc:
        logger.error("ws: unexpected error session=%s: %s", session_id, exc)
    finally:
        import contextlib
        with contextlib.suppress(Exception):
            await websocket.close()
