"""ch-bsd plan-4 r1 remediation (6ae4b6f): #b-1 an aborted repair is an
error on the wire; #b-2 adoption never SIGKILLs a busy predecessor and the
offline repair never opens the writer under one; #b-3 the graceful stop
signals FIRST and then waits the grace; #b-4 every invalidation detector
queues the boot repair; #b-5 the entities rebuild is DuckDB-only; #b-6
`hub status` shows each daemon's version and flags a stale one, and
`rmx hub relaunch-fleet` relaunches every supervised store; #s-7 the
heartbeat is derived from serving progress; #m-9 adoption is gated on the
supervisor; #m-10 a degraded read arms the repair; #m-11 boot repair is
proven on a spawned daemon; #m-12 stop_daemon reports why it could not ask."""
from __future__ import annotations

import json
import os
import shutil
import signal
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
from refmatrix.cli import main as cli_main
from refmatrix.store import RepairAbort, Store
from tests.test_plan2_remedy import _SilentDaemon


def _spawn():
    base = Path(tempfile.mkdtemp(prefix="rmxp4-", dir="/tmp"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    return base, root, pid


@pytest.fixture
def stopped():
    """A real daemon, SIGSTOPped: alive, holds its pid file + socket, cannot
    answer, cannot handle SIGTERM — the state a SIGKILL corrupts."""
    base, root, pid = _spawn()
    os.kill(pid, signal.SIGSTOP)
    yield base, root, pid
    try:
        os.kill(pid, signal.SIGCONT)
    except ProcessLookupError:
        pass
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


# ---- #b-1 abort on the wire ---------------------------------------------------

def test_repair_entities_op_raises_so_the_dispatcher_answers_ok_false(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"; root.mkdir()
    d = dm.Daemon(root); d.store = Store(root); d.store.init()
    d._log = lambda m: None
    monkeypatch.setattr(d.store, "rebuild_entities_indexes",
                        lambda: (_ for _ in ()).throw(RepairAbort("2 real duplicate groups")))
    with pytest.raises(RepairAbort, match="duplicate"):
        dm._op_repair_entities(d, {})
    d.store.close()


def test_repair_index_entities_cli_reports_the_abort(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr("refmatrix.discovery.daemon_status", lambda r, **kw: {"up": True, "busy": False, "pid": 1})
    monkeypatch.setattr(dm, "call", lambda r, op, args=None, **kw: {"ok": False, "error": "repair aborted: 2 real duplicate groups"})
    r = CliRunner().invoke(cli_main, ["repair-index", "--entities"])
    assert r.exit_code != 0 and "aborted" in r.output and "rebuilt" not in r.output


# ---- #b-2 busy predecessor / offline writer --------------------------------------

def test_adoption_never_kills_a_busy_predecessor(stopped, monkeypatch):
    base, root, pid = stopped
    monkeypatch.setenv("RMX_ADOPT_GRACE_S", "1")
    monkeypatch.setattr(dm, "ADOPT_GRACE_S", 1.0)
    d = dm.Daemon(root)
    logs = []
    d._log = lambda m: logs.append(m)
    t0 = time.monotonic()
    adopted = d._adopt_unsupervised(dm.socket_path(root))
    assert adopted is True
    assert time.monotonic() - t0 < 8.0     # grace 1 s + stop_daemon's own 2 s SIGTERM wait
    assert dm.is_alive(pid), "the predecessor was killed"
    assert any("did not stop" in m for m in logs), logs
    # the reap defers to a fresh heartbeat: no SIGKILL, yield instead
    assert d._reap_predecessor(dm.socket_path(root)) is False
    assert dm.is_alive(pid)
    assert any("heartbeat" in m and "yield" in m for m in logs), logs


def test_repair_index_entities_refuses_a_busy_daemon(monkeypatch):
    d = _SilentDaemon()
    try:
        monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
        r = CliRunner().invoke(cli_main, ["repair-index", "--entities"])
        assert r.exit_code != 0 and "busy" in r.output
        assert not list(d.root.glob("catalog*.duckdb")), "opened the writer under a busy daemon"
    finally:
        d.close()


# ---- #b-3 signal first, then the grace ----------------------------------------------

def test_graceful_stop_signals_first_then_waits_the_grace(stopped):
    base, root, pid = stopped
    t0 = time.monotonic()
    ok = hub_mod.graceful_stop(root, grace=1.0)
    elapsed = time.monotonic() - t0
    assert ok is False and 0.9 < elapsed < 3.0
    assert dm.is_alive(pid), "graceful_stop must never SIGKILL"


def test_graceful_stop_on_a_live_daemon_returns_quickly():
    base, root, pid = _spawn()
    try:
        t0 = time.monotonic()
        assert hub_mod.graceful_stop(root, grace=10.0) is True
        assert time.monotonic() - t0 < 8.0
        assert not dm.is_alive(pid)
    finally:
        dm.stop_daemon(root); shutil.rmtree(base, ignore_errors=True)


def test_watchdog_restart_order_is_signal_then_grace_then_kick(monkeypatch, tmp_path):
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    calls = []
    monkeypatch.setattr(hub_mod, "graceful_stop", lambda r, grace: calls.append(("graceful_stop", grace)) or False)
    monkeypatch.setattr(launchctl, "is_loaded", lambda r: True)
    monkeypatch.setattr(launchctl, "kickstart", lambda r, restart=False: calls.append(("kickstart", restart)) or "l")
    monkeypatch.setattr(hub_mod, "RMX_HUB_KILL_GRACE_S", 7.0)
    hub_mod.Watchdog()._restart(root, alive=True)
    assert calls == [("graceful_stop", 7.0), ("kickstart", True)]


# ---- #b-4 every detector queues the repair ------------------------------------------

def test_fast_exit_queues_the_boot_repair(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"; root.mkdir()
    d = dm.Daemon(root); d._log = lambda m: None
    exited = []
    monkeypatch.setattr(dm.os, "_exit", lambda code: exited.append(code))
    d._fast_exit_if_invalidated(RuntimeError("Failed to delete all rows from index"), "watch flush")
    assert exited == [2]
    body = json.loads(dm.repair_marker_path(root).read_text())
    assert body["table"] == "entities" and body["op"] == "watch flush"


# ---- #b-5 DuckDB-only -------------------------------------------------------------

def test_rebuild_entities_refuses_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    s = Store(tmp_path / ".refmatrix"); s.init()
    s.add_memory(name="m", content="b", mtype="project")
    c = s.add_concept("alpha")
    with pytest.raises(RepairAbort, match="DuckDB"):
        s.rebuild_entities_indexes()
    assert s.get_memory("m") is not None
    s.close()


# ---- #b-6 versions visible; fleet relaunch ----------------------------------------------

def test_hub_status_shows_each_daemons_version_and_flags_stale(monkeypatch):
    monkeypatch.setattr(hub_mod, "status", lambda: {
        "running": True, "pid": 1, "port": 7777, "registry_size": 2, "sock": "/s", "home": "/h",
        "version": "0.69.1", "code_path": "/x/refmatrix/__init__.py", "dev_tree": False})
    monkeypatch.setattr(hub_mod, "rpc", lambda op, args=None, **kw: {"ok": True, "result": {"health": {
        "/a/.refmatrix": {"history": [{"up": True}], "policy": "auto", "restart_count": 0, "paused": False},
        "/b/.refmatrix": {"history": [{"up": True}], "policy": "auto", "restart_count": 0, "paused": False}}}})
    monkeypatch.setattr(hub_mod, "_daemon_identity", lambda root, **kw: (
        {"code_path": "/x/refmatrix/__init__.py", "dev_tree": False, "version": "0.66.3"}
        if str(root).startswith("/a") else
        {"code_path": "/x/refmatrix/__init__.py", "dev_tree": False, "version": "0.69.1"}))
    r = CliRunner().invoke(cli_main, ["hub", "status"])
    assert r.exit_code == 0, r.output
    a = [l for l in r.output.splitlines() if "/a/.refmatrix" in l][0]
    b = [l for l in r.output.splitlines() if "/b/.refmatrix" in l][0]
    assert "v0.66.3" in a and "STALE" in a
    assert "v0.69.1" in b and "STALE" not in b


def test_relaunch_fleet_relaunches_every_supervised_store(monkeypatch, tmp_path):
    roots = [tmp_path / "a" / ".refmatrix", tmp_path / "b" / ".refmatrix"]
    for r in roots:
        r.mkdir(parents=True)
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: list(roots))
    monkeypatch.setattr(launchctl, "is_loaded", lambda r: str(r).endswith("a/.refmatrix"))
    ran = []

    class R:
        returncode = 0
        stdout = "relaunch verified pid 1->2 version=x code=/deploy\n"
        stderr = ""
    monkeypatch.setattr("subprocess.run", lambda argv, **kw: ran.append((argv, kw.get("env", {}).get("REFMATRIX_ROOT"))) or R())
    r = CliRunner().invoke(cli_main, ["hub", "relaunch-fleet"])
    assert r.exit_code == 0, r.output
    assert len(ran) == 1 and ran[0][1] == str(roots[0]) and "daemon" in ran[0][0] and "--relaunch" in ran[0][0]
    assert "b/.refmatrix" in r.output and "not supervised" in r.output


# ---- #s-7 heartbeat from serving progress ----------------------------------------------

class _DeadPool:
    def submit(self, fn, *a, **kw):
        return Future()          # never completes: a deadlocked pool


class _LivePool:
    def submit(self, fn, *a, **kw):
        f = Future(); f.set_result(fn(*a, **kw)); return f


def test_heartbeat_stops_when_the_serving_pool_is_dead(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setenv("RMX_HEARTBEAT_S", "0.05")
    d = dm.Daemon(root); d._log = lambda m: None
    d._cli_pool = _DeadPool()
    d._start_heartbeat()
    try:
        time.sleep(0.3)
        hb = dm.heartbeat_path(root)
        t1 = hb.stat().st_mtime
        time.sleep(0.4)
        assert hb.stat().st_mtime == t1, "heartbeat advanced without the serving pool making progress"
    finally:
        d._stop_heartbeat()
    d._cli_pool = _LivePool()
    d._start_heartbeat()
    try:
        time.sleep(0.3)
        t2 = hb.stat().st_mtime
        time.sleep(0.3)
        assert hb.stat().st_mtime > t2
    finally:
        d._stop_heartbeat()


# ---- #m-9 adoption is gated on the supervisor ---------------------------------------------

def test_plist_marks_the_daemon_supervised_and_adoption_is_gated(tmp_path):
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    assert b"RMX_SUPERVISED" in launchctl.render_plist(root)
    base, r, pid = _spawn()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            dm.serve_foreground(r, supervised=False)
        assert dm.is_alive(pid) and dm.ping(r)
    finally:
        dm.stop_daemon(r); shutil.rmtree(base, ignore_errors=True)


# ---- #m-10 a degraded read arms the repair --------------------------------------------------

def test_degraded_learn_arms_a_deferred_exit(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"; root.mkdir()
    d = dm.Daemon(root); d.store = Store(root); d.store.init()
    d._request_snapshot = lambda: None; d._log = lambda m: None
    monkeypatch.setenv("RMX_DEGRADE_EXIT_S", "0.2")
    monkeypatch.setattr(dm, "_learn_grep_hits", lambda *a: (_ for _ in ()).throw(
        RuntimeError("Failed to delete all rows from index. Only deleted 0 out of 1 rows.")))
    exited = []
    monkeypatch.setattr(dm.os, "_exit", lambda code: exited.append(code))
    res = dm._op_learn_from_grep(d, {"pattern": "x", "hits": [{"file": "a.py", "line": 1}]})
    assert res == {"added": 0, "skipped": "store-invalid"} and exited == []
    time.sleep(0.8)
    assert exited == [2], "the repair was never armed"
    d.store.close()


# ---- #m-11 boot repair on a spawned daemon ----------------------------------------------------

def test_boot_repair_runs_on_a_spawned_daemon():
    base = Path(tempfile.mkdtemp(prefix="rmxp4b-", dir="/tmp"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    s = Store(root); s.init(); s.add_memory(name="m", content="b", mtype="project"); s.close()
    dm.repair_marker_path(root).write_text(json.dumps({"table": "entities", "op": "test", "at": 0}))
    try:
        pid = dm.spawn_daemon_subprocess(root, watch_root=[])
        assert pid and dm.ping(root)
        deadline = time.monotonic() + 20
        while dm.repair_marker_path(root).exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not dm.repair_marker_path(root).exists()
        assert "repaired entities" in (root / "rmxd.log").read_text()
    finally:
        dm.stop_daemon(root); shutil.rmtree(base, ignore_errors=True)


# ---- #m-12 stop_daemon says why -----------------------------------------------------------------

def test_stop_daemon_reports_why_it_could_not_ask(stopped):
    base, root, pid = stopped
    report: dict = {}
    ok = dm.stop_daemon(root, timeout=0.5, report=report)
    assert ok is False
    assert report.get("stop_op") and "not answering" in report["stop_op"]
