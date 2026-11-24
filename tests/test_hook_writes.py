"""task-hook-writes-queue (L212, 2026-11-24): hook writes enqueue and return.

23.1 R11's contract (`task-23.1-queue-and-drain#r11` items 1-7) on an interim spool
(`task-hook-writes-queue#d1`-`#d6`): `src/refmatrix/hook_writes.py` owns `enqueue`,
`read_pending`, `newest_by_ts`, `drain` and the startup `*.tmp` sweep; one file per entry under
`<store root>/hook_writes.spool/`, unreadable entries moved to `bad/`; the daemon drains on its
flush tick and once at boot; `_store_health` reports `hook_writes_pending` / `hook_writes_bad`.

WHY (bug-309, measured 2026-11-24): the Stop hook's turn-end promote waited on the daemon's
single writer and timed out at 8.04 s on 72 of 136 runs, each a hook error in the session. The
write itself was not lost (the dispatcher kept it); the confirmation and the subject filing
were. The hook now enqueues a durable entry and exits 0; the daemon applies it when the writer
frees, newest AUTHORING time winning (`Store.add_memory(updated_at=)`).

What lives here: the module (`newest_by_ts`, the spool write), the drain's ordering and
exactly-once rules on an in-process daemon (AC-3, AC-4), unreadable entries (AC-6), and the
daemon-death case on real daemon processes (AC-2). The Stop-hook entry point is in
`tests/test_plan2_remedy.py` (AC-1, AC-5, AC-6's failing enqueue), save-state in
`tests/test_save_state.py` (AC-8), the replay of the authoring time in
`tests/test_memory_content_log.py` (AC-7).

Interface decisions this file pins where the spec leaves a name open (listed for the lead):
- `hook_writes.enqueue(root, entry) -> Path` (the final spool file);
- `Daemon._drain_hook_writes() -> dict` with `applied` / `superseded` / `bad` counts, the
  tick's and the boot drain's one entry point, the sibling of `_drain_learn_queue()`;
- `superseded` counts ENTRIES: one coalesced away by a newer queued entry, and one whose
  coalesced winner is older than (or as old as) the stored row (AC-3: "counts the two queued
  entries superseded").
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import discovery
from tests.held_writer import (QUIET_ENV, HeldWriterDaemon, facts_events, spool_dir,
                               spool_files)
from tests.task21_1_support import SandboxDaemon, generated_cmd, run_hook, run_rmx
from tests.timing import wait_for, with_budget

_SPOOL_NAME = re.compile(
    r"^\d{20}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json$")


def _hw():
    """Imported per test, so a missing module fails each test, not the collection."""
    from refmatrix import hook_writes
    return hook_writes


def _root() -> Path:
    return Path(os.environ["REFMATRIX_ROOT"])


def _part(root: Path) -> str:
    return discovery.resolve_partition(root, cwd=root.parent)


def _daemon_with_store(root: Path) -> dm.Daemon:
    """An in-process daemon over a real Store (the `tests/test_learn_queue.py` shape): the
    drain and the ops run for real; nothing serves a socket."""
    from refmatrix.store import Store
    d = dm.Daemon(root)
    s = Store(root)
    s.init()
    d.store = s
    d._log = lambda m: d.__dict__.setdefault("_logs", []).append(m)
    return d


def _args(name: str, content: str, ts: float) -> dict:
    """The exact `memory_add` payload both producers build (R11.2, R11.4 item 2: `updated_at`
    is the entry's `ts`, the content's authoring time)."""
    return {"name": name, "content": content, "mtype": "session/digest",
            "tags": ["session:hwq", "summary"], "metadata": {"title": "Session summary hwq"},
            "protected": False, "updated_at": ts}


def _entry(root: Path, name: str, content: str, ts: float, *, subject: "str | None" = None,
           origin: str = "stop-hook") -> dict:
    return {"op": "memory_add", "partition": _part(root), "name": name,
            "args": _args(name, content, ts), "subject": subject, "origin": origin, "ts": ts}


def _memory(d: dm.Daemon, root: Path, name: str) -> "dict | None":
    with d.store.with_partition(_part(root)):
        return d.store.get_memory(name)


def _leaf_names(d: dm.Daemon, root: Path, label: str) -> set:
    with d.store.with_partition(_part(root)):
        return {m["name"] for m in d.store.subject_leaves(label)}


class _CountingLock:
    """Pass-through around the daemon's REAL `_FairLock`, counting acquisitions (D2: ONE
    `_store_lock` acquisition per drain). The lock still excludes; only the count is added."""

    def __init__(self, real):
        self.real, self.n = real, 0

    def acquire(self, *a, **kw):
        self.n += 1
        return self.real.acquire(*a, **kw)

    def release(self):
        return self.real.release()

    def locked(self):
        return self.real.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


# ---- R11.1 `newest_by_ts`: the explicit merge ---------------------------------------------------

def _e(ts: float, content: str, subject=None, subjects=None) -> dict:
    e = {"op": "memory_add", "partition": "p", "name": "focus_summary_x",
         "args": {"name": "focus_summary_x", "content": content, "updated_at": ts},
         "subject": subject, "origin": "stop-hook", "ts": ts}
    if subjects is not None:
        e["subjects"] = subjects
    return e


@pytest.mark.parametrize("acc, ev, kept, subjects", [
    # the newer AUTHORING time wins whichever line came first (round 13, s2)
    (_e(100, "old", "a"), _e(110, "new", "b"), "new", ["a", "b"]),
    (_e(110, "new", "a"), _e(100, "old", "b"), "new", ["a", "b"]),
    # a tie goes to the later line
    (_e(100, "first", "a"), _e(100, "second", "a"), "second", ["a"]),
    # null labels are dropped from the union
    (_e(100, "v1", None), _e(110, "v2", "b"), "v2", ["b"]),
    (_e(100, "v1", None), _e(110, "v2", None), "v2", []),
    # an already-merged accumulator carries `subjects`: ordered, de-duplicated union
    (_e(105, "v2", subjects=["a", "b"]), _e(101, "v1", "a"), "v2", ["a", "b"]),
    (_e(105, "v2", subjects=["a", "b"]), _e(120, "v3", "c"), "v3", ["a", "b", "c"]),
], ids=["ev-newer", "acc-newer", "tie-later-line", "null-dropped", "all-null",
        "merged-dedup", "merged-extend"])
def test_newest_by_ts_keeps_the_newest_authoring_time_and_unions_the_subject_labels(
        acc, ev, kept, subjects):
    """R11.1: `newest_by_ts(acc, ev)` keeps `ev` when `ev["ts"] >= acc["ts"]`, else `acc`, and
    the kept entry carries `subjects`, the ordered de-duplicated union of `acc`'s labels
    (`acc.get("subjects")` or `[acc["subject"]]`) then `ev`'s, `null` dropped. Why: a line's
    position is its APPEND time; the save-state promote can append ~29 s after its `ts`, so a
    position merge applies older content. The union because `link_part_of` only sets bits and
    the synchronous path files a digest under both labels when the subject changed between
    turns. Mutations: a position (last-line) merge fails `acc-newer`; keeping the newer
    entry's label only fails `ev-newer`."""
    out = _hw().newest_by_ts(acc, ev)
    assert out["args"]["content"] == kept, out
    assert out["ts"] == max(acc["ts"], ev["ts"]), out
    assert out["subjects"] == subjects, out


# ---- D1 the spool write ----------------------------------------------------------------------

def test_enqueue_writes_one_durable_spool_file_per_entry(monkeypatch):
    """D1: one file per entry under `<root>/hook_writes.spool/`, named
    `<time_ns:020d>-<uuid4>.json` (oldest first by name), written exactly like
    `gmd_curator.write_spool`: a `.tmp` name, fsync, rename, fsync the directory. A reader never
    sees half an entry, and nothing is held in memory across a crash. The fsync / rename spies
    delegate to the real calls (registered: the filesystem write ordering)."""
    hw = _hw()
    root = _root()
    events: list = []
    real_fsync, real_rename, real_replace = os.fsync, os.rename, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (events.append(("fsync",)), real_fsync(fd))[1])
    monkeypatch.setattr(os, "rename", lambda a, b, *x, **k: (
        events.append(("rename", str(a), str(b))), real_rename(a, b, *x, **k))[1])
    monkeypatch.setattr(os, "replace", lambda a, b, *x, **k: (
        events.append(("rename", str(a), str(b))), real_replace(a, b, *x, **k))[1])

    t0 = time.time_ns()
    e1 = _entry(root, "focus_summary_hwqa", "v1", time.time(), subject="s-x")
    p1 = Path(hw.enqueue(root, e1))
    e2 = _entry(root, "focus_summary_hwqb", "v2", time.time(), origin="save-state")
    p2 = Path(hw.enqueue(root, e2))
    t1 = time.time_ns()

    assert p1.parent.resolve() == p2.parent.resolve() == spool_dir(root).resolve(), (p1, p2)
    assert [p.name for p in spool_files(root)] == [p1.name, p2.name], (
        "one file per entry, names sorting oldest-first", list(spool_dir(root).iterdir()))
    for p, e in ((p1, e1), (p2, e2)):
        assert _SPOOL_NAME.match(p.name), p.name
        assert t0 <= int(p.name[:20]) <= t1, (p.name, t0, t1)
        assert json.loads(p.read_text(encoding="utf-8")) == e
    assert not list(spool_dir(root).glob("*.tmp")), "a .tmp was left behind"
    renames = [ev for ev in events if ev[0] == "rename"]
    assert [Path(b).name for _, a, b in renames] == [p1.name, p2.name], events
    assert all(a.endswith(".tmp") for _, a, _b in renames), events
    for _, a, b in renames:
        i = events.index(("rename", a, b))
        assert ("fsync",) in events[:i], f"no fsync of the entry before its rename: {events}"
        nxt = [ev for ev in events[i + 1:] if ev[0] == "rename"]
        upto = events.index(nxt[0]) if nxt else len(events)
        assert ("fsync",) in events[i + 1:upto], (
            f"no directory fsync after the rename of {b}: {events}")


# ---- AC-3 newest authoring time wins ----------------------------------------------------------

@pytest.mark.parametrize("later_sync_write", [True, False], ids=["with-T3", "without-T3"])
def test_newest_authoring_time_wins_over_line_order_and_over_a_later_sync_write(
        later_sync_write):
    """AC-3. Two queued entries for one name, T1 < T2, appended T2 FIRST then T1 (the
    save-state promote appends up to ~29 s after its `ts`), and a later synchronous write at
    T3 > T2 (turn N+1's dial, after the holder freed and before the tick). One drain: the row
    holds T3's content and the drain counts BOTH queued entries `superseded`; without T3 it holds
    T2's. Both subject labels are filed either way (R11.1 union; a skipped upsert still files,
    R11.3). D2: one `_store_lock` acquisition, the applied files deleted, a snapshot requested
    after the committing drain; an empty spool takes no lock.
    Mutations: merge by line order (T1 wins without T3); drop the `add_memory` guard (T2
    overwrites T3, and a second `memory_content` event follows T3's)."""
    root = _root()
    d = _daemon_with_store(root)
    try:
        name = "focus_summary_hwqac3"
        base = time.time() - 100.0
        t1, t2, t3 = base + 1.0, base + 2.0, base + 3.0
        hw = _hw()
        hw.enqueue(root, _entry(root, name, "v-T2", t2, subject="hwq s-a"))
        hw.enqueue(root, _entry(root, name, "v-T1", t1, subject="hwq s-b", origin="save-state"))
        if later_sync_write:
            dm.OPS["memory_add"](d, {**_args(name, "v-T3", t3), "partition": _part(root)})
        events_before = len(facts_events(root, op="memory_content", name=name))
        d._snapshot_dirty = False
        lock = _CountingLock(d._store_lock)
        d._store_lock = lock

        r = d._drain_hook_writes()

        m = _memory(d, root, name)
        assert m is not None, f"no row for {name}: {r}"
        if later_sync_write:
            assert m["content"] == "v-T3", (m["content"], r)
            assert m["updated_at"] == t3, m
            assert (r["applied"], r["superseded"]) == (0, 2), r
            assert len(facts_events(root, op="memory_content", name=name)) == events_before, (
                "a skipped (superseded) upsert must log no memory_content event")
        else:
            assert m["content"] == "v-T2", (m["content"], r)
            assert m["updated_at"] == t2, m
            assert (r["applied"], r["superseded"]) == (1, 1), r
            evs = facts_events(root, op="memory_content", name=name)
            assert len(evs) == events_before + 1 and evs[-1]["content"] == "v-T2", evs
        for label in ("hwq s-a", "hwq s-b"):
            assert name in _leaf_names(d, root, label), f"not filed under {label!r}"
        assert lock.n == 1, f"D2: one _store_lock acquisition per drain, saw {lock.n}"
        assert not spool_files(root), "the applied entries were not deleted"
        assert d._snapshot_dirty is True, "no snapshot requested after a committing drain"

        lock.n = 0
        r2 = d._drain_hook_writes()
        assert r2["applied"] == 0 and lock.n == 0, (
            f"an empty spool must not take the writer every tick: {r2}, {lock.n} acquisitions")
    finally:
        d.store.close()


# ---- AC-4 one write when both land --------------------------------------------------------------

@pytest.mark.parametrize("order", ["dial-lands-first", "drain-applies-first"])
def test_a_timed_out_dial_that_lands_and_its_queued_entry_write_once(order):
    """AC-4. The dispatcher never drops a write, so a dial that timed out client-side can land
    after the release AND its queued entry be drained. Both carry the same `updated_at` (the
    producer stamps `ts` into the one payload), so whichever applies second is skipped by
    `add_memory`'s guard: ONE row, ONE `memory_content` event, ONE part-of edge, in either
    order. The dial runs through the real `memory_add` op (`_op_memory_add` passes
    `args["updated_at"]`). Mutation: `add_memory` ignoring `updated_at` (two events)."""
    root = _root()
    d = _daemon_with_store(root)
    try:
        name = "focus_summary_hwqac4"
        ts = time.time() - 50.0
        entry = _entry(root, name, "the digest", ts, subject="hwq s-4")
        dial = {**entry["args"], "partition": entry["partition"]}
        hw = _hw()
        if order == "dial-lands-first":
            eid = dm.OPS["memory_add"](d, dial)["id"]
            hw.enqueue(root, entry)
            r = d._drain_hook_writes()
            assert (r["applied"], r["superseded"]) == (0, 1), r
        else:
            hw.enqueue(root, entry)
            r = d._drain_hook_writes()
            assert (r["applied"], r["superseded"]) == (1, 0), r
            eid = dm.OPS["memory_add"](d, dial)["id"]
        m = _memory(d, root, name)
        assert m is not None and m["id"] == eid, (m, eid, "the skipped write returns the row's id")
        assert m["updated_at"] == ts, m
        evs = facts_events(root, op="memory_content", name=name)
        assert len(evs) == 1, f"two writes of one authoring time logged {len(evs)} events: {evs}"
        assert evs[0].get("updated_at") == ts, evs[0]
        with d.store.with_partition(_part(root)):
            con = d.store._connect()
            rows = con.execute(
                "SELECT count(*) FROM entities WHERE kind='memory' AND name=?",
                (name,)).fetchone()[0]
        assert rows == 1, rows
        assert _leaf_names(d, root, "hwq s-4") == {name}
    finally:
        d.store.close()


# ---- AC-6 nothing silent: an unreadable entry -------------------------------------------------

@pytest.mark.parametrize("body", [b"{not json", b'{"op": "memory_add", "ts": 1.0}',
                                  b"\xff\xfe\x00 binary"],
                         ids=["not-json", "missing-keys", "not-utf8"])
def test_an_unreadable_spool_entry_is_counted_logged_and_moved_to_bad(body):
    """AC-6 / D3. A malformed spool file is counted (`bad`), named in `rmxd.log`, MOVED to
    `hook_writes.spool/bad/` byte for byte, never deleted and never silently skipped; it does
    not block the readable entry beside it. `_store_health` reports `hook_writes_pending`
    (files waiting in the spool) before the drain and `hook_writes_bad` after it (D4).
    Decided: an entry missing a required key (`name`, `partition`, `args`) is unreadable too:
    applying it would guess."""
    root = _root()
    d = _daemon_with_store(root)
    try:
        hw = _hw()
        good = "focus_summary_hwqac6"
        hw.enqueue(root, _entry(root, good, "readable", time.time() - 10.0))
        bad_name = f"{time.time_ns():020d}-{uuid.uuid4()}.json"
        (spool_dir(root) / bad_name).write_bytes(body)
        h0 = dm._store_health(d)
        assert (h0.get("hook_writes_pending"), h0.get("hook_writes_bad")) == (2, 0), h0

        r = d._drain_hook_writes()

        assert r["bad"] == 1 and r["applied"] == 1, r
        moved = spool_dir(root) / "bad" / bad_name
        assert moved.exists() and moved.read_bytes() == body, list(spool_dir(root).rglob("*"))
        assert not (spool_dir(root) / bad_name).exists(), "the bad file was left in the spool"
        assert not spool_files(root), spool_files(root)
        logs = d.__dict__.get("_logs", [])
        assert any(bad_name in line for line in logs), f"rmxd.log does not name it: {logs}"
        assert _memory(d, root, good)["content"] == "readable"
        h1 = dm._store_health(d)
        assert (h1.get("hook_writes_pending"), h1.get("hook_writes_bad")) == (0, 1), h1
    finally:
        d.store.close()


def test_daemon_status_and_health_name_a_bad_entry_after_the_boot_drain():
    """AC-6 / D4 through the entry points: a malformed entry present at boot is moved to `bad/`
    by the BOOT drain of a real `rmx daemon start`, the `stats` op's health carries
    `hook_writes_bad: 1`, `rmx daemon status` prints a line for it, and `rmxd.log` names the
    file. Decided wording: the status line contains `hook_writes`, `bad` and the count."""
    root = _root()
    sp = spool_dir(root)
    sp.mkdir()
    bad_name = f"{time.time_ns():020d}-{uuid.uuid4()}.json"
    (sp / bad_name).write_bytes(b"{truncated")
    with SandboxDaemon(root, RMX_DAEMON_FLUSH_S="3600", **QUIET_ENV):
        wait_for(lambda: (sp / "bad" / bad_name).exists(), timeout=30.0,
                 what="the boot drain to move the malformed entry to bad/")
        resp = dm.call(root, "stats", {"include_health": True}, timeout=30.0, retries=0)
        h = (resp.get("result") or {}).get("health") or {}
        assert (h.get("hook_writes_pending"), h.get("hook_writes_bad")) == (0, 1), resp
        st = run_rmx(["daemon", "status"], root=root)
        lines = [ln for ln in st.stdout.splitlines() if "hook_writes" in ln]
        assert any("bad" in ln and re.search(r"\b1\b", ln) for ln in lines), (
            f"`rmx daemon status` does not report the bad entry:\n{st.stdout}\n{st.stderr}")
    log = (root / dm.LOG_NAME).read_text(errors="replace")
    assert bad_name in log, log[-2000:]


# ---- AC-2 survives a daemon death ---------------------------------------------------------------

def test_an_entry_queued_before_a_daemon_death_is_applied_by_the_boot_drain():
    """AC-2 / R11.7. The Stop hook enqueues under a held writer; the daemon is SIGKILLed before
    any tick (its flush interval is 3600 s, and the writer is held); a stale `*.tmp` crash
    leftover sits in the spool. A fresh `rmx daemon start` (flush interval 3600 s again, so only
    the BOOT drain can apply it) applies the entry: `rmx memory get` shows the digest, the
    spool is empty, the `.tmp` is swept (never read as an entry, never moved to `bad/`), and
    facts.log holds ONE `memory_content` event (the timed-out dial died with the daemon).
    Mutation: no boot drain (the entry waits for a tick that, here, never comes)."""
    from refmatrix import stm as stm_mod
    root = _root()
    sess = f"hwq{uuid.uuid4().hex[:6]}"
    name = f"focus_summary_{sess}"
    stm_mod.Stm(root, sess).record("input", "queue the digest, then lose the daemon")
    cmd = with_budget(generated_cmd(root, "Stop", "focus summarize --promote"), 3)
    with HeldWriterDaemon(root, flush_s=3600) as hd:
        hd.hold()
        r = run_hook(cmd, root=root, envelope={"session_id": sess, "hook_event_name": "Stop"},
                     RMX_SESSION=sess)
        assert r.returncode == 0, (
            f"the Stop promote must enqueue and exit 0 on a held writer; rc={r.returncode}\n"
            f"{r.stdout}\n{r.stderr}")
        assert len(spool_files(root)) == 1, list(spool_dir(root).rglob("*"))
        hd.kill()
    stale = spool_dir(root) / f"{1:020d}-{uuid.uuid4()}.json.tmp"
    stale.write_text('{"half": ')
    with SandboxDaemon(root, RMX_DAEMON_FLUSH_S="3600", **QUIET_ENV):
        wait_for(lambda: not spool_files(root), timeout=30.0,
                 what="the boot drain to apply the entry queued before the crash")
        got = wait_for(lambda: (lambda p: p.returncode == 0
                                and f"Session summary — {sess}" in p.stdout and p)(
            run_rmx(["memory", "get", name], root=root)), timeout=30.0,
            what=f"`rmx memory get {name}` to show the digest")
        assert got
    assert not stale.exists(), "the startup sweep left a crash-leftover .tmp"
    bad = spool_dir(root) / "bad"
    assert not (bad.is_dir() and any(bad.iterdir())), list(bad.iterdir())
    assert len(facts_events(root, op="memory_content", name=name)) == 1
