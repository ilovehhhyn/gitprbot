from __future__ import annotations

import asyncio

from gitprbot.db.connection import get_db
from gitprbot.db.jobs import get_job, mark_job_started, update_job_status
from gitprbot.observability.logging import log_event
from gitprbot.worker.pr_flow import run_pr_flow
from gitprbot.worker.queue import dequeue_job


async def start_worker() -> None:
    asyncio.create_task(_worker_loop())


async def _worker_loop() -> None:
    log_event("worker_started")
    while True:
        job_id = await dequeue_job()
        try:
            async with get_db() as db:
                await mark_job_started(db, job_id)
            await run_pr_flow(job_id)
        except Exception as exc:
            log_event("worker_error", job_id=job_id, error=str(exc))
            async with get_db() as db:
                await update_job_status(db, job_id, "infra_error", finished=True)
