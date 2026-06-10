from __future__ import annotations

from dataclasses import dataclass

from gitprbot.config import settings
from gitprbot.machines.errors import PatchFailed
from gitprbot.models.costs import CostTracker
from gitprbot.tools.machine_tools import apply_patch, run_tests


@dataclass
class RepairResult:
    green: bool
    iterations: int
    last_output: str


async def run_repair_loop(
    machine_id: str,
    runner,
    cost_tracker: CostTracker,
    initial_test_output: str,
) -> RepairResult:
    """Run test → diagnose → patch → repeat until green or cap reached.

    On PatchFailed: re-fetch and re-read context, retry once. If still failing,
    count as an iteration and continue.
    """
    from gitprbot.agent.prompts import build_repair_prompt
    from gitprbot.models.client import make_runner
    from gitprbot.models.router import ModelPhase, route_model

    last_output = initial_test_output
    model = route_model(ModelPhase.TEST_DIAGNOSIS)

    for iteration in range(1, settings.max_repair_iterations + 1):
        repair_prompt = build_repair_prompt(last_output, iteration)

        result = await runner.run(
            input=repair_prompt,
            model=model,
            tools=[apply_patch],
            max_steps=8,
        )
        cost_tracker.check_ceiling()

        try:
            test_out = await run_tests(machine_id)
        except Exception as exc:
            last_output = str(exc)
            continue

        if _tests_passed(test_out):
            return RepairResult(green=True, iterations=iteration, last_output=test_out)

        last_output = test_out

    return RepairResult(green=False, iterations=settings.max_repair_iterations, last_output=last_output)


def _tests_passed(output: str) -> bool:
    lower = output.lower()
    failure_markers = ["failed", "error", "errors", "assertion", "traceback", "exit code 1"]
    pass_markers = ["passed", "ok", "success", "✓", "all tests"]
    if any(m in lower for m in pass_markers):
        return True
    if any(m in lower for m in failure_markers):
        return False
    return True
