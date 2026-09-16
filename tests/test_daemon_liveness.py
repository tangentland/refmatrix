"""A busy daemon is not a dead one, and the embedder warms before it is asked.

Both defects showed up on the same store within an hour: `rmx daemon status`
reported cliquet as `stale pid 59049 (socket unreachable)` while a direct RPC
ping answered in 0.1s, and every slow UserPromptSubmit hook in cli.log
(5.2s, 5.3s, 6.0s, 8.8s, 21.8s) was the first `memory recall` after a daemon
restart, paying the ~134MB sentence-transformers load on a user prompt.
"""
from __future__ import annotations

import os
import threading
import time

import pytest

from refmatrix import daemon as dm
from refmatrix import discovery


def test_ping_retries_before_declaring_a_daemon_dead(tmp_path, monkeypatch):
    """A single 0.5s probe cannot tell dead from busy. The retry is only paid
    on the path about to call a live daemon dead."""
    calls = {"n": 0}
    monkeypatch.setattr(dm, "socket_path", lambda root: tmp_path / "rmxd.sock")
    (tmp_path / "rmxd.sock").touch()

    import socket as sock_mod

    class Boom:
        def __init__(self, *a, **k): calls["n"] += 1
        def __enter__(self): raise OSError("busy")
        def __exit__(self, *a): return False
        def settimeout(self, t): pass

    monkeypatch.setattr(sock_mod, "socket", Boom)
    assert dm.ping(tmp_path, timeout=0.01, retries=2, retry_backoff=0.001) is False
    assert calls["n"] == 3, "one initial attempt plus two retries"


def test_ping_absent_socket_short_circuits(tmp_path, monkeypatch):
    """No socket = nothing to retry against; must not burn the backoff."""
    monkeypatch.setattr(dm, "socket_path", lambda root: tmp_path / "nope.sock")
    t0 = time.time()
    assert dm.ping(tmp_path, timeout=0.5, retries=2, retry_backoff=0.5) is False
    assert time.time() - t0 < 0.2


def test_daemon_status_reports_busy_for_a_live_unresponsive_process(tmp_path, monkeypatch):
    """The distinction that matters: reporting a live daemon as dead invites a
    kill, and killing mid-startup is how the damage compounds."""
    monkeypatch.setattr(dm, "ping", lambda root, **kw: False)
    monkeypatch.setattr(dm, "socket_path", lambda root: tmp_path / "rmxd.sock")
    (tmp_path / "rmxd.sock").touch()
    monkeypatch.setattr(discovery, "_read_pid", lambda root: os.getpid())
    # A live pid is not enough: `busy` requires the pid to BE an rmx process
    # (`pid_is_rmx`), so a stale pid file whose number a foreign process has
    # reused reads as absent rather than busy (bsd-plan5-r2 #b-1-r2). Under
    # pytest the command line is `python -m pytest`, which correctly does not
    # match — so the fixture, not the code, was wrong, and this test had been
    # red ever since that guard landed (bug-034).
    monkeypatch.setattr(discovery, "pid_is_rmx", lambda pid: True)
    st = discovery.daemon_status(tmp_path)
    assert st["up"] is False and st["busy"] is True


def test_a_foreign_process_reusing_the_pid_number_is_not_busy(tmp_path, monkeypatch):
    """The other half of the same contract, which nothing asserted: a live pid
    that is NOT rmx must read absent, or a reused pid number keeps a dead
    store looking occupied forever."""
    monkeypatch.setattr(dm, "ping", lambda root, **kw: False)
    monkeypatch.setattr(dm, "socket_path", lambda root: tmp_path / "rmxd.sock")
    (tmp_path / "rmxd.sock").touch()
    monkeypatch.setattr(discovery, "_read_pid", lambda root: os.getpid())
    monkeypatch.setattr(discovery, "pid_is_rmx", lambda pid: False)
    st = discovery.daemon_status(tmp_path)
    assert st["up"] is False and st["busy"] is False


def test_daemon_status_reports_dead_when_the_process_is_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "ping", lambda root, **kw: False)
    monkeypatch.setattr(dm, "socket_path", lambda root: tmp_path / "rmxd.sock")
    (tmp_path / "rmxd.sock").touch()
    monkeypatch.setattr(discovery, "_read_pid", lambda root: 2 ** 22)  # no such pid
    st = discovery.daemon_status(tmp_path)
    assert st["up"] is False and st["busy"] is False


def test_embedder_warmup_runs_off_the_critical_path(monkeypatch):
    """Warmup must not block startup and must not be able to kill the daemon."""
    d = object.__new__(dm.Daemon)
    d.log_fh = None
    d._log = lambda msg: None
    done = threading.Event()

    def boom():
        done.set()
        raise RuntimeError("model missing")

    d._embedder = boom
    monkeypatch.delenv("RMX_NO_EMBED_WARMUP", raising=False)
    d._start_embedder_warmup()          # must return immediately
    assert done.wait(5), "warmup thread should have run"


def test_embedder_warmup_can_be_disabled(monkeypatch):
    """A memory-constrained host may prefer to hold the model only on demand."""
    d = object.__new__(dm.Daemon)
    d.log_fh = None
    d._log = lambda msg: None
    called = {"n": 0}
    d._embedder = lambda: called.__setitem__("n", called["n"] + 1)
    monkeypatch.setenv("RMX_NO_EMBED_WARMUP", "1")
    d._start_embedder_warmup()
    time.sleep(0.2)
    assert called["n"] == 0
