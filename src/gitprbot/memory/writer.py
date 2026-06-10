from __future__ import annotations

import json

from gitprbot.machines.runner import run_on_machine
from gitprbot.memory.sanitizer import SanitizationResult, sanitize_memory
from gitprbot.models.costs import CostTracker
from gitprbot.observability.logging import log_event


async def write_memory_atomic(
    machine_id: str,
    target_path: str,
    content: str,
) -> None:
    """Write content to target_path via a .tmp file + atomic rename.
    A crash mid-write leaves a detectable .tmp rather than a corrupt target.
    """
    tmp_path = target_path + ".tmp"
    script = f"""
import os
content = {json.dumps(content)}
tmp = {json.dumps(tmp_path)}
target = {json.dumps(target_path)}
os.makedirs(os.path.dirname(target), exist_ok=True)
with open(tmp, 'w') as f:
    f.write(content)
os.rename(tmp, target)
print('written')
"""
    await run_on_machine(machine_id, ["python3", "-c", script], timeout_ms=15_000)


async def write_journal(
    machine_id: str,
    job_id: str,
    pr_number: int | str,
    content: str,
    cost_tracker: CostTracker | None = None,
) -> None:
    """Write the job journal entry. Must be called BEFORE open_pr."""
    result = await sanitize_memory(content, cost_tracker)
    if result == SanitizationResult.INJECTION_DETECTED:
        import hashlib
        log_event(
            "prompt_injection_attempt",
            job_id=job_id,
            content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
        )
        raise ValueError(f"Injection detected in journal content for job {job_id}")

    path = f"/agent/memory/journal/pr-{pr_number}.md"
    await write_memory_atomic(machine_id, path, content)


async def append_provenance_entry(
    machine_id: str,
    target_path: str,
    entry_text: str,
    job_id: str,
    trigger: str,
    cost_tracker: CostTracker | None = None,
) -> None:
    """Sanitize then append a provenance-tagged entry to an always-on memory file."""
    result = await sanitize_memory(entry_text, cost_tracker)
    if result == SanitizationResult.INJECTION_DETECTED:
        import hashlib
        log_event(
            "prompt_injection_attempt",
            job_id=job_id,
            target_path=target_path,
            content_hash=hashlib.sha256(entry_text.encode()).hexdigest()[:16],
        )
        return

    from datetime import date
    date_str = date.today().isoformat()
    tagged = (
        f"\n<!-- added: {date_str}, job: {job_id}, trigger: {trigger} -->\n"
        f"{entry_text.strip()}\n"
    )

    script = f"""
import os
path = {json.dumps(target_path)}
entry = {json.dumps(tagged)}
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'a') as f:
    f.write(entry)
print('appended')
"""
    await run_on_machine(machine_id, ["python3", "-c", script], timeout_ms=10_000)
