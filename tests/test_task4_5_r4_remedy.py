"""Task 4.5 (W1-a) — plan-4 round-4 remedy. RED tests; spec
`workflow/plans/plan-4-daemon-resilience-tasks/task-4.5-r4-remedy.md`.

r4 #s-2  `binary_identity` answers `{"dev_tree": None}` for a binary it cannot read, and the
         three guards (`_refuse_dev_tree`, `check`, `check_hub`) read `if ident.get("dev_tree")`
         — None is falsy, so "unknown" passes as "not a dev tree". Fail closed. (AC-1..AC-4)
r4 #s-3  `stop_daemon(root, *, timeout=5.0)`: five stop paths still hand the daemon launchd's
         OLD 5 s, `launchctl.install` bypasses the helper, and `_respawn` discards a False and
         spawns beside a live predecessor. Every stop path resolves `stop_grace_s()`. (AC-5..7)
r4 #m-5  `install(allow_dev=)` has no CLI caller; the refusal tells the operator to use it.
         `rmx daemon launchctl install --allow-dev`, parity with the hub command. (AC-8)
r4 #m-6  the session-indexer plist has no ExitTimeOut (launchd's 5 s). (AC-9)
r4 #s-4  tests appended to the LIVE ~/.refmatrix/hub.log — closed by task 23.0's sandbox
         (AC-10 is a GREEN-at-HEAD guard); the marker-wait line names no root (AC-11, RED).

Nothing here reaches launchd or a live store: the launchd surfaces are faked exactly as
tests/test_plan4_remedy_r3.py fakes them, the 23.0 audit hook refuses the live home, and every
store is a short /tmp root. Doubles are registered in workflow/test_mock_registry.md.
"""
from __future__ import annotations

import inspect
import os
import plistlib
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import hub as hub_mod
from refmatrix import launchctl as lc
from refmatrix import session_launchctl as slc
from refmatrix.store import Store
from tests.fake_rmx import identity_binary, script_binary
from tests.test_plan4_remedy_r3 import _draining_process, _age

_DEPLOYED = "/deployed/bin/rmx"   # a path rendered INTO a fixture plist; never executed


@pytest.fixture
def root():
    base = Path(tempfile.mkdtemp(prefix="rmx45-", dir="/tmp"))
    r = base / ".refmatrix"; r.mkdir()
    Store(r).init()
    try:
        yield r
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(autouse=True)
def _fresh_identity_cache(monkeypatch):
    """`binary_identity` caches per path for the life of the process; each test asks afresh."""
    monkeypatch.setattr(lc, "_IDENTITY_CACHE", {})


def _script(tmp_path: Path, name: str, body: str) -> Path:
    return script_binary(tmp_path, name, body)


def _identity_binary(tmp_path: Path, *, dev_tree: bool) -> Path:
    return identity_binary(tmp_path, dev_tree=dev_tree)


# The three shapes of "unknown" the r4 probe found: a pre-0.69 binary that prints a version
# line, a binary whose venv is mid-rebuild (exits non-zero, no output), a mistyped --rmx.
_UNKNOWN = {
    "version-line": lambda t: _script(t, "old", "echo 'rmx 0.68.0'"),
    "exits-nonzero": lambda t: _script(t, "failing", "exit 3"),
    "missing-path": lambda t: t / "nowhere" / "rmx",
}


@pytest.fixture(params=sorted(_UNKNOWN))
def unknown_binary(request, tmp_path):
    b = _UNKNOWN[request.param](tmp_path)
    ident = lc.binary_identity(str(b))
    assert ident.get("dev_tree") is None and ident.get("error"), (
        f"fixture precondition: {request.param} must read as unknown, got {ident}")
    return b


def _fake_launchd(monkeypatch, tmp_path: Path, *, loaded: bool = False) -> list:
    """Every launchd surface `launchctl.install` touches, faked. Call AFTER priming the
    identity cache: `subprocess.run` is the process-wide function `binary_identity` uses."""
    runs: list = []
    agents = tmp_path / "agents"
    monkeypatch.setattr(lc, "LAUNCH_AGENTS_DIR", agents)
    monkeypatch.setattr(lc, "plist_path", lambda r: agents / "x.plist")
    monkeypatch.setattr(lc, "_migrate_legacy", lambda r: False)
    monkeypatch.setattr(lc, "is_loaded", lambda r: loaded)
    monkeypatch.setattr(lc, "_wait_loaded", lambda r, expected, timeout: True)
    monkeypatch.setattr(lc, "_loaded_env_drift", lambda r, rendered: [])
    monkeypatch.setattr(lc.subprocess, "run",
                        lambda cmd, **kw: runs.append(list(cmd)[:2])
                        or subprocess.CompletedProcess(cmd, 0, "", ""))
    return runs


# ---- AC-1..AC-4 (r4 #s-2): unknown fails closed ----------------------------------------------

def test_refuse_dev_tree_refuses_a_binary_whose_identity_is_unknown(unknown_binary):
    """AC-1. At HEAD `_refuse_dev_tree` returns silently: `None` is falsy."""
    ident = lc.binary_identity(str(unknown_binary))
    with pytest.raises(RuntimeError) as ei:
        lc._refuse_dev_tree(str(unknown_binary))
    msg = str(ei.value)
    assert "identity unknown" in msg, msg
    assert str(unknown_binary) in msg, msg
    assert ident["error"].split(":")[0] in msg, f"the identity error is not named: {msg}"
    assert "--allow-dev" in msg, msg


def test_refuse_dev_tree_passes_a_binary_that_says_it_is_not_a_dev_tree(tmp_path):
    """AC-1 control (GREEN at HEAD): fail-closed must not refuse the deployed binary."""
    lc._refuse_dev_tree(str(_identity_binary(tmp_path, dev_tree=False)))


def test_install_refuses_an_unknown_binary_before_writing_or_calling_launchd(
        root, tmp_path, monkeypatch):
    """AC-2. At HEAD the refusal passes, the plist is written and `launchctl bootstrap` runs."""
    unknown = _UNKNOWN["version-line"](tmp_path)
    lc.binary_identity(str(unknown))                     # prime before subprocess.run is faked
    runs = _fake_launchd(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="identity unknown"):
        lc.install(root, rmx=str(unknown))
    assert not (tmp_path / "agents" / "x.plist").exists(), "plist written before the refusal"
    assert runs == [], f"launchctl called before the refusal: {runs}"


def test_reinstall_refuses_an_unknown_binary_and_leaves_the_daemon_plist_alone(
        root, tmp_path, monkeypatch):
    """AC-2, the r4 scenario end to end on the DAEMON plist: `relaunch-fleet` ->
    `reinstall(rmx=<unreadable>)` -> `install(force=True)`. The installed plist (rendered for
    the deployed binary) must survive byte-identical, and launchd is never called."""
    unknown = _UNKNOWN["version-line"](tmp_path)
    lc.binary_identity(str(unknown))
    runs = _fake_launchd(monkeypatch, tmp_path, loaded=True)
    installed = tmp_path / "agents" / "x.plist"
    installed.parent.mkdir(parents=True, exist_ok=True)
    installed.write_bytes(lc.render_plist(root, rmx=_DEPLOYED))
    before = installed.read_bytes()
    stops: list = []
    monkeypatch.setattr(dm, "graceful_stop",
                        lambda r, *, grace, report=None: stops.append(grace) or True)
    with pytest.raises(RuntimeError, match="identity unknown"):
        lc.reinstall(root, rmx=str(unknown))
    assert installed.read_bytes() == before, "the daemon plist was rewritten to an unknown binary"
    assert runs == [] and stops == [], f"launchd / the daemon was touched: {runs} {stops}"


def test_install_hub_refuses_an_unknown_binary_before_writing_or_calling_launchd(
        tmp_path, monkeypatch):
    """AC-2's hub twin: `install_hub` shares `_refuse_dev_tree`."""
    unknown = _UNKNOWN["exits-nonzero"](tmp_path)
    lc.binary_identity(str(unknown))
    runs = _fake_launchd(monkeypatch, tmp_path)
    monkeypatch.setattr(lc, "hub_plist_path", lambda: tmp_path / "agents" / "hub.plist")
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: False)
    with pytest.raises(RuntimeError, match="identity unknown"):
        lc.install_hub(rmx=str(unknown))
    assert not (tmp_path / "agents" / "hub.plist").exists()
    assert runs == [], runs


def test_install_with_allow_dev_installs_against_an_unknown_binary(root, tmp_path, monkeypatch):
    """AC-2 control (GREEN at HEAD): the explicit override still installs."""
    unknown = _UNKNOWN["version-line"](tmp_path)
    lc.binary_identity(str(unknown))
    _fake_launchd(monkeypatch, tmp_path)
    p = lc.install(root, rmx=str(unknown), allow_dev=True)
    assert plistlib.loads(p.read_bytes())["ProgramArguments"][0] == str(unknown)


def test_check_reports_unknown_identity_not_drift(root, tmp_path, monkeypatch, unknown_binary):
    """AC-3. At HEAD `check` renders against the unreadable binary and reports
    `ProgramArguments` drift — the drift `relaunch-fleet` then "fixes" by rewriting the plist."""
    installed = tmp_path / "installed.plist"
    installed.write_bytes(lc.render_plist(root, rmx=_DEPLOYED))
    monkeypatch.setattr(lc, "plist_path", lambda r: installed)
    monkeypatch.setattr(lc, "is_loaded", lambda r: True)
    monkeypatch.setattr(lc, "_loaded_env_drift", lambda r, rendered: [])
    before = installed.read_bytes()
    ok, why = lc.check(root, rmx=str(unknown_binary))
    assert ok is False
    assert "identity unknown" in why, why   # not just "unknown": tmp_path names carry it
    assert "drifted" not in why, f"an unknown binary was reported as fixable drift: {why}"
    assert installed.read_bytes() == before


def test_check_hub_reports_unknown_identity_not_drift(tmp_path, monkeypatch, unknown_binary):
    """AC-4. Same guard, the hub's twin (`launchctl.py:575`)."""
    installed = tmp_path / "hub.plist"
    installed.write_bytes(lc.render_hub_plist(rmx=_DEPLOYED, allow_dev=True))
    monkeypatch.setattr(lc, "hub_plist_path", lambda: installed)
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: True)
    ok, why = lc.check_hub(rmx=str(unknown_binary))
    assert ok is False
    assert "identity unknown" in why, why   # not just "unknown": tmp_path names carry it
    assert "drifted" not in why, f"an unknown binary was reported as fixable drift: {why}"


# ---- AC-5..AC-7 (r4 #s-3): one stop grace on every stop path --------------------------------

class _Stopped(Exception):
    """Raised by the recording `graceful_stop` once it has the grace: the command under test
    stops there, so nothing past the stop order (an export, a pip install) runs."""


def _record_grace(monkeypatch) -> list:
    graces: list = []

    def fake(root, *, grace, report=None):
        graces.append(grace)
        raise _Stopped(grace)
    monkeypatch.setattr(dm, "graceful_stop", fake)
    return graces


def _path_daemon_stop(root, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    CliRunner().invoke(cli_mod.main, ["daemon", "stop"])


def _path_compact(root, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dm, "ping", lambda *a, **kw: True)
    CliRunner().invoke(cli_mod.main, ["compact"])


def _path_upgrade_restart(root, monkeypatch, tmp_path):
    from refmatrix import upgrade
    monkeypatch.setattr(lc, "status", lambda r: {})
    upgrade._default_restart(root, log=lambda m: None)


def _path_launchctl_install_force(root, monkeypatch, tmp_path):
    _fake_launchd(monkeypatch, tmp_path, loaded=True)
    with pytest.raises(_Stopped):
        lc.install(root, rmx=_DEPLOYED, allow_dev=True, force=True)


def _path_hub_ui_stop(root, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from refmatrix import discovery
    from refmatrix.ui import server as srv
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    monkeypatch.setattr(discovery, "all_projects", lambda with_footprint=True: [])
    TestClient(srv.create_app(hub_mod.Hub(port=0))).post(
        "/api/daemon", json={"root": str(root), "action": "stop"})


def _path_stop_daemon_default(root, monkeypatch, tmp_path):
    with pytest.raises(_Stopped):
        dm.stop_daemon(root)


_STOP_PATHS = {
    "1-daemon-stop": _path_daemon_stop,
    "5-compact": _path_compact,
    "6-upgrade-restart": _path_upgrade_restart,
    "7-launchctl-install-force": _path_launchctl_install_force,
    "8-hub-ui-stop": _path_hub_ui_stop,
    "stop_daemon-default": _path_stop_daemon_default,
}


@pytest.mark.parametrize("path", sorted(_STOP_PATHS))
def test_every_stop_path_hands_the_daemon_the_one_stop_grace(path, root, monkeypatch, tmp_path):
    """AC-5. `RMX_STOP_GRACE_S=7.5` is distinguishable from both stale numbers (5.0, the old
    `stop_daemon` default; 45, `EXIT_TIMEOUT_S` read past the helper). At HEAD paths 1/5/6/8
    and the bare default hand 5.0 and path 7 hands 45."""
    monkeypatch.setenv("RMX_STOP_GRACE_S", "7.5")
    assert dm.stop_grace_s() == 7.5
    graces = _record_grace(monkeypatch)
    _STOP_PATHS[path](root, monkeypatch, tmp_path)
    assert graces, f"{path} never reached graceful_stop"
    assert graces[0] == 7.5, f"{path} handed the daemon {graces[0]}s, not stop_grace_s()=7.5"


@pytest.mark.timeout(60)
def test_daemon_stop_waits_out_a_six_second_drain_and_exits_zero(root, monkeypatch):
    """AC-6, the ledger's own acceptance on a real process: SIGTERM, a fresh heartbeat, exit 6 s
    later. At HEAD: False at 5.0 s, SIGKILL withheld (working) -> exit 1 "did not stop"."""
    monkeypatch.delenv("RMX_STOP_GRACE_S", raising=False)
    p = _draining_process(root, exit_after_term_s=6.0, heartbeat=True)
    dm.pid_path(root).write_text(str(p.pid))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    try:
        r = CliRunner().invoke(cli_mod.main, ["daemon", "stop"])
        assert r.exit_code == 0, r.output
        assert "daemon stopped" in r.output, r.output
        assert p.wait(timeout=2.0) == 0, "the draining process was killed, not waited for"
    finally:
        if p.poll() is None:
            p.kill(); p.wait()


@pytest.mark.timeout(60)
def test_relaunch_respawn_honours_a_failed_stop_and_never_spawns_beside_it(root, monkeypatch):
    """AC-7. `_respawn` (the `--relaunch` kick on the standalone path) stopped with the 5 s
    default, discarded the False and spawned. At HEAD: a second `spawn_daemon`, then the
    verify loop runs to "did not converge"."""
    old = subprocess.Popen(["sleep", "300"])         # the clinging predecessor (our own child)
    _missing = object()
    real_default = inspect.signature(dm.stop_daemon).parameters["timeout"].default
    stops: list = []
    spawned: list = []

    def fake_stop(r, *, timeout=_missing, report=None):
        t = real_default if timeout is _missing else timeout
        stops.append(dm.stop_grace_s() if t is None else t)
        return len(stops) == 1                       # the first stop works; the kick's does not

    monkeypatch.setenv("RMX_STOP_GRACE_S", "7.5")
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dm, "stop_daemon", fake_stop)
    monkeypatch.setattr(dm, "spawn_daemon", lambda *a, **kw: spawned.append(1) or 4242)
    monkeypatch.setattr(dm, "served_identity", lambda r, timeout=1.5: (old.pid, "0.0.0-old"))
    monkeypatch.setattr(dm, "heartbeat_age", lambda r: 120.0)      # stale: the kick is reached
    monkeypatch.setattr(time, "sleep", lambda s: None)
    try:
        r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--standalone", "--relaunch"])
        assert len(stops) == 2, f"the kick never reached _respawn's stop: {stops} {r.output}"
        assert stops[1] == 7.5, f"_respawn stopped with {stops[1]}s, not stop_grace_s()"
        assert spawned == [1], f"_respawn spawned beside a predecessor that did not stop: {spawned}"
        assert r.exit_code != 0
        assert "still alive" in r.output and "did not converge" not in r.output, r.output
    finally:
        old.kill(); old.wait()


# ---- AC-8 (r4 #m-5): a reachable --allow-dev ----------------------------------------------

def test_daemon_launchctl_install_allow_dev_installs_a_dev_tree_plist(root, tmp_path, monkeypatch):
    """AC-8. At HEAD: `No such option: --allow-dev` (exit 2)."""
    dev = _identity_binary(tmp_path, dev_tree=True)
    assert lc.binary_identity(str(dev))["dev_tree"] is True
    monkeypatch.setenv("RMX_BIN", str(dev))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    _fake_launchd(monkeypatch, tmp_path)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "launchctl", "install", "--allow-dev"])
    assert r.exit_code == 0, r.output
    written = tmp_path / "agents" / "x.plist"
    assert plistlib.loads(written.read_bytes())["ProgramArguments"][0] == str(dev)


def test_daemon_launchctl_install_refusal_names_the_cli_flag(root, tmp_path, monkeypatch):
    """AC-8. At HEAD the message says "pass allow_dev to install" — a Python parameter no
    command exposes."""
    dev = _identity_binary(tmp_path, dev_tree=True)
    lc.binary_identity(str(dev))
    monkeypatch.setenv("RMX_BIN", str(dev))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    runs = _fake_launchd(monkeypatch, tmp_path)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "launchctl", "install"])
    assert r.exit_code != 0, r.output
    assert "--allow-dev" in r.output, r.output
    assert runs == [] and not (tmp_path / "agents" / "x.plist").exists()


# ---- AC-9 (r4 #m-6): the session indexer's ExitTimeOut ------------------------------------

def test_session_indexer_plist_carries_the_one_exit_timeout(root, monkeypatch):
    """AC-9. At HEAD the key is absent (launchd's 5 s default)."""
    monkeypatch.setenv("RMX_BIN", _DEPLOYED)
    d = plistlib.loads(slc.render_plist(root))
    assert d.get("ExitTimeOut") == int(lc.EXIT_TIMEOUT_S), d.get("ExitTimeOut")
    assert "EXIT_TIMEOUT_S" in Path(slc.__file__).read_text(), \
        "the session indexer must read launchctl.EXIT_TIMEOUT_S, not carry a second literal"


# ---- AC-10/AC-11 (r4 #s-4): hub.log -----------------------------------------------------------

def _drain_with_marker(root: Path) -> subprocess.Popen:
    p = _draining_process(root, exit_after_term_s=0.5, heartbeat=False)
    dm.pid_path(root).write_text(str(p.pid))
    hb = root / "heartbeat"; hb.touch(); _age(hb, 61)
    os.kill(p.pid, signal.SIGTERM)
    (root / "shutdown.started").touch()
    return p


@pytest.mark.timeout(30)
def test_watchdog_lines_written_by_a_test_land_in_the_sandbox_hub_log(root):
    """AC-10 — GREEN at HEAD by design: task 23.0 closed the pollution half of r4 #s-4 (the
    canary `test_redirect_canary_every_home_derived_path_is_in_the_sandbox` pins `hub_home()`;
    the audit hook refuses the live home). This pins the r4 symptom itself: the marker-wait
    line an UNPATCHED `_log` writes goes to the sandbox hub.log."""
    sandbox = Path(os.environ["RMX_SANDBOX_ROOT"]).resolve()
    log = hub_mod.hub_log_path().resolve()
    assert log.is_relative_to(sandbox), f"hub.log {log} is outside the sandbox {sandbox}"
    p = _drain_with_marker(root)
    try:
        hub_mod.Watchdog()._await_shutdown(root)
    finally:
        if p.poll() is None:
            p.kill(); p.wait()
    lines = [ln for ln in log.read_text().splitlines()
             if f"pid={p.pid} still alive after the grace" in ln]
    assert lines, f"the marker-wait line did not reach the sandbox hub.log {log}"


@pytest.mark.timeout(30)
def test_await_shutdown_line_names_its_root(root, monkeypatch):
    """AC-11. At HEAD it is the one watchdog line without `{root}`: all 8 such lines in the
    live hub.log at r4 were tests, and nothing in them said so."""
    lines: list = []
    monkeypatch.setattr(hub_mod, "_log", lambda m: lines.append(m))
    p = _drain_with_marker(root)
    try:
        hub_mod.Watchdog()._await_shutdown(root)
    finally:
        if p.poll() is None:
            p.kill(); p.wait()
    waits = [m for m in lines if "still alive after the grace and shutting down" in m]
    assert waits, lines
    assert str(root) in waits[0], f"the line names no root: {waits[0]}"
