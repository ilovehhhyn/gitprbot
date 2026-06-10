from __future__ import annotations

import httpx

GITHUB_API = "https://api.github.com"
ACCEPT = "application/vnd.github+json"
API_VERSION = "2022-11-28"


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": ACCEPT,
            "X-GitHub-Api-Version": API_VERSION,
        }

    async def create_pull_request(
        self,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool = False,
    ) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{GITHUB_API}/repos/{repo}/pulls",
                headers=self._headers,
                json={"title": title, "head": head, "base": base, "body": body, "draft": draft},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()

    async def create_comment(self, repo: str, issue_number: int, body: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments",
                headers=self._headers,
                json={"body": body},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()

    async def get_pull_request(self, repo: str, pr_number: int) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
                headers=self._headers,
                timeout=30,
            )
            r.raise_for_status()
            return r.json()

    async def list_open_issues_with_label(self, repo: str, label: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{GITHUB_API}/repos/{repo}/issues",
                headers=self._headers,
                params={"state": "open", "labels": label, "per_page": 50},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
