from __future__ import annotations

from enum import Enum
from typing import Any

import httpx

from gitprbot.config import settings
from gitprbot.observability.logging import log_event


class AlertType(str, Enum):
    DUPLICATE_MACHINE = "duplicate_machine"
    STUCK_BOOTSTRAP = "stuck_bootstrap"
    STALE_LOCK = "stale_lock"
    REPAIR_CAP_HIT = "repair_cap_hit"
    PROMPT_INJECTION = "prompt_injection"
    MACHINE_AWAKE_TOO_LONG = "machine_awake_too_long"
    COST_CEILING = "cost_ceiling"


def alert(alert_type: AlertType, **context: Any) -> None:
    payload = {"alert_type": alert_type.value, **context}
    log_event("alert", **payload)

    if settings.alert_webhook_url:
        try:
            httpx.post(settings.alert_webhook_url, json=payload, timeout=5)
        except Exception:
            pass
