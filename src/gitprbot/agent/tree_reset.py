from __future__ import annotations

from gitprbot.machines.runner import run_on_machine


async def reset_tree(machine_id: str, base_branch: str) -> None:
    """Reset the working tree to a clean state on base_branch.
    /caches lives outside /repo so git clean -fdx is safe with no excludes.
    """
    script = (
        f"git -C /repo fetch origin && "
        f"git -C /repo checkout {base_branch} && "
        f"git -C /repo reset --hard origin/{base_branch} && "
        f"git -C /repo clean -fdx && "
        f"rm -rf /agent/tmp && mkdir -p /agent/tmp"
    )
    await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", script],
        timeout_ms=120_000,
    )


async def checkout_agent_branch(machine_id: str, branch_name: str) -> None:
    """Check out an existing agent branch for an amend operation."""
    script = (
        f"git -C /repo fetch origin && "
        f"git -C /repo checkout {branch_name} && "
        f"git -C /repo reset --hard origin/{branch_name}"
    )
    await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", script],
        timeout_ms=60_000,
    )
