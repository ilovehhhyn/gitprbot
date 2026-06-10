from __future__ import annotations

import aiosqlite

from gitprbot.config import settings


async def acquire_lock(
    db: aiosqlite.Connection, repo_full_name: str, worker_id: str
) -> bool:
    """Atomically acquire the per-repo lock via a leased advisory lock.
    Returns True if acquired, False if another worker holds a non-expired lock.
    """
    cursor = await db.execute(
        """UPDATE repos
           SET lock_holder_id = ?,
               lock_expires_at = datetime('now', ? || ' seconds')
           WHERE repo_full_name = ?
             AND (lock_holder_id IS NULL OR lock_expires_at < datetime('now'))
        """,
        (worker_id, str(settings.lock_lease_ttl_seconds), repo_full_name),
    )
    await db.commit()
    return cursor.rowcount == 1


async def heartbeat_lock(
    db: aiosqlite.Connection, repo_full_name: str, worker_id: str
) -> None:
    await db.execute(
        """UPDATE repos
           SET lock_expires_at = datetime('now', ? || ' seconds')
           WHERE repo_full_name = ? AND lock_holder_id = ?""",
        (str(settings.lock_lease_ttl_seconds), repo_full_name, worker_id),
    )
    await db.commit()


async def release_lock(
    db: aiosqlite.Connection, repo_full_name: str, worker_id: str
) -> None:
    await db.execute(
        """UPDATE repos
           SET lock_holder_id = NULL, lock_expires_at = NULL
           WHERE repo_full_name = ? AND lock_holder_id = ?""",
        (repo_full_name, worker_id),
    )
    await db.commit()


async def sweep_stale_locks(db: aiosqlite.Connection) -> int:
    """Release all locks whose lease has expired. Call on worker startup."""
    cursor = await db.execute(
        """UPDATE repos
           SET lock_holder_id = NULL, lock_expires_at = NULL
           WHERE lock_expires_at IS NOT NULL AND lock_expires_at < datetime('now')"""
    )
    await db.commit()
    return cursor.rowcount
