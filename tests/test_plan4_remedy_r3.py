"""bsd-plan4-r3 remedy (round 4 of plan 4): launchd is a supervisor too.

#b-1  the deploy step was a bare `launchctl kickstart -k` under launchd's
      5 s ExitTimeOut — five daemons SIGKILLed mid-drain in one night. The
      plist carries `ExitTimeOut` = the kill grace; `daemon restart` under
      launchd asks the daemon to stop (the grace) and kicks WITHOUT `-k`
      when it stopped; `_verify_relaunch` never SIGKILLs a predecessor whose
      heartbeat is fresh; the standalone path waits for a draining
      predecessor instead of spawning beside it.
#b-2  `_await_shutdown` read a heartbeat the shutdown stops first, so it
      could never wait from the state its caller hands it. The daemon writes
      `shutdown.started` as its first act of shutdown and the watchdog waits
      on THAT marker.
#s-3  the watchdog's no-process branch kicked inside a relaunch's throttle
      gap: it needs two consecutive no-process ticks; `daemon restart
      --relaunch` pauses the watchdog for the root and resumes after.
#s-4  `launchctl.check`/`reinstall`/`render_plist` take the binary the
      caller resolved; `install` refuses a dev-tree binary.
#m-5  `stop_daemon` keeps the ping-discovered pid after a failed grace.
#m-6  a heartbeat that cannot write is logged once per errno.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import hub as hub_mod
from refmatrix import launchctl as lc
from refmatrix.store import Store


def _draining_process(root: Path, *, exit_after_term_s: float, heartbeat: bool,
                      marker: bool = False, ignore_term: bool = False) -> subprocess.Popen:
    """A real process shaped like a daemon mid-drain: argv names rmx, it
    traps SIGTERM and exits `exit_after_term_s` later (never, when
    `ignore_term`), keeps its heartbeat fresh when `heartbeat`, and writes
    `shutdown.started` on SIGTERM when `marker` — what the daemon does."""
    code = f"""
import signal, sys, time, pathlib
root = pathlib.Path({str(root)!r})
hb = root / "heartbeat"; mk = root / "shutdown.started"
state = {{"term_at": None}}
def on_term(*_):
    state["term_at"] = time.monotonic()
    if {bool(marker)!r}:
        mk.touch()
signal.signal(signal.SIGTERM, on_term)
print("ready", flush=True)
t0 = time.monotonic()
while time.monotonic() - t0 < 300:
    if {bool(heartbeat)!r}:
        hb.touch()
    if (state["term_at"] is not None and not {bool(ignore_term)!r}
            and time.monotonic() - state["term_at"] >= {float(exit_after_term_s)!r}):
        sys.exit(0)
    time.sleep(0.1)
"""
    p = subprocess.Popen([sys.executable, "-c", code, "rmx", "daemon", "start"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    assert p.stdout.readline().strip() == "ready"
    return p


@pytest.fixture
def root():
    base = Path(tempfile.mkdtemp(prefix="rmxp4-", dir="/tmp"))
    r = base / ".refmatrix"; r.mkdir()
    Store(r).init()
    try:
        yield r
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


# ---- #b-1 launchd's own budget --------------------------------------------------------------

def test_plist_carries_an_exit_timeout_equal_to_the_kill_grace(root, monkeypatch):
    monkeypatch.setenv("RMX_BIN", "/usr/local/bin/rmx")
    d = plistlib.loads(lc.render_plist(root))
    assert d["ExitTimeOut"] == int(hub_mod.DEFAULT_KILL_GRACE_S) == 45
    assert lc.EXIT_TIMEOUT_S == hub_mod.DEFAULT_KILL_GRACE_S


def _launchd_fakes(monkeypatch, *, stopped: bool):
    calls = []
    monkeypatch.setattr(lc, "is_loaded", lambda r: True)
    monkeypatch.setattr(lc, "is_installed", lambda r: True)
    monkeypatch.setattr(lc, "kickstart",
                        lambda r, restart=False: calls.append(("kickstart", restart)) or "label")
    monkeypatch.setattr(dm, "graceful_stop",
                        lambda r, *, grace, report=None: calls.append(("graceful_stop", grace)) or stopped)
    monkeypatch.setattr(hub_mod, "rpc", lambda op, args=None, **kw: calls.append((op, args)) or {"ok": True})
    return calls


def test_daemon_restart_under_launchd_stops_gracefully_then_kicks_without_k(root, monkeypatch):
    calls = _launchd_fakes(monkeypatch, stopped=True)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart"])
    assert r.exit_code == 0, r.output
    ops = [c[0] for c in calls]
    assert ("graceful_stop", hub_mod.DEFAULT_KILL_GRACE_S) in calls, calls
    assert ops.index("graceful_stop") < ops.index("kickstart"), calls   # the stop order goes FIRST
    assert ("kickstart", False) in calls and ("kickstart", True) not in calls, calls


def test_daemon_restart_under_launchd_kicks_with_k_only_when_the_stop_was_ignored_and_says_so(root, monkeypatch):
    calls = _launchd_fakes(monkeypatch, stopped=False)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart"])
    assert r.exit_code == 0, r.output
    assert ("kickstart", True) in calls, calls
    assert "still alive" in r.output and "kickstart -k" in r.output, r.output


def test_verify_relaunch_never_kills_a_predecessor_with_a_fresh_heartbeat(root, monkeypatch):
    from refmatrix import __version__
    _launchd_fakes(monkeypatch, stopped=False)
    kills = []
    monkeypatch.setattr(dm, "served_identity", lambda r, timeout=2.0: (4242, __version__))
    monkeypatch.setattr(dm, "heartbeat_age", lambda r: 0.0)
    monkeypatch.setattr(cli_mod.os, "kill", lambda pid, sig: kills.append((pid, sig)))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch"])
    assert r.exit_code != 0
    assert "heartbeat" in r.output and "4242" in r.output, r.output
    assert kills == [], "a predecessor with a fresh heartbeat is WORKING; never SIGKILL it"


def test_verify_relaunch_kills_a_predecessor_only_when_its_heartbeat_is_stale(root, monkeypatch):
    from refmatrix import __version__, upgrade
    _launchd_fakes(monkeypatch, stopped=False)
    kills = []
    state = {"pid": 4242}
    monkeypatch.setattr(dm, "served_identity", lambda r, timeout=2.0: (state["pid"], __version__))
    monkeypatch.setattr(dm, "heartbeat_age", lambda r: float("inf"))

    def kill(pid, sig):
        kills.append((pid, sig)); state["pid"] = 4243
    monkeypatch.setattr(cli_mod.os, "kill", kill)
    mine = str(upgrade.runtime_identity()["import_path"])
    monkeypatch.setattr(dm, "call", lambda r, op, args=None, *, timeout=60.0, retries=2:
                        {"ok": True, "result": {"code_path": mine, "dev_tree": False, "pid": state["pid"]}})
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch"])
    assert r.exit_code == 0, r.output
    assert kills == [(4242, 9)], kills


@pytest.mark.timeout(60)
def test_standalone_restart_waits_for_a_draining_predecessor_instead_of_spawning_beside_it(root, monkeypatch):
    """A predecessor that exits 7 s after SIGTERM with a fresh heartbeat is
    draining; the old path gave it 5 s, withheld the SIGKILL (fresh beat),
    ignored the False and spawned a second daemon beside it."""
    p = _draining_process(root, exit_after_term_s=7.0, heartbeat=True)
    dm.pid_path(root).write_text(str(p.pid))
    spawned = []
    monkeypatch.setattr(dm, "spawn_daemon", lambda *a, **kw: spawned.append(time.monotonic()) or 1)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    try:
        t0 = time.monotonic()
        r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--standalone"])
        assert r.exit_code == 0, r.output
        rc = p.wait(timeout=1.0)
        assert rc == 0, f"the predecessor was killed (rc={rc}); it was draining"
        assert spawned and time.monotonic() - t0 >= 6.5, "spawned before the predecessor was gone"
    finally:
        if p.poll() is None:
            p.kill(); p.wait()


@pytest.mark.timeout(60)
def test_standalone_restart_refuses_to_spawn_beside_a_working_predecessor_that_will_not_stop(root, monkeypatch):
    p = _draining_process(root, exit_after_term_s=0.0, heartbeat=True, ignore_term=True)
    dm.pid_path(root).write_text(str(p.pid))
    spawned = []
    monkeypatch.setattr(dm, "spawn_daemon", lambda *a, **kw: spawned.append(1) or 1)
    monkeypatch.setenv("RMX_STOP_GRACE_S", "2")
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    try:
        r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--standalone"])
        assert r.exit_code != 0, r.output
        assert "still alive" in r.output and "heartbeat" in r.output, r.output
        assert spawned == [], "spawned a second daemon beside a live one"
        assert p.poll() is None, "a working predecessor was killed"
    finally:
        p.kill(); p.wait()


# ---- #b-2 the shutdown produces its own signal --------------------------------------------

@pytest.mark.timeout(90)
def test_a_real_daemon_writes_shutdown_started_as_its_first_act_of_shutdown(root):
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    marker = root / "shutdown.started"
    assert not marker.exists()
    t0 = time.time()
    try:
        dm.call(root, "stop", {}, timeout=5.0, retries=0)
    except Exception:  # noqa: BLE001 — the daemon may close the socket before answering
        pass
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and dm.is_alive(pid):
        time.sleep(0.1)
    assert not dm.is_alive(pid)
    assert marker.exists() and marker.stat().st_mtime >= t0 - 1.0
    assert dm.shutdown_started_age(root) < 60.0


def test_await_shutdown_waits_on_a_fresh_marker_until_the_pid_exits(root):
    p = _draining_process(root, exit_after_term_s=2.0, heartbeat=False)
    dm.pid_path(root).write_text(str(p.pid))
    hb = root / "heartbeat"; hb.touch(); _age(hb, 61)          # the caller's state
    try:
        os.kill(p.pid, signal.SIGTERM)
        (root / "shutdown.started").touch()
        t0 = time.monotonic()
        hub_mod.Watchdog()._await_shutdown(root)
        elapsed = time.monotonic() - t0
        assert elapsed >= 1.5, f"returned in {elapsed*1000:.0f} ms — did not wait for the drain"
        assert p.poll() is not None
    finally:
        if p.poll() is None:
            p.kill(); p.wait()


def test_await_shutdown_returns_at_once_without_a_marker(root):
    """No marker = not shutting down: the caller's stale-heartbeat state
    alone must not buy a second grace (the r3 arithmetic)."""
    p = _draining_process(root, exit_after_term_s=0.0, heartbeat=False, ignore_term=True)
    dm.pid_path(root).write_text(str(p.pid))
    hb = root / "heartbeat"; hb.touch(); _age(hb, 61)
    try:
        t0 = time.monotonic()
        hub_mod.Watchdog()._await_shutdown(root)
        assert time.monotonic() - t0 < 0.3
    finally:
        p.kill(); p.wait()


@pytest.mark.timeout(60)
def test_watchdog_check_waits_for_a_daemon_that_is_draining_after_its_signal(root, monkeypatch):
    """The CALLER's path (`_check`, not `_restart`): heartbeat stale, pid
    alive, the grace expires with the pid still draining — the kick lands
    after the process is gone, never on top of it."""
    p = _draining_process(root, exit_after_term_s=3.0, heartbeat=False, marker=True)
    dm.pid_path(root).write_text(str(p.pid))
    hb = root / "heartbeat"; hb.touch(); _age(hb, 61)
    events = []
    monkeypatch.setattr(hub_mod, "RMX_HUB_KILL_GRACE_S", 1.0)
    monkeypatch.setattr(hub_mod, "WATCHDOG_GRACE_MISSES", 1)
    monkeypatch.setattr(hub_mod.launchctl, "is_loaded", lambda r: True)
    monkeypatch.setattr(hub_mod.launchctl, "kickstart",
                        lambda r, restart=False: events.append(("kick", time.monotonic(), p.poll())) or "label")
    monkeypatch.setattr(hub_mod, "_log", lambda m: events.append(("log", m)))
    try:
        t0 = time.monotonic()
        hub_mod.Watchdog()._check(root)
        elapsed = time.monotonic() - t0
        kicks = [e for e in events if e[0] == "kick"]
        assert kicks and kicks[0][2] is not None, "kicked while the predecessor was still draining"
        assert elapsed >= 3.0, f"{elapsed:.1f}s"
        assert any("waiting" in e[1] for e in events if e[0] == "log"), events
    finally:
        if p.poll() is None:
            p.kill(); p.wait()


# ---- #s-3 no kick inside a relaunch's throttle gap -------------------------------------------

def test_watchdog_dead_branch_needs_two_consecutive_no_process_ticks(root, monkeypatch):
    monkeypatch.setattr(dm, "ping", lambda r, timeout=1.0, **kw: False)
    monkeypatch.setattr(dm, "read_pid", lambda r: None)
    restarts = []
    w = hub_mod.Watchdog()
    monkeypatch.setattr(w, "_restart", lambda r, *, alive=False: restarts.append(alive) or True)
    w._check(root)
    assert restarts == [], "kicked on the first no-process tick (a relaunch in progress)"
    w._check(root)
    assert restarts == [False]


def test_daemon_restart_relaunch_pauses_the_watchdog_for_the_root_and_resumes(root, monkeypatch):
    from refmatrix import __version__, upgrade
    calls = _launchd_fakes(monkeypatch, stopped=True)
    mine = str(upgrade.runtime_identity()["import_path"])
    # no predecessor answers before the kick; the new instance after it
    monkeypatch.setattr(dm, "served_identity",
                        lambda r, timeout=2.0: ((777, __version__)
                                                if any(c[0] == "kickstart" for c in calls) else None))
    monkeypatch.setattr(dm, "call", lambda r, op, args=None, *, timeout=60.0, retries=2:
                        {"ok": True, "result": {"code_path": mine, "dev_tree": False, "pid": 777}})
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch"])
    assert r.exit_code == 0, r.output
    ops = [c[0] for c in calls]
    assert ops.index("pause") < ops.index("kickstart") < ops.index("resume"), calls
    pause_args = next(c[1] for c in calls if c[0] == "pause")
    assert Path(pause_args["root"]).resolve() == root.resolve()
    assert pause_args["seconds"] >= hub_mod.DEFAULT_KILL_GRACE_S


def test_daemon_restart_relaunch_survives_a_hub_that_is_down(root, monkeypatch):
    calls = _launchd_fakes(monkeypatch, stopped=True)
    monkeypatch.setattr(hub_mod, "rpc", lambda op, args=None, **kw: (_ for _ in ()).throw(ConnectionRefusedError()))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart"])
    assert r.exit_code == 0, r.output
    assert ("kickstart", False) in calls


# ---- #s-4 the binary is the caller's, and never a dev tree ----------------------------------

def test_render_check_and_reinstall_take_the_callers_binary(root, monkeypatch):
    monkeypatch.setenv("RMX_BIN", "/env/bin/rmx")
    d = plistlib.loads(lc.render_plist(root, rmx="/given/bin/rmx"))
    assert d["ProgramArguments"][0] == "/given/bin/rmx"
    import inspect
    assert "rmx" in inspect.signature(lc.check).parameters
    assert "rmx" in inspect.signature(lc.reinstall).parameters


def _fake_binary(tmp_path: Path, *, dev_tree: bool) -> Path:
    b = tmp_path / "bin" / "rmx"; b.parent.mkdir(parents=True)
    ident = '{"dev_tree": %s, "import_path": "/x/src/refmatrix/__init__.py"}' % ("true" if dev_tree else "false")
    b.write_text(f"#!/bin/sh\necho '{ident}'\n")
    b.chmod(0o755)
    return b


def test_install_refuses_a_dev_tree_binary(root, tmp_path, monkeypatch):
    dev = _fake_binary(tmp_path, dev_tree=True)
    ident = lc.binary_identity(str(dev))
    assert ident["dev_tree"] is True
    with pytest.raises(RuntimeError, match="dev tree"):
        lc.install(root, rmx=str(dev))
    assert not lc.plist_path(root).exists(), "the plist was written before the refusal"


def test_check_names_a_dev_tree_binary_without_writing(root, tmp_path, monkeypatch):
    dev = _fake_binary(tmp_path, dev_tree=True)
    monkeypatch.setattr(lc, "installed_flags", lambda r: {})
    monkeypatch.setattr(lc, "plist_path", lambda r: tmp_path / "x.plist")
    (tmp_path / "x.plist").write_bytes(b"<plist/>")
    ok, why = lc.check(root, rmx=str(dev))
    assert ok is False and "dev tree" in why, why
    assert (tmp_path / "x.plist").read_bytes() == b"<plist/>"


# ---- #m-5 the discovered pid is kept ---------------------------------------------------------

def test_stop_daemon_keeps_the_ping_discovered_pid_after_a_failed_grace(monkeypatch):
    from tests.test_plan2_remedy import _PingOnlyDaemon
    d = _PingOnlyDaemon(seeded=True)
    try:
        # the live process is one that IGNORES SIGTERM and keeps its
        # heartbeat fresh (working); the ping answers with its pid
        d.proc.kill(); d.proc.wait()
        d.proc = _draining_process(d.root, exit_after_term_s=0.0, heartbeat=True, ignore_term=True)
        d.pid = d.proc.pid
        # the pid file is stale; the ping carries the real pid
        dm.pid_path(d.root).write_text("999999")
        rep = {}
        t0 = time.monotonic()
        out = dm.stop_daemon(d.root, timeout=1.0, report=rep)
        assert out is False, rep
        assert rep.get("pid") == d.pid, rep
        assert str(rep.get("kill", "")).startswith("withheld"), rep
        assert d.proc.poll() is None
        assert time.monotonic() - t0 < 10.0
    finally:
        d.close()


# ---- #m-6 a beat that cannot write says so, once ---------------------------------------------

def test_heartbeat_touch_failure_is_logged_once_per_errno(tmp_path):
    root = tmp_path / "gone" / ".refmatrix"
    d = dm.Daemon(root)
    lines = []
    d._log = lambda m: lines.append(m)
    d._heartbeat_touch()
    d._heartbeat_touch()
    assert len(lines) == 1 and "heartbeat touch failed" in lines[0], lines
    root.mkdir(parents=True)
    d._heartbeat_touch()
    assert (root / "heartbeat").exists()
    assert len(lines) == 1, lines


def test_forced_install_stops_the_daemon_gracefully_before_the_bootout(root, monkeypatch, tmp_path):
    """`reinstall` on drift = `install(force=True)` = a bootout, which is
    launchd's SIGTERM + SIGKILL at the OLD plist's ExitTimeOut (5 s): the
    first relaunch-fleet on the new plists would have killed every draining
    daemon. The daemon is asked to stop with the grace first."""
    calls = []
    monkeypatch.setenv("RMX_BIN", "/usr/local/bin/rmx")
    monkeypatch.setattr(lc, "_refuse_dev_tree", lambda rmx: None)
    monkeypatch.setattr(lc, "_migrate_legacy", lambda r: False)
    monkeypatch.setattr(lc, "is_loaded", lambda r: True)
    monkeypatch.setattr(lc, "_wait_loaded", lambda r, *, expected, timeout=3.0: True)
    monkeypatch.setattr(lc, "_loaded_env_drift", lambda r, rendered: [])   # launchd's own view: faked
    monkeypatch.setattr(lc, "plist_path", lambda r: tmp_path / "x.plist")
    monkeypatch.setattr(lc, "LAUNCH_AGENTS_DIR", tmp_path)
    monkeypatch.setattr(lc.subprocess, "run",
                        lambda cmd, **kw: calls.append(("run", list(cmd)[:2]))
                        or subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(dm, "graceful_stop",
                        lambda r, *, grace, report=None: calls.append(("graceful_stop", grace)) or True)
    lc.install(root, force=True)
    ops = [c[0] for c in calls]
    assert "graceful_stop" in ops, calls
    assert ops.index("graceful_stop") < ops.index("run"), calls      # the stop order before launchd's
    assert calls[ops.index("graceful_stop")][1] == lc.EXIT_TIMEOUT_S
    assert (tmp_path / "x.plist").exists()


def test_hub_plist_carries_the_exit_timeout_too(monkeypatch):
    monkeypatch.setenv("RMX_BIN", "/usr/local/bin/rmx")
    d = plistlib.loads(lc.render_hub_plist())
    assert d["ExitTimeOut"] == int(lc.EXIT_TIMEOUT_S)


def test_forced_hub_install_stops_the_hub_before_the_bootout(monkeypatch, tmp_path):
    """launchd SIGKILLed the hub at 04:26:17 (2026-09-15) on a `kickstart -k`
    — a forced reinstall boots it out the same way."""
    calls = []
    monkeypatch.setenv("RMX_BIN", "/usr/local/bin/rmx")
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: True)
    monkeypatch.setattr(lc, "hub_plist_path", lambda: tmp_path / "hub.plist")
    monkeypatch.setattr(lc, "LAUNCH_AGENTS_DIR", tmp_path)
    state = {"stopped": False}

    def rpc(op, args=None, *, timeout=30.0):
        calls.append(("rpc", op))
        if op == "stop":
            state["stopped"] = True; return {"ok": True}
        if state["stopped"]:
            raise ConnectionRefusedError()
        return {"ok": True}
    monkeypatch.setattr(hub_mod, "rpc", rpc)
    monkeypatch.setattr(lc.subprocess, "run",
                        lambda cmd, **kw: calls.append(("run", list(cmd)[:2]))
                        or subprocess.CompletedProcess(cmd, 0, "", ""))
    lc.install_hub(force=True)
    assert ("rpc", "stop") in calls, calls
    first_run = [i for i, c in enumerate(calls) if c[0] == "run"][0]
    assert calls.index(("rpc", "stop")) < first_run, calls

