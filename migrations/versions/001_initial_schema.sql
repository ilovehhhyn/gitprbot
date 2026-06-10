-- 001_initial_schema.sql

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS repos (
    repo_full_name  TEXT PRIMARY KEY,
    machine_id      TEXT,
    install_id      TEXT,
    default_branch  TEXT DEFAULT 'main',
    bootstrap_phase TEXT DEFAULT 'none',
    storage_gib     INTEGER DEFAULT 20,
    lock_holder_id  TEXT,
    lock_expires_at TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    repo_full_name  TEXT NOT NULL,
    trigger_type    TEXT NOT NULL,
    ref             TEXT,
    pr_number       INTEGER,
    issue_number    INTEGER,
    instruction     TEXT,
    actor           TEXT,
    status          TEXT NOT NULL DEFAULT 'queued',
    result_pr_url   TEXT,
    cost_usd        REAL DEFAULT 0.0,
    started_at      TEXT,
    finished_at     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    delivery_id TEXT PRIMARY KEY,
    received_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS machine_costs (
    machine_id  TEXT NOT NULL,
    day         TEXT NOT NULL,
    compute_usd REAL DEFAULT 0.0,
    storage_usd REAL DEFAULT 0.0,
    PRIMARY KEY (machine_id, day)
);

CREATE INDEX IF NOT EXISTS idx_jobs_repo_status ON jobs (repo_full_name, status);
CREATE INDEX IF NOT EXISTS idx_repos_lock_expires ON repos (lock_expires_at);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at);
