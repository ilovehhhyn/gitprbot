from __future__ import annotations

from functools import lru_cache

from dedalus_labs import AsyncDedalus, DedalusRunner

from gitprbot.config import settings


@lru_cache(maxsize=1)
def get_models_client() -> AsyncDedalus:
    return AsyncDedalus(
        api_key=settings.dedalus_api_key,
        base_url=settings.models_base_url,
    )


def make_runner(client: AsyncDedalus | None = None) -> DedalusRunner:
    return DedalusRunner(client or get_models_client())
