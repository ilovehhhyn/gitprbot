from __future__ import annotations

import aiosqlite


async def record_delivery_atomic(db: aiosqlite.Connection, delivery_id: str) -> bool:
    """Atomically insert a delivery_id. Returns True if newly inserted, False if duplicate."""
    cursor = await db.execute(
        """INSERT INTO webhook_deliveries (delivery_id, received_at)
           VALUES (?, datetime('now'))
           ON CONFLICT(delivery_id) DO NOTHING""",
        (delivery_id,),
    )
    await db.commit()
    return cursor.rowcount == 1
