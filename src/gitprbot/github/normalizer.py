from __future__ import annotations

import re
import uuid
from typing import Optional

from gitprbot.db.schema import JobRow

BOT_MENTION_RE = re.compile(r"@(?:bot|gitprbot)\s+(.+)", re.IGNORECASE)
SLASH_FIX_RE = re.compile(r"/fix\s*(.*)", re.IGNORECASE)


def is_bot_mentioned(text: str) -> bool:
    return bool(BOT_MENTION_RE.search(text) or SLASH_FIX_RE.search(text))


def extract_bot_mention(text: str) -> Optional[str]:
    m = BOT_MENTION_RE.search(text)
    if m:
        return m.group(1).strip()
    m = SLASH_FIX_RE.search(text)
    if m:
        return m.group(1).strip() or "fix the issue"
    return None


def normalize_webhook_event(event_type: str, payload: dict) -> Optional[JobRow]:
    """Convert a raw GitHub webhook payload to a normalized JobRow.
    Returns None for events we don't act on.
    """
    repo = payload.get("repository", {}).get("full_name", "")
    if not repo:
        return None

    if event_type == "pull_request":
        action = payload.get("action", "")
        if action not in ("opened", "synchronize"):
            return None
        pr = payload.get("pull_request", {})
        return JobRow(
            job_id=str(uuid.uuid4()),
            repo_full_name=repo,
            trigger_type="webhook_pr",
            ref=pr.get("head", {}).get("ref"),
            pr_number=pr.get("number"),
            instruction=pr.get("body") or pr.get("title") or "",
            actor=pr.get("user", {}).get("login", ""),
        )

    if event_type in ("issue_comment", "pull_request_review_comment"):
        comment_body = payload.get("comment", {}).get("body", "")
        if not is_bot_mentioned(comment_body):
            return None
        instruction = extract_bot_mention(comment_body) or ""
        pr = payload.get("pull_request") or {}
        issue = payload.get("issue") or {}
        return JobRow(
            job_id=str(uuid.uuid4()),
            repo_full_name=repo,
            trigger_type="webhook_comment",
            pr_number=pr.get("number"),
            issue_number=issue.get("number"),
            instruction=instruction,
            actor=payload.get("comment", {}).get("user", {}).get("login", ""),
        )

    if event_type == "issues":
        action = payload.get("action", "")
        if action != "labeled":
            return None
        label = payload.get("label", {}).get("name", "")
        if label != "agent":
            return None
        issue = payload.get("issue", {})
        return JobRow(
            job_id=str(uuid.uuid4()),
            repo_full_name=repo,
            trigger_type="webhook_issue",
            issue_number=issue.get("number"),
            instruction=issue.get("body") or issue.get("title") or "",
            actor=payload.get("sender", {}).get("login", ""),
        )

    return None
