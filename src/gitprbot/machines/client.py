from __future__ import annotations

import asyncio
import hashlib
import time
from functools import lru_cache

from dedalus_sdk import Dedalus

from gitprbot.config import settings
from gitprbot.machines.errors import MachineGone


@lru_cache(maxsize=1)
def get_machines_client() -> Dedalus:
    return Dedalus(api_key=settings.dedalus_api_key, base_url=settings.machines_base_url)


def _make_idempotency_key(repo_full_name: str) -> str:
    day = str(int(time.time()) // 86400)
    prefix = settings.dedalus_api_key[:8]
    raw = f"{prefix}:{repo_full_name}:{day}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_machine(repo_full_name: str) -> str:
    client = get_machines_client()
    loop = asyncio.get_event_loop()

    # SDK is synchronous — run blocking calls in a thread executor
    machine = await loop.run_in_executor(
        None,
        lambda: client.machines.create(
            vcpu=settings.machine_vcpu,
            memory_mib=settings.machine_memory_mib,
            storage_gib=settings.machine_storage_gib,
        ),
    )

    # Drain the watch stream to wait for the machine to be fully running
    # before any executions are attempted (matches the SDK doc pattern)
    def _watch() -> None:
        stream = client.machines.watch(machine_id=machine.machine_id)
        for _ in stream:
            pass

    await loop.run_in_executor(None, _watch)
    return machine.machine_id


async def sleep_machine(machine_id: str) -> None:
    client = get_machines_client()
    client.machines.sleep(machine_id)


async def wake_machine(machine_id: str) -> None:
    client = get_machines_client()
    client.machines.wake(machine_id)


async def get_machine_phase(machine_id: str) -> str:
    client = get_machines_client()
    try:
        m = client.machines.retrieve(machine_id)
        return m.status.phase
    except Exception as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            raise MachineGone(machine_id) from exc
        raise


async def verify_machine_exists(machine_id: str) -> None:
    """Raises MachineGone if the machine no longer exists."""
    phase = await get_machine_phase(machine_id)
    if phase == "destroyed":
        raise MachineGone(machine_id)
