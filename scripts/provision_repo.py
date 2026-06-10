#!/usr/bin/env python3
"""Manually provision a repo: register it in the DB and trigger bootstrap."""
import asyncio
import sys

sys.path.insert(0, "src")

from gitprbot.auth.github_app import mint_installation_token
from gitprbot.config import settings
from gitprbot.db.connection import get_db, init_db
from gitprbot.db.repos import get_repo, set_machine_id, upsert_repo
from gitprbot.machines.bootstrap import bootstrap_machine
from gitprbot.machines.client import create_machine


async def provision(repo_full_name: str, install_id: str, default_branch: str = "main") -> None:
    await init_db()
    async with get_db() as db:
        await upsert_repo(db, repo_full_name, install_id, default_branch)
        repo = await get_repo(db, repo_full_name)

        if repo and repo.machine_id:
            print(f"Repo already has machine: {repo.machine_id}")
            machine_id = repo.machine_id
        else:
            print(f"Creating machine for {repo_full_name}...")
            machine_id = await create_machine(repo_full_name)
            await set_machine_id(db, repo_full_name, machine_id)
            print(f"Machine created: {machine_id}")

        print("Running bootstrap...")
        install_token = mint_installation_token(install_id)
        await bootstrap_machine(machine_id, repo_full_name, install_token, db)
        print("Bootstrap complete.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: provision_repo.py <owner/repo> <install_id> [default_branch]")
        sys.exit(1)
    asyncio.run(provision(*sys.argv[1:4]))
