"""plan-1 remediation (ch-bsd bsd-plan1-deploy-runtime-cabce24: #b-1, #b-2,
#s-3, #s-4, #s-8, #m-7). The recurrence guard must fire in the state that
caused the incident, and every surface must distinguish unknown from clean."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as daemon_mod
from refmatrix import hub as hub_mod
from refmatrix import upgrade as up
from tests.test_upgrade import _fake_tree, _fake_venv, _init_repo, _bump, _git


# ---- #b-1 the queues alert gates on dev_tree ------------------------------

def test_queue_row_is_hot_on_dev_tree():
    assert hub_mod._queue_row_is_hot({"daemon_up": True, "stale_files": 0, "dev_tree": True})
    assert not hub_mod._queue_row_is_hot({"daemon_up": True, "stale_files": 0, "dev_tree": False})
    assert hub_mod._queue_row_is_hot({"daemon_up": True, "stale_files": 3})


def test_gather_queues_carries_identity_end_to_end(tmp_path, monkeypatch):
    """The wiring, not a dict copy: discover → stats → ping → row."""
    root = tmp_path / "p" / ".refmatrix"; root.mkdir(parents=True)
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [root])
    monkeypatch.setattr("refmatrix.discovery.daemon_status", lambda r: {"up": True, "pid": 1})
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda r: "p")

    def fake_call(r, op, args=None, timeout=0.0, retries=2, **kw):
        if op == "stats":
            return {"ok": True, "result": {"stale_files": [], "health": {}}}
        if op == "ping":
            return {"ok": True, "result": {"pid": 1, "version": "9.9.9",
                                          "code_path": "/dev/src/refmatrix/__init__.py",
                                          "dev_tree": True}}
        return {"ok": False}
    monkeypatch.setattr(daemon_mod, "call", fake_call)
    rows = hub_mod.Hub._gather_queues(None)
    assert rows[0]["dev_tree"] is True and rows[0]["code_path"].startswith("/dev/")
    assert any(hub_mod._queue_row_is_hot(r) for r in rows)


# ---- #b-2 upgrade refuses in the incident state, on every path -----------

def test_upgrade_refuses_when_this_interpreter_runs_a_dev_tree(tmp_path, monkeypatch):
    deploy = tmp_path / "deploy"; _init_repo(deploy, "0.1.0")
    monkeypatch.setattr(up, "runtime_identity", lambda **kw: {
        "version": "0.1.0", "import_path": Path("/dev/src/refmatrix/__init__.py"),
        "code_root": Path("/dev"), "venv_tree": deploy, "editable_target": Path("/dev/src"),
        "dev_tree": True})
    with pytest.raises(up.UpgradeError, match="DEV TREE|dev tree"):
        up.upgrade(root=deploy, check=True)
    with pytest.raises(up.UpgradeError, match="DEV TREE|dev tree"):
        up.upgrade(root=deploy, install_fn=lambda r, log=print: None, restart_fn=lambda r, log=print: True)


def test_upgrade_verifies_editable_on_the_already_up_to_date_path(tmp_path):
    """2026-09-14 state: the deploy tree WAS at master's sha; only the .pth
    was wrong. 'already up to date' must still verify the venv."""
    deploy = tmp_path / "deploy"; _init_repo(deploy, "0.1.0")
    (deploy / "src" / "refmatrix").mkdir(parents=True)
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(deploy), str(dev)], check=True)
    _fake_venv(deploy, dev / "src")             # wrong target, same head
    with pytest.raises(up.UpgradeError, match="editable target"):
        up.upgrade(root=deploy, from_dev=dev, install_fn=lambda r, log=print: None,
                   restart_fn=lambda r, log=print: True)


def test_editable_marker_present_but_unreadable_fails_loud(tmp_path):
    deploy = _fake_tree(tmp_path, "deploy")
    sp = deploy / ".venv" / "lib" / "python3.14" / "site-packages"; sp.mkdir(parents=True)
    (sp / "__editable__.refmatrix-0.0.0.pth").write_text("import __editable___refmatrix_finder\n")
    with pytest.raises(up.UpgradeError, match="unreadable|finder"):
        up.verify_editable(deploy)


def test_daemon_restart_relaunch_fails_on_code_path_mismatch(tmp_path, monkeypatch):
    """The documented deploy path is ff + `daemon restart --relaunch`; it must
    compare what the NEW daemon imports with what this CLI imports."""
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    (tmp_path / ".refmatrix").mkdir()
    monkeypatch.setattr("refmatrix.launchctl.is_loaded", lambda root: False)
    monkeypatch.setattr(daemon_mod, "stop_daemon", lambda root, **kw: True)
    monkeypatch.setattr(daemon_mod, "spawn_daemon", lambda root, **kw: 4243)
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)
    from refmatrix import __version__
    seq = iter([(4242, __version__), (4243, __version__), (4243, __version__), (4243, __version__)])
    monkeypatch.setattr(daemon_mod, "served_identity", lambda root, timeout=1.0: next(seq))
    monkeypatch.setattr(daemon_mod, "call", lambda root, op, args=None, **kw: {
        "ok": True, "result": {"pid": 4243, "version": __version__,
                                "code_path": "/somewhere/else/refmatrix/__init__.py"}})
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch", "--standalone"])
    assert r.exit_code != 0
    assert "code path" in r.output.lower() or "code_path" in r.output


# ---- #s-3 / #s-4 hub status distinguishes unknown; hub reports itself -----

def test_daemon_identity_marks_unknown_not_clean(monkeypatch):
    monkeypatch.setattr(daemon_mod, "call", lambda root, op, args=None, **kw: {
        "ok": True, "result": {"pid": 1, "version": "0.65.0"}})
    ident = hub_mod._daemon_identity(Path("/x"))
    assert ident.get("unknown") is True and ident.get("version") == "0.65.0"


def test_hub_status_renders_unverified_and_hub_identity(monkeypatch):
    monkeypatch.setattr(hub_mod, "status", lambda: {
        "running": True, "pid": 7, "port": 7777, "registry_size": 2,
        "version": "9.9.9", "code_path": "/deploy/src/refmatrix/__init__.py", "dev_tree": False})
    monkeypatch.setattr(hub_mod, "rpc", lambda op, args=None: {"ok": True, "result": {"health": {
        "/a/.refmatrix": {"history": [{"up": True}], "policy": "auto", "restart_count": 0},
        "/b/.refmatrix": {"history": [{"up": True}], "policy": "auto", "restart_count": 0},
    }}})
    monkeypatch.setattr(hub_mod, "_daemon_identity", lambda root: (
        {"unknown": True, "version": "0.65.0"} if str(root).startswith("/a")
        else {"code_path": "/dev/x", "dev_tree": True}))
    out = CliRunner().invoke(cli_mod.main, ["hub", "status"]).output
    assert "UNVERIFIED" in out and "0.65.0" in out
    assert "DEV TREE" in out
    assert "code: /deploy/src/refmatrix/__init__.py" in out


def test_hub_info_carries_identity(monkeypatch):
    class FakeHub:
        port = 7777
        class watchdog: interval = 5
    monkeypatch.setattr("refmatrix.discovery.load_registry", lambda: {})
    info = hub_mod.Hub._op_hub_info(FakeHub(), {})
    assert "code_path" in info and "dev_tree" in info and "version" in info


# ---- #m-7 identity computed once, ping never fails because of it ----------

def test_ping_uses_cached_identity(monkeypatch, tmp_path):
    daemon_mod._process_identity()               # populate the per-process cache once
    def boom(**kw):
        raise RuntimeError("must not be called per ping")
    monkeypatch.setattr(up, "runtime_identity", boom)
    class D:
        root = tmp_path
        store = None
    res = daemon_mod._op_ping(D(), {})
    assert "code_path" in res and "dev_tree" in res


# ---- round 2 (bsd-plan1-r2): the relaunch guard must fire in the incident state ----

def _relaunch_env(monkeypatch, tmp_path, *, cli_ident, ping_result):
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    (tmp_path / ".refmatrix").mkdir(exist_ok=True)
    monkeypatch.setattr("refmatrix.launchctl.is_loaded", lambda root: False)
    monkeypatch.setattr(daemon_mod, "stop_daemon", lambda root, **kw: True)
    monkeypatch.setattr(daemon_mod, "spawn_daemon", lambda root, **kw: 4243)
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)
    from refmatrix import __version__
    seq = iter([(4242, __version__)] + [(4243, __version__)] * 6)
    monkeypatch.setattr(daemon_mod, "served_identity", lambda root, timeout=1.0: next(seq))
    monkeypatch.setattr(up, "runtime_identity", lambda **kw: cli_ident)
    monkeypatch.setattr(daemon_mod, "call", lambda root, op, args=None, **kw: ping_result)


def test_relaunch_fails_when_cli_and_daemon_both_run_a_dev_tree(tmp_path, monkeypatch):
    """The 2026-09-14 state: every plist runs ~/bin/rmx, the same venv/.pth as
    the CLI, so BOTH import the dev tree — paths match. The guard must look at
    dev_tree on both sides, not only compare paths."""
    from refmatrix import __version__
    dev = "/dev/src/refmatrix/__init__.py"
    ident = {"version": __version__, "import_path": Path(dev), "code_root": Path("/dev"),
             "venv_tree": Path("/deploy"), "editable_target": Path("/dev/src"), "dev_tree": True}
    _relaunch_env(monkeypatch, tmp_path, cli_ident=ident, ping_result={
        "ok": True, "result": {"pid": 4243, "version": __version__, "code_path": dev, "dev_tree": True}})
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch", "--standalone"])
    assert r.exit_code != 0
    assert "DEV TREE" in r.output


def test_relaunch_fails_when_the_daemons_code_path_cannot_be_read(tmp_path, monkeypatch):
    """A ping without code_path (or a ping error) is not 'verified'."""
    from refmatrix import __version__
    ident = {"version": __version__, "import_path": Path("/deploy/src/refmatrix/__init__.py"),
             "code_root": Path("/deploy"), "venv_tree": Path("/deploy"),
             "editable_target": Path("/deploy/src"), "dev_tree": False}
    _relaunch_env(monkeypatch, tmp_path, cli_ident=ident, ping_result={
        "ok": True, "result": {"pid": 4243, "version": __version__}})
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch", "--standalone"])
    assert r.exit_code != 0
    assert "code path" in r.output.lower()


def test_queue_alert_once_publishes_on_dev_tree(monkeypatch):
    published = []
    class FakeBus:
        def refinement_queue(self, status): return []
        def publish(self, channel, payload, *, sender, mtype): published.append((channel, payload, sender, mtype))
    class FakeHub:
        bus = FakeBus()
        def _gather_queues(self):
            return [{"project": "p", "root": "/r", "daemon_up": True, "stale_files": 0, "dev_tree": True}]
    hub_mod.Hub._queue_alert_once(FakeHub())
    assert published and published[0][0] == "global:queues"
    assert published[0][1]["queues"][0]["dev_tree"] is True
    published.clear()
    class QuietHub(FakeHub):
        def _gather_queues(self):
            return [{"project": "p", "root": "/r", "daemon_up": True, "stale_files": 0, "dev_tree": False}]
    hub_mod.Hub._queue_alert_once(QuietHub())
    assert published == []


def test_unknown_identity_row_is_hot():
    assert hub_mod._queue_row_is_hot({"daemon_up": True, "stale_files": 0, "identity": "unknown"})
