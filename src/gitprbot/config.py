from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))


def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))


@dataclass(frozen=True)
class Settings:
    # Dedalus
    dedalus_api_key: str = field(default_factory=lambda: _env("DEDALUS_API_KEY"))
    machines_base_url: str = "https://dcs.dedaluslabs.ai/v1"
    models_base_url: str = "https://api.dedaluslabs.ai/v1"

    # GitHub App
    github_app_id: str = field(default_factory=lambda: _env("GITHUB_APP_ID"))
    github_app_private_key_path: str = field(
        default_factory=lambda: _env("GITHUB_APP_PRIVATE_KEY_PATH")
    )
    github_webhook_secret: str = field(
        default_factory=lambda: _env("GITHUB_WEBHOOK_SECRET")
    )

    # Database
    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "sqlite+aiosqlite:///./gitprbot.db")
    )

    # Worker identity
    worker_id: str = field(default_factory=lambda: _env("WORKER_ID", "worker-1"))

    # Models
    strong_model: str = field(
        default_factory=lambda: _env("STRONG_MODEL", "anthropic/claude-opus-4-5")
    )
    cheap_model: str = field(
        default_factory=lambda: _env(
            "CHEAP_MODEL", "anthropic/claude-haiku-4-5-20251001"
        )
    )
    embed_model: str = field(
        default_factory=lambda: _env("EMBED_MODEL", "openai/text-embedding-3-small")
    )

    # Machine defaults
    machine_vcpu: int = field(default_factory=lambda: _env_int("MACHINE_VCPU", 2))
    machine_memory_mib: int = field(
        default_factory=lambda: _env_int("MACHINE_MEMORY_MIB", 4096)
    )
    machine_storage_gib: int = field(
        default_factory=lambda: _env_int("MACHINE_STORAGE_GIB", 10)
    )
    machine_autosleep: str = field(
        default_factory=lambda: _env("MACHINE_AUTOSLEEP", "30m")
    )

    # Agent loop limits
    max_steps: int = field(default_factory=lambda: _env_int("MAX_STEPS", 40))
    max_repair_iterations: int = field(
        default_factory=lambda: _env_int("MAX_REPAIR_ITERATIONS", 6)
    )
    wall_clock_cap_seconds: int = field(
        default_factory=lambda: _env_int("WALL_CLOCK_CAP_SECONDS", 2700)
    )
    per_job_cost_ceiling_usd: float = field(
        default_factory=lambda: _env_float("PER_JOB_COST_CEILING_USD", 2.0)
    )

    # Lock
    lock_lease_ttl_seconds: int = field(
        default_factory=lambda: _env_int("LOCK_LEASE_TTL_SECONDS", 900)
    )
    lock_heartbeat_seconds: int = field(
        default_factory=lambda: _env_int("LOCK_HEARTBEAT_SECONDS", 120)
    )

    # Memory budgets (tokens)
    repo_md_token_budget: int = field(
        default_factory=lambda: _env_int("REPO_MD_TOKEN_BUDGET", 400)
    )
    conventions_md_token_budget: int = field(
        default_factory=lambda: _env_int("CONVENTIONS_MD_TOKEN_BUDGET", 300)
    )
    consolidation_threshold: float = field(
        default_factory=lambda: _env_float("CONSOLIDATION_THRESHOLD", 0.80)
    )

    # Observability
    alert_webhook_url: str = field(
        default_factory=lambda: _env("ALERT_WEBHOOK_URL", "")
    )
    metrics_port: int = field(default_factory=lambda: _env_int("METRICS_PORT", 9090))

    def github_app_private_key(self) -> str:
        path = Path(self.github_app_private_key_path).expanduser()
        return path.read_text()


settings = Settings()
