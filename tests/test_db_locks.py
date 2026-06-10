from __future__ import annotations

import pytest

from gitprbot.db.locks import acquire_lock, heartbeat_lock, release_lock, sweep_stale_locks
from gitprbot.db.repos import upsert_repo


@pytest.mark.asyncio
async def test_acquire_lock_on_unlocked_repo(db):
    await upsert_repo(db, "owner/repo", "inst-1")
    acquired = await acquire_lock(db, "owner/repo", "worker-1")
    assert acquired is True


@pytest.mark.asyncio
async def test_acquire_lock_rejected_when_held(db):
    await upsert_repo(db, "owner/repo", "inst-1")
    await acquire_lock(db, "owner/repo", "worker-1")
    acquired = await acquire_lock(db, "owner/repo", "worker-2")
    assert acquired is False


@pytest.mark.asyncio
async def test_acquire_lock_granted_after_expiry(db):
    await upsert_repo(db, "owner/repo", "inst-1")
    await db.execute(
        "UPDATE repos SET lock_holder_id = 'old-worker', lock_expires_at = datetime('now', '-1 minute') WHERE repo_full_name = 'owner/repo'"
    )
    await db.commit()
    acquired = await acquire_lock(db, "owner/repo", "worker-new")
    assert acquired is True


@pytest.mark.asyncio
async def test_release_lock(db):
    await upsert_repo(db, "owner/repo", "inst-1")
    await acquire_lock(db, "owner/repo", "worker-1")
    await release_lock(db, "owner/repo", "worker-1")
    acquired = await acquire_lock(db, "owner/repo", "worker-2")
    assert acquired is True


@pytest.mark.asyncio
async def test_sweep_stale_locks(db):
    await upsert_repo(db, "owner/repo-a", "inst-a")
    await upsert_repo(db, "owner/repo-b", "inst-b")
    await db.execute(
        "UPDATE repos SET lock_holder_id = 'dead-worker', lock_expires_at = datetime('now', '-5 minutes') WHERE repo_full_name IN ('owner/repo-a', 'owner/repo-b')"
    )
    await db.commit()
    count = await sweep_stale_locks(db)
    assert count == 2


@pytest.mark.asyncio
async def test_heartbeat_refreshes_expiry(db):
    await upsert_repo(db, "owner/repo", "inst-1")
    await acquire_lock(db, "owner/repo", "worker-1")
    await heartbeat_lock(db, "owner/repo", "worker-1")
    cursor = await db.execute(
        "SELECT lock_expires_at FROM repos WHERE repo_full_name = 'owner/repo'"
    )
    row = await cursor.fetchone()
    assert row["lock_expires_at"] is not None
