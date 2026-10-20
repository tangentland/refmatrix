"""Per-project GMD curator driven by the change queue.

The daemon's watcher writes each flush of curator-relevant file changes as ONE
spool file under `<root>/curator.spool/` (task 3.7 #fam-refine-drain; it used to
append to a shared `<root>/curator.queue`). This module owns that spool — the
one parser, the status/drain token, the legacy-queue adoption, the startup
`*.tmp` sweep — and *consumes* it: it lints the queued
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
import uuid
from pathlib import Path

# The GMD lint lives outside the package (project convention); override with
# RMX_GMD_LINT. Absent/unfound → lint step is skipped, structural checks still run.
DEFAULT_LINT = str(Path.home() / "claude_tools" / "gmd" / "lint.py")


SPOOL_DIR = "curator.spool"
LEGACY_QUEUE = "curator.queue"
# `<time_ns zero-padded to 20>-<uuid4>.jsonl`: names sort oldest-first.
_SPOOL_SUFFIX = ".jsonl"


class SpoolTokenError(ValueError):
    """A drain token entry that is not a bare spool file name (a path, `..`, a hidden or
    non-`.jsonl` name). Raised before anything is deleted; a path is never followed."""


def curator_spool_dir(root: Path) -> Path:
    return Path(root) / SPOOL_DIR


def _spool_name(t_ns: "int | None" = None) -> str:
    return f"{(t_ns if t_ns is not None else time.time_ns()):020d}-{uuid.uuid4()}{_SPOOL_SUFFIX}"


def write_spool(root: Path, paths: "list[str]", *, reason: str = "fs-change") -> str:
    """Write ONE watcher flush as a new spool file: `{ts, path, reason}` per line, written to
    a `.tmp` name, fsynced, then renamed into place — a reader never sees it half-written
    and nothing holds it in memory across a fast-exit. Returns the spool file name.

    Why a file per flush (task 3.7 #fam-refine-drain, r4): rounds r2-r4 patched the shared
    `curator.queue` with a token, a lock, a generation counter and an in-place truncate, and
    each patch opened a new loss window. A failed write raises; its `.tmp` (never globbed by
    readers) is reaped by the daemon's startup sweep, the only deleter besides drain."""
    d = curator_spool_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    name = _spool_name()
    tmp = d / (name + ".tmp")
    now = time.time()
    body = "".join(json.dumps({"ts": now, "path": p, "reason": reason}, ensure_ascii=False)
                   + "\n" for p in paths)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, d / name)
    # The rename is durable only once the DIRECTORY entry is (remedy r1 R-L): a crash
    # after an un-synced rename can lose the new name.
    dfd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return name


def sweep_stale_tmp(root: Path) -> int:
    """Delete the spool's `*.tmp` files — a previous daemon's crash leftovers (task 3.7 r5
    M1). Run by the daemon at STARTUP only, before its watcher can write a new one.
    Returns the count removed; a file that cannot be removed raises."""
    d = curator_spool_dir(root)
    if not d.is_dir():
        return 0
    n = 0
    for f in sorted(d.glob("*.tmp")):
        try:
            f.unlink()
        except FileNotFoundError:
            continue
        n += 1
    return n


def _adopt_legacy_queue(root: Path, missing: "list[str]") -> None:
    """Rollout (task 3.7 #fam-refine-drain): a daemon still running pre-3.7 code appends to
    `curator.queue` until it is restarted. Move that file into the spool with ONE
    `os.rename` (atomic; the inode is kept), named by its last-append time so it sorts
    with the flushes it predates; it is then drained like any spool file. Nothing unlinks
    the legacy file. A rename that finds it gone means a concurrent status took it: that
    is `missing`, not an error."""
    legacy = Path(root) / LEGACY_QUEUE
    try:
        t_ns = legacy.stat().st_mtime_ns
    except FileNotFoundError:
        return
    d = curator_spool_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(legacy, d / _spool_name(t_ns))
    except FileNotFoundError:
        missing.append(LEGACY_QUEUE)


def _parse_spool_bytes(raw: bytes) -> "tuple[list[dict], int]":
    """THE parser of the watcher's format (task 3.7 r2 B1): one JSON object per line with
    at least a string `path`. Returns `(entries, bad_line_count)` — a bad line is counted,
    never silently dropped. (`read_queue` used to read each line as a raw path, so the
    scheduled scan found zero files in a queue the watcher had filled.)"""
    entries: list[dict] = []
    bad = 0
    for ln in raw.decode("utf-8", errors="replace").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            # A pre-spool `curator.queue` line may be a bare PATH (the format the old
            # fixtures and some writers used); adopted into the spool it is a legacy
            # entry, not noise (task 3.7 remedy r1 R-M2). Broken JSON stays bad.
            text = ln.strip()
            if text[:1] in ("{", "[", '"'):
                bad += 1
                continue
            entries.append({"ts": None, "path": text, "reason": "legacy"})
            continue
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) or not row["path"]:
            bad += 1
            continue
        entries.append(row)
    return entries, bad


def read_spool(root: Path, *, max_entries: "int | None" = 500) -> dict:
    """The `rmx_curator` status: `{entries, token, spool, warnings, missing}`.

    Reads WHOLE spool files oldest-first until the next one would pass `max_entries`
    (always at least one file, so a big flush can never wedge the spool; None = every
    file). `token` names exactly the files read, oldest first — the only names `drain`
    will delete. `spool = {files, bytes, remaining_files}` makes a never-drained spool
    visible. A listed file that is gone when read (ENOENT: a concurrent drain took it) is
    skipped, kept out of the token and reported in `missing`; any other OSError raises.
    Never deletes anything."""
    missing: list[str] = []
    _adopt_legacy_queue(root, missing)
    d = curator_spool_dir(root)
    names = sorted(f.name for f in d.glob("*" + _SPOOL_SUFFIX)) if d.is_dir() else []
    entries: list[dict] = []
    token: list[str] = []
    warnings: list[str] = []
    full = False
    for name in names:
        if full:
            break
        try:
            raw = (d / name).read_bytes()
        except FileNotFoundError:
            missing.append(name)
            continue
        rows, bad = _parse_spool_bytes(raw)
        if token and max_entries is not None and len(entries) + len(rows) > max_entries:
            full = True
            break
        token.append(name)
        # Each entry names the spool file it came from, so a caller that shows only
        # part of a read can drain exactly the files it showed in full (remedy r1 R-B1).
        entries.extend({**r, "file": name} for r in rows)
        if bad:
            warnings.append(f"{bad} unparseable line(s) in spool file {name} skipped "
                            f"(expected one {{ts, path, reason}} JSON object per line)")
    present: list[int] = []
    for name in names:
        if name in missing:
            continue
        try:
            present.append((d / name).stat().st_size)
        except FileNotFoundError:
            continue
    return {"entries": entries, "token": token,
            "spool": {"files": len(present), "bytes": sum(present),
                      "remaining_files": max(0, len(present) - len(token))},
            "warnings": warnings, "missing": missing}


def _check_token_name(name: str) -> str:
    n = str(name)
    if (not n or n != Path(n).name or n.startswith(".") or "/" in n or "\\" in n
            or not n.endswith(_SPOOL_SUFFIX)):
        raise SpoolTokenError(f"token entry {name!r} is not a spool file name "
                              f"(`<20 digits>-<uuid>.jsonl`, no path); nothing was drained")
    return n


def drain_spool(root: Path, token: "list[str]") -> dict:
    """Unlink EXACTLY the spool files `token` names (a `read_spool` result's `token`).
    Returns `{drained, missing}`: a name already gone was taken by a concurrent drain —
    reported, never an error, never a reason to delete anything else. Every name is
    validated before the first unlink; any other OSError raises naming the file and what
    was already drained. A flush written after the status is never in its token, so it
    can never be drained unread (the r1 B3 loss)."""
    names = [_check_token_name(n) for n in token]
    d = curator_spool_dir(root)
    drained: list[str] = []
    missing: list[str] = []
    for name in dict.fromkeys(names):
        try:
            (d / name).unlink()
        except FileNotFoundError:
            missing.append(name)
            continue
        except OSError as e:
            raise OSError(e.errno, f"could not drain spool file {name} ({e.strerror}); "
                                   f"already drained: {drained}") from e
        drained.append(name)
    return {"drained": drained, "missing": missing}


def read_queue(root: Path) -> list[str]:
    """Every queued path across the whole spool, deduped, oldest first."""
    out: list[str] = []
    for e in read_spool(root, max_entries=None)["entries"]:
        if e["path"] not in out:
            out.append(e["path"])
    return out


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
    return _scan_paths(Path(root), read_queue(root)[:limit])


def _scan_paths(root: Path, paths: "list[str]") -> list[dict]:
    out: list[dict] = []
    for rel in paths:
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
    """Scan the spool → write candidates to the shared refinement queue (the same
    surface bus promotions use) → with `drain`, drain EXACTLY the spool files it read
    (task 3.7 #fam-refine-drain: it deleted the whole queue, files it never read
    included). Every path of those files is scanned — draining a file whose paths
    were cut by a scan limit would lose them. Returns {candidates, drained, files,
    missing}."""
    from refmatrix.bus import refine_path
    root = Path(root)
    snap = read_spool(root)
    paths = list(dict.fromkeys(e["path"] for e in snap["entries"]))
    candidates = _scan_paths(root, paths)
    if candidates:
        p = refine_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            for c in candidates:
                f.write(json.dumps(c) + "\n")
    missing = list(snap["missing"])
    if drain and snap["token"]:
        missing += drain_spool(root, snap["token"])["missing"]
    return {"candidates": len(candidates), "drained": drain, "files": len(snap["token"]),
            "missing": missing, "warnings": snap["warnings"]}
