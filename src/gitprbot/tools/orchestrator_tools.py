from __future__ import annotations

from gitprbot.auth.github_app import mint_installation_token
from gitprbot.machines.runner import run_on_machine
from gitprbot.tools.dispatch import orchestrator_tool


@orchestrator_tool
async def git_push(machine_id: str, branch_name: str, install_id: str) -> str:
    """Push branch to origin using a freshly minted token in an isolated execution.
    The token is never visible to the agent loop's tool execution environment.
    """
    token = mint_installation_token(install_id)
    askpass_setup = (
        "echo '#!/bin/sh' > /tmp/git-askpass.sh && "
        "echo 'echo $GIT_TOKEN' >> /tmp/git-askpass.sh && "
        "chmod +x /tmp/git-askpass.sh"
    )
    await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", askpass_setup],
        timeout_ms=5_000,
    )
    return await run_on_machine(
        machine_id,
        ["git", "-C", "/repo", "push", "origin", branch_name],
        timeout_ms=60_000,
        env={
            "GIT_ASKPASS": "/tmp/git-askpass.sh",
            "GIT_TOKEN": token,
        },
    )


@orchestrator_tool
async def open_pr(
    repo_full_name: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    install_id: str,
    draft: bool = False,
) -> str:
    """Open a pull request via the GitHub API. Returns the PR HTML URL."""
    from gitprbot.github.client import GitHubClient

    token = mint_installation_token(install_id)
    client = GitHubClient(token)
    pr = await client.create_pull_request(
        repo=repo_full_name,
        head=head_branch,
        base=base_branch,
        title=title,
        body=body,
        draft=draft,
    )
    return pr["html_url"]


@orchestrator_tool
async def comment(
    repo_full_name: str,
    issue_or_pr_number: int,
    body: str,
    install_id: str,
) -> str:
    """Post a comment on an issue or PR. Returns the comment URL."""
    from gitprbot.github.client import GitHubClient

    token = mint_installation_token(install_id)
    client = GitHubClient(token)
    result = await client.create_comment(
        repo=repo_full_name,
        issue_number=issue_or_pr_number,
        body=body,
    )
    return result.get("html_url", "")
