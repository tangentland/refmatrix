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
    # Synchronous + detached start are mutating → bg pool.
    assert "ingest_gmd" not in CLI_OPS
    assert "ingest_gmd_start" not in CLI_OPS
    # Status is a read → cli pool so polling stays responsive even
    # while bg_pool is saturated.
    assert "ingest_gmd_status" in CLI_OPS
