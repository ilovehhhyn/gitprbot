#!/usr/bin/env python3
"""Deploy the gitprbot orchestrator onto a Dedalus Machine.

Run this once from your laptop:
  python3 scripts/deploy_orchestrator.py

It will:
  1. Create a Dedalus Machine for the orchestrator
  2. Install Python + dependencies
  3. Clone the repo
  4. Upload your .env and private key
  5. Start the server
  6. Expose port 8000 publicly
  7. Print the webhook URL to paste into your GitHub App settings
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


def run(client, machine_id: str, command: list, stdin: str = None, timeout_ms: int = 300_000) -> str:
    kwargs = {"timeout_ms": timeout_ms}
    if stdin:
        kwargs["stdin"] = stdin
    exc = client.machines.executions.create(machine_id=machine_id, command=command, **kwargs)
    while exc.status not in DONE:
        time.sleep(1)
        exc = client.machines.executions.retrieve(
            machine_id=machine_id, execution_id=exc.execution_id
        )
    out = client.machines.executions.output(
        machine_id=machine_id, execution_id=exc.execution_id
    )
    if exc.status != "succeeded":
        raise RuntimeError(
            f"Command failed ({exc.status}): {exc.error_message}\n"
            f"stdout: {out.stdout}\nstderr: {out.stderr}"
        )
    return out.stdout or ""


def build_env_content() -> str:
    """Read local .env and rewrite GITHUB_APP_PRIVATE_KEY_PATH to the machine path."""
    env_path = Path(".env")
    if not env_path.exists():
        print("ERROR: .env file not found in current directory.")
        sys.exit(1)

    lines = []
    for line in env_path.read_text().splitlines():
        if line.startswith("GITHUB_APP_PRIVATE_KEY_PATH="):
            lines.append(f"GITHUB_APP_PRIVATE_KEY_PATH={KEY_PATH_ON_MACHINE}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def main():
    api_key = os.environ.get("DEDALUS_API_KEY")
    if not api_key:
        print("ERROR: DEDALUS_API_KEY not set in .env")
        sys.exit(1)

    client = Dedalus(api_key=api_key)

    # 1. Create the orchestrator machine (long autosleep so it stays up between webhooks)
    print("Creating orchestrator machine...")
    machine = client.machines.create(
        vcpu=2,
        memory_mib=4096,
        storage_gib=20,
    )
    machine_id = machine.machine_id
    print(f"  Machine ID: {machine_id}")

    # 2. Wait for the machine to be fully running
    print("Waiting for machine to be ready...")
    for event in client.machines.watch(machine_id=machine_id):
        pass
    print("  Machine ready.")

    # 3. Install system dependencies
    print("Installing Python and git...")
    run(client, machine_id, [
        "/bin/bash", "-c",
        "apt-get update -qq && apt-get install -y -qq python3 python3-pip git"
    ])

    # 4. Clone the repo
    print(f"Cloning {REPO_URL}...")
    run(client, machine_id, [
        "/bin/bash", "-c",
        f"git clone {REPO_URL} {INSTALL_DIR}"
    ])

    # 5. Install Python dependencies
    print("Installing Python dependencies...")
    run(client, machine_id, [
        "/bin/bash", "-c",
        f"cd {INSTALL_DIR} && pip3 install -e ."
    ], timeout_ms=600_000)

    # 6. Upload .env (with key path rewritten to machine path)
    print("Uploading .env...")
    env_content = build_env_content()
    run(client, machine_id, ["/bin/bash", "-c", f"cat > {INSTALL_DIR}/.env"], stdin=env_content)

    # 7. Upload GitHub App private key
    local_key_path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "")
    if local_key_path and Path(local_key_path).expanduser().exists():
        print("Uploading GitHub App private key...")
        key_content = Path(local_key_path).expanduser().read_text()
        run(client, machine_id, ["/bin/bash", "-c", f"cat > {KEY_PATH_ON_MACHINE}"], stdin=key_content)
    else:
        print(f"WARNING: GITHUB_APP_PRIVATE_KEY_PATH not found locally ({local_key_path}).")
        print(f"         You will need to manually upload it to {KEY_PATH_ON_MACHINE} on the machine.")

    # 8. Start the server as a background process
    print("Starting gitprbot server...")
    run(client, machine_id, [
        "/bin/bash", "-c",
        f"cd {INSTALL_DIR} && nohup python3 -m gitprbot.main > /var/log/gitprbot.log 2>&1 &"
    ])

    # Give the server a moment to start
    time.sleep(3)

    # 9. Verify the server is up
    print("Verifying server health...")
    try:
        health = run(client, machine_id, [
            "/bin/bash", "-c",
            "curl -sf http://localhost:8000/healthz"
        ])
        print(f"  Health check: {health.strip()}")
    except RuntimeError:
        print("  WARNING: health check failed — server may still be starting. Check /var/log/gitprbot.log")

    # 10. Expose port 8000 publicly
    print("Exposing port 8000...")
    preview = client.machines.previews.create(
        machine_id,
        port=8000,
        protocol="https",
        visibility="public",
    )
    webhook_url = f"{preview.url}/webhooks/github"

    print()
    print("=" * 60)
    print("Orchestrator deployed successfully!")
    print()
    print(f"  Machine ID : {machine_id}")
    print(f"  Preview URL: {preview.url}")
    print()
    print("Paste this into your GitHub App webhook URL setting:")
    print()
    print(f"  {webhook_url}")
    print()
    print("Server logs: ssh into the machine and run:")
    print(f"  tail -f /var/log/gitprbot.log")
    print("=" * 60)


if __name__ == "__main__":
    main()
