"""bug-053 (ch-bsd #s-2): the in-flight registry lost the op it exists to name.

bug-041 replaced a guess in the shutdown log ("leaked worker likely holds it")
with a registry of running ops — "the evidence". The registry was a dict keyed
by op NAME, so two concurrent calls of the same op shared one entry: the second
arrival overwrote the first's timestamp, and whichever finished first popped the
key while the other was still running. On a daemon with `disp=20`, duplicate
concurrent op names are the normal case (the hub tick's `ping` and
`daemon_status`, the watcher's and the queue's `ingest_path`).

The audit reproduced it on the exact scenario the fix exists for — an
`ingest_path` holding `_store_lock` at shutdown, with a second `ingest_path`
that finished first:

    A still holds _store_lock; registry: {}
    SHUTDOWN LOG: ... in flight: nothing tracked — the holder is not an op,
      check the watcher or a background tick

A guess had been replaced by a confident misdirection. These tests drive the
REAL dispatcher on real pools, because the defect only exists in the hand-off.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from refmatrix import daemon as dm
from refmatrix.store import Store


def _daemon(tmp_path):
    d = dm.Daemon(tmp_path / ".refmatrix")
    d._log = lambda m: d.__dict__.setdefault("_logs", []).append(m)
    return d


def _logs(d):
    return d.__dict__.get("_logs", [])


@pytest.fixture
def pools():
    cli = ThreadPoolExecutor(max_workers=4, thread_name_prefix="t-cli")
    bg = ThreadPoolExecutor(max_workers=4, thread_name_prefix="t-bg")
    yield cli, bg
    cli.shutdown(wait=False)
    bg.shutdown(wait=False)


def _call(d, pools, op, sockets):
    """Drive one request through the real `_handle` on real pools."""
    a, b = socket.socketpair()
    sockets.append((a, b))
    t = threading.Thread(target=d._handle, args=(a, *pools), daemon=True)
    t.start()
    b.sendall(json.dumps({"op": op, "args": {}}).encode() + b"\n")
    return t, b


def _names(d):
    with d._inflight_lock:
        return sorted(op for op, _t0 in d._inflight_ops.values())


# ---- the defect ----------------------------------------------------------

def test_two_concurrent_calls_of_one_op_are_both_tracked(tmp_path, pools):
    """Keyed by name, the second arrival overwrote the first. Both are real."""
    d = _daemon(tmp_path)
    entered = threading.Semaphore(0)
    release = threading.Event()
    socks: list = []

    dm.OPS["__hold__"] = lambda daemon, args: (entered.release(),
                                               release.wait(10), {})[-1]
    try:
        _call(d, pools, "__hold__", socks)
        assert entered.acquire(timeout=5)
        time.sleep(0.05)
        _call(d, pools, "__hold__", socks)
        assert entered.acquire(timeout=5)

        assert _names(d) == ["__hold__", "__hold__"], (
            f"one of the two calls is missing: {d._inflight_ops}")
        with d._inflight_lock:
            starts = sorted(t0 for _op, t0 in d._inflight_ops.values())
        assert starts[0] < starts[1], (
            "both entries carry the same start — the younger call overwrote "
            "the older one's timestamp")
    finally:
        release.set()
        dm.OPS.pop("__hold__", None)
        for a, b in socks:
            b.close()


def test_the_call_that_finishes_first_does_not_clear_the_one_still_running(
        tmp_path, pools):
    """The reproduced scenario: A holds the lock, B finishes, the registry
    goes empty and the shutdown log sends the reader to the watcher."""
    d = _daemon(tmp_path)
    entered = threading.Semaphore(0)
    release_a = threading.Event()
    release_b = threading.Event()
    gates = [release_a, release_b]
    socks: list = []

    def _hold(daemon, args):
        gate = gates.pop(0)
        entered.release()
        gate.wait(10)
        return {}

    dm.OPS["__hold2__"] = _hold
    try:
        _call(d, pools, "__hold2__", socks)
        assert entered.acquire(timeout=5)
        _, b2 = _call(d, pools, "__hold2__", socks)
        assert entered.acquire(timeout=5)

        release_b.set()                       # B finishes first
        b2.settimeout(5.0)
        b2.makefile("rb").readline()          # B's reply landed → B is done
        time.sleep(0.05)

        assert _names(d) == ["__hold2__"], (
            f"B's completion cleared A: {d._inflight_ops}")
    finally:
        release_a.set()
        release_b.set()
        dm.OPS.pop("__hold2__", None)
        for a, b in socks:
            b.close()


def test_an_entry_is_cleared_when_its_own_call_finishes(tmp_path, pools):
    d = _daemon(tmp_path)
    dm.OPS["__quick__"] = lambda daemon, args: {"ok": 1}
    socks: list = []
    try:
        _, b = _call(d, pools, "__quick__", socks)
        b.settimeout(5.0)
        reply = json.loads(b.makefile("rb").readline().decode())
        assert reply["ok"] is True
        time.sleep(0.05)
        assert d._inflight_ops == {}, "the op was never cleared"
    finally:
        dm.OPS.pop("__quick__", None)
        for a, b in socks:
            b.close()


# ---- what the log says ---------------------------------------------------

def test_the_skipped_flush_names_every_holder_with_its_own_age(tmp_path):
    """Two live calls of one op render as two entries, oldest first — the age
    is per call, not per name."""
    d = _daemon(tmp_path)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    d.store = s
    now = time.time()
    with d._inflight_lock:
        d._inflight_ops[1] = ("ingest_path", now - 42.0)
        d._inflight_ops[2] = ("ingest_path", now - 3.0)
    held = threading.Event()
    release = threading.Event()

    def _holder():
        with d._store_lock:
            held.set()
            release.wait(10)

    threading.Thread(target=_holder, daemon=True).start()
    assert held.wait(5)
    try:
        assert d._final_flush(budget_s=0.2) is False
        line = next(m for m in _logs(d) if "final flush skipped" in m)
        assert line.count("ingest_path") == 2, line
        assert "42" in line and "3s" in line, line
        assert line.index("42") < line.index("(3s)"), (
            f"the oldest holder should come first: {line}")
    finally:
        release.set()
        s.close()


def test_the_drain_log_still_lists_the_op_names(tmp_path):
    d = _daemon(tmp_path)
    with d._inflight_lock:
        d._inflight_ops[7] = ("sync_path", time.time())

    # A real pool whose only worker is stuck: `_drain_pool` joins
    # `pool._threads`, so the timeout branch needs a live worker, not a stub.
    stuck = threading.Event()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="t-stuck")
    pool.submit(stuck.wait, 30)
    try:
        d._drain_pool("bg", pool, 0.2)
        line = next((m for m in _logs(d) if "pool drain bg" in m), None)
        assert line is not None, _logs(d)
        assert "sync_path" in line, line
    finally:
        stuck.set()
        pool.shutdown(wait=False)
