from __future__ import annotations

import json

from gitprbot.machines.errors import PatchFailed
from gitprbot.machines.runner import run_on_machine
from gitprbot.tools.dispatch import machine_tool


@machine_tool
async def read_file(machine_id: str, path: str) -> str:
    """Read the contents of a file on the machine."""
    return await run_on_machine(
        machine_id, ["cat", path], timeout_ms=10_000
    )


@machine_tool
async def list_dir(machine_id: str, path: str) -> str:
    """List files and directories at a path on the machine."""
    return await run_on_machine(
        machine_id, ["ls", "-la", path], timeout_ms=10_000
    )


@machine_tool
async def search_code(machine_id: str, query: str) -> str:
    """Search for a pattern in the repo using ripgrep."""
    return await run_on_machine(
        machine_id,
        ["rg", "--line-number", "--with-filename", "-e", query, "/repo"],
        timeout_ms=30_000,
    )


@machine_tool
async def retrieve(machine_id: str, query: str) -> str:
    """Semantic search over the codebase embedding index. Returns top-k code chunks."""
    script = f"""
import sqlite3, json, sys
try:
    conn = sqlite3.connect('/agent/memory/index/embeddings.sqlite')
    # Simple keyword fallback when embeddings not yet built
    rows = conn.execute(
        "SELECT chunk FROM chunks WHERE chunk LIKE ? LIMIT 10",
        (f'%{query.replace("'", "")}%',)
    ).fetchall()
    print('\\n---\\n'.join(r[0] for r in rows) if rows else 'No results found.')
except Exception as e:
    print(f'Retrieval error: {{e}}')
"""
    return await run_on_machine(
        machine_id, ["python3", "-c", script], timeout_ms=15_000
    )


@machine_tool
async def apply_patch(machine_id: str, unified_diff: str) -> str:
    """Apply a unified diff to the repo using git apply. Raises PatchFailed on error."""
    # Write diff to a temp file then apply
    script = f"""
import subprocess, sys, tempfile, os
diff = {json.dumps(unified_diff)}
with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
    f.write(diff)
    patch_path = f.name
result = subprocess.run(
    ['git', '-C', '/repo', 'apply', '--check', patch_path],
    capture_output=True, text=True
)
if result.returncode != 0:
    print('PATCH_CHECK_FAILED: ' + result.stderr)
    sys.exit(1)
result = subprocess.run(
    ['git', '-C', '/repo', 'apply', patch_path],
    capture_output=True, text=True
)
os.unlink(patch_path)
if result.returncode != 0:
    print('PATCH_APPLY_FAILED: ' + result.stderr)
    sys.exit(1)
print('Patch applied successfully.')
"""
    try:
        return await run_on_machine(
            machine_id, ["python3", "-c", script], timeout_ms=30_000
        )
    except Exception as exc:
        raise PatchFailed(str(exc)) from exc


@machine_tool
async def run_tests(machine_id: str) -> str:
    """Run the test suite. Returns stdout+stderr."""
    detect = """
import os
repo = '/repo'
if os.path.exists(f'{repo}/package.json'):
    import json
    pkg = json.load(open(f'{repo}/package.json'))
    cmd = pkg.get('scripts', {}).get('test', 'npm test')
    print(f'cd /repo && {cmd}')
elif os.path.exists(f'{repo}/pyproject.toml') or os.path.exists(f'{repo}/requirements.txt'):
    print('cd /repo && python -m pytest -x --tb=short 2>&1')
elif os.path.exists(f'{repo}/go.mod'):
    print('cd /repo && go test ./... 2>&1')
else:
    print('echo "No test command detected"')
"""
    cmd_str = await run_on_machine(
        machine_id, ["python3", "-c", detect], timeout_ms=5_000
    )
    return await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", cmd_str.strip()],
        timeout_ms=300_000,
    )


@machine_tool
async def run_lint(machine_id: str) -> str:
    """Run the linter."""
    script = """
import os, subprocess
repo = '/repo'
if os.path.exists(f'{repo}/package.json'):
    r = subprocess.run(['npm', 'run', 'lint', '--prefix', repo], capture_output=True, text=True)
elif os.path.exists(f'{repo}/pyproject.toml'):
    r = subprocess.run(['python', '-m', 'ruff', 'check', repo], capture_output=True, text=True)
else:
    print('No lint configured'); exit(0)
print(r.stdout + r.stderr)
"""
    return await run_on_machine(
        machine_id, ["python3", "-c", script], timeout_ms=120_000
    )


@machine_tool
async def run_build(machine_id: str) -> str:
    """Run the build step."""
    script = """
import os, subprocess
repo = '/repo'
if os.path.exists(f'{repo}/package.json'):
    import json
    pkg = json.load(open(f'{repo}/package.json'))
    build_cmd = pkg.get('scripts', {}).get('build', '')
    if build_cmd:
        r = subprocess.run(f'cd {repo} && npm run build', shell=True, capture_output=True, text=True)
        print(r.stdout + r.stderr)
    else:
        print('No build script in package.json')
elif os.path.exists(f'{repo}/pyproject.toml'):
    r = subprocess.run(['python', '-m', 'build', '--outdir', '/tmp/dist', repo], capture_output=True, text=True)
    print(r.stdout + r.stderr)
else:
    print('No build step configured')
"""
    return await run_on_machine(
        machine_id, ["python3", "-c", script], timeout_ms=300_000
    )


@machine_tool
async def git_branch(machine_id: str, name: str) -> str:
    """Create and checkout a new branch."""
    return await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", f"git -C /repo checkout -b {name}"],
        timeout_ms=15_000,
    )


@machine_tool
async def git_commit(machine_id: str, message: str) -> str:
    """Stage all changes and create a commit."""
    script = f"""
import subprocess
r = subprocess.run(
    ['git', '-C', '/repo', 'add', '-A'],
    capture_output=True, text=True
)
r2 = subprocess.run(
    ['git', '-C', '/repo', 'commit', '-m', {json.dumps(message)}],
    capture_output=True, text=True
)
print(r.stdout + r2.stdout + r.stderr + r2.stderr)
"""
    return await run_on_machine(
        machine_id, ["python3", "-c", script], timeout_ms=30_000
    )
