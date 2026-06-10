# gitprbot

A GitHub bot that watches your repositories and autonomously writes code. When a PR opens, an issue is labeled `agent`, or someone comments `@bot fix this`, the bot wakes a persistent Dedalus Machine for that repo, reads the code, writes a fix, runs the tests, and opens a pull request for a human to review.

## Key Features

- **One persistent VM per repo** — each repository gets its own long-lived Dedalus Machine. Clone once; every subsequent job does a fast `git fetch` delta.
- **Toolchain and caches survive between jobs** — `node_modules`, `.venv`, build caches, and compiler artifacts live in `/caches` and are never thrown away.
- **Durable agent memory** — the bot writes structured notes about repo architecture, team conventions, and past PRs to the machine's disk. Every new job reads those notes back into the model's context so it builds on prior knowledge instead of starting blind.
- **Sleep when idle, wake in under a second** — machines cost nothing while sleeping. The next webhook auto-wakes them.
- **Injection-safe memory writes** — all GitHub content (issue body, PR title, comment text) passes through a cheap-model sanitization check before touching persistent memory files.
- **Atomic git push with isolated tokens** — GitHub App tokens are minted fresh immediately before the push, passed in an isolated subprocess environment, and never stored or logged.
- **DB-backed leased advisory lock** — one worker holds a job at a time per repo; stale locks (crashed workers) are swept on startup.
- **45-minute wall-clock cap** — runaway jobs are hard-killed.
- **Two-model routing** — strong model (`claude-opus-4-5`) for patch generation and diagnosis; cheap model (`claude-haiku`) for reads, summarization, and sanitization.

## Trigger Events

| Event | Condition | What happens |
|---|---|---|
| `pull_request` opened / synchronized | any PR | Bot reviews and patches |
| `issues` labeled | label name is `agent` | Bot fixes the issue and opens a PR |
| `issue_comment` / `pull_request_review_comment` | body contains `@bot` or `/fix` | Bot applies the instruction |

---

## Prerequisites

- Python 3.9+
- A [Dedalus](https://dedaluslabs.ai) account and API key
- A GitHub account with permission to create a GitHub App

---

## Step 1 — Create a GitHub App

1. Go to **GitHub → Settings → Developer settings → GitHub Apps → New GitHub App**.
2. Fill in:
   - **GitHub App name**: anything (e.g. `my-gitprbot`)
   - **Homepage URL**: your server URL or `http://localhost:8000`
   - **Webhook URL**: `https://your-server.example.com/webhooks/github`
   - **Webhook secret**: generate a random string and save it — this becomes `GITHUB_WEBHOOK_SECRET`
3. Under **Repository permissions** set:
   - Contents: **Read & write**
   - Issues: **Read & write**
   - Pull requests: **Read & write**
   - Metadata: **Read-only**
4. Under **Subscribe to events** check: `Pull request`, `Issues`, `Issue comment`, `Pull request review comment`.
5. Click **Create GitHub App**.
6. Note the **App ID** at the top of the app page — this becomes `GITHUB_APP_ID`.
7. Scroll to **Private keys** → **Generate a private key**. Save the downloaded `.pem` file (e.g. at `/etc/gitprbot/private-key.pem`). This path becomes `GITHUB_APP_PRIVATE_KEY_PATH`.
8. Install the app on the repositories you want to watch (**Install App** tab → select repos).

---

## Step 2 — Install dependencies

```bash
git clone https://github.com/ilovehhhyn/gitprbot.git
cd gitprbot
pip install -r requirements.txt
```

For development (includes pytest, ruff, mypy):

```bash
pip install -r requirements-dev.txt
```

---

## Step 3 — Configure environment

Copy the example env file and fill it in:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|---|---|
| `DEDALUS_API_KEY` | Your Dedalus API key |
| `GITHUB_APP_ID` | Numeric app ID from Step 1 |
| `GITHUB_APP_PRIVATE_KEY_PATH` | Absolute path to the `.pem` file from Step 1 |
| `GITHUB_WEBHOOK_SECRET` | The webhook secret you set in Step 1 |

Optional variables (safe to leave as defaults):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./gitprbot.db` | Swap for `postgresql+asyncpg://...` in production |
| `WORKER_ID` | `worker-1` | Unique string per process; used for lock ownership |
| `STRONG_MODEL` | `anthropic/claude-opus-4-5` | Model used for patch generation |
| `CHEAP_MODEL` | `anthropic/claude-haiku-4-5-20251001` | Model used for reads and sanitization |
| `WALL_CLOCK_CAP_SECONDS` | `2700` | Max seconds per job (45 min) |
| `PER_JOB_COST_CEILING_USD` | `2.00` | Hard cost cap per job |
| `MACHINE_VCPU` | `2` | vCPUs for each Dedalus Machine |
| `MACHINE_MEMORY_MIB` | `4096` | RAM for each Dedalus Machine |
| `MACHINE_STORAGE_GIB` | `20` | Disk for each Dedalus Machine |
| `LOCK_LEASE_TTL_SECONDS` | `900` | Lock expires after 15 min if heartbeat stops |
| `ALERT_WEBHOOK_URL` | _(empty)_ | POST JSON alerts here (Slack, PagerDuty, etc.) |
| `METRICS_PORT` | `9090` | Prometheus metrics endpoint port |

---

## Step 4 — Run

```bash
python -m gitprbot.main
```

The server starts on `http://0.0.0.0:8000`. Verify it's alive:

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

For production use a process manager (systemd, Docker, etc.) and put the server behind a TLS-terminating reverse proxy (nginx, Caddy) so GitHub can reach the webhook endpoint over HTTPS.

---

## Step 5 — Expose the webhook (local dev)

GitHub needs to reach your `/webhooks/github` endpoint. For local development use [ngrok](https://ngrok.com) or [smee.io](https://smee.io):

```bash
ngrok http 8000
```

Copy the `https://....ngrok-free.app` URL, append `/webhooks/github`, and paste it into your GitHub App's **Webhook URL** field.

---

## How it works

```
GitHub webhook
      │
      ▼
Webhook handler (World A — always-on)
  1. Verify HMAC signature
  2. Atomic dedup by delivery ID
  3. Parse event → normalize to JobRow
  4. Upsert repo in DB
  5. Enqueue job → return 200 immediately
      │
      ▼
Worker (World A)
  6. Acquire per-repo leased lock
  7. Ensure Dedalus Machine exists (create + watch if new)
  8. Bootstrap if needed (clone, install deps, warm caches, build memory files)
  9. Run agent loop (World B — Dedalus Machine)
     • Reset working tree
     • Read memory files into context
     • LLM proposes tool calls → execute on machine
     • Run tests, iterate on failures
     • Write journal entry (sanitized, atomic)
     • Push branch, open PR
 10. Release lock → sleep machine
```

### Agent memory layout (on the Dedalus Machine)

```
/agent/memory/
  repo.md            # always loaded — project overview, stack, key paths
  conventions.md     # always loaded — naming, style, patterns the team uses
  architecture.md    # loaded on-demand for structural tasks
  journal/
    pr-123.md        # one file per PR the bot has worked on
  index/
    embeddings.sqlite
```

---

## Running tests

```bash
pytest tests/ -v
```

All 37 tests run fully offline — the Dedalus SDK and GitHub API are mocked.

---

## Project structure

```
src/gitprbot/
  agent/          # LLM loop, prompts, repair iterations, tree reset
  auth/           # GitHub App JWT + installation token minting, HMAC verify
  db/             # SQLite schema, jobs, repos, locks, webhook dedup
  machines/       # Dedalus SDK wrapper, execution runner, bootstrap phases
  memory/         # Sanitizer, atomic writer, memory reader, consolidator
  models/         # Dedalus Models API client, cost tracker, model router
  observability/  # Structured JSON logging, Prometheus metrics, alerts
  poller/         # Background reconciler for stuck jobs
  tools/          # Machine tools (@machine_tool) and orchestrator tools (@orchestrator_tool)
  webhook/        # FastAPI router, HMAC verification, event handler
  worker/         # Async queue, worker loop, full PR flow orchestration
  config.py       # Frozen Settings dataclass, all env vars in one place
  main.py         # FastAPI app with lifespan startup
migrations/
  versions/001_initial_schema.sql
tests/
```

---

## Security notes

- **GitHub App tokens are never stored.** A fresh installation token is minted immediately before each `git push`, passed in an isolated subprocess `env=` dict, and discarded.
- **Issue and PR text is treated as untrusted.** All content from GitHub runs through a cheap-model sanitization pass before any write to persistent memory files on the machine.
- **The GitHub token never reaches the agent's tool execution environment.** Only the git push subprocess sees it.
