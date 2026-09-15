"""Hub watchdog liveness grace: a busy-but-alive daemon (GIL/lock held in a
long op) must NOT be SIGKILL-restarted mid-op; only a dead process, or one
wedged past the grace window, is restarted."""
from __future__ import annotations

from pathlib import Path

from refmatrix import hub as hub_mod
from refmatrix.hub import Watchdog, WATCHDOG_GRACE_MISSES


def _wd(monkeypatch, *, up: bool, proc_alive: bool):
    wd = Watchdog()
    restarts = {"n": 0}
    monkeypatch.setattr(hub_mod.daemon_mod, "ping", lambda root, timeout=2.0: up)
    monkeypatch.setattr(
        hub_mod.daemon_mod, "read_pid",
        lambda root: 4242 if proc_alive else None)
    monkeypatch.setattr(wd, "_restart", lambda root, **kw: restarts.__setitem__(
        "n", restarts["n"] + 1) or True)
    return wd, restarts


def test_dead_process_restarts_immediately(tmp_path, monkeypatch):
    wd, restarts = _wd(monkeypatch, up=False, proc_alive=False)
    wd._check(tmp_path)
    assert restarts["n"] == 1


def test_busy_alive_daemon_is_not_restarted_within_grace(tmp_path, monkeypatch):
    wd, restarts = _wd(monkeypatch, up=False, proc_alive=True)
    # Up to (grace - 1) consecutive misses: observed, never restarted.
    for _ in range(WATCHDOG_GRACE_MISSES - 1):
        wd._check(tmp_path)
    assert restarts["n"] == 0


def test_wedged_alive_daemon_restarts_after_grace(tmp_path, monkeypatch):
    wd, restarts = _wd(monkeypatch, up=False, proc_alive=True)
    for _ in range(WATCHDOG_GRACE_MISSES):
        wd._check(tmp_path)
    assert restarts["n"] == 1                       # exactly one, at the threshold


def test_recovery_resets_miss_counter(tmp_path, monkeypatch):
    wd, restarts = _wd(monkeypatch, up=False, proc_alive=True)
    for _ in range(WATCHDOG_GRACE_MISSES - 1):
        wd._check(tmp_path)
    # daemon answers again → counter resets, so a later miss starts fresh
    monkeypatch.setattr(hub_mod.daemon_mod, "ping", lambda root, timeout=2.0: True)
    wd._check(tmp_path)
    assert wd.miss_counts[str(Path(tmp_path).resolve())] == 0
    assert restarts["n"] == 0


def test_manual_policy_never_restarts(tmp_path, monkeypatch):
    wd, restarts = _wd(monkeypatch, up=False, proc_alive=False)
    wd.set_policy(tmp_path, "manual")
    for _ in range(WATCHDOG_GRACE_MISSES + 2):
        wd._check(tmp_path)
    assert restarts["n"] == 0
