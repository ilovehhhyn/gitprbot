from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from gitprbot.config import settings
from gitprbot.db.connection import get_db, init_db
from gitprbot.db.locks import sweep_stale_locks
from gitprbot.observability.logging import configure_logging, log_event
from gitprbot.observability.metrics import snapshot
from gitprbot.poller.reconciler import start_poller
from gitprbot.webhook.router import webhook_router
from gitprbot.worker.worker import start_worker


@asynccontextmanager
async def _lifespan(app: FastAPI):
    configure_logging()
    await init_db()
    async with get_db() as db:
        swept = await sweep_stale_locks(db)
        if swept:
            log_event("startup_stale_locks_swept", count=swept)
    await start_worker()
    await start_poller()
    log_event("gitprbot_started", worker_id=settings.worker_id)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="gitprbot", version="0.1.0", lifespan=_lifespan)
    app.include_router(webhook_router)

    @app.get("/metrics")
    async def metrics() -> JSONResponse:
        return JSONResponse(snapshot())

    return app


def main() -> None:
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
