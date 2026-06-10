#!/usr/bin/env python3
"""Deploy the gitprbot orchestrator onto a Dedalus Machine.

First run (creates a new machine):
  python3 scripts/deploy_orchestrator.py

Resume after a failed run (reuses existing machine):
  python3 scripts/deploy_orchestrator.py dm-xxxx-xxxx-xxxx

Each step is idempotent — safe to rerun on the same machine.
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from dedalus_sdk import Dedalus
except ImportError:
    print("ERROR: dedalus_sdk not installed. Run: pip3 install dedalus-sdk")
    sys.exit(1)

DONE = {"succeeded", "failed", "cancelled", "expired"}
REPO_URL = "https://github.com/ilovehhhyn/gitprbot.git"
INSTALL_DIR = "/opt/gitprbot"
KEY_PATH_ON_MACHINE = "/opt/gitprbot/private-key.pem"
VENV = f"{INSTALL_DIR}/.venv"
PYTHON = f"{VENV}/bin/python"
PIP = f"{VENV}/bin/pip"


def run(client, machine_id: str, bash: str, stdin: str = None, timeout_ms: int = 300_000) -> str:
    """Run a bash command on the machine and return stdout. Raises on failure."""
    kwargs = {"timeout_ms": timeout_ms}
    if stdin is not None:
        kwargs["stdin"] = stdin
    exc = client.machines.executions.create(
        machine_id=machine_id,
        command=["/bin/bash", "-c", bash],
        **kwargs,
    )
    while exc.status not in DONE:
        time.sleep(2)
        print(".", end="", flush=True)
        exc = client.machines.executions.retrieve(
            machine_id=machine_id, execution_id=exc.execution_id
        )
    print()  # newline after dots
    out = client.machines.executions.output(
        machine_id=machine_id, execution_id=exc.execution_id
    )
    stdout = (out.stdout or "").strip()
    stderr = (out.stderr or "").strip()
    if exc.status != "succeeded":
        raise RuntimeError(
            f"FAILED ({exc.status}): {exc.error_message or ''}\n"
            f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
        )
    return stdout


def build_env_content() -> str:
    """Read local .env and rewrite GITHUB_APP_PRIVATE_KEY_PATH to the machine path."""
    env_path = Path(".env")
    if not env_path.exists():
        print("ERROR: .env not found. Run this script from the gitprbot directory.")
        sys.exit(1)
    lines = []
    for line in env_path.read_text().splitlines():
        if line.startswith("GITHUB_APP_PRIVATE_KEY_PATH="):
            lines.append(f"GITHUB_APP_PRIVATE_KEY_PATH={KEY_PATH_ON_MACHINE}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def wait_ready(client, machine_id: str) -> None:
    for _ in client.machines.watch(machine_id=machine_id):
        pass


def main():
    api_key = os.environ.get("DEDALUS_API_KEY")
    if not api_key:
        print("ERROR: DEDALUS_API_KEY not set in .env")
        sys.exit(1)

    client = Dedalus(api_key=api_key)

    # ── Step 1: get or create the orchestrator machine ──────────────────────
    existing_id = os.environ.get("ORCHESTRATOR_MACHINE_ID") or (
        sys.argv[1] if len(sys.argv) > 1 else None
    )

    if existing_id:
        machine_id = existing_id
        print(f"[1/9] Resuming machine {machine_id} ...")
        client.machines.wake(machine_id=machine_id)
        wait_ready(client, machine_id)
        print("      Running.")
    else:
        print("[1/9] Creating orchestrator machine ...")
        m = client.machines.create(vcpu=2, memory_mib=4096, storage_gib=10)
        machine_id = m.machine_id
        print(f"      Machine ID: {machine_id}")
        wait_ready(client, machine_id)
        print("      Running.")

    # ── Step 2: system deps — install only what's missing, no apt-get update ─
    print("[2/9] Checking system dependencies ...")
    run(client, machine_id,
        "python3 -c 'import venv' 2>/dev/null || "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends python3-venv; "
        "command -v git >/dev/null 2>&1 || "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends git; "
        "command -v curl >/dev/null 2>&1 || "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends curl",
        timeout_ms=120_000)
    print("      Done.")

    # ── Step 3: clone or pull (idempotent) ──────────────────────────────────
    print("[3/9] Cloning / updating repo ...")
    run(client, machine_id,
        f"if [ -d {INSTALL_DIR}/.git ]; then "
        f"  git -C {INSTALL_DIR} pull --ff-only; "
        f"else "
        f"  git clone {REPO_URL} {INSTALL_DIR}; "
        f"fi")
    print("      Done.")

    # ── Step 4: create venv and install deps (idempotent) ───────────────────
    print("[4/9] Installing Python dependencies ...")
    run(client, machine_id,
        f"python3 -m venv {VENV} && {PIP} install --quiet -e {INSTALL_DIR}",
        timeout_ms=600_000)
    print("      Done.")

    # ── Step 5: upload .env ─────────────────────────────────────────────────
    print("[5/9] Uploading .env ...")
    run(client, machine_id, f"cat > {INSTALL_DIR}/.env", stdin=build_env_content())
    print("      Done.")

    # ── Step 6: upload GitHub App private key ───────────────────────────────
    print("[6/9] Uploading GitHub App private key ...")
    local_key = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "")
    key_path = Path(local_key).expanduser() if local_key else None
    if key_path and key_path.exists():
        run(client, machine_id, f"cat > {KEY_PATH_ON_MACHINE}",
            stdin=key_path.read_text())
        run(client, machine_id, f"chmod 600 {KEY_PATH_ON_MACHINE}")
        print("      Done.")
    else:
        print(f"      WARNING: {local_key} not found locally.")
        print(f"      You must upload it manually to {KEY_PATH_ON_MACHINE} on the machine.")

    # ── Step 7: kill any previous server instance and start fresh ───────────
    print("[7/9] Starting gitprbot server ...")
    run(client, machine_id,
        f"pkill -f 'gitprbot.main' 2>/dev/null || true; "
        f"sleep 1; "
        f"cd {INSTALL_DIR} && "
        f"nohup {PYTHON} -m gitprbot.main > /var/log/gitprbot.log 2>&1 &")
    time.sleep(4)
    print("      Started.")

    # ── Step 8: health check ────────────────────────────────────────────────
    print("[8/9] Health check ...")
    try:
        health = run(client, machine_id, "curl -sf http://localhost:8000/healthz")
        print(f"      {health}")
    except RuntimeError as e:
        # Print server log tail to help diagnose
        try:
            log = run(client, machine_id, "tail -30 /var/log/gitprbot.log")
            print(f"      Health check failed. Server log:\n{log}")
        except Exception:
            pass
        raise SystemExit("Server did not start — see log above.") from e

    # ── Step 9: expose port publicly ────────────────────────────────────────
    print("[9/9] Exposing port 8000 ...")
    preview = client.machines.previews.create(
        machine_id=machine_id,
        port=8000,
        protocol="https",
        visibility="public",
    )
    webhook_url = f"{preview.url}/webhooks/github"
    print("      Done.")

    print()
    print("=" * 62)
    print("  Orchestrator deployed!")
    print()
    print(f"  Machine ID  : {machine_id}")
    print(f"  Preview URL : {preview.url}")
    print()
    print("  Paste this into GitHub App → Webhook URL:")
    print()
    print(f"    {webhook_url}")
    print()
    print("  To watch live logs:")
    print(f"    (ssh into machine and run: tail -f /var/log/gitprbot.log)")
    print("=" * 62)


if __name__ == "__main__":
    main()
