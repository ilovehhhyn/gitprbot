from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from gitprbot.db.schema import JobRow
from gitprbot.github.normalizer import extract_bot_mention, is_bot_mentioned, normalize_webhook_event


def test_is_bot_mentioned():
    assert is_bot_mentioned("@bot fix the login bug")
    assert is_bot_mentioned("@gitprbot refactor this")
    assert is_bot_mentioned("/fix the auth issue")
    assert not is_bot_mentioned("just a regular comment")
    assert not is_bot_mentioned("can you review this?")


def test_extract_bot_mention():
    assert extract_bot_mention("@bot fix the null pointer") == "fix the null pointer"
    assert extract_bot_mention("@gitprbot add pagination") == "add pagination"
    assert extract_bot_mention("/fix") == "fix the issue"
    assert extract_bot_mention("/fix add tests") == "add tests"
    assert extract_bot_mention("no mention") is None


def test_normalize_pr_opened():
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Add feature",
            "body": "Please add X",
            "head": {"ref": "feature-branch"},
            "user": {"login": "alice"},
        },
        "repository": {"full_name": "owner/repo"},
    }
    job = normalize_webhook_event("pull_request", payload)
    assert job is not None
    assert job.trigger_type == "webhook_pr"
    assert job.pr_number == 42
    assert job.actor == "alice"


def test_normalize_pr_closed_ignored():
    payload = {
        "action": "closed",
        "pull_request": {"number": 1, "title": "x", "head": {"ref": "x"}, "user": {"login": "a"}},
        "repository": {"full_name": "owner/repo"},
    }
    job = normalize_webhook_event("pull_request", payload)
    assert job is None


def test_normalize_comment_with_bot_mention():
    payload = {
        "action": "created",
        "comment": {"body": "@bot fix the flaky test", "user": {"login": "bob"}},
        "issue": {"number": 10},
        "repository": {"full_name": "owner/repo"},
    }
    job = normalize_webhook_event("issue_comment", payload)
    assert job is not None
    assert job.trigger_type == "webhook_comment"
    assert job.instruction == "fix the flaky test"
    assert job.issue_number == 10


def test_normalize_comment_without_bot_mention_ignored():
    payload = {
        "action": "created",
        "comment": {"body": "LGTM!", "user": {"login": "bob"}},
        "issue": {"number": 10},
        "repository": {"full_name": "owner/repo"},
    }
    job = normalize_webhook_event("issue_comment", payload)
    assert job is None


def test_normalize_issue_labeled_agent():
    payload = {
        "action": "labeled",
        "label": {"name": "agent"},
        "issue": {"number": 5, "title": "Fix the bug", "body": "Details here", "user": {"login": "carol"}},
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "carol"},
    }
    job = normalize_webhook_event("issues", payload)
    assert job is not None
    assert job.trigger_type == "webhook_issue"
    assert job.issue_number == 5


def test_normalize_issue_wrong_label_ignored():
    payload = {
        "action": "labeled",
        "label": {"name": "bug"},
        "issue": {"number": 5, "title": "x", "user": {"login": "a"}},
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "a"},
    }
    job = normalize_webhook_event("issues", payload)
    assert job is None


@pytest.mark.asyncio
async def test_journal_written_before_pr_opened(db):
    """The journal write must happen before open_pr is called."""
    call_order = []

    async def mock_write_journal(*args, **kwargs):
        call_order.append("write_journal")

    async def mock_open_pr(*args, **kwargs):
        call_order.append("open_pr")
        return "https://github.com/owner/repo/pull/99"

    async def mock_run_tests(machine_id):
        return "1 passed"

    async def mock_git_commit(*args, **kwargs):
        return ""

    async def mock_git_push(*args, **kwargs):
        return ""

    async def mock_read_memory(*args, **kwargs):
        return ""

    async def mock_reset_tree(*args, **kwargs):
        pass

    async def mock_git_branch(*args, **kwargs):
        return ""

    async def mock_comment(*args, **kwargs):
        return ""

    mock_runner_result = MagicMock()
    mock_runner_result.final_output = "done"
    mock_runner_result.tools_called = []

    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(return_value=mock_runner_result)

    job = JobRow(
        job_id="test-job-001",
        repo_full_name="owner/repo",
        trigger_type="webhook_issue",
        issue_number=1,
        instruction="fix the bug",
        actor="alice",
    )

    # Seed repo into DB
    from gitprbot.db.repos import upsert_repo
    await upsert_repo(db, "owner/repo", "inst-1")

    with (
        patch("gitprbot.agent.loop.write_journal", side_effect=mock_write_journal),
        patch("gitprbot.agent.loop.open_pr", side_effect=mock_open_pr),
        patch("gitprbot.agent.loop.run_tests", side_effect=mock_run_tests),
        patch("gitprbot.agent.loop.git_commit", side_effect=mock_git_commit),
        patch("gitprbot.agent.loop.git_push", side_effect=mock_git_push),
        patch("gitprbot.agent.loop.read_memory_for_job", side_effect=mock_read_memory),
        patch("gitprbot.agent.loop.reset_tree", side_effect=mock_reset_tree),
        patch("gitprbot.agent.loop.git_branch", side_effect=mock_git_branch),
        patch("gitprbot.agent.loop.comment", side_effect=mock_comment),
        patch("gitprbot.agent.loop.make_runner", return_value=mock_runner),
        patch("gitprbot.agent.loop.update_job_status", new_callable=AsyncMock),
        patch("gitprbot.agent.loop.needs_consolidation", new_callable=AsyncMock, return_value=False),
        patch("gitprbot.agent.loop._maybe_update_always_on_memory", new_callable=AsyncMock),
    ):
        pr_url = await run_agent_loop(job, "dm-test", db, is_amend=False)

    assert pr_url == "https://github.com/owner/repo/pull/99"
    journal_idx = call_order.index("write_journal")
    pr_idx = call_order.index("open_pr")
    assert journal_idx < pr_idx, f"journal ({journal_idx}) must come before open_pr ({pr_idx})"


from gitprbot.agent.loop import run_agent_loop
