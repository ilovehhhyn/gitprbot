from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Use a temp file DB so aiosqlite connections share state across requests in TestClient.
# :memory: opens a fresh empty DB per connection, so startup-created tables vanish.
import tempfile as _tempfile
_test_db_file = _tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_file}"

# Stub out the Dedalus SDKs before any gitprbot code imports them.
# These are alpha packages not yet on PyPI; tests run fully mocked.
_dedalus_sdk_mock = MagicMock()
_dedalus_sdk_mock.Dedalus = MagicMock
sys.modules.setdefault("dedalus_sdk", _dedalus_sdk_mock)

_dedalus_labs_mock = MagicMock()
_dedalus_labs_mock.AsyncDedalus = MagicMock
_dedalus_labs_mock.DedalusRunner = MagicMock
sys.modules.setdefault("dedalus_labs", _dedalus_labs_mock)

os.environ.setdefault("DEDALUS_API_KEY", "test-key")
os.environ.setdefault("GITHUB_APP_ID", "12345")
os.environ.setdefault("GITHUB_APP_PRIVATE_KEY_PATH", "/dev/null")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("WORKER_ID", "test-worker")
os.environ.setdefault("STRONG_MODEL", "anthropic/claude-opus-4-5")
os.environ.setdefault("CHEAP_MODEL", "anthropic/claude-haiku-4-5-20251001")
os.environ.setdefault("PER_JOB_COST_CEILING_USD", "10.0")


@pytest.fixture
async def db():
    from gitprbot.db.connection import init_db, get_db
    # Use in-memory SQLite for tests
    import aiosqlite
    from pathlib import Path
    migrations = Path(__file__).parent.parent / "migrations" / "versions"
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    for sql_file in sorted(migrations.glob("*.sql")):
        await conn.executescript(sql_file.read_text())
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
def mock_machines_client():
    client = MagicMock()
    exec_obj = MagicMock()
    exec_obj.status = "succeeded"
    exec_obj.execution_id = "exec-123"
    exec_obj.retry_after_ms = None
    exec_obj.error_code = None
    exec_obj.error_message = None
    client.machines.executions.create.return_value = exec_obj
    client.machines.executions.retrieve.return_value = exec_obj
    output_obj = MagicMock()
    output_obj.stdout = "test output"
    client.machines.executions.output.return_value = output_obj
    return client
