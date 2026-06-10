from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from gitprbot.tools.dispatch import ToolKind, get_tool_kind
from gitprbot.tools.machine_tools import git_branch, git_commit, read_file
from gitprbot.tools.orchestrator_tools import git_push


def test_machine_tool_kind():
    assert get_tool_kind(read_file) == ToolKind.MACHINE
    assert get_tool_kind(git_branch) == ToolKind.MACHINE
    assert get_tool_kind(git_commit) == ToolKind.MACHINE


def test_orchestrator_tool_kind():
    assert get_tool_kind(git_push) == ToolKind.ORCHESTRATOR


@pytest.mark.asyncio
async def test_read_file_calls_run_on_machine():
    with patch("gitprbot.tools.machine_tools.run_on_machine", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "file contents"
        result = await read_file("dm-test", "/repo/README.md")
    assert result == "file contents"
    mock_run.assert_called_once_with("dm-test", ["cat", "/repo/README.md"], timeout_ms=10_000)


@pytest.mark.asyncio
async def test_git_push_uses_fresh_token_in_isolated_env():
    """git_push must pass token via env on a separate execution, not in agent loop env."""
    with patch("gitprbot.tools.orchestrator_tools.mint_installation_token", return_value="fresh-tok"):
        with patch("gitprbot.tools.orchestrator_tools.run_on_machine", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ""
            await git_push("dm-test", "gitprbot/job-abc", "inst-1")

    # Second call is the actual push; check it carries the token in env
    push_call = mock_run.call_args_list[-1]
    env_arg = push_call.kwargs.get("env") or (push_call.args[4] if len(push_call.args) > 4 else {})
    assert "GIT_TOKEN" in env_arg or "GITHUB_TOKEN" in env_arg
    assert "fresh-tok" in env_arg.values()


@pytest.mark.asyncio
async def test_apply_patch_raises_patch_failed_on_error():
    from gitprbot.machines.errors import ExecutionFailed, PatchFailed
    from gitprbot.tools.machine_tools import apply_patch

    with patch(
        "gitprbot.tools.machine_tools.run_on_machine",
        new_callable=AsyncMock,
        side_effect=ExecutionFailed("failed", "nonzero", "patch does not apply"),
    ):
        with pytest.raises(PatchFailed):
            await apply_patch("dm-test", "--- a/foo.py\n+++ b/foo.py\n@@\n-old\n+new\n")
