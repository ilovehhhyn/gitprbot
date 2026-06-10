from __future__ import annotations

import re

from gitprbot.machines.runner import run_on_machine


_PROVENANCE_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_provenance(text: str) -> str:
    """Strip HTML provenance comment headers before injecting into model context."""
    return _PROVENANCE_RE.sub("", text).strip()


async def _read_file_safe(machine_id: str, path: str) -> str:
    """Read a file; return empty string if it doesn't exist."""
    script = f"""
import os
path = {repr(path)}
print(open(path).read() if os.path.exists(path) else '')
"""
    return await run_on_machine(machine_id, ["python3", "-c", script], timeout_ms=10_000)


async def read_memory_for_job(
    machine_id: str,
    job_type: str,
    pr_number: int | str | None = None,
) -> str:
    """Assemble the memory context block for injection into the agent system prompt.

    Always loads: repo.md + conventions.md (stripped of provenance headers).
    Conditionally loads based on job_type:
      - 'amend'     → also loads journal/pr-<N>.md
      - 'structural' → also loads architecture.md
    """
    parts: list[str] = []

    repo_md = await _read_file_safe(machine_id, "/agent/memory/repo.md")
    if repo_md:
        parts.append(f"## Repo Info\n{_strip_provenance(repo_md)}")

    conventions_md = await _read_file_safe(machine_id, "/agent/memory/conventions.md")
    if conventions_md:
        parts.append(f"## Team Conventions\n{_strip_provenance(conventions_md)}")

    if job_type == "amend" and pr_number is not None:
        journal = await _read_file_safe(
            machine_id, f"/agent/memory/journal/pr-{pr_number}.md"
        )
        if journal:
            parts.append(f"## Prior Work on PR #{pr_number}\n{_strip_provenance(journal)}")

    if job_type == "structural":
        arch = await _read_file_safe(machine_id, "/agent/memory/architecture.md")
        if arch:
            parts.append(f"## Architecture\n{_strip_provenance(arch)}")

    return "\n\n---\n\n".join(parts) if parts else ""
