from __future__ import annotations

import time

import httpx
import jwt

from gitprbot.config import settings

GITHUB_API = "https://api.github.com"


def _make_app_jwt() -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": settings.github_app_id,
    }
    private_key = settings.github_app_private_key()
    return jwt.encode(payload, private_key, algorithm="RS256")


def mint_installation_token(install_id: str) -> str:
    """Mint a fresh short-lived GitHub App installation access token.
    Always call immediately before use — never cache or store the result.
    """
    app_jwt = _make_app_jwt()
    resp = httpx.post(
        f"{GITHUB_API}/app/installations/{install_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def build_authenticated_clone_url(repo_full_name: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
