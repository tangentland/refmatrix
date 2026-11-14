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
    _ingest_tldr,
    _is_adr_file,
    should_ignore,
)
from refmatrix.store import MemoryOwnershipError, Store
from refmatrix.workdir import current_dir


_GMD_SNIFF_BYTES = 512


def _gmd_route_pending(s, path: Path, ext: str) -> bool:
    """Would this file route to GMD, but has never actually been GMD-ingested?

    The mtime gate above means "the previous ingest's output is still current",
    and that premise is false when the ROUTING changed rather than the file. A
    `.md` first indexed by the plain-doc branch got `mark_tracked(mtime)`
    stamped there; if it later becomes GMD-eligible — frontmatter added, or the
    GMD dispatch itself introduced after the fact — its mtime is unchanged, so
    the gate fires and the file NEVER reaches the dispatch below. It stays a
    content-less doc entity forever, because only an edit to the file can
    dislodge it.

    Measured on cliquedb: 199 `.md` files with zero `mentions` edges, 179 of
    them valid GMD, 100% skipped by this gate. That is 43% of the store's
    documents present in the index and unretrievable by their own content.

    Cost is one 512-byte sniff plus one indexed meta lookup, and ONLY for files
    that both sniff as GMD and were going to be skipped anyway.
    """
    if ext not in (".gmd", ".md"):
        return False
    if ext == ".md" and not _is_gmd_file(path):
        return False
    try:
        from refmatrix.ingest_gmd import _existing_hash_for, parse_gmd
        doc = parse_gmd(path)
        if doc is None:
            return False
        return _existing_hash_for(s, doc.doc_id, ("memory", "doc")) is None
    except Exception:
        return False


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
               cancel_check: Callable[[], bool] | None = None) -> dict:
    return _sync_paths(s, [Path(p) for p in paths], project_root, semantic,
                       cancel_check=cancel_check)


class GitRefError(RuntimeError):
    """`git diff --name-only <ref>` refused: a ref git does not know, a null sha, a range
    with a bad end. Carries the ref, git's exit status and git's own stderr.

    Why (bug-212, 2026-11-11): `changed_since` ran git with `check=True` and let
    `subprocess.CalledProcessError` escape, whose text is the argv and the exit status --
    never git's message. A post-checkout on `git worktree add` (null previous HEAD) printed a
    raw traceback on the committing terminal. The user asked for loud sync failures
    (2026-11-10: "if the sync stops in an error, it needs to fail loudly on the commandline or
    console, not just logs"); loud means one clean line naming the ref and what git said.

    A RuntimeError, so the CLI's daemon-down `--since` branch (which turns RuntimeError into
    a ClickException) needs no second handler; the in-process route names it explicitly; the
    daemon's op dispatcher turns it into `ok:false` with this text, which the CLI prints as
    `Error: daemon sync_since failed: ...`."""

    def __init__(self, git_ref: str, returncode: int, stderr: str):
        self.git_ref = git_ref
        self.returncode = returncode
        self.stderr = stderr
        # One line: an `Error:` line that names the ref and git's message on the SAME line.
        said = " ".join(ln.strip() for ln in stderr.splitlines() if ln.strip())
        super().__init__(f"sync --since {git_ref} failed: git diff exited {returncode}: "
                         f"{said or '(git printed nothing)'}")


# `git diff` in `changed_since` is bounded (bug-212 r4, ruling L82, 2026-11-13): the
# post-commit hook's backgrounded `rmx sync --since` calls it before any store opens, and a
# hanging git (a stuck mount, an fsmonitor) hung that sync silently, forever.
GIT_DIFF_TIMEOUT_S = 10


class GitTimeoutError(RuntimeError):
    """`git diff --name-only <ref>` ran past `GIT_DIFF_TIMEOUT_S` (bug-212 r4, ruling L82,
    2026-11-13). A RuntimeError for the same reason as `GitRefError`: the daemon-down
    `--since` branch turns any RuntimeError into one `Error:` line, the in-process route names
    it explicitly, and the daemon's op dispatcher reports it as `ok:false`."""

    def __init__(self, git_ref: str, project_root: Path, timeout: float):
        self.git_ref = git_ref
        super().__init__(f"sync --since {git_ref} failed: git diff timed out after "
                         f"{timeout:g}s in {project_root}")


def changed_since(project_root: Path, git_ref: str) -> list[Path]:
    """Absolute paths of files changed since `git_ref`
    (`git diff --name-only`). No Store needed, so the CLI can resolve a
    `--since` set to enqueue for the daemon without opening the catalog.

    A ref git rejects raises `GitRefError` (ref + git's stderr), never a bare
    `CalledProcessError` (bug-212, 2026-11-11); a `git diff` past `GIT_DIFF_TIMEOUT_S`
    raises `GitTimeoutError` (bug-212 r4, L82)."""
    project_root = Path(project_root).resolve()
    if shutil.which("git") is None:
        raise RuntimeError("git not on PATH")
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--name-only", git_ref],
            capture_output=True, text=True, timeout=GIT_DIFF_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitTimeoutError(git_ref, project_root, GIT_DIFF_TIMEOUT_S) from exc
    if out.returncode != 0:
        raise GitRefError(git_ref, out.returncode, out.stderr)
    return [project_root / f for f in out.stdout.splitlines() if f.strip()]


# The remedy a vanished cwd names in this module: the library reads the cwd only when its
# caller passed no `project_root` (the CLI and the daemon ops always pass one).
_NO_PROJECT_ROOT = "pass project_root, or run from an existing project directory"


def sync_since(s: Store, git_ref: str, project_root: Path | None = None,
               semantic: bool = False,
               cancel_check: Callable[[], bool] | None = None) -> dict:
    """Sync every path `git diff --name-only <git_ref>` names. With no `project_root` the
    cwd is the project; a vanished cwd raises `workdir.WorkingDirectoryGone`, not a bare
    `FileNotFoundError` naming nothing (bug-212 r1, ch-bsd s-1, 2026-11-11)."""
    project_root = (project_root or current_dir(remedy=_NO_PROJECT_ROOT)).resolve()
    files = changed_since(project_root, git_ref)
    return _sync_paths(s, files, project_root, semantic,
                       cancel_check=cancel_check)


def flush_queue(s: Store, project_root: Path | None = None,
                semantic: bool = False,
                cancel_check: Callable[[], bool] | None = None) -> dict:
    """Drain `dirty.queue` and sync it. Nothing drained is lost (task 26.2,
    ch-bsd r2 #s2-1, 2026-11-10): `drain_queue` unlinks the queue BEFORE the
    sync, so a path refused per path (`memory_ownership_errors`) goes back on
    the queue for the next flush to retry -- the healthy paths of the batch do
    not -- and a batch that raises outright puts EVERY drained path back
    (its one transaction rolled them all back) before re-raising."""
    raws = drain_queue(s.root)
    paths = [Path(p) for p in raws]
    try:
        report = _sync_paths(s, paths, project_root, semantic,
                             cancel_check=cancel_check)
    except BaseException:
        if raws:
            enqueue(s.root, raws)
        raise
    refused = [path for path, _msg in report.get("memory_ownership_errors") or []]
    if refused:
        enqueue(s.root, refused)
    report["requeued"] = len(refused)
    return report


def refusal_summary(refused: "list") -> str:
    """One line naming every path a sync refused and why (the memory and the
    cause, from `MemoryOwnershipError`). Shared by the CLI's `Error:` line, the
    daemon's error reply and the recorded daemon sync error, so every surface
    says the same thing (26.2 r2 #s2-1)."""
    parts = [f"{path}: {msg}" for path, msg in refused]
    return (f"{len(refused)} path(s) refused, their entities kept: " + " | ".join(parts))


def raise_if_refused(report: dict) -> None:
    """Fail loudly AFTER the batch committed (26.2 r2 #s2-1, user requirement
    2026-11-10: "if the sync stops in an error, it needs to fail loudly on the
    commandline or console, not just logs"): the healthy paths are synced, and
    the caller still sees a `MemoryOwnershipError` naming every refused path."""
    refused = report.get("memory_ownership_errors") or []
    if refused:
        raise MemoryOwnershipError(refusal_summary(refused))


def _sync_one(s: Store, ap: Path, project_root: Path, gmd_paths: list) -> str:
    """One path of `_sync_paths`' batch; returns what happened to it: `purged`,
    `none` (nothing to purge / not indexable), `skipped_unchanged`, `gmd`
    (queued on `gmd_paths` for the batch GMD ingest), `added` or `updated`.

    Split out of the loop (task 26.2, ch-bsd r2 #s2-1, 2026-11-10) so a
    `MemoryOwnershipError` from any of its `purge_path` calls is refused for
    THIS path only. Every write here follows its purge, so a refused path has
    written nothing."""
    # Honor .refmatrix_ignore (+ built-in dir rules). A path that is or
    # became ignored — e.g. content moved under workflow/ — is purged
    # from the index and skipped, so the concept graph self-cleans on
    # the next sync rather than retaining stale operational nodes.
    if should_ignore(ap, project_root):
        return "purged" if s.purge_path(str(ap)) > 0 else "none"
    ext = ap.suffix.lower()
    is_supported = ext in CODE_EXTS or ext in DOC_EXTS or ext == ".gmd"
    if not ap.exists() or not is_supported:
        return "purged" if s.purge_path(str(ap)) > 0 else "none"

    # Skip unchanged: if the file's on-disk mtime matches what we
    # already indexed, the previous ingest's output is still
    # current and re-extraction would be wasted work.
    try:
        disk_mtime = ap.stat().st_mtime
    except OSError:
        disk_mtime = None
    if disk_mtime is not None:
        cached_mtime = s.get_tracked_mtime(str(ap))
        if (cached_mtime is not None and disk_mtime == cached_mtime
                and not _gmd_route_pending(s, ap, ext)):
            return "skipped_unchanged"

    # GMD dispatch: .gmd extension, or .md with gmd: frontmatter
    if ext == ".gmd" or (ext == ".md" and _is_gmd_file(ap)):
        if s.get_entity("doc", _relpath(ap, project_root)) is not None:
            s.purge_path(str(ap))
        gmd_paths.append(ap)
        return "gmd"

    kind = "code" if ext in CODE_EXTS else "doc"
    rel = _relpath(ap, project_root)
    existed_before = s.get_entity(kind, rel) is not None
    # purge before re-add: drops stale per-function entities and any
    # linkages (semantic mentions, etc.) tied to the previous version.
    if existed_before:
        s.purge_path(str(ap))
    s.upsert_entity(kind=kind, name=rel, path=str(ap))
    s.mark_tracked(str(ap), ap.stat().st_mtime)
    return "updated" if existed_before else "added"


def _sync_paths(
    s: Store,
    paths: list[Path],
    project_root: Path | None,
    semantic: bool,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
    # Non-empty only: hook-driven `flush_queue` no-ops against an empty
    # global queue must stay quiet.
    if paths:
        from refmatrix.store import is_memory_only_root
        if is_memory_only_root(s.root):
            raise RuntimeError(
                f"sync refused: {s.root} is the memory-only global store "
                "and does not track filesystem paths. Sync from a project "
                "store instead."
            )
    # The cwd through the shared reader (bug-212 r1, ch-bsd s-1): `sync_files` and
    # `flush_queue` with no `project_root` reach here.
    project_root = (project_root or current_dir(remedy=_NO_PROJECT_ROOT)).resolve()
    added = updated = purged = skipped_unchanged = 0
    failed0 = getattr(s, "vector_delete_failures", 0)
    # Memory-bridge anchors a purge below DECLINED (task 26.2 r1 #b-1,
    # 2026-11-10): `Store.purge_path` keeps them and counts them on the store;
    # the delta is this sync's, reported and logged like a vector-delete failure.
    kept0 = getattr(s, "memory_anchors_kept", 0)
    touched_existing: list[Path] = []
    gmd_paths: list[Path] = []
    # [path, error] per path refused by `MemoryOwnershipError` (26.2 r2 #s2-1)
    refused: list[list[str]] = []
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
    # NB: this loop deliberately does NOT yield the store lock, and takes no
    # yield_lock/yield_every parameters to suggest otherwise. Releasing
    # _store_lock mid-`s.transaction()` would let another daemon thread see
    # the connection in a half-open state. Reads (via-replica) are the real
    # CLI-priority lever -- they skip _store_lock entirely. Yielding for
    # writes is only safe BETWEEN transactions, which is why `ingest_path`
    # and `ingest_gmd_paths` take those parameters and this does not; the
    # daemon passes them only to those two. They sat dead in four signatures
    # here until task 6.1 (2026-09-16) removed them.
    with s.transaction(), s.deferred_links():
        for p in paths:
            if _cancelled():
                cancelled = True
                break
            # Resolve so symlinked roots like /tmp -> /private/tmp on macOS
            # don't break relative_to() against the resolved project_root.
            ap = (p if p.is_absolute() else project_root / p).resolve()
            try:
                outcome = _sync_one(s, ap, project_root, gmd_paths)
            except MemoryOwnershipError as exc:
                # Refused PER PATH (task 26.2, ch-bsd r2 #s2-1, 2026-11-10):
                # `purge_path` raises before it deletes anything, so this
                # path's entities are intact; recording it and going on keeps
                # one unreadable memory row from rolling back every other path
                # in the batch. Named in the report; every caller fails loudly
                # on it (`raise_if_refused`, the daemon's recorded sync error).
                refused.append([str(ap), str(exc)])
                continue
            if outcome == "purged":
                purged += 1
            elif outcome == "skipped_unchanged":
                skipped_unchanged += 1
            elif outcome in ("added", "updated"):
                if outcome == "added":
                    added += 1
                else:
                    updated += 1
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
            # BULK, as full ingest does (bug-093): build each file's record off
            # the store, then apply them with batched upserts. The per-row
            # `_ingest_python_semantics` issued one INSERT ... ON CONFLICT per
            # docstring keyword under `_store_lock`; a watch re-sync of cli.py
            # held the lock for minutes and the hub watchdog killed the daemon.
            from refmatrix.ingest import _build_python_semantic_record
            from refmatrix.ingest_records import bulk_apply_records
            records = []
            for ap in touched_existing:
                if _cancelled():
                    cancelled = True
                    break
                if ap.suffix.lower() == ".py":
                    records.append(_build_python_semantic_record(ap, project_root))
            if records and not cancelled:
                bulk_apply_records(s, records)

    vector_delete_failed = getattr(s, "vector_delete_failures", 0) - failed0
    memory_anchors_kept = getattr(s, "memory_anchors_kept", 0) - kept0
    report = {"added": added, "updated": updated, "purged": purged,
              "touched": len(touched_existing), "cancelled": cancelled,
              "vector_delete_failed": vector_delete_failed,
              "memory_anchors_kept": memory_anchors_kept,
              "memory_ownership_errors": refused}
    s.append_sync_log(
        f"{time.strftime('%Y-%m-%dT%H:%M:%S')} "
        f"paths={len(paths)} +{added} ~{updated} -{purged} touched={len(touched_existing)} "
        f"semantic={semantic}"
        + (f" vector_delete_failed={vector_delete_failed}" if vector_delete_failed else "")
        + (f" memory_anchors_kept={memory_anchors_kept}" if memory_anchors_kept else "")
        + (f" memory_ownership_refused={len(refused)}" if refused else "")
    )
    return report


def _relpath(ap: Path, root: Path) -> str:
    try:
        return ap.relative_to(root).as_posix()
    except ValueError:
        return str(ap)
