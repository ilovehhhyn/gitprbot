from __future__ import annotations

import asyncio

from gitprbot.db.connection import get_db
from gitprbot.db.jobs import list_jobs
from gitprbot.db.locks import sweep_stale_locks
from gitprbot.db.repos import get_repo, get_stale_bootstrap_repos
from gitprbot.github.client import GitHubClient
from gitprbot.observability.alerts import AlertType, alert
from gitprbot.observability.logging import log_event
from gitprbot.worker.queue import enqueue_job

POLL_INTERVAL_S = 300  # 5 minutes


async def start_poller() -> None:
    asyncio.create_task(_poller_loop())


async def _poller_loop() -> None:
    log_event("poller_started")
    while True:
        try:
            await _reconcile_once()
        except Exception as exc:
            log_event("poller_error", error=str(exc))
        await asyncio.sleep(POLL_INTERVAL_S)


async def _reconcile_once() -> None:
    async with get_db() as db:
        swept = await sweep_stale_locks(db)
        if swept:
            log_event("stale_locks_swept", count=swept)

        stale_bootstraps = await get_stale_bootstrap_repos(db)
        for repo in stale_bootstraps:
            alert(
                AlertType.STUCK_BOOTSTRAP,
                repo=repo.repo_full_name,
                phase=repo.bootstrap_phase,
            )

        # Scan all tracked repos for missed issues/PRs
        cursor = await db.execute(
            "SELECT repo_full_name, install_id FROM repos WHERE bootstrap_phase = 'done'"
        )
        repos = await cursor.fetchall()

    for row in repos:
        await _check_repo_for_missed_jobs(row["repo_full_name"], row["install_id"])


async def _check_repo_for_missed_jobs(repo_full_name: str, install_id: str) -> None:
    if not install_id:
        return
    try:
        from gitprbot.auth.github_app import mint_installation_token
        token = mint_installation_token(install_id)
        client = GitHubClient(token)
        issues = await client.list_open_issues_with_label(repo_full_name, "agent")

        async with get_db() as db:
            recent_jobs = await list_jobs(db, repo_full_name, limit=50)

        handled_issues = {j.issue_number for j in recent_jobs if j.issue_number}

        import uuid
        from gitprbot.db.jobs import create_job
        from gitprbot.db.schema import JobRow

        for issue in issues:
            issue_number = issue.get("number")
            if issue_number and issue_number not in handled_issues:
                job = JobRow(
                    job_id=str(uuid.uuid4()),
                    repo_full_name=repo_full_name,
                    trigger_type="poll",
                    issue_number=issue_number,
                    instruction=issue.get("body") or issue.get("title") or "",
                    actor=issue.get("user", {}).get("login", "poller"),
                )
                async with get_db() as db:
                    await create_job(db, job)
                await enqueue_job(job.job_id)
                log_event("poller_enqueued", repo=repo_full_name, issue=issue_number)
    except Exception as exc:
        log_event("poller_repo_error", repo=repo_full_name, error=str(exc))
