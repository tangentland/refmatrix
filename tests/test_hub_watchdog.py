"""plan-4 task 4.3 — supervisors never SIGKILL a working daemon.

The corruption of 2026-09-14 was `kickstart -k` (SIGKILL) on a daemon that
was alive and merely reconnecting to an evicted model worker. Liveness is a
heartbeat file the daemon touches from a lock-free thread; a restart is
graceful first, kill only after a grace window."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import hub as hub_mod
from refmatrix import launchctl


def _root():
    base = Path(tempfile.mkdtemp(prefix="rmxw-"))
    root = base / "proj" / ".refmatrix"; root.mkdir(parents=True)
    return root


def test_daemon_heartbeat_thread_touches_file(monkeypatch):
    root = _root()
    monkeypatch.setenv("RMX_HEARTBEAT_S", "0.05")
    d = dm.Daemon(root)
    d._start_heartbeat()
    try:
        time.sleep(0.3)
        hb = dm.heartbeat_path(root)
        assert hb.exists()
        t1 = hb.stat().st_mtime
        time.sleep(0.2)
        assert hb.stat().st_mtime >= t1
        assert dm.heartbeat_age(root) < 1.0
    finally:
        d._stop_heartbeat()


def _wd(monkeypatch, root, *, ping, pid_alive, hb_age, loaded=True):
    wd = hub_mod.Watchdog()
    monkeypatch.setattr(dm, "ping", lambda r, **kw: ping)
    monkeypatch.setattr(dm, "read_pid", lambda r: (4242 if pid_alive else None))
    monkeypatch.setattr(dm, "heartbeat_age", lambda r: hb_age)
    calls = []
    monkeypatch.setattr(launchctl, "is_loaded", lambda r: loaded)
    monkeypatch.setattr(launchctl, "kickstart", lambda r, restart=False: calls.append(("kickstart", restart)) or "label")
    monkeypatch.setattr(dm, "stop_daemon", lambda r, timeout=5.0: calls.append(("stop", timeout)) or True)
    monkeypatch.setattr(dm, "spawn_daemon_subprocess", lambda r, **kw: calls.append(("spawn", None)) or 1)
    monkeypatch.setattr(hub_mod, "RMX_HUB_KILL_GRACE_S", 0.0, raising=False)
    return wd, calls


def test_busy_daemon_with_fresh_heartbeat_is_never_restarted(monkeypatch):
    root = _root()
    wd, calls = _wd(monkeypatch, root, ping=False, pid_alive=True, hb_age=2.0)
    for _ in range(hub_mod.WATCHDOG_GRACE_MISSES + 3):
        wd._check(root)
    assert calls == [], f"busy daemon restarted: {calls}"
    last = wd.health()[str(root.resolve())]["history"][-1]
    assert last["reason"].startswith("busy")


def test_stale_heartbeat_past_grace_restarts_gracefully_first(monkeypatch):
    root = _root()
    wd, calls = _wd(monkeypatch, root, ping=False, pid_alive=True, hb_age=999.0)
    for _ in range(hub_mod.WATCHDOG_GRACE_MISSES):
        wd._check(root)
    assert calls and calls[0][0] == "stop", f"graceful stop must precede any kill: {calls}"
    assert ("kickstart", True) in calls


def test_dead_process_restarts_immediately(monkeypatch):
    root = _root()
    wd, calls = _wd(monkeypatch, root, ping=False, pid_alive=False, hb_age=999.0)
    wd._check(root)
    assert any(c[0] == "kickstart" for c in calls)
