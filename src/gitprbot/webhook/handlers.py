from __future__ import annotations

import uuid
from typing import Any

from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from gitprbot.auth.hmac_verify import verify_signature
from gitprbot.db.connection import get_db
from gitprbot.db.jobs import create_job
from gitprbot.db.repos import get_repo, upsert_repo
from gitprbot.db.schema import JobRow
from gitprbot.db.webhooks import record_delivery_atomic
from gitprbot.github.normalizer import normalize_webhook_event
from gitprbot.observability.logging import log_event
from gitprbot.worker.queue import enqueue_job


async def handle_github_webhook(request: Request) -> JSONResponse:
    payload_bytes = await request.body()

    # 1. Verify HMAC
    sig = request.headers.get("X-Hub-Signature-256", "")
    verify_signature(payload_bytes, sig)

    # 2. Atomic dedup on delivery ID
    delivery_id = request.headers.get("X-GitHub-Delivery", str(uuid.uuid4()))
    async with get_db() as db:
        is_new = await record_delivery_atomic(db, delivery_id)
    if not is_new:
        return JSONResponse({"status": "duplicate"}, status_code=200)

    # 3. Parse and filter
    import json
    payload = json.loads(payload_bytes)
    event_type = request.headers.get("X-GitHub-Event", "")
    job = normalize_webhook_event(event_type, payload)

    if job is None:
        return JSONResponse({"status": "ignored"}, status_code=200)

    # 4. Ensure repo is registered
    repo_name = payload.get("repository", {}).get("full_name", "")
    install_id = str(payload.get("installation", {}).get("id", ""))
    default_branch = payload.get("repository", {}).get("default_branch", "main")

    async with get_db() as db:
        await upsert_repo(db, repo_name, install_id, default_branch)
        await create_job(db, job)

    # 5. Enqueue — returns 200 immediately
    await enqueue_job(job.job_id)
    log_event("webhook_enqueued", delivery_id=delivery_id, github_event=event_type, repo=repo_name)
    return JSONResponse({"status": "accepted", "job_id": job.job_id}, status_code=200)


async def handle_manual_job(request: Request) -> JSONResponse:
    data = await request.json()
    job = JobRow(
        job_id=str(uuid.uuid4()),
        repo_full_name=data["repo_full_name"],
        trigger_type="manual",
        instruction=data.get("instruction", ""),
        actor=data.get("actor", "manual"),
        pr_number=data.get("pr_number"),
        issue_number=data.get("issue_number"),
    )
    async with get_db() as db:
        await create_job(db, job)
    await enqueue_job(job.job_id)
    return JSONResponse({"status": "accepted", "job_id": job.job_id}, status_code=200)


async def handle_healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})
