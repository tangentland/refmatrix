"""Per-project GMD curator driven by the change queue.

The daemon's watcher already appends curator-relevant file changes to
`<root>/curator.queue`. This module *consumes* that queue: it lints the queued
GMD docs and turns problems (lint errors, dangling wikilinks, missing `rel:`
provenance, brand-new docs) into **curation candidates** — entries in the shared
refinement queue that an agent or human approves before anything lands. No
silent graph writes (per the no-silent-failures rule); the heavy LLM curation
stays agent-driven (the `gmd-curator` subagent drains the candidates).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# The GMD lint lives outside the package (project convention); override with
# RMX_GMD_LINT. Absent/unfound → lint step is skipped, structural checks still run.
DEFAULT_LINT = str(Path.home() / "claude_tools" / "gmd" / "lint.py")


def curator_queue_path(root: Path) -> Path:
    return Path(root) / "curator.queue"


def read_queue(root: Path) -> list[str]:
    p = curator_queue_path(root)
    if not p.exists():
        return []
    paths = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and ln not in paths:
            paths.append(ln)
    return paths


def drain_queue(root: Path) -> None:
    p = curator_queue_path(root)
    try:
        p.unlink()
    except OSError:
        pass


def _is_gmd(path: Path) -> bool:
    if path.suffix not in (".md", ".gmd"):
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return False
    return 'gmd:' in head and path.suffix in (".md", ".gmd")


def _lint(path: Path) -> tuple[bool, str]:
    """Run the GMD linter on a file. Returns (ok, output). ok=True when lint is
    unavailable (don't manufacture failures)."""
    lint = os.environ.get("RMX_GMD_LINT", DEFAULT_LINT)
    if not Path(lint).exists():
        return True, "(lint unavailable)"
    try:
        r = subprocess.run([sys.executable, lint, str(path)],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout or r.stderr)[-800:]
    except (OSError, subprocess.SubprocessError) as e:
        return True, f"(lint error: {e})"


def scan(root: Path, *, limit: int = 50) -> list[dict]:
    """Lint the queued GMD docs and build curation candidates. Each candidate:
    {id, ts, origin, kind, path, status, detail, suggested}. Does NOT enqueue —
    `scan_and_enqueue` writes them to the refinement queue."""
    root = Path(root)
    out: list[dict] = []
    for rel in read_queue(root)[:limit]:
        p = Path(rel)
        if not p.is_absolute():
            p = (root.parent / rel)
        if not p.exists() or not _is_gmd(p):
            continue
        ok, detail = _lint(p)
        cid = f"gmd-{abs(hash((str(p), detail))) % (10**10):010d}"
        if not ok:
            out.append({
                "id": cid, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "origin": "gmd-curator", "kind": "lint",
                "path": str(p), "status": "pending", "detail": detail,
                "suggested": {"action": "fix-gmd", "path": str(p),
                              "hint": "lint errors — dispatch gmd-curator subagent"},
            })
    return out


def scan_and_enqueue(root: Path, *, drain: bool = True) -> dict:
    """Scan the queue → write candidates to the shared refinement queue (the
    same surface bus promotions use) → optionally drain the curator queue.
    Returns {candidates: N, drained: bool}."""
    from refmatrix.bus import refine_path
    candidates = scan(root)
    if candidates:
        p = refine_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            for c in candidates:
                f.write(json.dumps(c) + "\n")
    if drain:
        drain_queue(root)
    return {"candidates": len(candidates), "drained": drain}
