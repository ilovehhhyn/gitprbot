from __future__ import annotations

from gitprbot.machines.runner import run_on_machine

BUILD_EMBED_SCRIPT = '''
import os, json, sqlite3, hashlib

INDEX_DIR = "/agent/memory/index"
MANIFEST = f"{INDEX_DIR}/manifest.json"
DB_PATH = f"{INDEX_DIR}/embeddings.sqlite"
REPO = "/repo"

SKIP = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".md", ".txt"}

os.makedirs(INDEX_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        path TEXT,
        chunk_idx INTEGER,
        chunk TEXT,
        content_hash TEXT,
        PRIMARY KEY (path, chunk_idx)
    )
""")
conn.commit()

manifest = {}
if os.path.exists(MANIFEST):
    manifest = json.load(open(MANIFEST))

new_manifest = {}
changed_files = []

for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
    for fname in files:
        if not any(fname.endswith(ext) for ext in EXTENSIONS):
            continue
        fpath = os.path.join(root, fname)
        rel = os.path.relpath(fpath, REPO)
        try:
            content = open(fpath, errors="replace").read()
        except Exception:
            continue
        h = hashlib.sha256(content.encode()).hexdigest()
        new_manifest[rel] = h
        if manifest.get(rel) != h:
            changed_files.append((rel, fpath, content))

print(f"Files changed: {len(changed_files)}")

CHUNK_SIZE = 100

for rel, fpath, content in changed_files:
    lines = content.splitlines()
    conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
    for i in range(0, len(lines), CHUNK_SIZE):
        chunk = "\\n".join(lines[i:i+CHUNK_SIZE])
        chunk_idx = i // CHUNK_SIZE
        h = hashlib.sha256(chunk.encode()).hexdigest()
        conn.execute(
            "INSERT OR REPLACE INTO chunks (path, chunk_idx, chunk, content_hash) VALUES (?,?,?,?)",
            (rel, chunk_idx, chunk, h)
        )

conn.commit()
conn.close()

with open(MANIFEST + ".tmp", "w") as f:
    json.dump(new_manifest, f)
os.rename(MANIFEST + ".tmp", MANIFEST)

print("Index built.")
'''


async def build_embedding_index(machine_id: str) -> None:
    """Build the full keyword/chunk index on the machine."""
    await run_on_machine(
        machine_id,
        ["python3", "-c", BUILD_EMBED_SCRIPT],
        timeout_ms=300_000,
    )


async def update_embedding_index(machine_id: str) -> None:
    """Incremental update: only re-indexes changed files via manifest hash comparison."""
    await run_on_machine(
        machine_id,
        ["python3", "-c", BUILD_EMBED_SCRIPT],
        timeout_ms=300_000,
    )


async def query_index(machine_id: str, query: str, top_k: int = 10) -> list[str]:
    script = f"""
import sqlite3
conn = sqlite3.connect('/agent/memory/index/embeddings.sqlite')
rows = conn.execute(
    "SELECT chunk FROM chunks WHERE chunk LIKE ? LIMIT ?",
    ('%{query.replace("'", "")}%', {top_k})
).fetchall()
for r in rows:
    print(r[0])
    print('---')
"""
    out = await run_on_machine(
        machine_id, ["python3", "-c", script], timeout_ms=15_000
    )
    chunks = [c.strip() for c in out.split("---") if c.strip()]
    return chunks
