from __future__ import annotations

from typing import Optional

import aiosqlite

from gitprbot.db.schema import JobRow


async def create_job(db: aiosqlite.Connection, job: JobRow) -> None:
    await db.execute(
        """INSERT INTO jobs
           (job_id, repo_full_name, trigger_type, ref, pr_number, issue_number,
            instruction, actor, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (
            job.job_id,
            job.repo_full_name,
            job.trigger_type,
            job.ref,
            job.pr_number,
            job.issue_number,
            job.instruction,
            job.actor,
            job.status,
        ),
    )
    await db.commit()


async def update_job_status(
    db: aiosqlite.Connection,
    job_id: str,
    status: str,
    result_pr_url: Optional[str] = None,
    cost_usd: float = 0.0,
    finished: bool = False,
) -> None:
    await db.execute(
        """UPDATE jobs SET status = ?, result_pr_url = ?, cost_usd = ?,
           finished_at = CASE WHEN ? THEN datetime('now') ELSE finished_at END
           WHERE job_id = ?""",
        (status, result_pr_url, cost_usd, finished, job_id),
    )
    await db.commit()


async def mark_job_started(db: aiosqlite.Connection, job_id: str) -> None:
    await db.execute(
        "UPDATE jobs SET status = 'running', started_at = datetime('now') WHERE job_id = ?",
        (job_id,),
    )
    await db.commit()


async def get_job(db: aiosqlite.Connection, job_id: str) -> Optional[JobRow]:
    cursor = await db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return JobRow(**dict(row))


async def get_recent_succeeded_job_for_repo(
    db: aiosqlite.Connection, repo_full_name: str
) -> Optional[JobRow]:
    """Returns the most recent succeeded job that produced a PR URL, used to detect amend path."""
    cursor = await db.execute(
        """SELECT * FROM jobs
           WHERE repo_full_name = ? AND status = 'succeeded' AND result_pr_url IS NOT NULL
           ORDER BY finished_at DESC LIMIT 1""",
        (repo_full_name,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return JobRow(**dict(row))


async def list_jobs(
    db: aiosqlite.Connection, repo_full_name: str, limit: int = 20
) -> list[JobRow]:
    cursor = await db.execute(
        "SELECT * FROM jobs WHERE repo_full_name = ? ORDER BY created_at DESC LIMIT ?",
        (repo_full_name, limit),
    )
    rows = await cursor.fetchall()
    return [JobRow(**dict(r)) for r in rows]
