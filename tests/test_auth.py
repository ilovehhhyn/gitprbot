from __future__ import annotations

import hashlib
import hmac

import pytest

from gitprbot.auth.hmac_verify import verify_signature
from fastapi import HTTPException


def _make_sig(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_signature_valid():
    payload = b'{"action": "opened"}'
    sig = _make_sig(payload, "test-secret")
    # Should not raise
    verify_signature(payload, sig)


def test_verify_signature_invalid():
    payload = b'{"action": "opened"}'
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(payload, "sha256=badhash")
    assert exc_info.value.status_code == 401


def test_verify_signature_missing():
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(b"payload", "")
    assert exc_info.value.status_code == 401


def test_verify_signature_wrong_prefix():
    with pytest.raises(HTTPException):
        verify_signature(b"payload", "md5=abc123")
