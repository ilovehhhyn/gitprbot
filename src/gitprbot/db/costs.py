from __future__ import annotations

import aiosqlite

from gitprbot.db.schema import MachineCostRow


async def upsert_machine_cost(
    db: aiosqlite.Connection,
    machine_id: str,
    day: str,
    compute_usd: float,
    storage_usd: float,
) -> None:
    await db.execute(
        """INSERT INTO machine_costs (machine_id, day, compute_usd, storage_usd)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(machine_id, day) DO UPDATE SET
               compute_usd = excluded.compute_usd,
               storage_usd = excluded.storage_usd""",
        (machine_id, day, compute_usd, storage_usd),
    )
    await db.commit()


async def get_costs_by_repo(
    db: aiosqlite.Connection, repo_full_name: str
) -> list[MachineCostRow]:
    cursor = await db.execute(
        """SELECT mc.* FROM machine_costs mc
           JOIN repos r ON r.machine_id = mc.machine_id
           WHERE r.repo_full_name = ?
           ORDER BY mc.day DESC""",
        (repo_full_name,),
    )
    rows = await cursor.fetchall()
    return [MachineCostRow(**dict(r)) for r in rows]
