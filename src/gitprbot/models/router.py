from __future__ import annotations

from enum import Enum

import tiktoken

from gitprbot.config import settings

_ENCODING = tiktoken.get_encoding("cl100k_base")


class ModelPhase(str, Enum):
    PATCH_GENERATION = "patch_generation"
    TEST_DIAGNOSIS = "test_diagnosis"
    FILE_READ = "file_read"
    SUMMARIZATION = "summarization"
    SANITIZATION = "sanitization"
    COMMIT_MESSAGE = "commit_message"
    CONSOLIDATION = "consolidation"


_STRONG_PHASES = {ModelPhase.PATCH_GENERATION, ModelPhase.TEST_DIAGNOSIS}


def route_model(phase: ModelPhase) -> str:
    if phase in _STRONG_PHASES:
        return settings.strong_model
    return settings.cheap_model


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))
