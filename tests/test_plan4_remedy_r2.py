"""bsd-plan4-r2 remedy (round 3 of plan 4).

#b-1  the adoption gate rode a plist env var no deploy step re-rendered:
      `serve_foreground` now also recognises launchd's own XPC_SERVICE_NAME;
      `launchctl.check` compares the installed plist with its render (the
      hooks shape) and `relaunch-fleet` re-installs a drifted one first.
#b-2  the serving-derived heartbeat ticked only when the cli pool answered
      within the interval — a saturated (busy) pool read as a wedge after
      60 s. The tick lands on COMPLETION, however late.
#b-3  `stop_daemon` spent its grace before the first signal; the sibling of
      the hub fix. `daemon.graceful_stop` signals first; `stop_daemon` uses
      it and keeps only the heartbeat-gated SIGKILL; `hub.graceful_stop`
      delegates.
#b-4  the unsupervised foreground gate was a bare `ping`: a busy daemon was
      reaped. Typed classifier: up → refuse, busy → refuse, absent → serve.
#s-5  the watchdog's kickstart -k after the grace waits one more grace while
      the pid is alive with a fresh heartbeat (it is shutting down); the
      default grace covers three pool drains plus the store close.
#m-6  `repair_entities` driven through the real dispatcher in-process.
"""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import Future
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import hub as hub_mod
from refmatrix import launchctl
from refmatrix.store import RepairAbort, Store
from tests.test_plan2_remedy import _SilentDaemon


# ---- #b-1 supervised gate + plist drift ----------------------------------------

def test_supervised_gate_recognises_launchd_without_the_plist_variable(monkeypatch):
    monkeypatch.delenv("RMX_SUPERVISED", raising=False)
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)
    assert dm.is_supervised_start() is False
    monkeypatch.setenv("XPC_SERVICE_NAME", "com.refmatrix.daemon.proj-0123abcd")
    assert dm.is_supervised_start() is True
    monkeypatch.setenv("XPC_SERVICE_NAME", "com.apple.something")
    assert dm.is_supervised_start() is False
    monkeypatch.setenv("RMX_SUPERVISED", "1")
    assert dm.is_supervised_start() is True


def test_supervised_start_under_xpc_service_name_adopts_instead_of_exiting_1(monkeypatch):
    """The incident shape: an unsupervised daemon holds the root; launchd
    starts the supervised one with the OLD plist (no RMX_SUPERVISED)."""
    base = Path(tempfile.mkdtemp(prefix="rmxx-", dir="/tmp"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    monkeypatch.delenv("RMX_SUPERVISED", raising=False)
    monkeypatch.setenv("XPC_SERVICE_NAME", launchctl.label_for_root(root))
    try:
        d = dm.Daemon(root)
        logs = []
        d._log = lambda m: logs.append(m)
        # the gate serve_foreground applies, on the daemon it built
        assert dm.is_supervised_start() is True
        assert d._adopt_unsupervised(dm.socket_path(root)) is True
        assert any("adopted unsupervised daemon" in m for m in logs)
    finally:
        dm.stop_daemon(root)
        shutil.rmtree(base, ignore_errors=True)


def _installed_plist(tmp_path, monkeypatch, root, **flags) -> Path:
    """A plist on disk + a launchd that reports it loaded with exactly the
    rendered env (tests override `is_loaded` / `loaded_env` for drift)."""
    agents = tmp_path / "LaunchAgents"; agents.mkdir(exist_ok=True)
    monkeypatch.setattr(launchctl, "LAUNCH_AGENTS_DIR", agents)
    p = launchctl.plist_path(root)
    p.write_bytes(launchctl.render_plist(root, **flags))
    monkeypatch.setattr(launchctl, "is_loaded", lambda r: True)
    monkeypatch.setattr(launchctl, "loaded_env",
                        lambda r: dict(plistlib.loads(p.read_bytes())["EnvironmentVariables"]))
    return p


def test_plist_check_sees_a_missing_supervised_variable(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    p = _installed_plist(tmp_path, monkeypatch, root)
    ok, why = launchctl.check(root)
    assert ok is True and why == "", why
    data = plistlib.loads(p.read_bytes())
    del data["EnvironmentVariables"]["RMX_SUPERVISED"]
    p.write_bytes(plistlib.dumps(data))
    ok, why = launchctl.check(root)
    assert ok is False and "RMX_SUPERVISED" in why, why


def test_plist_check_keeps_the_installed_flags(tmp_path, monkeypatch):
    """The render depends on install-time flags; the check re-renders from
    the installed ProgramArguments, so a `--no-watch --semantic --watch-root`
    install is not reported as drift."""
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    extra = tmp_path / "extra"; extra.mkdir()
    _installed_plist(tmp_path, monkeypatch, root, watch=False, semantic=True,
                     debounce_ms=900, watch_roots=[extra])
    ok, why = launchctl.check(root)
    assert ok is True, why


def test_plist_check_reports_a_missing_plist(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    monkeypatch.setattr(launchctl, "LAUNCH_AGENTS_DIR", tmp_path / "LaunchAgents")
    ok, why = launchctl.check(root)
    assert ok is False and "not installed" in why


def test_launchctl_install_check_cli_exits_1_on_drift(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    p = _installed_plist(tmp_path, monkeypatch, root)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "launchctl", "install", "--check"])
    assert r.exit_code == 0 and "in sync" in r.output, r.output
    data = plistlib.loads(p.read_bytes())
    data["EnvironmentVariables"].pop("RMX_SUPERVISED")
    p.write_bytes(plistlib.dumps(data))
    r = CliRunner().invoke(cli_mod.main, ["daemon", "launchctl", "install", "--check"])
    assert r.exit_code == 1 and "RMX_SUPERVISED" in r.output, r.output


def test_relaunch_fleet_reinstalls_a_drifted_plist_before_restarting(monkeypatch, tmp_path):
    from refmatrix import discovery
    from refmatrix import launchctl as lc
    a = tmp_path / "a" / ".refmatrix"; b = tmp_path / "b" / ".refmatrix"
    for r in (a, b):
        r.mkdir(parents=True)
    monkeypatch.setattr(discovery, "discover_roots", lambda: [a, b])
    monkeypatch.setattr(lc, "is_loaded", lambda r: True)
    monkeypatch.setattr(lc, "check", lambda r: (False, "RMX_SUPERVISED missing") if r == a else (True, ""))
    calls = []
    monkeypatch.setattr(lc, "reinstall", lambda r: calls.append(("reinstall", r)) or lc.plist_path(r))
    monkeypatch.setattr(cli_mod.subprocess if hasattr(cli_mod, "subprocess") else subprocess, "run",
                        lambda argv, **kw: calls.append(("restart", Path(kw["env"]["REFMATRIX_ROOT"])))
                        or subprocess.CompletedProcess(argv, 0, "ok pid=1 v", ""))
    r = CliRunner().invoke(cli_mod.main, ["hub", "relaunch-fleet"])
    assert r.exit_code == 0, r.output
    assert calls == [("reinstall", a), ("restart", a), ("restart", b)], calls
    assert "reinstalled" in r.output and "RMX_SUPERVISED" in r.output


def test_reinstall_verifies_the_label_is_loaded_afterwards(tmp_path, monkeypatch):
    """`install --force` has left a label unloaded (thiquet, 2026-09-14);
    `reinstall` re-runs a plain install when the forced one did not load."""
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    _installed_plist(tmp_path, monkeypatch, root)
    calls = []
    loaded = {"n": 0}

    def fake_install(r, *, force=False, **kw):
        calls.append(("install", force)); return launchctl.plist_path(r)

    def fake_is_loaded(r):
        loaded["n"] += 1
        return loaded["n"] > 1        # unloaded right after the forced install, loaded after the plain one
    monkeypatch.setattr(launchctl, "install", fake_install)
    monkeypatch.setattr(launchctl, "is_loaded", fake_is_loaded)
    monkeypatch.setattr(launchctl, "check", lambda r: (True, ""))
    launchctl.reinstall(root)
    assert calls == [("install", True), ("install", False)], calls


# ---- #b-2 heartbeat ticks on completion ---------------------------------------------

class _SlowPool:
    """Every no-op completes, but only after `delay` seconds: a saturated
    pool that is making progress."""
    def __init__(self, delay):
        self.delay = delay
    def submit(self, fn, *a, **kw):
        f = Future()
        threading.Timer(self.delay, lambda: f.set_result(fn(*a, **kw))).start()
        return f


class _DeadPool:
    def submit(self, fn, *a, **kw):
        return Future()


def test_heartbeat_advances_when_the_pool_completes_late(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setenv("RMX_HEARTBEAT_S", "0.1")
    d = dm.Daemon(root); d._log = lambda m: None
    d._cli_pool = _SlowPool(0.3)          # 3x the interval
    d._start_heartbeat()
    try:
        hb = dm.heartbeat_path(root)
        t0 = hb.stat().st_mtime
        time.sleep(0.9)
        assert hb.stat().st_mtime > t0, "a progressing pool must tick, however late"
    finally:
        d._stop_heartbeat()
    d._cli_pool = _DeadPool()
    d._start_heartbeat()
    try:
        time.sleep(0.3)
        t1 = dm.heartbeat_path(root).stat().st_mtime
        time.sleep(0.4)
        assert dm.heartbeat_path(root).stat().st_mtime == t1, "a deadlocked pool must not tick"
    finally:
        d._stop_heartbeat()


# ---- #b-3 stop_daemon signals first --------------------------------------------------

def test_stop_daemon_signals_first_when_ping_fails():
    d = _SilentDaemon()
    try:
        report: dict = {}
        t0 = time.monotonic()
        ok = dm.stop_daemon(d.root, timeout=5.0, report=report)
        elapsed = time.monotonic() - t0
        assert ok is True and elapsed < 1.5, (elapsed, report)
        assert d.proc.poll() is not None, "SIGTERM was not delivered at t=0"
        assert report.get("signal") == "SIGTERM" and "not answering" in report.get("stop_op", ""), report
    finally:
        d.close()


def test_daemon_graceful_stop_exists_and_the_hub_delegates(monkeypatch):
    seen = []
    monkeypatch.setattr(dm, "graceful_stop", lambda root, *, grace, report=None: seen.append(grace) or True)
    assert hub_mod.graceful_stop(Path("/nowhere/.refmatrix"), grace=3.5) is True
    assert seen == [3.5]


# ---- #b-4 foreground gate is typed -----------------------------------------------------

def test_foreground_start_refuses_a_busy_daemon_without_reaping_it(monkeypatch):
    """The gate is a helper so this test never reaches `serve_forever` (a
    RED run that did took the pytest process over — bug-009 shape)."""
    import inspect
    d = _SilentDaemon(seeded=True)
    try:
        t0 = time.monotonic()
        with pytest.raises(RuntimeError, match="busy"):
            dm.refuse_unsupervised_start(d.root)
        assert time.monotonic() - t0 < 4.0
        assert d.proc.poll() is None, "the busy predecessor was reaped"
        assert dm.socket_path(d.root).exists()
    finally:
        d.close()
    src = inspect.getsource(dm.serve_foreground)
    assert "refuse_unsupervised_start(root)" in src and "elif ping(root)" not in src


def test_unsupervised_gate_lets_an_absent_root_serve_and_refuses_a_live_one(tmp_path):
    root = tmp_path / ".refmatrix"; root.mkdir()
    dm.refuse_unsupervised_start(root)          # absent: no raise
    base = Path(tempfile.mkdtemp(prefix="rmxg-", dir="/tmp"))
    live = base / "proj" / ".refmatrix"; live.parent.mkdir()
    Store(live).init()
    pid = dm.spawn_daemon_subprocess(live, watch_root=[])
    try:
        assert pid and dm.ping(live)
        with pytest.raises(RuntimeError, match="already running"):
            dm.refuse_unsupervised_start(live)
    finally:
        dm.stop_daemon(live); shutil.rmtree(base, ignore_errors=True)


# ---- #s-5 watchdog waits while the heartbeat is fresh after the signal ------------

def test_watchdog_waits_one_more_grace_while_the_pid_is_alive_and_ticking(monkeypatch, tmp_path):
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    calls = []
    ages = iter([0.0] * 1000)        # fresh throughout: the full extra grace elapses
    monkeypatch.setattr(hub_mod, "graceful_stop", lambda r, grace: calls.append(("graceful_stop", grace)) or False)
    monkeypatch.setattr(dm, "read_pid", lambda r: 4242)
    monkeypatch.setattr(dm, "is_alive", lambda pid: True)
    monkeypatch.setattr(dm, "heartbeat_age", lambda r: next(ages))
    monkeypatch.setattr(launchctl, "is_loaded", lambda r: True)
    monkeypatch.setattr(launchctl, "kickstart", lambda r, restart=False: calls.append(("kickstart", restart)) or "l")
    monkeypatch.setattr(hub_mod, "RMX_HUB_KILL_GRACE_S", 0.2)
    t0 = time.monotonic()
    hub_mod.Watchdog()._restart(root, alive=True)
    assert calls == [("graceful_stop", 0.2), ("kickstart", True)]
    assert time.monotonic() - t0 >= 0.2, "must wait another grace while the heartbeat is fresh"


def test_kill_grace_default_covers_the_drain_budget():
    assert hub_mod.DEFAULT_KILL_GRACE_S >= 3 * 10 + 10


# ---- #m-6 repair_entities through the dispatcher -----------------------------------------

class _NowPool:
    def submit(self, fn, *a, **kw):
        f = Future()
        try:
            f.set_result(fn(*a, **kw))
        except BaseException as e:  # noqa: BLE001 — the dispatcher reads it back
            f.set_exception(e)
        return f


def _dispatch(d, req: dict) -> dict:
    a, b = socket.socketpair()
    a.sendall((json.dumps(req) + "\n").encode())
    d._handle(b, _NowPool(), _NowPool())
    b.close()
    out = a.recv(65536).decode().strip()
    a.close()
    return json.loads(out)


def test_repair_entities_abort_reaches_the_wire_and_the_daemon_keeps_serving(monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="rmxd-", dir="/tmp"))
    root = base / ".refmatrix"
    s = Store(root); s.init(); s.close()
    d = dm.Daemon(root)
    d.store = Store(root); d.store.init()
    d._log = lambda m: None
    exits = []
    monkeypatch.setattr(dm.os, "_exit", lambda code: exits.append(code))
    monkeypatch.setattr(d.store, "rebuild_entities_indexes",
                        lambda: (_ for _ in ()).throw(RepairAbort("repair aborted: 2 real duplicate group(s)")))
    try:
        resp = _dispatch(d, {"op": "repair_entities", "args": {}})
        assert resp["ok"] is False and "repair aborted" in resp["error"], resp
        assert exits == [], "an abort must not fast-exit the daemon"
        ping = _dispatch(d, {"op": "ping", "args": {}})
        assert ping["ok"] is True
    finally:
        d.store.close()
        shutil.rmtree(base, ignore_errors=True)


# ---- #b-1 (live follow-up, bug-013): a forced reinstall must actually reload -----

_PRINT = """\
gui/501/com.refmatrix.daemon.x = {
\tactive count = 1
\tpath = /Users/x/Library/LaunchAgents/com.refmatrix.daemon.x.plist
\tstate = running
\tenvironment = {
\t\tOBJC_DISABLE_INITIALIZE_FORK_SAFETY => YES
\t\tREFMATRIX_ROOT => /proj/.refmatrix
\t\tRMX_SUPERVISED => 1
\t}
\tdefault environment = {
\t\tPATH => /usr/bin:/bin
\t}
}
"""


def test_loaded_env_parses_launchctl_print(monkeypatch):
    monkeypatch.setattr(launchctl.subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, _PRINT, ""))
    env = launchctl.loaded_env(Path("/proj/.refmatrix"))
    assert env == {"OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
                   "REFMATRIX_ROOT": "/proj/.refmatrix", "RMX_SUPERVISED": "1"}
    monkeypatch.setattr(launchctl.subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 113, "", "Could not find service"))
    assert launchctl.loaded_env(Path("/proj/.refmatrix")) is None


def _fake_launchctl(monkeypatch, tmp_path, root, *, loaded_seq, env_after=None):
    """launchd stand-in: `is_loaded` answers from `loaded_seq` (last value
    repeats), `loaded_env` from `env_after` (None = the rendered env), and
    every launchctl subprocess succeeds."""
    calls: list = []
    seq = list(loaded_seq)
    monkeypatch.setattr(launchctl, "_require_darwin", lambda: None)
    monkeypatch.setattr(launchctl, "LAUNCH_AGENTS_DIR", tmp_path / "LaunchAgents")
    monkeypatch.setattr(launchctl, "BOOTOUT_WAIT_S", 0.3)
    monkeypatch.setattr(launchctl, "is_loaded",
                        lambda r: seq.pop(0) if len(seq) > 1 else seq[0])

    def fake_run(argv, **kw):
        verb = argv[1] if argv and argv[0] == "launchctl" else argv[0]
        if verb != "print":                 # `_migrate_legacy` / `is_loaded` probes
            calls.append(verb)
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(launchctl.subprocess, "run", fake_run)

    def fake_env(r):
        if env_after is not None:
            return env_after
        want = plistlib.loads(launchctl.render_plist(r))["EnvironmentVariables"]
        return dict(want)
    monkeypatch.setattr(launchctl, "loaded_env", fake_env)
    return calls


def test_install_force_raises_when_the_bootout_does_not_complete(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    (tmp_path / "LaunchAgents").mkdir()
    calls = _fake_launchctl(monkeypatch, tmp_path, root, loaded_seq=[True])   # never unloads
    launchctl.plist_path(root).write_bytes(launchctl.render_plist(root))
    with pytest.raises(RuntimeError, match="still loaded"):
        launchctl.install(root, force=True)
    assert "bootout" in calls and "bootstrap" not in calls, calls   # never bootstrap against a loaded label


def test_install_force_reloads_and_verifies_the_loaded_env(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    (tmp_path / "LaunchAgents").mkdir()
    calls = _fake_launchctl(monkeypatch, tmp_path, root, loaded_seq=[True, False, True])
    launchctl.plist_path(root).write_bytes(b"old")
    p = launchctl.install(root, force=True)
    assert calls == ["bootout", "bootstrap"], calls
    assert p.read_bytes() == launchctl.render_plist(root)


def test_install_raises_when_the_loaded_job_lacks_the_rendered_env(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    (tmp_path / "LaunchAgents").mkdir()
    _fake_launchctl(monkeypatch, tmp_path, root, loaded_seq=[False, True],
                    env_after={"REFMATRIX_ROOT": str(root.resolve())})
    with pytest.raises(RuntimeError, match="RMX_SUPERVISED"):
        launchctl.install(root)


def test_check_reports_a_loaded_job_that_lacks_the_rendered_env(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    _installed_plist(tmp_path, monkeypatch, root)
    monkeypatch.setattr(launchctl, "is_loaded", lambda r: True)
    monkeypatch.setattr(launchctl, "loaded_env", lambda r: {"REFMATRIX_ROOT": str(root.resolve())})
    ok, why = launchctl.check(root)
    assert ok is False and "loaded job" in why and "RMX_SUPERVISED" in why, why


def test_check_reports_an_installed_but_unloaded_label(tmp_path, monkeypatch):
    """The bug-013 state: plist current on disk, nothing loaded, a standalone
    daemon on the root."""
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    _installed_plist(tmp_path, monkeypatch, root)
    monkeypatch.setattr(launchctl, "is_loaded", lambda r: False)
    ok, why = launchctl.check(root)
    assert ok is False and "not loaded" in why, why


def test_relaunch_bootstraps_an_installed_but_unloaded_plist_instead_of_spawning(tmp_path, monkeypatch):
    from refmatrix import __version__
    from refmatrix import upgrade as up
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(sys, "platform", "darwin")
    calls = []
    monkeypatch.setattr(launchctl, "is_installed", lambda r: True)
    monkeypatch.setattr(launchctl, "is_loaded", lambda r: False)
    monkeypatch.setattr(launchctl, "install", lambda r, **kw: calls.append("install") or launchctl.plist_path(r))
    monkeypatch.setattr(launchctl, "kickstart", lambda r, restart=False: calls.append("kickstart") or "l")
    monkeypatch.setattr(dm, "spawn_daemon", lambda r, **kw: calls.append("spawn") or 1)
    monkeypatch.setattr(dm, "stop_daemon", lambda r, **kw: calls.append("stop") or True)
    ident = up.runtime_identity()
    seen = {"n": 0}

    def served(r, timeout=1.0):
        seen["n"] += 1
        return None if seen["n"] == 1 else (7, __version__)   # nothing before, the new daemon after
    monkeypatch.setattr(dm, "served_identity", served)
    monkeypatch.setattr(dm, "call", lambda r, op, a=None, **kw: {"ok": True, "result": {
        "code_path": str(ident["import_path"]), "dev_tree": False}})
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch"])
    assert r.exit_code == 0, r.output
    assert calls == ["install"], calls
    assert "bootstrapped" in r.output
