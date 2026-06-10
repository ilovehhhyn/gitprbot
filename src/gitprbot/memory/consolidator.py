from __future__ import annotations

from gitprbot.machines.runner import run_on_machine
from gitprbot.memory.writer import write_memory_atomic
from gitprbot.models.client import get_models_client
from gitprbot.models.costs import CostTracker
from gitprbot.models.router import ModelPhase, count_tokens, route_model
from gitprbot.observability.logging import log_event


async def needs_consolidation(
    machine_id: str, file_path: str, budget_tokens: int
) -> bool:
    script = f"""
import os
path = {repr(file_path)}
print(open(path).read() if os.path.exists(path) else '')
"""
    content = await run_on_machine(
        machine_id, ["python3", "-c", script], timeout_ms=10_000
    )
    current_tokens = count_tokens(content)
    threshold = int(budget_tokens * 0.80)
    return current_tokens >= threshold


async def consolidate_file(
    machine_id: str,
    file_path: str,
    budget_tokens: int,
    job_id: str,
    cost_tracker: CostTracker | None = None,
) -> None:
    """Run the cheap model over the file, using provenance headers to prune stale entries.
    Logs what was removed before overwriting. Atomic write to prevent corruption.
    """
    script = f"""
import os
path = {repr(file_path)}
print(open(path).read() if os.path.exists(path) else '')
"""
    current_content = await run_on_machine(
        machine_id, ["python3", "-c", script], timeout_ms=10_000
    )

    if not current_content.strip():
        return

    model = route_model(ModelPhase.CONSOLIDATION)
    client = get_models_client()

    consolidation_prompt = f"""You are consolidating a memory file for a coding agent.
The file contains entries with provenance comment headers like:
<!-- added: YYYY-MM-DD, job: <id>, trigger: <trigger> -->

Rules:
1. Remove entries that are duplicates or contradict newer entries.
2. Remove entries older than 90 days if there is a newer entry covering the same topic.
3. Merge related entries into a single, cleaner entry.
4. Keep ALL entries that have no newer equivalent.
5. Preserve ALL provenance headers for entries you keep.
6. Target token count: under {int(budget_tokens * 0.70)} tokens.

Output ONLY the consolidated file content. No explanation.

File content:
{current_content}
"""

    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": consolidation_prompt}],
        max_tokens=budget_tokens,
        temperature=0,
    )

    consolidated = response.choices[0].message.content

    if cost_tracker:
        cost_tracker.record_step(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            model=model,
        )

    log_event(
        "memory_consolidated",
        job_id=job_id,
        file_path=file_path,
        original_tokens=count_tokens(current_content),
        consolidated_tokens=count_tokens(consolidated),
    )

    await write_memory_atomic(machine_id, file_path, consolidated)
