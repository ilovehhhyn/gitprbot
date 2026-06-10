from __future__ import annotations

from typing import Optional

import aiosqlite

from gitprbot.db.schema import RepoRow


async def upsert_repo(
    db: aiosqlite.Connection,
    repo_full_name: str,
    install_id: str,
    default_branch: str = "main",
) -> None:
    await db.execute(
        """
        INSERT INTO repos (repo_full_name, install_id, default_branch)
        VALUES (?, ?, ?)
        ON CONFLICT(repo_full_name) DO UPDATE SET
            install_id = excluded.install_id,
            default_branch = excluded.default_branch,
            updated_at = datetime('now')
        """,
        (repo_full_name, install_id, default_branch),
    )
    await db.commit()


async def get_repo(db: aiosqlite.Connection, repo_full_name: str) -> Optional[RepoRow]:
    cursor = await db.execute(
        "SELECT * FROM repos WHERE repo_full_name = ?", (repo_full_name,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return RepoRow(**dict(row))


async def set_machine_id(
    db: aiosqlite.Connection, repo_full_name: str, machine_id: str
) -> None:
    await db.execute(
        "UPDATE repos SET machine_id = ?, updated_at = datetime('now') WHERE repo_full_name = ?",
        (machine_id, repo_full_name),
    )
    await db.commit()


async def clear_machine(db: aiosqlite.Connection, repo_full_name: str) -> None:
    await db.execute(
        """UPDATE repos SET machine_id = NULL, bootstrap_phase = 'none',
           updated_at = datetime('now') WHERE repo_full_name = ?""",
        (repo_full_name,),
    )
    await db.commit()


async def set_bootstrap_phase(
    db: aiosqlite.Connection, repo_full_name: str, phase: str
) -> None:
    await db.execute(
        "UPDATE repos SET bootstrap_phase = ?, updated_at = datetime('now') WHERE repo_full_name = ?",
        (phase, repo_full_name),
    )
    await db.commit()


async def get_stale_bootstrap_repos(
    db: aiosqlite.Connection, threshold_s: int = 7200
) -> list[RepoRow]:
    cursor = await db.execute(
        """SELECT * FROM repos
           WHERE bootstrap_phase NOT IN ('done', 'none')
           AND updated_at < datetime('now', ? || ' seconds')""",
        (f"-{threshold_s}",),
    )
    rows = await cursor.fetchall()
    return [RepoRow(**dict(r)) for r in rows]
