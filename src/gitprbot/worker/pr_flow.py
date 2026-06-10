from __future__ import annotations

import asyncio

from gitprbot.agent.loop import NeedsHuman, run_agent_loop
from gitprbot.config import settings
from gitprbot.db.connection import get_db
from gitprbot.db.jobs import get_job, get_recent_succeeded_job_for_repo, update_job_status
from gitprbot.db.locks import acquire_lock, heartbeat_lock, release_lock, sweep_stale_locks
from gitprbot.db.repos import clear_machine, get_repo
from gitprbot.db.schema import JobRow
from gitprbot.machines.bootstrap import bootstrap_machine
from gitprbot.machines.client import create_machine, sleep_machine, verify_machine_exists
from gitprbot.machines.errors import MachineGone
from gitprbot.models.costs import CostCeilingExceeded
from gitprbot.observability.alerts import AlertType, alert
from gitprbot.observability.logging import log_event


async def run_pr_flow(job_id: str) -> None:
    async with get_db() as db:
        job = await get_job(db, job_id)
        if job is None:
            log_event("job_not_found", job_id=job_id)
            return

        # Acquire per-repo leased lock (retry with backoff)
        acquired = False
        for attempt in range(12):
            acquired = await acquire_lock(db, job.repo_full_name, settings.worker_id)
            if acquired:
                break
            await asyncio.sleep(5 * (attempt + 1))

        if not acquired:
            await update_job_status(db, job_id, "queued", finished=False)
            from gitprbot.worker.queue import enqueue_job
            await enqueue_job(job_id)
            return

    heartbeat_task = asyncio.create_task(_heartbeat_loop(job.repo_full_name))

    try:
        async with get_db() as db:
            machine_id = await _ensure_machine(db, job)

        is_amend = await _is_amend_job(job)

        async with get_db() as db:
            pr_url = await run_agent_loop(job, machine_id, db, is_amend=is_amend)
            await update_job_status(
                db, job_id, "succeeded", result_pr_url=pr_url, finished=True
            )
        log_event("pr_flow_succeeded", job_id=job_id, pr_url=pr_url)

    except NeedsHuman as exc:
        async with get_db() as db:
            await update_job_status(
                db, job_id, "needs_human", result_pr_url=exc.pr_url, finished=True
            )
    except CostCeilingExceeded as exc:
        log_event("cost_ceiling", job_id=job_id, cost=exc.current)
        async with get_db() as db:
            await update_job_status(db, job_id, "failed", finished=True)
    except TimeoutError as exc:
        log_event("wall_clock_exceeded", job_id=job_id, error=str(exc))
        async with get_db() as db:
            await update_job_status(db, job_id, "failed", finished=True)
    except Exception as exc:
        log_event("pr_flow_error", job_id=job_id, error=str(exc))
        async with get_db() as db:
            await update_job_status(db, job_id, "failed", finished=True)
    finally:
        heartbeat_task.cancel()
        async with get_db() as db:
            await release_lock(db, job.repo_full_name, settings.worker_id)
        try:
            async with get_db() as db:
                repo = await get_repo(db, job.repo_full_name)
                if repo and repo.machine_id:
                    await sleep_machine(repo.machine_id)
        except Exception:
            pass


async def _ensure_machine(db, job: JobRow) -> str:
    """Verify the machine exists; re-provision if not."""
    repo = await get_repo(db, job.repo_full_name)

    if repo is None or repo.machine_id is None:
        machine_id = await create_machine(job.repo_full_name)
        await db.execute(
            "UPDATE repos SET machine_id = ? WHERE repo_full_name = ?",
            (machine_id, job.repo_full_name),
        )
        await db.commit()
    else:
        machine_id = repo.machine_id
        try:
            await verify_machine_exists(machine_id)
        except MachineGone:
            alert(AlertType.DUPLICATE_MACHINE, repo=job.repo_full_name, old_machine=machine_id)
            await clear_machine(db, job.repo_full_name)
            machine_id = await create_machine(job.repo_full_name)
            await db.execute(
                "UPDATE repos SET machine_id = ? WHERE repo_full_name = ?",
                (machine_id, job.repo_full_name),
            )
            await db.commit()

    # Bootstrap if needed
    repo = await get_repo(db, job.repo_full_name)
    if repo and repo.bootstrap_phase != "done":
        from gitprbot.auth.github_app import mint_installation_token
        install_token = mint_installation_token(repo.install_id or "")
        await bootstrap_machine(machine_id, job.repo_full_name, install_token, db)

    return machine_id


async def _is_amend_job(job: JobRow) -> bool:
    """Returns True if this job should amend an existing agent PR."""
    if job.trigger_type != "webhook_pr" or not job.pr_number:
        return False
    async with get_db() as db:
        recent = await get_recent_succeeded_job_for_repo(db, job.repo_full_name)
    if recent and recent.result_pr_url:
        return True
    return False


async def _heartbeat_loop(repo_full_name: str) -> None:
    while True:
        await asyncio.sleep(settings.lock_heartbeat_seconds)
        try:
            async with get_db() as db:
                await heartbeat_lock(db, repo_full_name, settings.worker_id)
        except Exception:
            pass
