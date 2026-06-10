from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException

from gitprbot.config import settings


def verify_signature(payload: bytes, signature_header: str) -> None:
    """Verify the X-Hub-Signature-256 header using constant-time comparison.
    Raises HTTP 401 on mismatch.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    received = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
