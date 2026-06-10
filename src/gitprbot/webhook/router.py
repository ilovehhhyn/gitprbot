from fastapi import APIRouter

from gitprbot.webhook.handlers import handle_github_webhook, handle_healthz, handle_manual_job

webhook_router = APIRouter()

webhook_router.post("/webhooks/github")(handle_github_webhook)
webhook_router.post("/jobs")(handle_manual_job)
webhook_router.get("/healthz")(handle_healthz)
