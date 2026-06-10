from __future__ import annotations

import functools
from enum import Enum
from typing import Callable


class ToolKind(str, Enum):
    MACHINE = "machine"
    ORCHESTRATOR = "orchestrator"


_TOOL_KIND: dict[str, ToolKind] = {}


def machine_tool(fn: Callable) -> Callable:
    """Marks a tool as machine-dispatched (runs via run_on_machine on a Dedalus VM)."""
    _TOOL_KIND[fn.__name__] = ToolKind.MACHINE

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        return await fn(*args, **kwargs)

    wrapper._tool_kind = ToolKind.MACHINE
    return wrapper


def orchestrator_tool(fn: Callable) -> Callable:
    """Marks a tool as orchestrator-direct (runs in World A, never dispatches to a machine)."""
    _TOOL_KIND[fn.__name__] = ToolKind.ORCHESTRATOR

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        return await fn(*args, **kwargs)

    wrapper._tool_kind = ToolKind.ORCHESTRATOR
    return wrapper


def get_tool_kind(fn: Callable) -> ToolKind:
    return getattr(fn, "_tool_kind", _TOOL_KIND.get(fn.__name__, ToolKind.MACHINE))
