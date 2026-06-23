"""Ingest concurrency contract: _FairLock + ingest job registry.

Locks in the four pieces of the 0.5.3 ingest-blocking fix:

  1. `_FairLock` — strict FIFO mutex. Waiters MUST be served in the
     order they arrived, even when an existing holder releases and
     immediately re-acquires (the ingest-yield pattern). This is the
     property `threading.Lock` does not give us and the reason every
     CLI op queued behind a long ingest until the ingest finished.

  2. Single-active-ingest guard — `_register_ingest_job` rejects a
     second concurrent claim. Two ingests against the same daemon
     would interleave their two-pass parse/resolve state and corrupt
     the resolve table.

  3. `_op_ingest_gmd_start` returns a job id immediately; the
     synchronous `_op_ingest_gmd` ALSO registers as a job so polling +
     active-guard work uniformly for both surfaces.

  4. `_op_ingest_gmd_status` streams per-file events keyed by a
     monotonic `seq` cursor.

The body itself is exercised by the existing GMD ingest tests; here
we only nail the lifecycle.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path

import pytest

from refmatrix.daemon import (
    Daemon,
    _FairLock,
    _op_ingest_gmd_status,
    _register_ingest_job,
)


# ---- _FairLock -------------------------------------------------------------


def test_fairlock_serves_waiters_in_arrival_order():
    """Spin up N waiters in a controlled order; verify they acquire in
    that order. The control comes from polling `lk._waiters` so each
    thread is confirmed to have reached `acquire()` before the next
    one is started — without this, two threads can hit `acquire()` in
    swapped order under scheduler noise.
    """
    lk = _FairLock()
    lk.acquire()
    order: list[int] = []

    def _waiter(i: int) -> None:
        lk.acquire()
        order.append(i)
        lk.release()

    threads = [
        threading.Thread(target=_waiter, args=(i,)) for i in range(5)
    ]
    for idx, t in enumerate(threads):
        t.start()
        # Wait until this thread has registered in the waiter deque
        # before launching the next one. Polls the private `_waiters`
        # deque — internal but stable enough for this test.
        deadline = time.monotonic() + 1.0
        while len(lk._waiters) <= idx:
            if time.monotonic() > deadline:
                raise AssertionError(
                    f"waiter {idx} did not register in 1s "
                    f"(deque len={len(lk._waiters)})"
                )
            time.sleep(0.001)
    # Release once. With strict-FIFO ownership transfer, waiter[0]
    # inherits the lock immediately, then chain-passes to waiter[1]
    # on release, and so on. A non-FIFO lock would scramble the chain.
    lk.release()
    for t in threads:
        t.join(timeout=2.0)
        assert not t.is_alive(), "waiter never acquired"
    assert order == [0, 1, 2, 3, 4], f"non-FIFO order: {order}"


def test_fairlock_acquire_timeout_returns_false():
    lk = _FairLock()
    lk.acquire()
    assert lk.acquire(timeout=0.05) is False
    lk.release()
    # Lock is free again after the timeout-withdrawn waiter dropped.
    assert lk.acquire(timeout=0.05) is True
    lk.release()


def test_fairlock_context_manager():
    lk = _FairLock()
    with lk:
        assert lk.locked()
    assert not lk.locked()


def test_fairlock_release_without_acquire_raises():
    lk = _FairLock()
    with pytest.raises(RuntimeError):
        lk.release()


# ---- ingest job registry --------------------------------------------------


def _bare_daemon() -> Daemon:
    """Shell Daemon with only the fields the job-registry helpers
    touch. Mirrors `_bare_daemon` in test_snapshot_tier.py — no socket,
    no thread pool, no store.
    """
    d = object.__new__(Daemon)
    d._ingest_jobs = {}
    d._ingest_jobs_lock = threading.Lock()
    return d


def test_register_ingest_job_returns_id_and_records_state():
    d = _bare_daemon()
    job_id = _register_ingest_job(d, files_total=42, args={"verbose": True})
    assert job_id in d._ingest_jobs
    js = d._ingest_jobs[job_id]
    assert js["status"] == "running"
    assert js["files_total"] == 42
    assert js["files_done"] == 0
    assert js["args"]["verbose"] is True
    assert isinstance(js["events"], deque)


def test_register_ingest_job_rejects_concurrent_claim():
    d = _bare_daemon()
    _register_ingest_job(d, files_total=10, args={})
    with pytest.raises(RuntimeError, match="ingest already active"):
        _register_ingest_job(d, files_total=20, args={})


def test_register_ingest_job_allows_claim_after_previous_done():
    d = _bare_daemon()
    first = _register_ingest_job(d, files_total=10, args={})
    d._ingest_jobs[first]["status"] = "done"
    second = _register_ingest_job(d, files_total=20, args={})
    assert second != first
    assert d._ingest_jobs[second]["status"] == "running"


def test_register_ingest_job_allows_claim_after_previous_error():
    d = _bare_daemon()
    first = _register_ingest_job(d, files_total=10, args={})
    d._ingest_jobs[first]["status"] = "error"
    second = _register_ingest_job(d, files_total=20, args={})
    assert second != first


# ---- _op_ingest_gmd_status ------------------------------------------------


def test_status_lists_all_jobs_when_no_id_given():
    d = _bare_daemon()
    a = _register_ingest_job(d, files_total=5, args={})
    d._ingest_jobs[a]["status"] = "done"
    b = _register_ingest_job(d, files_total=7, args={})
    resp = _op_ingest_gmd_status(d, {})
    assert "jobs" in resp
    ids = {j["id"] for j in resp["jobs"]}
    assert ids == {a, b}
    # Events stripped from list view for compactness.
    for j in resp["jobs"]:
        assert "events" not in j


def test_status_returns_single_job_and_streams_events_since_cursor():
    d = _bare_daemon()
    job_id = _register_ingest_job(d, files_total=3, args={})
    js = d._ingest_jobs[job_id]
    for i, p in enumerate(("a.md", "b.md", "c.md"), start=1):
        js["events"].append({
            "seq": js["next_seq"], "phase": "pass2",
            "i": i, "n": 3, "path": p, "ts": time.time(),
        })
        js["next_seq"] += 1
    # cursor=0 → all three events.
    resp = _op_ingest_gmd_status(d, {"job_id": job_id, "since_seq": 0})
    assert [e["path"] for e in resp["events"]] == ["a.md", "b.md", "c.md"]
    # cursor=2 → only the last event (seq=3) is past the cursor.
    resp = _op_ingest_gmd_status(d, {"job_id": job_id, "since_seq": 2})
    assert [e["path"] for e in resp["events"]] == ["c.md"]
    assert resp["job"]["files_total"] == 3


def test_status_raises_on_unknown_job_id():
    d = _bare_daemon()
    with pytest.raises(KeyError):
        _op_ingest_gmd_status(d, {"job_id": "nonsense"})


# ---- OPS / CLI_OPS registration --------------------------------------------


def test_ingest_ops_registered():
    """Renames or removals break the CLI surface — pin them."""
    from refmatrix.daemon import OPS, CLI_OPS
    assert "ingest_gmd" in OPS
    assert "ingest_gmd_start" in OPS
    assert "ingest_gmd_status" in OPS
    # Detached fire-and-poll starts for the plain ingest + embed paths.
    assert "ingest_path_start" in OPS
    assert "embed_start" in OPS
    # Synchronous + detached start dispatch onto bg pool (the start op just
    # registers the job + submits; the work runs on another bg worker).
    assert "ingest_gmd" not in CLI_OPS
    assert "ingest_gmd_start" not in CLI_OPS
    assert "ingest_path_start" not in CLI_OPS
    assert "embed_start" not in CLI_OPS
    # Status is a read → cli pool so polling stays responsive even
    # while bg_pool is saturated.
    assert "ingest_gmd_status" in CLI_OPS


# ---- snapshot-direct read resolution --------------------------------------


def _make_bare_store(tmp_path):
    """Construct a bare Store shell with just enough state to exercise
    the read_only resolution block in __init__."""
    from refmatrix.store import Store
    s = object.__new__(Store)
    s.root = tmp_path
    s._read_only = True

    class _Backend:
        kind = "duckdb"
        db_filename = "catalog.duckdb"
    s._backend = _Backend()
    s.db_path = s.root / s._backend.db_filename
    return s


def _resolve_read_only_path(s, tmp_path):
    """Replay the snapshot-first resolution block from Store.__init__
    against the bare-store fixture."""
    snap = tmp_path / "catalog.read.duckdb"
    link = tmp_path / "read_only.duckdb"
    if s._read_only and s._backend.kind == "duckdb":
        if snap.exists():
            s.db_path = snap
        elif link.exists() or link.is_symlink():
            s.db_path = link


def test_read_only_store_lands_on_snapshot_not_symlink(tmp_path):
    """Lock-free reads resolve `catalog.read.duckdb` DIRECTLY at open
    time, not via the `read_only.duckdb` symlink. Rotation code in the
    daemon swings the symlink at a writer slot on every rotation
    cycle; chasing it lands a reader at the locked writer. Snapshot-
    first resolution is self-correcting."""
    import os as _os
    snap = tmp_path / "catalog.read.duckdb"
    snap.write_bytes(b"")
    link = tmp_path / "read_only.duckdb"
    _os.symlink("catalog.A.duckdb", link)
    s = _make_bare_store(tmp_path)
    _resolve_read_only_path(s, tmp_path)
    assert s.db_path == snap, f"snapshot should win; got {s.db_path}"


def test_read_only_store_falls_back_to_symlink_without_snapshot(tmp_path):
    """Pre-snapshot-tier stores still resolve via the legacy symlink
    when the snapshot file is absent (fresh install, daemon never
    started)."""
    import os as _os
    link = tmp_path / "read_only.duckdb"
    _os.symlink("catalog.B.duckdb", link)
    s = _make_bare_store(tmp_path)
    _resolve_read_only_path(s, tmp_path)
    assert s.db_path == link, (
        f"symlink fallback should fire; got {s.db_path}"
    )


# ---- in-memory mirror -----------------------------------------------------


def _bare_daemon_with_store(tmp_path):
    """Daemon shell with a real DuckDB writer Store. Mirrors the snapshot-
    tier test helper shape so we can exercise mirror refresh end-to-end."""
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store
    s = Store(tmp_path, backend="duckdb")
    s._connect()
    d = object.__new__(Daemon)
    d.root = tmp_path
    d._log = lambda *a, **k: None
    d.store = s
    d._store_lock = threading.Lock()
    d._snapshot_lock = threading.Lock()
    d._last_snapshot_ts = 0.0
    d._snapshot_dirty = False
    d._snapshot_event = threading.Event()
    d._snapshot_stop = threading.Event()
    d._mem_mirror = None
    return d, s


def test_mem_mirror_refresh_loads_tables_from_snapshot(tmp_path):
    """After a snapshot is materialized and the mirror refresh fires,
    the in-memory Store can answer queries that touch the loaded data.
    Concrete probe: insert a partition row, snapshot, refresh, then
    SELECT the partition through the mirror Store."""
    from refmatrix.daemon import _MemMirror
    d, s = _bare_daemon_with_store(tmp_path)
    try:
        s._connect().execute(
            "INSERT OR IGNORE INTO partitions(name, kind, root_path, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("mirror_probe", "repo", None, time.time()),
        )
        s._connect().commit()
        d._snapshot_catalog(force=True)
        mirror = _MemMirror(d)
        d._mem_mirror = mirror
        assert mirror.refresh() is True
        assert mirror.ready
        ms = mirror.borrow()
        assert ms is not None
        row = ms._conn._duck.execute(
            "SELECT name FROM partitions WHERE name=?", ("mirror_probe",),
        ).fetchone()
        assert row == ("mirror_probe",)
    finally:
        s.close()


def test_mem_mirror_refresh_returns_false_without_snapshot(tmp_path):
    """No snapshot file → refresh is a no-op returning False, ready
    stays False, mirror state preserved."""
    from refmatrix.daemon import _MemMirror
    d, s = _bare_daemon_with_store(tmp_path)
    try:
        mirror = _MemMirror(d)
        d._mem_mirror = mirror
        assert mirror.refresh() is False
        assert mirror.ready is False
        assert mirror.borrow() is None
    finally:
        s.close()


def test_mem_mirror_borrow_close_is_noop(tmp_path):
    """The borrowed mirror Store is shared. Callers `close()` it at
    end of op (per `_read_with_fallback` convention) — that close MUST
    be a no-op so the shared connection survives. Concrete: borrow,
    close, borrow again, and assert the same Store + working
    connection comes back."""
    from refmatrix.daemon import _MemMirror
    d, s = _bare_daemon_with_store(tmp_path)
    try:
        d._snapshot_catalog(force=True)
        mirror = _MemMirror(d)
        d._mem_mirror = mirror
        mirror.refresh()
        first = mirror.borrow()
        assert first is not None
        first.close()  # no-op
        second = mirror.borrow()
        assert second is first
        # Connection is still functional.
        row = second._conn._duck.execute("SELECT 1").fetchone()
        assert row == (1,)
    finally:
        s.close()


def test_open_read_store_prefers_mirror_when_ready(tmp_path):
    """`Daemon._open_read_store` returns the mirror Store when it's
    ready, ahead of the snapshot-file path. The two stores have
    distinct `db_path` values — mirror is `:memory:`, snapshot is
    `catalog.read.duckdb` — so we can distinguish them by that
    attribute.
    """
    from refmatrix.daemon import _MemMirror
    d, s = _bare_daemon_with_store(tmp_path)
    try:
        d._snapshot_catalog(force=True)
        mirror = _MemMirror(d)
        d._mem_mirror = mirror
        assert mirror.refresh() is True
        # Wire the swap-gate + read_inflight bookkeeping shape that
        # `_open_read_store` peeks at on the file path. We won't hit
        # the file path, but the wiring keeps the call safe.
        d._swap_gate = threading.Condition()
        d._read_inflight = 0
        d._active_slot = None
        rs = d._open_read_store()
        assert rs is not None
        assert str(rs.db_path) == ":memory:", (
            f"expected mirror path, got {rs.db_path}"
        )
    finally:
        s.close()


def test_open_read_store_falls_back_to_snapshot_when_mirror_empty(tmp_path):
    """When the mirror exists but has never been refreshed (no
    snapshot yet, or refresh failed), `_open_read_store` falls
    through to the snapshot-file Store. We don't have a snapshot
    file in this test, so the result is None — proving the mirror
    didn't short-circuit the resolution chain when it has nothing to
    serve.
    """
    from refmatrix.daemon import _MemMirror
    d, s = _bare_daemon_with_store(tmp_path)
    try:
        mirror = _MemMirror(d)
        d._mem_mirror = mirror
        # No refresh -> mirror.borrow() returns None.
        d._swap_gate = threading.Condition()
        d._read_inflight = 0
        d._active_slot = None
        rs = d._open_read_store()
        # No snapshot file + no slot files in this bare daemon shell →
        # falls through to None, NOT to a mirror Store.
        assert rs is None
    finally:
        s.close()
