from __future__ import annotations

import asyncio
from typing import Optional

_queue: Optional[asyncio.Queue[str]] = None


def get_queue() -> asyncio.Queue[str]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def enqueue_job(job_id: str) -> None:
    await get_queue().put(job_id)


async def dequeue_job() -> str:
    return await get_queue().get()
