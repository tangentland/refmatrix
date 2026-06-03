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
from typing import Callable

from refmatrix.ingest import (
    CODE_EXTS,
    DOC_EXTS,
    _ingest_adr_semantics,
    _ingest_markdown_semantics,
    _ingest_pseudo_semantics,
    _ingest_python_semantics,
    _ingest_tldr,
    _is_adr_file,
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
               semantic: bool = False,
               cancel_check: Callable[[], bool] | None = None,
               yield_lock: Callable[[], None] | None = None,
               yield_every: int = 1) -> dict:
    return _sync_paths(s, [Path(p) for p in paths], project_root, semantic,
                       cancel_check=cancel_check,
                       yield_lock=yield_lock, yield_every=yield_every)


def changed_since(project_root: Path, git_ref: str) -> list[Path]:
    """Absolute paths of files changed since `git_ref`
    (`git diff --name-only`). No Store needed, so the CLI can resolve a
    `--since` set to enqueue for the daemon without opening the catalog."""
    project_root = Path(project_root).resolve()
    if shutil.which("git") is None:
        raise RuntimeError("git not on PATH")
    out = subprocess.run(
        ["git", "-C", str(project_root), "diff", "--name-only", git_ref],
        capture_output=True, text=True, check=True,
    )
    return [project_root / f for f in out.stdout.splitlines() if f.strip()]


def sync_since(s: Store, git_ref: str, project_root: Path | None = None,
               semantic: bool = False,
               cancel_check: Callable[[], bool] | None = None,
               yield_lock: Callable[[], None] | None = None,
               yield_every: int = 1) -> dict:
    project_root = (project_root or Path.cwd()).resolve()
    files = changed_since(project_root, git_ref)
    return _sync_paths(s, files, project_root, semantic,
                       cancel_check=cancel_check,
                       yield_lock=yield_lock, yield_every=yield_every)


def flush_queue(s: Store, project_root: Path | None = None,
                semantic: bool = False,
                cancel_check: Callable[[], bool] | None = None,
                yield_lock: Callable[[], None] | None = None,
                yield_every: int = 1) -> dict:
    raws = drain_queue(s.root)
    paths = [Path(p) for p in raws]
    return _sync_paths(s, paths, project_root, semantic,
                       cancel_check=cancel_check,
                       yield_lock=yield_lock, yield_every=yield_every)


def _sync_paths(
    s: Store,
    paths: list[Path],
    project_root: Path | None,
    semantic: bool,
    *,
    cancel_check: Callable[[], bool] | None = None,
    yield_lock: Callable[[], None] | None = None,
    yield_every: int = 1,
) -> dict:
    project_root = (project_root or Path.cwd()).resolve()
    added = updated = purged = skipped_unchanged = 0
    touched_existing: list[Path] = []
    gmd_paths: list[Path] = []
    cancelled = False

    def _cancelled() -> bool:
        return cancel_check is not None and cancel_check()

    # Whole-batch transaction + cross-file deferred-link buffer.
    # Bundles every write in this sync into one DuckDB transaction (skips
    # per-statement WAL fsync) and accumulates every emitted link into one
    # bulk_link flush at the very end. Combined this turns a per-file
    # round-trip pattern into one batch round-trip — big wins on 100+ file
    # diffs (git post-commit `--since`).
    #
    # NB: yield_lock is plumbed through the signature for forward
    # compatibility but is intentionally NOT invoked inside the per-file
    # loop here. Releasing _store_lock mid-`s.transaction()` would let
    # another daemon thread see the connection in a half-open state.
    # Reads (via-replica) are the real CLI-priority lever -- they skip
    # _store_lock entirely. Yielding for writes is only safe between
    # transactions; ingest_gmd takes that path explicitly.
    _ = yield_lock, yield_every  # unused for now; see note above
    with s.transaction(), s.deferred_links():
        for p in paths:
            if _cancelled():
                cancelled = True
                break
            # Resolve so symlinked roots like /tmp -> /private/tmp on macOS
            # don't break relative_to() against the resolved project_root.
            ap = (p if p.is_absolute() else project_root / p).resolve()
            ext = ap.suffix.lower()
            is_supported = ext in CODE_EXTS or ext in DOC_EXTS or ext == ".gmd"
            if not ap.exists() or not is_supported:
                n = s.purge_path(str(ap))
                if n > 0:
                    purged += 1
                continue

            # Skip unchanged: if the file's on-disk mtime matches what we
            # already indexed, the previous ingest's output is still
            # current and re-extraction would be wasted work.
            try:
                disk_mtime = ap.stat().st_mtime
            except OSError:
                disk_mtime = None
            if disk_mtime is not None:
                cached_mtime = s.get_tracked_mtime(str(ap))
                if cached_mtime is not None and disk_mtime == cached_mtime:
                    skipped_unchanged += 1
                    continue

            # GMD dispatch: .gmd extension, or .md with gmd: frontmatter
            if ext == ".gmd" or (ext == ".md" and _is_gmd_file(ap)):
                if s.get_entity("doc", _relpath(ap, project_root)) is not None:
                    s.purge_path(str(ap))
                gmd_paths.append(ap)
                continue

            kind = "code" if ext in CODE_EXTS else "doc"
            rel = _relpath(ap, project_root)
            existed_before = s.get_entity(kind, rel) is not None
            # purge before re-add: drops stale per-function entities and any
            # linkages (semantic mentions, etc.) tied to the previous version.
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
        if gmd_paths and not _cancelled():
            from refmatrix.ingest_gmd import ingest_gmd_paths
            gmd_stats = ingest_gmd_paths(s, gmd_paths)
            added += gmd_stats.docs
            touched_existing.extend(gmd_paths)
        elif gmd_paths:
            cancelled = True

        # Refresh tldr-derived linkages only when at least one .py file
        # was touched. Doc-only commits (the common case for an ADR /
        # design-doc heavy repo) skip the 5-10 MB call_graph.json rewalk
        # entirely.
        py_touched = any(ap.suffix.lower() == ".py" for ap in touched_existing)
        cache = project_root / ".tldr" / "cache" / "call_graph.json"
        if py_touched and cache.exists() and not _cancelled():
            _ingest_tldr(s, project_root)

        # Per-file semantic extraction for markdown + pseudocode. All emitted
        # links accumulate into the single outer deferred_links buffer.
        md_touched = [ap for ap in touched_existing if ap.suffix.lower() == ".md"]
        pseudo_touched = [ap for ap in touched_existing if ap.suffix.lower() == ".pseudo"]

        for ap in pseudo_touched:
            if _cancelled():
                cancelled = True
                break
            _ingest_pseudo_semantics(s, ap, project_root)

        if md_touched and not _cancelled():
            adr_num_to_eid: dict[str, int] = {}
            adr_touched: list[Path] = []
            for ap in md_touched:
                adr_num = _is_adr_file(ap)
                if adr_num is not None:
                    adr_touched.append(ap)
                    e = s.get_entity("doc", _relpath(ap, project_root))
                    if e is not None:
                        adr_num_to_eid[adr_num] = e.id

            import re as _re
            adr_fn_re = _re.compile(r"/adr/(\d{4})-")
            for row in s._connect().execute(
                "SELECT id, name FROM entities WHERE kind='doc' AND name LIKE '%/adr/%'"
            ).fetchall():
                m = adr_fn_re.search(row["name"])
                if m:
                    adr_num_to_eid.setdefault(m.group(1), row["id"])

            for ap in adr_touched:
                if _cancelled():
                    cancelled = True
                    break
                _ingest_adr_semantics(s, ap, project_root, adr_num_to_eid)

            for ap in md_touched:
                if _cancelled():
                    cancelled = True
                    break
                if _is_adr_file(ap) is not None:
                    continue
                _ingest_markdown_semantics(s, ap, project_root, adr_num_to_eid)

        if semantic and not _cancelled():
            for ap in touched_existing:
                if _cancelled():
                    cancelled = True
                    break
                if ap.suffix.lower() == ".py":
                    _ingest_python_semantics(s, ap, project_root)

    report = {"added": added, "updated": updated, "purged": purged,
              "touched": len(touched_existing), "cancelled": cancelled}
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
