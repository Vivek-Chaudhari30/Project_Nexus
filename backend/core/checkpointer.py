"""
AsyncPostgresSaver wrapper for LangGraph checkpointing.

Architecture rule: every agent transition writes a checkpoint. If setup
fails the caller must abort — never continue without a working checkpointer.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


@asynccontextmanager
async def get_checkpointer(conn_string: str) -> AsyncIterator[AsyncPostgresSaver]:
    """
    Async context manager that yields a ready-to-use AsyncPostgresSaver.

    Calls setup() on first use so the langgraph_checkpoints table is
    created if it does not already exist. Callers must not swallow errors
    from this function — a failed checkpointer means the session cannot
    guarantee replay.

    Usage::
        async with get_checkpointer(cfg.database_url) as saver:
            graph = build_graph().compile(checkpointer=saver)
    """
    async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
        await saver.setup()
        yield saver
