from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    )


_logger = structlog.get_logger()


def log_event(event_type: str, **kwargs: Any) -> None:
    _logger.info(event_type, **kwargs)


def log_injection_attempt(job_id: str, repo: str, content_hash: str) -> None:
    _logger.warning(
        "prompt_injection_attempt",
        job_id=job_id,
        repo=repo,
        content_hash=content_hash,
    )
