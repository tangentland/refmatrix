"""Durable, coalescing queue for `learn_from_grep` work (bug-049).

`rmx grep` renders its hits and then teaches the graph what it found. That
teach used to be an RPC per grep — a WRITE taking the daemon's `_store_lock`,
on a store whose writer is simultaneously serving ingest and watch-flush. Two
costs fell out of that:

1. The CLI blocked on it. Each site passed a timeout and inherited
   `daemon.call`'s default `retries=2`, so a busy writer cost 3x the budget:
   30.16 s measured for the grep brokers, up to 180 s for one site. 104 of
   1,165 `grep-replica` calls in this project's `query.log` sat at
   30,178-30,222 ms, every one of them AFTER its results were on stdout.
2. Even bounded, N greps meant N write attempts, each contending for the lock
   whose contention was the problem.

So the client appends here instead — an `O_APPEND` write, no socket, no lock —
and the daemon's existing 30 s flush tick drains the queue: coalesced by
pattern, deduped by (file, line), applied under ONE lock acquisition. A queue
also survives a daemon restart, which the fire-and-forget RPC never did.

Nothing is dropped quietly. A malformed line, an unusable hit, and an overflow
past `MAX_QUEUE_LINES` are each COUNTED and reported by the caller
(CLAUDE.md#no-silent-failures) — a graph that silently stops learning shows up
only as retrieval slowly getting worse, which is the hardest thing to notice.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

QUEUE_NAME = "learn.queue.jsonl"

# A grep in a shell loop must not be able to fill the disk. On overflow the
# NEWEST entries win: an older pattern is likelier to have been learned
# already, and the freshest search is the one the user is actually doing.
MAX_QUEUE_LINES = int(os.environ.get("RMX_LEARN_QUEUE_MAX") or 5000)


@dataclass
class Batch:
    """One drained queue: what to apply, and everything that did not survive."""
    entries: list = field(default_factory=list)   # [{pattern, hits}]
    dropped_malformed: int = 0
    dropped_overflow: int = 0
    lines_read: int = 0


def queue_path(root: Path) -> Path:
    return Path(root) / QUEUE_NAME


def enqueue(root: Path, pattern: str, hits: list) -> int:
    """Append one teach record. Returns the number of records written (0 or 1).

    Deliberately the cheapest thing that can persist: one `O_APPEND` line. No
    socket, no lock, no daemon — this runs on a read path that has already
    produced its answer.
    """
    if not pattern or not hits:
        return 0
    rec = {"ts": time.time(), "pattern": pattern, "hits": hits}
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    p = queue_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    # O_APPEND: concurrent greps interleave whole lines rather than corrupting
    # each other, and a drain rotating the file underneath us loses nothing.
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return 1


def rotate(root: Path) -> "Path | None":
    """Move the queue aside so a concurrent `enqueue` starts a fresh file.

    Rename is atomic within the directory, so an append racing this lands in
    the NEXT batch instead of being truncated away.
    """
    p = queue_path(root)
    if not p.exists():
        return None
    rotated = p.with_suffix(f".jsonl.{int(time.time() * 1000)}.draining")
    try:
        p.rename(rotated)
    except FileNotFoundError:          # another drain won the race
        return None
    return rotated


def read_rotated(rotated: "Path | None") -> Batch:
    """Parse a rotated queue file into a coalesced batch and delete it."""
    batch = Batch()
    if rotated is None or not rotated.exists():
        return batch

    raw: list = []
    for line in rotated.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        batch.lines_read += 1
        try:
            rec = json.loads(line)
            pattern = rec["pattern"]
            hits = rec["hits"]
        except Exception:              # noqa: BLE001 — counted, never ignored
            batch.dropped_malformed += 1
            continue
        if not pattern or not isinstance(hits, list):
            batch.dropped_malformed += 1
            continue
        raw.append((pattern, hits))

    # Bound AFTER parsing so the count describes real work, and keep the tail:
    # the newest searches are the ones worth learning.
    if len(raw) > MAX_QUEUE_LINES:
        batch.dropped_overflow = len(raw) - MAX_QUEUE_LINES
        raw = raw[-MAX_QUEUE_LINES:]

    # Coalesce: one entry per pattern, hits deduped by (file, line). N greps
    # for the same term become ONE write instead of N.
    order: list = []
    merged: dict = {}
    for pattern, hits in raw:
        if pattern not in merged:
            merged[pattern] = {}
            order.append(pattern)
        for h in hits:
            try:
                key = (h["file"], int(h["line"]))
            except Exception:          # noqa: BLE001 — counted, never ignored
                batch.dropped_malformed += 1
                continue
            merged[pattern].setdefault(key, {"file": key[0], "line": key[1]})

    batch.entries = [{"pattern": p, "hits": list(merged[p].values())}
                     for p in order if merged[p]]
    try:
        rotated.unlink()
    except FileNotFoundError:
        pass
    return batch


def drain(root: Path) -> Batch:
    """Rotate and parse in one step. The daemon's flush tick calls this."""
    return read_rotated(rotate(root))


def requeue(root: Path, entries: list) -> int:
    """Put unprocessed entries back at the tail of the queue.

    The drain yields the writer lock between entries and stops at a time
    budget, so a big batch finishes across several ticks instead of holding
    the lock against ingest, recall and save-state. Whatever it did not reach
    comes back here — the alternative is dropping work to make a tick look
    fast, which is the shape this project calls a cheap fix.
    """
    n = 0
    for e in entries:
        n += enqueue(root, e.get("pattern") or "", e.get("hits") or [])
    return n


def pending_lines(root: Path) -> int:
    """Cheap depth probe for status surfaces. 0 when the queue is absent."""
    p = queue_path(root)
    if not p.exists():
        return 0
    try:
        with p.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0
