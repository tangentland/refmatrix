"""
Incremental sync. Three trigger paths:

- `sync_files(paths)`         — caller hands us the list (hooks)
- `sync_since(git_ref)`       — derive list from `git diff --name-only`
- `flush_queue()`             — drain `.refmatrix/dirty.queue`

All paths route through `_sync_paths`. Missing files purge their entities.
Existing files are re-ingested via the same logic as `rmx ingest`.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from refmatrix.ingest import (
    CODE_EXTS,
    DOC_EXTS,
    _ingest_tldr,
    _ingest_python_semantics,
)
from refmatrix.store import Store


_GMD_SNIFF_BYTES = 512


def _is_gmd_file(path: Path) -> bool:
    """Cheap sniff: file opens with `---` and has `gmd:` in first ~512 bytes."""
    try:
        with path.open("rb") as f:
            head = f.read(_GMD_SNIFF_BYTES)
    except OSError:
        return False
    if not head.startswith(b"---"):
        return False
    return b"\ngmd:" in head or b"\ngmd :" in head


QUEUE_FILE = "dirty.queue"


def enqueue(root: Path, paths: list[str]) -> None:
    """Append paths to the dirty queue. Cheap, safe to call from any hook."""
    q = root / QUEUE_FILE
    q.parent.mkdir(parents=True, exist_ok=True)
    with q.open("a") as f:
        for p in paths:
            f.write(p + "\n")


def drain_queue(root: Path) -> list[str]:
    q = root / QUEUE_FILE
    if not q.exists():
        return []
    raw = q.read_text().splitlines()
    q.unlink()
    # dedup, preserve order
    seen, out = set(), []
    for line in raw:
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            out.append(line)
    return out


def sync_files(s: Store, paths: list[str], project_root: Path | None = None,
               semantic: bool = False) -> dict:
    return _sync_paths(s, [Path(p) for p in paths], project_root, semantic)


def sync_since(s: Store, git_ref: str, project_root: Path | None = None,
               semantic: bool = False) -> dict:
    project_root = (project_root or Path.cwd()).resolve()
    if shutil.which("git") is None:
        raise RuntimeError("git not on PATH")
    out = subprocess.run(
        ["git", "-C", str(project_root), "diff", "--name-only", git_ref],
        capture_output=True, text=True, check=True,
    )
    files = [project_root / f for f in out.stdout.splitlines() if f.strip()]
    return _sync_paths(s, files, project_root, semantic)


def flush_queue(s: Store, project_root: Path | None = None,
                semantic: bool = False) -> dict:
    raws = drain_queue(s.root)
    paths = [Path(p) for p in raws]
    return _sync_paths(s, paths, project_root, semantic)


def _sync_paths(
    s: Store,
    paths: list[Path],
    project_root: Path | None,
    semantic: bool,
) -> dict:
    project_root = (project_root or Path.cwd()).resolve()
    added = updated = purged = 0
    touched_existing: list[Path] = []
    gmd_paths: list[Path] = []

    for p in paths:
        # Always resolve so symlinked roots like /tmp -> /private/tmp on macOS
        # don't break relative_to() against the (already-resolved) project_root.
        ap = (p if p.is_absolute() else project_root / p).resolve()
        ext = ap.suffix.lower()
        is_supported = ext in CODE_EXTS or ext in DOC_EXTS or ext == ".gmd"
        if not ap.exists() or not is_supported:
            n = s.purge_path(str(ap))
            if n > 0:
                purged += 1
            continue

        # GMD dispatch: .gmd extension, or .md with gmd: frontmatter
        if ext == ".gmd" or (ext == ".md" and _is_gmd_file(ap)):
            # Purge previous GMD state for this file, then re-ingest fully.
            if s.get_entity("doc", _relpath(ap, project_root)) is not None:
                s.purge_path(str(ap))
            gmd_paths.append(ap)
            continue

        kind = "code" if ext in CODE_EXTS else "doc"
        rel = _relpath(ap, project_root)
        existed_before = s.get_entity(kind, rel) is not None
        # purge before re-add: drops stale per-function entities and any
        # linkages (semantic mentions, etc.) tied to the previous version.
        # Stable file-level identity isn't preserved across syncs — saved
        # queries reference entities by (kind, name), not by id, so this
        # is safe.
        if existed_before:
            s.purge_path(str(ap))
        s.upsert_entity(kind=kind, name=rel, path=str(ap))
        s.mark_tracked(str(ap), ap.stat().st_mtime)
        if existed_before:
            updated += 1
        else:
            added += 1
        touched_existing.append(ap)

    # Batch GMD ingest so cross-doc refs in the same sync resolve correctly.
    if gmd_paths:
        from refmatrix.ingest_gmd import ingest_gmd_paths
        gmd_stats = ingest_gmd_paths(s, gmd_paths)
        added += gmd_stats.docs  # rough — ingest_gmd doesn't distinguish add/update
        touched_existing.extend(gmd_paths)

    # Refresh tldr-derived linkages for touched files when the call graph cache exists.
    cache = project_root / ".tldr" / "cache" / "call_graph.json"
    if cache.exists() and touched_existing:
        # Cheaper than re-importing the whole graph: re-run the importer; it is
        # idempotent because of the upsert + idempotent link semantics. The
        # forward index keeps deletes correct already (handled above).
        _ingest_tldr(s, project_root)

    if semantic:
        for ap in touched_existing:
            if ap.suffix.lower() == ".py":
                _ingest_python_semantics(s, ap, project_root)

    report = {"added": added, "updated": updated, "purged": purged,
              "touched": len(touched_existing)}
    s.append_sync_log(
        f"{time.strftime('%Y-%m-%dT%H:%M:%S')} "
        f"paths={len(paths)} +{added} ~{updated} -{purged} touched={len(touched_existing)} "
        f"semantic={semantic}"
    )
    return report


def _relpath(ap: Path, root: Path) -> str:
    try:
        return ap.relative_to(root).as_posix()
    except ValueError:
        return str(ap)
