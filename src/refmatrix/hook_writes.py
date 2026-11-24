"""Hook writes enqueue and return: the interim spool behind 23.1 R11 (task-hook-writes-queue).

WHY (bug-309, bug-177; L212, 2026-11-24). The Stop hook's turn-end promote (`focus summarize
--promote --timeout 8`) waited on the daemon's single writer, and 72 of 136 runs timed out at
8.04 s, each a hook error in the session. The write itself was not lost (the dispatcher keeps a
dialled op); the CONFIRMATION and the subject filing were. A best-effort producer whose write
finds the daemon busy now appends one durable entry here and returns; the daemon applies it on
its flush tick and once at boot, newest AUTHORING time winning (`Store.add_memory(updated_at=)`).

The storage is NOT 23.1 R3's `BoundedQueue` (unbuilt): it is one file per entry under
`<store root>/hook_writes.spool/`, written exactly like `gmd_curator.write_spool` (`.tmp`, fsync,
rename, fsync the directory), so a reader never sees half an entry and nothing is held in memory
across a crash. When 23.1 builds R3 it re-bases this spool on `BoundedQueue` the way its R9
re-bases `learn_queue` (deferral row D5 in `workflow/deferral_registry.md`).

Nothing on this path is silent (CLAUDE.md #no-silent-failures): an enqueue that cannot write
raises; an unreadable entry is counted, named in `rmxd.log` and MOVED to `bad/` (never deleted,
never skipped); a partition whose apply fails is logged and its entries stay for the next drain.

The entry (R11.2): `{"op": "memory_add", "partition": <name>, "name": <memory name>, "args":
<the exact memory_add payload, carrying "updated_at": ts>, "subject": <label> | null, "origin":
"stop-hook" | "precompact" | "save-state", "ts": <epoch s>}`.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

SPOOL_DIRNAME = "hook_writes.spool"
BAD_DIRNAME = "bad"
QUEUE_NAME = "hook_writes"

ORIGINS = ("stop-hook", "precompact", "save-state")
OPS = ("memory_add",)
# The keyword arguments `Store.add_memory` takes: `args` is applied as `add_memory(**args)`, so a
# key outside this set would raise inside the drain's transaction on every tick (a poison entry).
# It is rejected as unreadable at read time instead.
MEMORY_ADD_ARGS = frozenset({"name", "content", "mtype", "tags", "metadata", "protected",
                             "updated_at"})

# A `*.tmp` younger than this at boot may be a producer's enqueue in flight, not a crash
# leftover: a producer enqueues exactly when the daemon is busy, and a booting daemon is busy.
# Its name carries its creation time (`<time_ns:020d>-…`), so the sweep reads the age from the
# name and leaves a young one for the next boot rather than pull it out from under a writer.
TMP_SWEEP_MIN_AGE_S = 60.0


class UnreadableEntry(ValueError):
    """A spool file that is not a well-formed entry (D3). Carries the reason."""


def spool_dir(root: "Path | str") -> Path:
    return Path(root) / SPOOL_DIRNAME


def bad_dir(root: "Path | str") -> Path:
    return spool_dir(root) / BAD_DIRNAME


def _spool_name() -> str:
    """`<time_ns:020d>-<uuid4>.json`: names sort oldest-first, never collide."""
    return f"{time.time_ns():020d}-{uuid.uuid4()}.json"


def validate(entry: Any) -> dict:
    """Return `entry` when it is a well-formed R11.2 entry, else raise `UnreadableEntry`
    naming what is wrong. Missing `name`, `partition` or `args` is unreadable (RED decision 6):
    applying it would guess."""
    if not isinstance(entry, dict):
        raise UnreadableEntry(f"entry is a {type(entry).__name__}, not an object")
    missing = [k for k in ("op", "name", "partition", "args", "ts") if k not in entry]
    if missing:
        raise UnreadableEntry(f"missing key(s) {', '.join(missing)}")
    if entry["op"] not in OPS:
        raise UnreadableEntry(f"op {entry['op']!r} is not one of {', '.join(OPS)}")
    for k in ("name", "partition"):
        if not isinstance(entry[k], str) or not entry[k]:
            raise UnreadableEntry(f"{k} is not a non-empty string: {entry[k]!r}")
    ts = entry["ts"]
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        raise UnreadableEntry(f"ts is not a number: {ts!r}")
    args = entry["args"]
    if not isinstance(args, dict):
        raise UnreadableEntry(f"args is a {type(args).__name__}, not an object")
    extra = sorted(set(args) - MEMORY_ADD_ARGS)
    if extra:
        raise UnreadableEntry(f"args carries key(s) add_memory does not take: {extra}")
    if args.get("name") != entry["name"]:
        raise UnreadableEntry(f"args.name {args.get('name')!r} differs from name "
                              f"{entry['name']!r}")
    if not isinstance(args.get("content"), str):
        raise UnreadableEntry("args.content is missing or not a string")
    subject = entry.get("subject")
    if subject is not None and not isinstance(subject, str):
        raise UnreadableEntry(f"subject is not a string or null: {subject!r}")
    subjects = entry.get("subjects")
    if subjects is not None and (not isinstance(subjects, list)
                                 or not all(isinstance(x, str) for x in subjects)):
        raise UnreadableEntry(f"subjects is not a list of strings: {subjects!r}")
    return entry


def enqueue(root: "Path | str", entry: dict) -> Path:
    """Append ONE entry as its own spool file and return the final path.

    Written like `gmd_curator.write_spool`: a `.tmp` name, fsync, rename, then fsync the
    directory, because the rename is durable only once the directory entry is. A malformed
    entry is a caller bug (`UnreadableEntry`, a ValueError); a write that fails raises its
    OSError with the path in it, and the `.tmp` it may leave is reaped by the daemon's startup
    sweep (`sweep_stale_tmp`). Never swallowed: a promote that could not be queued is not a
    queued promote (D6)."""
    validate(entry)
    d = spool_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    name = _spool_name()
    tmp = d / (name + ".tmp")
    final = d / name
    body = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, final)
    dfd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return final


def pending_files(root: "Path | str") -> "list[Path]":
    """The entries waiting: `*.json` directly in the spool (not `bad/`, not `*.tmp`), oldest
    first by name (= enqueue time)."""
    d = spool_dir(root)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if p.is_file())


def counts(root: "Path | str") -> dict:
    """`{"pending": n, "bad": m}` for the health surface (D4). `pending` counts every `*.json`
    waiting, a malformed one included until a drain moves it (RED decision 5)."""
    b = bad_dir(root)
    nbad = sum(1 for p in b.iterdir() if p.is_file()) if b.is_dir() else 0
    return {"pending": len(pending_files(root)), "bad": nbad}


def read_pending(root: "Path | str") -> "tuple[list[tuple[Path, dict]], list[tuple[Path, str]]]":
    """Read every pending entry. Returns `(readable, unreadable)`: `(path, entry)` pairs in
    enqueue order, and `(path, reason)` pairs for files that are not well-formed entries
    (invalid UTF-8, invalid JSON, a missing key). A file that vanished between the listing and
    the read (a concurrent drain took it) is neither."""
    good: list = []
    bad: list = []
    for p in pending_files(root):
        try:
            raw = p.read_bytes()
        except FileNotFoundError:
            continue
        try:
            entry = validate(json.loads(raw.decode("utf-8")))
        except UnicodeDecodeError as exc:
            bad.append((p, f"not UTF-8: {exc}"))
            continue
        except json.JSONDecodeError as exc:
            bad.append((p, f"not JSON: {exc}"))
            continue
        except UnreadableEntry as exc:
            bad.append((p, str(exc)))
            continue
        good.append((p, entry))
    return good, bad


def _labels(e: dict) -> list:
    if "subjects" in e and e["subjects"] is not None:
        return list(e["subjects"])
    return [e.get("subject")]


def newest_by_ts(acc: dict, ev: dict) -> dict:
    """The explicit merge of two entries for one `(op, partition, name)` (R11.1, round 13 s2).

    Keeps `ev` when `ev["ts"] >= acc["ts"]` (a tie goes to the later line), else `acc`, and the
    kept entry carries `subjects`: the ordered, de-duplicated union of `acc`'s labels then
    `ev`'s, `null` dropped. Why the authoring time and not the line: a line's position is its
    APPEND time, and the save-state promote can append ~29 s after its `ts` while the Stop hook
    appends within ~4 s of its own, so a position merge would apply older content. Why the
    union: `link_part_of` only sets bits, and the synchronous path files a digest under both
    labels when the session's subject changed between turns; the queued path must not lose a
    filing the synchronous path keeps. Returns a new dict; neither input is modified."""
    kept = ev if float(ev["ts"]) >= float(acc["ts"]) else acc
    union: list = []
    for label in _labels(acc) + _labels(ev):
        if label is not None and label not in union:
            union.append(label)
    return {**kept, "subjects": union}


def coalesce(entries: "list[tuple[Path, dict]]") -> "list[tuple[dict, list[Path]]]":
    """Fold readable entries by `(op, partition, name)` with `newest_by_ts`, in enqueue order.
    Returns `(winner, the spool files it stands for)` per key; a winner that met no other entry
    still carries `subjects` (`[subject]`, or `[]` when `subject` is null)."""
    groups: dict = {}
    order: list = []
    for path, e in entries:
        key = (e["op"], e["partition"], e["name"])
        if key not in groups:
            groups[key] = ({**e, "subjects": [x for x in _labels(e) if x is not None]}, [path])
            order.append(key)
        else:
            acc, paths = groups[key]
            groups[key] = (newest_by_ts(acc, e), paths + [path])
    return [groups[k] for k in order]


def _move_bad(root: Path, path: Path, reason: str, log: Callable[[str], None]) -> bool:
    """Move an unreadable entry to `bad/` byte for byte and name it in the log. Returns
    whether it moved; a move that fails is logged and the file stays counted as pending."""
    b = bad_dir(root)
    try:
        b.mkdir(parents=True, exist_ok=True)
        os.rename(path, b / path.name)
    except FileNotFoundError:
        return False
    except OSError as exc:
        log(f"hook_writes: unreadable spool entry {path.name} ({reason}) could NOT be moved "
            f"to {BAD_DIRNAME}/: {exc!r}; it stays in {path.parent} and is counted pending")
        return False
    log(f"hook_writes: unreadable spool entry {path.name} moved to {b}: {reason}")
    return True


def drain(root: "Path | str", store, *, store_lock, log: Callable[[str], None],
          is_fatal: "Callable[[BaseException], bool]" = lambda exc: False) -> dict:
    """Apply every pending entry (D2). Returns `{"applied", "superseded", "bad", "failed",
    "committed"}`.

    Reading the spool and moving unreadable files to `bad/` take no store lock. With no
    readable entry the writer is never taken, so an empty spool costs the tick a directory
    listing. Otherwise ONE `store_lock` acquisition covers the batch: entries are coalesced by
    `(op, partition, name)` with `newest_by_ts`, and each partition is applied in ONE
    `store.transaction()` -- for each winner `add_memory_checked(**args)` (the authoring-time
    guard decides, R11.3), then every label in its `subjects` is filed with `upsert_subject` +
    `link_part_of` on the row's id, the SAME store methods the `memory_add`, `subject_upsert`
    and `subject_link` ops call. Every store method on this path commits through
    `_maybe_commit` (no bare `con.commit()` inside the transaction, R11.3 m6). The partition's
    spool files are deleted only AFTER its commit: a crash between the two re-applies them and
    the guard counts them `superseded`.

    `superseded` counts ENTRIES (RED decision 3): each folded into a newer queued entry, plus a
    winner the guard skipped because the stored row is at least as new. A partition whose
    apply raises is rolled back, logged, counted `failed` and left in the spool for the next
    drain; an exception `is_fatal` classifies as a store invalidation is re-raised so the
    daemon fast-exits as it does for every other write."""
    root = Path(root)
    out = {"applied": 0, "superseded": 0, "bad": 0, "failed": 0, "committed": False}
    good, unreadable = read_pending(root)
    for path, reason in unreadable:
        out["bad"] += 1
        _move_bad(root, path, reason, log)
    if not good:
        if out["bad"]:
            log(f"hook_writes drain: 0 applied, {out['bad']} unreadable moved to "
                f"{BAD_DIRNAME}/")
        return out
    by_part: dict = {}
    for winner, paths in coalesce(good):
        by_part.setdefault(winner["partition"], []).append((winner, paths))
    with store_lock:
        for part, groups in by_part.items():
            applied = superseded = 0
            done: list = []
            try:
                with store.with_partition(part), store.transaction():
                    for winner, paths in groups:
                        superseded += len(paths) - 1
                        eid, written = store.add_memory_checked(**winner["args"])
                        if written:
                            applied += 1
                        else:
                            superseded += 1
                        for label in winner["subjects"]:
                            sid = store.upsert_subject(label)["id"]
                            store.link_part_of(int(eid), int(sid))
                        done.extend(paths)
            except Exception as exc:  # noqa: BLE001 -- classified: fatal re-raised, else counted
                if is_fatal(exc):
                    raise
                n = sum(len(p) for _, p in groups)
                out["failed"] += n
                log(f"hook_writes drain: partition {part!r} FAILED ({exc!r}); its {n} "
                    f"entr{'y' if n == 1 else 'ies'} stay in {spool_dir(root)} for the next "
                    f"drain")
                continue
            out["committed"] = True
            out["applied"] += applied
            out["superseded"] += superseded
            for p in done:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
    log(f"hook_writes drain: {out['applied']} applied, {out['superseded']} superseded, "
        f"{out['bad']} unreadable, {out['failed']} failed")
    return out


def sweep_stale_tmp(root: "Path | str", *, min_age_s: float = TMP_SWEEP_MIN_AGE_S) -> dict:
    """Startup sweep of the spool's `*.tmp` crash leftovers (D1), run by the daemon at boot
    before its first drain. Readers never glob `*.tmp`, so a leftover is litter, not data.
    A `.tmp` whose name says it was created less than `min_age_s` ago is LEFT (a producer may
    be mid-enqueue against the booting daemon) and counted `kept`; a name that carries no time
    is a leftover. Returns `{"removed", "kept"}`; a file that cannot be removed raises."""
    d = spool_dir(root)
    out = {"removed": 0, "kept": 0}
    if not d.is_dir():
        return out
    now_ns = time.time_ns()
    for f in sorted(d.glob("*.tmp")):
        head = f.name[:20]
        if head.isdigit() and now_ns - int(head) < min_age_s * 1e9:
            out["kept"] += 1
            continue
        try:
            f.unlink()
        except FileNotFoundError:
            continue
        out["removed"] += 1
    return out
