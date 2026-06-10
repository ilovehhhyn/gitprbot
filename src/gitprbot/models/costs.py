from __future__ import annotations

from gitprbot.config import settings

# Rough per-token costs (USD). These are estimates; real billing comes from the usage API.
_COST_PER_1K: dict[str, tuple[float, float]] = {
    "anthropic/claude-opus-4-5": (0.015, 0.075),
    "anthropic/claude-haiku-4-5-20251001": (0.00025, 0.00125),
    "openai/text-embedding-3-small": (0.00002, 0.0),
    "default": (0.003, 0.015),
}


def _estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    in_rate, out_rate = _COST_PER_1K.get(model, _COST_PER_1K["default"])
    return (input_tokens / 1000) * in_rate + (output_tokens / 1000) * out_rate


class CostCeilingExceeded(Exception):
    def __init__(self, current: float, ceiling: float) -> None:
        super().__init__(f"Cost ceiling exceeded: ${current:.4f} > ${ceiling:.4f}")
        self.current = current
        self.ceiling = ceiling


class CostTracker:
    def __init__(self) -> None:
        self._total_usd: float = 0.0
        self._steps: list[dict] = []

    def record_step(self, input_tokens: int, output_tokens: int, model: str) -> None:
        cost = _estimate_cost(input_tokens, output_tokens, model)
        self._total_usd += cost
        self._steps.append(
            {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": model, "cost": cost}
        )

    def total_usd(self) -> float:
        return self._total_usd

    def check_ceiling(self) -> None:
        ceiling = settings.per_job_cost_ceiling_usd
        if self._total_usd > ceiling:
            raise CostCeilingExceeded(self._total_usd, ceiling)

    def summary(self) -> dict:
        return {"total_usd": self._total_usd, "steps": len(self._steps)}
