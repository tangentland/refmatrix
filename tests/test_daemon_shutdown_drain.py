"""bug-041: a graceful stop that times out on all three pools and skips the
final fragment flush.

Reproduced twice on this project's own store — 2026-09-16 11:32:38 and again on
the 11:51 deploy restart, identically: `pool drain disp: timed out, 20 workers
may outlive shutdown`, then `cli: … 4`, then `bg: … 12`, then `final flush
skipped: _store_lock contended (5s timeout)`, ~29 s to die.

Three defects behind one symptom:

1. The connection handler blocks on a **30 s** socket read while the drain
   budget is **10 s**, so any client connected-but-silent at stop time pins a
   dispatcher thread past the budget by construction. The hub polls every
   daemon on a tick, so this is the normal case, not a rare one.
2. The drain message reports the POOL SIZE as the number of stuck workers
   ("20 workers") when 20 is simply `disp`'s size — a diagnostic that overstates
   the damage and names nothing useful.
3. The final flush gives the lock a flat 5 s and then guesses in the log
   ("leaked worker likely holds it") instead of saying which op does.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

from refmatrix import daemon as dm


def _daemon(tmp_path):
    d = dm.Daemon(tmp_path / ".refmatrix")
    d._log = lambda m: d.__dict__.setdefault("_logs", []).append(m)
    return d


def _logs(d):
    return d.__dict__.get("_logs", [])


# ---- 1. the read that outlived the budget -------------------------------

def test_a_silent_client_does_not_pin_a_dispatcher_past_shutdown(tmp_path):
    """The 30 s read is the whole reason `disp` timed out. A handler must
    notice the shutdown event and let go, not sit on the socket."""
    d = _daemon(tmp_path)
    a, b = socket.socketpair()          # b never sends anything
    done = threading.Event()

    def _run():
        try:
            d._handle(a, None, None)
        finally:
            done.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.2)
    assert not done.is_set(), "the handler should still be waiting for a request"

    t0 = time.monotonic()
    d._shutdown_event.set()
    assert done.wait(5.0), "the handler ignored the shutdown event"
    elapsed = time.monotonic() - t0
    assert elapsed < 3.0, f"took {elapsed:.1f}s to let go of the socket"
    b.close()


def test_a_normal_request_still_works(tmp_path):
    """The bound must not break the ordinary path."""
    import json

    d = _daemon(tmp_path)
    a, b = socket.socketpair()
    seen = {}

    class _Pool:
        def submit(self, fn, *args):
            class _F:
                def result(self_inner, timeout=None):
                    seen["called"] = True
                    return {"pong": True}
            return _F()

    dm.OPS["__probe__"] = lambda daemon, args: {"pong": True}
    try:
        t = threading.Thread(target=d._handle, args=(a, _Pool(), _Pool()),
                             daemon=True)
        t.start()
        b.sendall(json.dumps({"op": "__probe__", "args": {}}).encode() + b"\n")
        b.settimeout(5.0)
        data = b.makefile("rb").readline()
        assert json.loads(data.decode())["ok"] is True
        assert seen.get("called") is True
    finally:
        dm.OPS.pop("__probe__", None)
        b.close()


# ---- 2. the drain says what is actually stuck ---------------------------

def test_the_drain_counts_live_threads_not_the_pool_size(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    d = _daemon(tmp_path)
    hold = threading.Event()
    pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="t")
    # four tasks that finish at once, one that outlives the budget
    for _ in range(4):
        pool.submit(lambda: None)
    pool.submit(lambda: hold.wait(30))
    time.sleep(0.3)

    d._drain_pool("probe", pool, 1.0)
    line = next((m for m in _logs(d) if "pool drain probe" in m), "")
    assert line, _logs(d)
    # The denominator is the threads the pool actually SPAWNED (it spawns
    # lazily, so four instant tasks share one), and the numerator is what is
    # still running. The old message printed the pool's max_workers for both.
    assert "1 of " in line, line
    assert " of 5 " not in line, "max_workers is not a count of stuck threads"
    hold.set()


def test_a_clean_drain_says_nothing(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    d = _daemon(tmp_path)
    pool = ThreadPoolExecutor(max_workers=3)
    pool.submit(lambda: None)
    time.sleep(0.2)
    d._drain_pool("probe", pool, 5.0)
    assert not [m for m in _logs(d) if "timed out" in m], _logs(d)


# ---- 3. the flush names what holds the lock -----------------------------

def test_the_skipped_flush_names_the_op_holding_the_lock(tmp_path):
    d = _daemon(tmp_path)

    class _Store:
        def flush_fragments(self):
            raise AssertionError("must not flush while the lock is held")

    d.store = _Store()
    d._inflight_ops["ingest_path"] = time.time() - 42.0
    held = threading.Event()
    release = threading.Event()

    def _holder():
        with d._store_lock:
            held.set()
            release.wait(10)

    threading.Thread(target=_holder, daemon=True).start()
    assert held.wait(5)
    try:
        ok = d._final_flush(budget_s=0.2)
        assert ok is False
        line = next(m for m in _logs(d) if "final flush skipped" in m)
        assert "ingest_path" in line, line
        assert "42" in line, "say how long it has been running"
    finally:
        release.set()


def test_the_flush_runs_when_the_lock_is_free(tmp_path):
    from refmatrix.store import Store

    d = _daemon(tmp_path)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    d.store = s
    try:
        assert d._final_flush(budget_s=5.0) is True
        assert not [m for m in _logs(d) if "skipped" in m]
    finally:
        s.close()


def test_inflight_ops_are_tracked_and_cleared(tmp_path):
    """The registry is the evidence; if it is not maintained the flush is
    back to guessing."""
    import json

    d = _daemon(tmp_path)
    a, b = socket.socketpair()
    saw = {}

    class _Pool:
        def submit(self, fn, *args):
            class _F:
                def result(self_inner, timeout=None):
                    saw["during"] = dict(d._inflight_ops)
                    return {}
            return _F()

    dm.OPS["__probe2__"] = lambda daemon, args: {}
    try:
        t = threading.Thread(target=d._handle, args=(a, _Pool(), _Pool()),
                             daemon=True)
        t.start()
        b.sendall(json.dumps({"op": "__probe2__", "args": {}}).encode() + b"\n")
        b.makefile("rb").readline()
        t.join(5)
        assert "__probe2__" in saw.get("during", {}), saw
        assert d._inflight_ops == {}, "the op was never cleared"
    finally:
        dm.OPS.pop("__probe2__", None)
        b.close()
