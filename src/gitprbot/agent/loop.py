from __future__ import annotations

import asyncio
import time
import uuid

import aiosqlite

from gitprbot.agent.prompts import (
    build_draft_pr_body,
    build_pr_body,
    build_system_prompt,
    build_task_instruction,
)
from gitprbot.agent.repair import run_repair_loop
from gitprbot.agent.tree_reset import checkout_agent_branch, reset_tree
from gitprbot.config import settings
from gitprbot.db.jobs import update_job_status
from gitprbot.db.schema import JobRow
from gitprbot.memory.consolidator import consolidate_file, needs_consolidation
from gitprbot.memory.reader import read_memory_for_job
from gitprbot.memory.writer import append_provenance_entry, write_journal
from gitprbot.models.client import make_runner
from gitprbot.models.costs import CostCeilingExceeded, CostTracker
from gitprbot.models.router import ModelPhase, route_model
from gitprbot.observability.logging import log_event
from gitprbot.tools import MACHINE_TOOLS
from gitprbot.tools.machine_tools import git_branch, git_commit, run_tests
from gitprbot.tools.orchestrator_tools import comment, git_push, open_pr


async def run_agent_loop(
    job: JobRow,
    machine_id: str,
    db: aiosqlite.Connection,
    is_amend: bool = False,
) -> str:
    """Full agent loop. Returns the PR URL on success. Raises on failure."""
    cost_tracker = CostTracker()
    start_time = time.monotonic()
    install_id = await _get_install_id(db, job.repo_full_name)

    # 1. Reset tree
    if is_amend and job.pr_number:
        branch_name = f"gitprbot/pr-{job.pr_number}"
        await checkout_agent_branch(machine_id, branch_name)
    else:
        base_branch = await _get_base_branch(db, job.repo_full_name)
        await reset_tree(machine_id, base_branch)
        branch_name = f"gitprbot/job-{job.job_id[:8]}"
        await git_branch(machine_id, branch_name)

    # 2. Load memory
    job_type = "amend" if is_amend else _classify_job_type(job)
    memory_context = await read_memory_for_job(
        machine_id, job_type, pr_number=job.pr_number
    )

    # 3. Run the agent loop
    system_prompt = build_system_prompt(memory_context, job_type)
    task_instruction = build_task_instruction(job)

    runner = make_runner()
    result = await runner.run(
        input=task_instruction,
        model=route_model(ModelPhase.PATCH_GENERATION),
        tools=MACHINE_TOOLS,
        instructions=system_prompt,
        max_steps=settings.max_steps,
    )
    cost_tracker.check_ceiling()
    _check_wall_clock(start_time)

    # 4. Run tests to get initial state
    test_output = await run_tests(machine_id)

    # 5. Repair loop if tests are red
    if not _tests_passed(test_output):
        repair = await run_repair_loop(machine_id, runner, cost_tracker, test_output)
        test_output = repair.last_output
        _check_wall_clock(start_time)

        if not repair.green:
            # Tests never went green — open draft PR + set needs_human
            await git_commit(machine_id, f"gitprbot: WIP fix for job {job.job_id[:8]}")
            journal_content = _build_journal(job, result, test_output, green=False)
            await write_journal(machine_id, job.job_id, job.pr_number or job.issue_number or "new", journal_content, cost_tracker)
            await update_job_status(db, job.job_id, "running")

            push_out = await git_push(machine_id, branch_name, install_id)
            base_branch = await _get_base_branch(db, job.repo_full_name)
            pr_url = await open_pr(
                repo_full_name=job.repo_full_name,
                head_branch=branch_name,
                base_branch=base_branch,
                title=f"[Draft] gitprbot: {job.instruction[:60] if job.instruction else 'fix'}",
                body=build_draft_pr_body(job, test_output),
                install_id=install_id,
                draft=True,
            )
            await comment(
                repo_full_name=job.repo_full_name,
                issue_or_pr_number=job.pr_number or job.issue_number or 0,
                body=f"⚠️ Could not make tests pass. Draft PR opened for human review: {pr_url}",
                install_id=install_id,
            )
            raise NeedsHuman(pr_url)

    # 6. Commit
    await git_commit(
        machine_id,
        f"gitprbot: {job.instruction[:72] if job.instruction else 'automated fix'}\n\nJob: {job.job_id}",
    )

    # 7. Write journal BEFORE opening PR (critical ordering)
    pr_ref = job.pr_number or job.issue_number or "new"
    journal_content = _build_journal(job, result, test_output, green=True)
    await write_journal(machine_id, job.job_id, pr_ref, journal_content, cost_tracker)

    # 8. Push + open PR
    _check_wall_clock(start_time)
    await git_push(machine_id, branch_name, install_id)
    base_branch = await _get_base_branch(db, job.repo_full_name)
    pr_url = await open_pr(
        repo_full_name=job.repo_full_name,
        head_branch=branch_name,
        base_branch=base_branch,
        title=f"gitprbot: {job.instruction[:60] if job.instruction else 'automated fix'}",
        body=build_pr_body(job, test_output),
        install_id=install_id,
        draft=False,
    )

    # 9. Comment on original thread
    if job.pr_number or job.issue_number:
        await comment(
            repo_full_name=job.repo_full_name,
            issue_or_pr_number=job.pr_number or job.issue_number,
            body=f"✅ Fix applied and tests passing. PR: {pr_url}",
            install_id=install_id,
        )

    # 10. Update always-on memory files (only on real signal)
    await _maybe_update_always_on_memory(machine_id, job, result, cost_tracker)

    # 11. Check consolidation
    await _maybe_consolidate(machine_id, job.job_id, cost_tracker)

    log_event(
        "job_completed",
        job_id=job.job_id,
        repo=job.repo_full_name,
        pr_url=pr_url,
        cost_usd=cost_tracker.total_usd(),
    )
    return pr_url


class NeedsHuman(Exception):
    def __init__(self, pr_url: str) -> None:
        self.pr_url = pr_url
        super().__init__(f"needs_human: {pr_url}")


def _tests_passed(output: str) -> bool:
    lower = output.lower()
    if any(m in lower for m in ["passed", "ok", "success", "✓"]):
        return True
    if any(m in lower for m in ["failed", "error", "traceback", "exit code 1"]):
        return False
    return True


def _check_wall_clock(start: float) -> None:
    elapsed = time.monotonic() - start
    if elapsed > settings.wall_clock_cap_seconds:
        raise TimeoutError(f"Wall-clock cap exceeded: {elapsed:.0f}s > {settings.wall_clock_cap_seconds}s")


def _classify_job_type(job: JobRow) -> str:
    if job.trigger_type in ("webhook_pr", "webhook_comment"):
        return "amend" if job.pr_number else "task"
    return "task"


def _build_journal(job: JobRow, runner_result, test_output: str, green: bool) -> str:
    tools_used = getattr(runner_result, "tools_called", [])
    status = "PASSED" if green else "FAILED"
    return f"""# Job {job.job_id}

**Repo:** {job.repo_full_name}
**Trigger:** {job.trigger_type}
**Actor:** {job.actor}
**Instruction:** {job.instruction}

## Tools used
{', '.join(tools_used) if tools_used else '(none recorded)'}

## Test result: {status}
```
{test_output[:2000]}
```
"""


async def _get_install_id(db: aiosqlite.Connection, repo_full_name: str) -> str:
    from gitprbot.db.repos import get_repo
    row = await get_repo(db, repo_full_name)
    return row.install_id if row and row.install_id else ""


async def _get_base_branch(db: aiosqlite.Connection, repo_full_name: str) -> str:
    from gitprbot.db.repos import get_repo
    row = await get_repo(db, repo_full_name)
    return row.default_branch if row else "main"


async def _maybe_update_always_on_memory(
    machine_id: str, job: JobRow, runner_result, cost_tracker: CostTracker
) -> None:
    """Only append to always-on files on explicit signal from the runner result."""
    notes = getattr(runner_result, "final_output", "") or ""
    if "REPO_FACT:" in notes:
        for line in notes.splitlines():
            if line.startswith("REPO_FACT:"):
                fact = line[len("REPO_FACT:"):].strip()
                await append_provenance_entry(
                    machine_id, "/agent/memory/repo.md", fact,
                    job.job_id, f"{job.trigger_type}-{job.pr_number or job.issue_number}",
                    cost_tracker,
                )
    if "CONVENTION:" in notes:
        for line in notes.splitlines():
            if line.startswith("CONVENTION:"):
                conv = line[len("CONVENTION:"):].strip()
                await append_provenance_entry(
                    machine_id, "/agent/memory/conventions.md", conv,
                    job.job_id, f"{job.trigger_type}-{job.pr_number or job.issue_number}",
                    cost_tracker,
                )


async def _maybe_consolidate(
    machine_id: str, job_id: str, cost_tracker: CostTracker
) -> None:
    for path, budget in [
        ("/agent/memory/repo.md", settings.repo_md_token_budget),
        ("/agent/memory/conventions.md", settings.conventions_md_token_budget),
    ]:
        if await needs_consolidation(machine_id, path, budget):
            await consolidate_file(machine_id, path, budget, job_id, cost_tracker)
