from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RepoRow:
    repo_full_name: str
    machine_id: Optional[str] = None
    install_id: Optional[str] = None
    default_branch: str = "main"
    bootstrap_phase: str = "none"
    storage_gib: int = 20
    lock_holder_id: Optional[str] = None
    lock_expires_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class JobRow:
    job_id: str
    repo_full_name: str
    trigger_type: str
    ref: Optional[str] = None
    pr_number: Optional[int] = None
    issue_number: Optional[int] = None
    instruction: Optional[str] = None
    actor: Optional[str] = None
    status: str = "queued"
    result_pr_url: Optional[str] = None
    cost_usd: float = 0.0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class WebhookDeliveryRow:
    delivery_id: str
    received_at: Optional[str] = None


@dataclass
class MachineCostRow:
    machine_id: str
    day: str
    compute_usd: float = 0.0
    storage_usd: float = 0.0
