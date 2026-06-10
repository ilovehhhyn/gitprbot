from __future__ import annotations

import asyncio
from typing import Any

from gitprbot.machines.client import get_machines_client
from gitprbot.machines.errors import ExecutionFailed

TERMINAL = {"succeeded", "failed", "cancelled", "expired"}


async def run_on_machine(
    machine_id: str,
    command: list[str],
    timeout_ms: int = 60_000,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> str:
    """Execute a command on a Dedalus machine and return stdout.

    The Dedalus SDK is synchronous; all blocking calls run in a thread executor
    so they don't block the event loop. Polls with exponential backoff (0.5s → 2s).
    """
    client = get_machines_client()
    loop = asyncio.get_event_loop()

    kwargs: dict[str, Any] = {"command": command, "timeout_ms": timeout_ms}
    if cwd:
        kwargs["cwd"] = cwd
    if env:
        kwargs["env"] = env
    if stdin:
        kwargs["stdin"] = stdin

    exc = await loop.run_in_executor(
        None, lambda: client.machines.executions.create(machine_id=machine_id, **kwargs)
    )

    delay = 0.5
    while exc.status not in TERMINAL:
        if exc.status == "wake_in_progress":
            wait = max((exc.retry_after_ms or 0) / 1000, 1.0)
        else:
            wait = delay
        await asyncio.sleep(wait)
        delay = min(delay * 2, 2.0)
        exc_id = exc.execution_id
        exc = await loop.run_in_executor(
            None,
            lambda: client.machines.executions.retrieve(
                machine_id=machine_id, execution_id=exc_id
            ),
        )

    if exc.status != "succeeded":
        raise ExecutionFailed(
            status=exc.status,
            error_code=exc.error_code or "",
            error_message=exc.error_message or "",
        )

    exc_id = exc.execution_id
    out = await loop.run_in_executor(
        None,
        lambda: client.machines.executions.output(
            machine_id=machine_id, execution_id=exc_id
        ),
    )
    return out.stdout or ""
