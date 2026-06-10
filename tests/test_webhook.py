from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from gitprbot.main import create_app

SECRET = "test-secret"


def _sign(payload: bytes) -> str:
    digest = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def client():
    import gitprbot.worker.queue as _wq
    _wq._queue = None  # reset so each TestClient gets a queue bound to its own event loop
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    _wq._queue = None


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_webhook_rejects_bad_signature(client):
    payload = json.dumps({"action": "opened"}).encode()
    r = client.post(
        "/webhooks/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": "sha256=badhash",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "delivery-bad",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401


def test_webhook_ignores_unknown_event(client):
    payload = json.dumps({"repository": {"full_name": "owner/repo", "default_branch": "main"}, "installation": {"id": 1}}).encode()
    sig = _sign(payload)
    r = client.post(
        "/webhooks/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "delivery-push",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_webhook_dedup_returns_200_on_duplicate(client):
    payload = json.dumps({
        "action": "labeled",
        "label": {"name": "agent"},
        "issue": {"number": 1, "title": "fix bug", "body": "please fix", "user": {"login": "alice"}},
        "repository": {"full_name": "owner/repo", "default_branch": "main"},
        "installation": {"id": 1},
        "sender": {"login": "alice"},
    }).encode()
    sig = _sign(payload)
    headers = {
        "X-Hub-Signature-256": sig,
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "delivery-dup-test",
        "Content-Type": "application/json",
    }
    r1 = client.post("/webhooks/github", content=payload, headers=headers)
    r2 = client.post("/webhooks/github", content=payload, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Second should be duplicate
    assert r2.json()["status"] == "duplicate"
