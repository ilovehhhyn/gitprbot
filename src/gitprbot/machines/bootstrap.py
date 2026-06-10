from __future__ import annotations

import json

from gitprbot.machines.runner import run_on_machine

BOOTSTRAP_PHASES = [
    "none",
    "cloned",
    "deps_installed",
    "caches_warm",
    "memory_built",
    "done",
]

STACK_DETECT_SCRIPT = """
import os, json, sys
repo = '/repo'
indicators = {
    'package.json': 'node',
    'requirements.txt': 'python',
    'Pipfile': 'python',
    'pyproject.toml': 'python',
    'go.mod': 'go',
    'Cargo.toml': 'rust',
    'pom.xml': 'java',
    'build.gradle': 'java',
}
for fname, stack in indicators.items():
    if os.path.exists(os.path.join(repo, fname)):
        print(stack)
        sys.exit(0)
print('unknown')
"""


async def bootstrap_machine(
    machine_id: str,
    repo_full_name: str,
    install_token: str,
    db: object,
) -> None:
    from gitprbot.db.repos import get_repo, set_bootstrap_phase

    row = await get_repo(db, repo_full_name)
    current_phase = row.bootstrap_phase if row else "none"
    phase_idx = BOOTSTRAP_PHASES.index(current_phase)

    clone_url = f"https://x-access-token:{install_token}@github.com/{repo_full_name}.git"

    if phase_idx < BOOTSTRAP_PHASES.index("cloned"):
        await _phase_cloned(machine_id, clone_url)
        await set_bootstrap_phase(db, repo_full_name, "cloned")

    if phase_idx < BOOTSTRAP_PHASES.index("deps_installed"):
        await _phase_deps_installed(machine_id)
        await set_bootstrap_phase(db, repo_full_name, "deps_installed")

    if phase_idx < BOOTSTRAP_PHASES.index("caches_warm"):
        await _phase_caches_warm(machine_id)
        await set_bootstrap_phase(db, repo_full_name, "caches_warm")

    if phase_idx < BOOTSTRAP_PHASES.index("memory_built"):
        await _phase_memory_built(machine_id, repo_full_name)
        await set_bootstrap_phase(db, repo_full_name, "memory_built")

    await set_bootstrap_phase(db, repo_full_name, "done")


async def _phase_cloned(machine_id: str, clone_url: str) -> None:
    setup = (
        "mkdir -p /caches /agent/memory/journal /agent/memory/index /agent/tmp && "
        f"git clone {clone_url} /repo"
    )
    await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", setup],
        timeout_ms=300_000,
    )


async def _phase_deps_installed(machine_id: str) -> None:
    stack_out = await run_on_machine(
        machine_id,
        ["python3", "-c", STACK_DETECT_SCRIPT],
        timeout_ms=10_000,
    )
    stack = stack_out.strip()

    if stack == "node":
        cmd = "npm ci --cache /caches/npm --prefix /repo"
    elif stack == "python":
        cmd = (
            "pip install --cache-dir /caches/pip "
            "-r /repo/requirements.txt 2>/dev/null || "
            "pip install --cache-dir /caches/pip -e /repo 2>/dev/null || true"
        )
    elif stack == "go":
        cmd = "cd /repo && GOPATH=/caches/go go mod download"
    elif stack == "rust":
        cmd = "cd /repo && CARGO_HOME=/caches/cargo cargo fetch"
    else:
        cmd = "echo 'unknown stack, skipping deps install'"

    await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", cmd],
        timeout_ms=600_000,
    )


async def _phase_caches_warm(machine_id: str) -> None:
    warm_script = """
cd /repo
if [ -f package.json ]; then
    npm test --passWithNoTests 2>&1 | tail -5 || true
elif [ -f requirements.txt ] || [ -f pyproject.toml ]; then
    python -m pytest --co -q 2>&1 | tail -5 || true
fi
"""
    await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", warm_script],
        timeout_ms=300_000,
    )


async def _phase_memory_built(machine_id: str, repo_full_name: str) -> None:
    from gitprbot.memory.embeddings import build_embedding_index

    # Write initial repo.md
    repo_md = await _generate_repo_md(machine_id, repo_full_name)
    await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", f"mkdir -p /agent/memory && cat > /agent/memory/repo.md.tmp << 'HEREDOC'\n{repo_md}\nHEREDOC\nmv /agent/memory/repo.md.tmp /agent/memory/repo.md"],
        timeout_ms=15_000,
    )

    # Write initial conventions.md
    conventions_md = "# Team Conventions\n\n<!-- No conventions learned yet. Updated as PRs are reviewed. -->\n"
    await run_on_machine(
        machine_id,
        ["/bin/bash", "-c", f"cat > /agent/memory/conventions.md.tmp << 'HEREDOC'\n{conventions_md}\nHEREDOC\nmv /agent/memory/conventions.md.tmp /agent/memory/conventions.md"],
        timeout_ms=10_000,
    )

    # Write architecture.md
    arch_md = await _generate_architecture_md(machine_id)
    await run_on_machine(
        machine_id,
        [
            "/bin/bash",
            "-c",
            f"cat > /agent/memory/architecture.md.tmp << 'HEREDOC'\n{arch_md}\nHEREDOC\nmv /agent/memory/architecture.md.tmp /agent/memory/architecture.md",
        ],
        timeout_ms=15_000,
    )

    # Build embedding index
    await build_embedding_index(machine_id)


async def _generate_repo_md(machine_id: str, repo_full_name: str) -> str:
    """Inspect the repo and emit a compact repo.md (~400 tokens or fewer)."""
    inspect = """
import os, json, sys

repo = '/repo'
info = {}

# Detect package manager and commands
if os.path.exists(f'{repo}/package.json'):
    try:
        pkg = json.load(open(f'{repo}/package.json'))
        scripts = pkg.get('scripts', {})
        info['install'] = 'npm ci'
        info['test'] = scripts.get('test', 'npm test')
        info['build'] = scripts.get('build', 'npm run build')
        info['stack'] = 'node'
    except Exception:
        pass
elif os.path.exists(f'{repo}/pyproject.toml'):
    info['install'] = 'pip install -e .'
    info['test'] = 'python -m pytest'
    info['build'] = 'python -m build'
    info['stack'] = 'python'
elif os.path.exists(f'{repo}/requirements.txt'):
    info['install'] = 'pip install -r requirements.txt'
    info['test'] = 'python -m pytest'
    info['build'] = 'echo no build step'
    info['stack'] = 'python'
elif os.path.exists(f'{repo}/go.mod'):
    info['install'] = 'go mod download'
    info['test'] = 'go test ./...'
    info['build'] = 'go build ./...'
    info['stack'] = 'go'
else:
    info['install'] = 'unknown'
    info['test'] = 'unknown'
    info['build'] = 'unknown'
    info['stack'] = 'unknown'

# Top-level dirs
dirs = [d for d in os.listdir(repo) if os.path.isdir(os.path.join(repo, d)) and not d.startswith('.')]
info['top_dirs'] = sorted(dirs)[:12]

print(json.dumps(info))
"""
    out = await run_on_machine(
        machine_id,
        ["python3", "-c", inspect],
        timeout_ms=15_000,
    )
    try:
        info = json.loads(out.strip())
    except Exception:
        info = {}

    return f"""# Repo: {repo_full_name}

## Commands
- Install: `{info.get('install', 'unknown')}`
- Test: `{info.get('test', 'unknown')}`
- Build: `{info.get('build', 'unknown')}`

## Stack
{info.get('stack', 'unknown')}

## Top-level directories
{', '.join(info.get('top_dirs', []))}

## Notes
- Caches: /caches  (outside /repo, never wiped by git clean)
- Agent memory: /agent/memory/
"""


async def _generate_architecture_md(machine_id: str) -> str:
    """Walk the source tree and produce a module map for architecture.md."""
    walk_script = r"""
import os

def walk(root, prefix='', depth=0, max_depth=4, skip=None):
    if skip is None:
        skip = {'.git', 'node_modules', '__pycache__', '.venv', 'dist', 'build', '.next'}
    entries = []
    try:
        items = sorted(os.scandir(root), key=lambda e: (not e.is_dir(), e.name))
    except PermissionError:
        return entries
    for entry in items:
        if entry.name in skip or entry.name.startswith('.'):
            continue
        rel = prefix + entry.name
        if entry.is_dir():
            entries.append(f"{'  ' * depth}{entry.name}/")
            if depth < max_depth:
                entries.extend(walk(entry.path, '', depth + 1, max_depth, skip))
        else:
            entries.append(f"{'  ' * depth}{entry.name}")
    return entries

lines = walk('/repo')
print('\n'.join(lines[:300]))
"""
    tree = await run_on_machine(
        machine_id,
        ["python3", "-c", walk_script],
        timeout_ms=20_000,
    )
    return f"# Architecture\n\n## Source tree\n\n```\n{tree.strip()}\n```\n"
