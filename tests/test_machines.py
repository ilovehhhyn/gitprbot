from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gitprbot.machines.errors import ExecutionFailed, MachineGone
from gitprbot.machines.runner import run_on_machine


@pytest.mark.asyncio
async def test_run_on_machine_success(mock_machines_client):
    with patch("gitprbot.machines.runner.get_machines_client", return_value=mock_machines_client):
        result = await run_on_machine("dm-test", ["/bin/echo", "hello"])
    assert result == "test output"


@pytest.mark.asyncio
async def test_run_on_machine_failed_status(mock_machines_client):
    fail_exec = MagicMock()
    fail_exec.status = "failed"
    fail_exec.execution_id = "exec-fail"
    fail_exec.error_code = "timeout"
    fail_exec.error_message = "execution timed out"
    fail_exec.retry_after_ms = None
    mock_machines_client.machines.executions.create.return_value = fail_exec

    with patch("gitprbot.machines.runner.get_machines_client", return_value=mock_machines_client):
        with pytest.raises(ExecutionFailed) as exc_info:
            await run_on_machine("dm-test", ["/bin/echo", "hello"])
    assert "failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_on_machine_wake_in_progress(mock_machines_client):
    """wake_in_progress should sleep at least 1s before retrying."""
    wake_exec = MagicMock()
    wake_exec.status = "wake_in_progress"
    wake_exec.execution_id = "exec-wake"
    wake_exec.retry_after_ms = 0  # API returns 0 — must floor at 1s
    wake_exec.error_code = None
    wake_exec.error_message = None

    succeeded_exec = MagicMock()
    succeeded_exec.status = "succeeded"
    succeeded_exec.execution_id = "exec-wake"
    succeeded_exec.retry_after_ms = None
    succeeded_exec.error_code = None
    succeeded_exec.error_message = None

    mock_machines_client.machines.executions.create.return_value = wake_exec
    mock_machines_client.machines.executions.retrieve.return_value = succeeded_exec
    output_obj = MagicMock()
    output_obj.stdout = "awake!"
    mock_machines_client.machines.executions.output.return_value = output_obj

    sleep_calls = []

    import asyncio
    original_sleep = asyncio.sleep

    async def mock_sleep(t):
        sleep_calls.append(t)

    with patch("gitprbot.machines.runner.get_machines_client", return_value=mock_machines_client):
        with patch("asyncio.sleep", side_effect=mock_sleep):
            result = await run_on_machine("dm-test", ["/bin/echo", "awake"])

    assert result == "awake!"
    # First sleep should be >= 1.0 (floored from wake_in_progress with retry_after_ms=0)
    assert sleep_calls[0] >= 1.0


@pytest.mark.asyncio
async def test_verify_machine_exists_gone():
    mock_client = MagicMock()
    mock_client.machines.retrieve.side_effect = Exception("404 not found")

    with patch("gitprbot.machines.client.get_machines_client", return_value=mock_client):
        from gitprbot.machines.client import verify_machine_exists
        with pytest.raises(MachineGone):
            await verify_machine_exists("dm-gone")
