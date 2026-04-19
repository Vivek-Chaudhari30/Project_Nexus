"""
Tool registry for Project Nexus.

Architecture rule: new tools are added by decorating an async function with
@tool in their own module. Importing the module self-registers the tool.
Agents must never hardcode tool lists — they read from REGISTRY.

Usage:
    from backend.tools import REGISTRY, tool

    @tool
    async def my_tool(query: str, session_id: str) -> str:
        ...
"""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

# Global registry: tool_name → async callable
REGISTRY: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}


def tool(fn: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Decorator that registers an async tool function by its __name__."""
    if not asyncio_is_coroutine(fn):
        raise TypeError(f"@tool requires an async function, got {fn!r}")
    REGISTRY[fn.__name__] = fn
    return fn


def asyncio_is_coroutine(fn: Any) -> bool:
    import asyncio
    return asyncio.iscoroutinefunction(fn)


def get_tool(name: str) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Return a registered tool by name, raising KeyError if absent."""
    try:
        return REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(REGISTRY))
        raise KeyError(f"Tool {name!r} not registered. Available: {available}") from None


def _import_all_tools() -> None:
    """Import every tool module so they self-register via @tool."""
    from backend.tools import (  # noqa: F401
        api_caller,
        code_executor,
        file_writer,
        rag_recall,
        web_search,
    )


_import_all_tools()
