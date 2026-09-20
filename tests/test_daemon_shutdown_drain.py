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
    # {token: (op, started_at)} since bug-053 — one entry per CALL.
    d._inflight_ops[1] = ("ingest_path", time.time() - 42.0)
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


# `test_inflight_ops_are_tracked_and_cleared` lived here. It drove the
# hand-off through a `_Pool` stub that ran the op inline, so it asserted the
# registry against a dispatcher that never used the executor (the ch-bsd #b-5
# MUST GRADUATE row). tests/test_inflight_registry.py replaces it on real
# ThreadPoolExecutors, where bug-053 actually lives.


# ---- 4. the partial read the poll loop used to throw away -----------------
#
# bug-047 (ch-bsd #b-3): splitting the 30 s block into 1 s slices made
# `_recv_line`'s LOCAL accumulator lossy. A request whose bytes did not all
# land inside one slice was destroyed by the `socket.timeout`, and the
# `except ...: req_bytes = b""` swallowed it — the daemon then answered
# `protocol error` for a well-formed request, on the single path EVERY op
# takes, writes included. `daemon.call` does not retry, because
# `{"ok": false}` is valid JSON. Nothing in the suite sent a split request;
# `test_a_normal_request_still_works` above sends one `sendall`, the only
# case that cannot fail.

def test_a_request_split_across_poll_slices_is_not_lost(tmp_path):
    """Send the payload in two pieces with a gap LONGER than a poll slice —
    the shape a sender descheduled mid-`sendall` produces under memory
    pressure (the jetsam incident on this machine)."""
    import json

    d = _daemon(tmp_path)
    a, b = socket.socketpair()
    seen = {}

    class _Pool:
        def submit(self, fn, *args):
            class _F:
                def result(self_inner, timeout=None):
                    return fn(*args)
            return _F()

    dm.OPS["__split__"] = lambda daemon, args: seen.setdefault("args", args) or {"echoed": args}
    try:
        t = threading.Thread(target=d._handle, args=(a, _Pool(), _Pool()),
                             daemon=True)
        t.start()
        payload = json.dumps({"op": "__split__", "args": {"k": "v" * 64}}).encode() + b"\n"
        head, tail = payload[:12], payload[12:]
        b.sendall(head)
        time.sleep(dm._RECV_POLL_S * 1.5)   # straddle at least one slice
        b.sendall(tail)

        b.settimeout(10.0)
        data = b.makefile("rb").readline()
        reply = json.loads(data.decode())
        assert reply["ok"] is True, f"split request was lost: {reply}"
        assert seen.get("args", {}).get("k") == "v" * 64
    finally:
        dm.OPS.pop("__split__", None)
        b.close()


def test_a_request_that_never_completes_is_reported_not_silently_dropped(tmp_path):
    """If the deadline expires with bytes still buffered, the daemon must SAY
    it dropped them. Returning quietly is how the loss stayed invisible."""
    d = _daemon(tmp_path)
    a, b = socket.socketpair()

    class _Pool:
        def submit(self, fn, *args):
            raise AssertionError("no op should run for an incomplete request")

    orig = dm._RECV_POLL_S
    dm._RECV_POLL_S = 0.05
    try:
        t = threading.Thread(target=d._handle, args=(a, _Pool(), _Pool()),
                             daemon=True)
        t.start()
        b.sendall(b'{"op": "__never__"')      # no newline, ever
        time.sleep(0.4)
        d._shutdown_event.set()               # end the wait deterministically
        t.join(5.0)
        assert not t.is_alive()
        assert any("partial" in m.lower() or "incomplete" in m.lower()
                   for m in _logs(d)), (
            f"no log line named the dropped partial request: {_logs(d)}")
    finally:
        dm._RECV_POLL_S = orig
        b.close()
