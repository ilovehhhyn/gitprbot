from __future__ import annotations

import collections
from typing import DefaultDict

_job_durations: list[float] = []
_job_costs: list[float] = []
_tool_calls: DefaultDict[str, int] = collections.defaultdict(int)
_tool_errors: DefaultDict[str, int] = collections.defaultdict(int)
_repair_iterations: list[int] = []


def record_job_duration(duration_s: float, status: str) -> None:
    _job_durations.append(duration_s)


def record_job_cost(cost_usd: float) -> None:
    _job_costs.append(cost_usd)


def record_tool_call(tool_name: str, success: bool) -> None:
    _tool_calls[tool_name] += 1
    if not success:
        _tool_errors[tool_name] += 1


def record_repair_iterations(n: int) -> None:
    _repair_iterations.append(n)


def snapshot() -> dict:
    return {
        "jobs_total": len(_job_durations),
        "avg_duration_s": sum(_job_durations) / max(len(_job_durations), 1),
        "avg_cost_usd": sum(_job_costs) / max(len(_job_costs), 1),
        "tool_calls": dict(_tool_calls),
        "repair_iterations_avg": sum(_repair_iterations) / max(len(_repair_iterations), 1),
    }
