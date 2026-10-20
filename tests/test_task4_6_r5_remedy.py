"""Task 4.6 (W1-a) — plan-4 round-5 remedy. RED tests; spec
`workflow/plans/plan-4-daemon-resilience-tasks/task-4.6-r5-remedy.md`.

r5 #b-1  `upgrade._default_restart` discards `stop_daemon`'s False, says "daemon stopped",
         returns True beside a live predecessor; its launchd branch is a bare `kickstart -k`
         and two `except Exception: pass` fall through to stopping a SUPERVISED daemon.
         One launchd helper (`launchctl.supervised_restart`) for `daemon restart` and
         `upgrade`; failures reported. Spec addition: `upgrade` restarts a STORE root, not
         the repo it upgraded. (AC-1..AC-7)
r5 #s-1  the daemon plist commands resolve `which rmx`; the hub uses `sys.argv[0]`. One
         resolver (`launchctl._rmx_path`: RMX_BIN, else argv[0], never PATH); restart's
         bug-013 bootstrap goes through `reinstall` and keeps the installed flags. (AC-8..11)
r5 #s-2  `runtime_identity` reads the dev tree's own `.venv-eval` as "not a dev tree". A
         source tree that is not the deploy tree is a dev tree. (AC-12..15)
r5 #s-3  the session-indexer plist has no guard, no check, no reinstall, a bare bootout, and is
         outside `relaunch-fleet`. (AC-16..21)
r5 #m-1  the CLI calls an identity objection "DRIFT" and prescribes the drift fix. (AC-22..25)

Nothing here reaches launchd, a live store or a real venv: launchd is a state machine at the
`subprocess.run` boundary (non-launchctl commands pass through to the real function, so the
identity probe of a fake binary still execs it); binaries are `tests/fake_rmx.py` scripts;
identity trees are tmp directories shaped like venvs; draining daemons and in-flight ticks are
real child processes. Doubles are registered in workflow/test_mock_registry.md.
"""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery
from refmatrix import launchctl as lc
from refmatrix import session_launchctl as slc
from refmatrix import upgrade
from tests.fake_rmx import deploy_tree, identity_binary, script_binary
from tests.test_plan4_remedy_r3 import _draining_process, _launchd_fakes
from tests.test_task4_5_r4_remedy import _fake_launchd
from tests.test_upgrade import _bump, _git, _init_repo


@pytest.fixture
def root():
    base = Path(tempfile.mkdtemp(prefix="rmx46-", dir="/tmp"))
    r = base / "proj" / ".refmatrix"
    r.mkdir(parents=True)
    try:
        yield r
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(autouse=True)
def _fresh_identity_cache(monkeypatch):
    """`binary_identity` caches per path for the life of the process; each test asks afresh
    (`deployed_rmx`, when requested, re-primes its own binary after this)."""
    monkeypatch.setattr(lc, "_IDENTITY_CACHE", {})


_real_run = subprocess.run


class _Launchd:
    """launchd at the `subprocess.run` boundary: `bootstrap`/`load` loads the plist's Label,
    `bootout` unloads it, `print` answers 0 for a loaded label (and `pid = N` for the session
    label while `tick` runs). `calls` records the state-changing verbs with whether the tick
    was alive at that moment. Anything that is not `launchctl` runs for real."""

    def __init__(self, monkeypatch, tmp_path: Path, *, tick: "subprocess.Popen | None" = None):
        self.loaded: set = set()
        self.calls: list = []
        self.tick = tick
        agents = tmp_path / "LaunchAgents"
        agents.mkdir(exist_ok=True)
        self.agents = agents
        monkeypatch.setattr(lc, "LAUNCH_AGENTS_DIR", agents)
        monkeypatch.setattr(slc, "LAUNCH_AGENTS_DIR", agents)    # imported by name
        monkeypatch.setattr(lc, "_migrate_legacy", lambda r: False)
        monkeypatch.setattr(lc, "_loaded_env_drift", lambda r, rendered: [])
        monkeypatch.setattr(lc, "BOOTOUT_WAIT_S", 0.5)
        monkeypatch.setattr(subprocess, "run", self.run)

    def tick_alive(self) -> bool:
        return self.tick is not None and self.tick.poll() is None

    def run(self, argv, *a, **kw):
        argv = [str(x) for x in argv]
        if not argv or argv[0] != "launchctl":
            return _real_run(argv, *a, **kw)
        verb = argv[1]
        if verb == "print":
            label = argv[2].rsplit("/", 1)[-1]
            if label not in self.loaded:
                return subprocess.CompletedProcess(argv, 113, "", "Could not find service")
            out = f"{argv[2]} = {{\n\tstate = running\n"
            if label.startswith(slc.LABEL_PREFIX) and self.tick_alive():
                out += f"\tpid = {self.tick.pid}\n"
            return subprocess.CompletedProcess(argv, 0, out + "}\n", "")
        self.calls.append((verb, self.tick_alive()))
        if verb in ("bootstrap", "load"):
            self.loaded.add(plistlib.loads(Path(argv[-1]).read_bytes())["Label"])
        elif verb == "bootout":
            self.loaded.discard(argv[2].rsplit("/", 1)[-1])
        return subprocess.CompletedProcess(argv, 0, "", "")

    def verbs(self) -> list:
        return [c[0] for c in self.calls]


def _supervised(monkeypatch, *, stopped: bool = True) -> list:
    """The r3 launchd fakes (kickstart / graceful_stop / hub.rpc recorders) plus a
    `launchctl.status` that says the store is loaded."""
    calls = _launchd_fakes(monkeypatch, stopped=stopped)
    monkeypatch.setattr(lc, "status", lambda r: {"label": "l", "plist_path": "p",
                                                  "installed": True, "loaded": True})
    return calls


# ---- AC-1..AC-7 (r5 #b-1): upgrade honours a failed stop; one launchd helper ----------------

@pytest.mark.timeout(60)
def test_upgrade_restart_honours_a_failed_stop_and_never_says_stopped(root, monkeypatch):
    """AC-1, the ledger's probe P4: a real process with a fresh heartbeat that ignores SIGTERM.
    At HEAD `_default_restart` returns True and logs "daemon stopped" while it lives."""
    p = _draining_process(root, exit_after_term_s=0.0, heartbeat=True, ignore_term=True)
    dm.pid_path(root).write_text(str(p.pid))
    monkeypatch.setenv("RMX_STOP_GRACE_S", "1")
    monkeypatch.setattr(lc, "status", lambda r: {"label": "l", "plist_path": "p",
                                                  "installed": False, "loaded": False})
    logs: list = []
    try:
        ok = upgrade._default_restart(root, log=logs.append)
        assert p.poll() is None, "precondition: the predecessor must still be alive"
        assert ok is False, f"reported a restart while pid {p.pid} still serves: {logs}"
        assert not any("daemon stopped" in m for m in logs), logs
        assert any("manually" in m for m in logs), logs
    finally:
        if p.poll() is None:
            p.kill(); p.wait()


def test_upgrade_restart_under_launchd_stops_gracefully_then_kicks(root, monkeypatch):
    """AC-2. At HEAD the launchd branch is a bare `kickstart -k`: no watchdog pause, no
    graceful stop, launchd's SIGKILL at ExitTimeOut for a draining daemon (r3 #b-1)."""
    monkeypatch.setenv("RMX_STOP_GRACE_S", "7.5")
    calls = _supervised(monkeypatch, stopped=True)
    assert upgrade._default_restart(root, log=lambda m: None) is True
    ops = [c[0] for c in calls]
    assert ("graceful_stop", 7.5) in calls, calls
    assert "pause" in ops and "resume" in ops, calls
    assert ops.index("pause") < ops.index("graceful_stop") < ops.index("kickstart") \
        < ops.index("resume"), calls
    assert ("kickstart", False) in calls and ("kickstart", True) not in calls, calls


def test_daemon_restart_and_upgrade_converge_on_one_launchd_helper(root, monkeypatch):
    """AC-3. Both launchd branches call `launchctl.supervised_restart`; at HEAD neither does
    (the CLI inlines the sequence, upgrade hand-rolls a bare kick)."""
    _supervised(monkeypatch, stopped=True)
    used: list = []
    monkeypatch.setattr(lc, "supervised_restart",
                        lambda r, *, log=print: used.append(Path(r)) or ("label", True),
                        raising=False)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart"])
    assert r.exit_code == 0, r.output
    upgrade._default_restart(root, log=lambda m: None)
    assert used == [root, root], f"launchd restarts not routed through the helper: {used}"
    assert "kickstart(" not in Path(upgrade.__file__).read_text(), \
        "upgrade.py still hand-rolls a kickstart"


def _boom_kickstart(r, restart=False):
    raise RuntimeError("launchctl kickstart failed (rc=5): Input/output error")


def test_upgrade_restart_reports_a_kickstart_failure_and_never_stops_a_supervised_daemon(
        root, monkeypatch):
    """AC-4. At HEAD `except Exception: pass` swallows the failure and falls through to
    `stop_daemon` on the supervised daemon (exit 0 -> KeepAlive does not respawn -> bug-013)."""
    _supervised(monkeypatch, stopped=True)
    monkeypatch.setattr(lc, "kickstart", _boom_kickstart)
    stops: list = []
    monkeypatch.setattr(dm, "stop_daemon", lambda r, **kw: stops.append(kw) or True)
    logs: list = []
    ok = upgrade._default_restart(root, log=logs.append)
    assert stops == [], f"fell through to stopping a supervised daemon: {stops}"
    assert ok is False, logs
    assert any("rc=5" in m for m in logs), f"the kickstart error was not reported: {logs}"


def test_daemon_restart_kickstart_failure_never_falls_back_to_a_standalone_spawn(
        root, monkeypatch):
    """AC-5 (spec). At HEAD: "kickstart failed …; restarting standalone" -> stop + spawn of an
    unsupervised daemon beside the loaded label."""
    _supervised(monkeypatch, stopped=True)
    monkeypatch.setattr(lc, "kickstart", _boom_kickstart)
    spawned: list = []
    monkeypatch.setattr(dm, "spawn_daemon", lambda *a, **kw: spawned.append(1) or 4242)
    monkeypatch.setattr(dm, "stop_daemon", lambda r, **kw: True)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart"])
    assert spawned == [], f"spawned an unsupervised daemon beside the label: {r.output}"
    assert r.exit_code != 0, r.output
    assert "--standalone" in r.output and "rc=5" in r.output, r.output


def test_upgrade_restart_reports_a_failed_launchd_probe_and_never_stops(root, monkeypatch):
    """AC-6. At HEAD a raising `launchctl.status` is swallowed and the daemon — possibly a
    supervised one — is stopped."""
    def boom(r):
        raise OSError("launchctl: probe exploded")
    monkeypatch.setattr(lc, "status", boom)
    stops: list = []
    monkeypatch.setattr(dm, "stop_daemon", lambda r, **kw: stops.append(kw) or True)
    logs: list = []
    ok = upgrade._default_restart(root, log=logs.append)
    assert stops == [], f"guessed unsupervised and stopped: {stops}"
    assert ok is False, logs
    assert any("probe exploded" in m for m in logs), logs


def test_daemon_restart_reports_a_failed_launchd_probe_and_never_restarts(root, monkeypatch):
    """AC-6's CLI twin (B1.4 defect class, found in GREEN 9851562): `rmx daemon restart` read a
    raising `launchctl.is_loaded` as `loaded = False`, then stopped a possibly supervised
    daemon and spawned one beside the label. The probe failure is an error naming the deliberate
    override `--standalone`; nothing is stopped or spawned."""
    def boom(r):
        raise OSError("launchctl: probe exploded")
    monkeypatch.setattr(lc, "is_loaded", boom)
    monkeypatch.setattr(sys, "platform", "darwin")
    stops: list = []
    spawned: list = []
    monkeypatch.setattr(dm, "stop_daemon", lambda r, **kw: stops.append(kw) or True)
    monkeypatch.setattr(dm, "graceful_stop", lambda r, **kw: stops.append(kw) or True)
    monkeypatch.setattr(dm, "spawn_daemon", lambda *a, **kw: spawned.append(1) or 4242)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart"])
    assert stops == [] and spawned == [], (stops, spawned, r.output)
    assert r.exit_code != 0, r.output
    assert "probe exploded" in r.output and "--standalone" in r.output, r.output


def _ff_pair(tmp_path: Path) -> "tuple[Path, Path]":
    deploy = tmp_path / "deploy"
    _init_repo(deploy, "0.1.0")
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(deploy), str(dev)], check=True)
    _git(dev, "config", "user.email", "t@t")
    _git(dev, "config", "user.name", "t")
    _bump(dev, "0.2.0")
    return deploy, dev


def test_upgrade_restarts_the_store_root_it_is_given(tmp_path, deployed_rmx):
    """AC-7 (spec #b1-root). At HEAD `upgrade` has no `store_root`: TypeError."""
    deploy, dev = _ff_pair(tmp_path)
    store = tmp_path / "proj" / ".refmatrix"; store.mkdir(parents=True)
    seen: list = []
    res = upgrade.upgrade(root=deploy, from_dev=dev, install_fn=lambda r, log=print: None,
                          restart_fn=lambda r, log=print: seen.append(Path(r)) or True,
                          store_root=store, log=lambda m: None)
    assert seen == [store], seen
    assert res.restarted is True


def test_upgrade_without_a_store_root_restarts_nothing(tmp_path, deployed_rmx):
    """AC-7. At HEAD `restart_fn` gets the REPO root (`~/refmatrix`): a path that is no store,
    whose `stop_daemon` finds no pid and returns True — `restarted=True`, nothing restarted."""
    deploy, dev = _ff_pair(tmp_path)
    seen: list = []
    logs: list = []
    res = upgrade.upgrade(root=deploy, from_dev=dev, install_fn=lambda r, log=print: None,
                          restart_fn=lambda r, log=print: seen.append(Path(r)) or True,
                          log=logs.append)
    assert seen == [], f"restart_fn was handed a non-store root: {seen}"
    assert res.restarted is False
    assert any("manually" in m for m in logs), logs


def test_upgrade_cli_passes_the_active_store(root, monkeypatch):
    """AC-7. `rmx upgrade` hands `_root()` to `upgrade(store_root=)`."""
    got: dict = {}
    monkeypatch.setattr(upgrade, "upgrade", lambda **kw: got.update(kw))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["upgrade"])
    assert r.exit_code == 0, r.output
    assert got.get("store_root") == root, got


# ---- AC-8..AC-11 (r5 #s-1): one binary resolver ------------------------------------------

def _two_binaries(tmp_path: Path, monkeypatch, *, ran_dev: bool) -> "tuple[Path, Path]":
    """The r5 P1 probe: the operator RAN `ran`; `which rmx` finds `onpath`; one is a dev tree.
    Both identities are primed before any `subprocess.run` fake."""
    ran = identity_binary(tmp_path, dev_tree=ran_dev, name="ran")
    onpath = identity_binary(tmp_path, dev_tree=not ran_dev, name="onpath")
    for b in (ran, onpath):
        lc.binary_identity(str(b))
    monkeypatch.delenv("RMX_BIN", raising=False)
    monkeypatch.setenv("PATH", f"{onpath.parent}:/usr/bin:/bin")
    monkeypatch.setattr(sys, "argv", [str(ran), "daemon", "launchctl", "install"])
    assert shutil.which("rmx") == str(onpath)
    return ran, onpath


def test_rmx_path_never_falls_back_to_the_rmx_on_path(tmp_path, monkeypatch):
    """AC-8. At HEAD `_rmx_path()` returns `which rmx` — a binary nobody ran."""
    onpath = identity_binary(tmp_path, dev_tree=True, name="onpath")
    monkeypatch.delenv("RMX_BIN", raising=False)
    monkeypatch.setenv("PATH", f"{onpath.parent}:/usr/bin:/bin")
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "bin" / "python3"), "-m", "pytest"])
    with pytest.raises(FileNotFoundError) as ei:
        lc._rmx_path()
    assert "RMX_BIN" in str(ei.value), str(ei.value)


def test_rmx_path_is_the_binary_this_invocation_ran(tmp_path, monkeypatch):
    """AC-8. RMX_BIN, else argv[0]. At HEAD: `which rmx` (onpath)."""
    ran, onpath = _two_binaries(tmp_path, monkeypatch, ran_dev=False)
    assert lc._rmx_path() == str(ran)
    monkeypatch.setenv("RMX_BIN", "/explicit/bin/rmx")
    assert lc._rmx_path() == "/explicit/bin/rmx"


def test_daemon_launchctl_install_renders_the_binary_the_operator_ran(root, tmp_path, monkeypatch):
    """AC-9. At HEAD: `refusing to render a plist: …/onpath/rmx is a dev tree` (exit 1)."""
    ran, onpath = _two_binaries(tmp_path, monkeypatch, ran_dev=False)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    _fake_launchd(monkeypatch, tmp_path)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "launchctl", "install"])
    assert r.exit_code == 0, r.output
    written = plistlib.loads((tmp_path / "agents" / "x.plist").read_bytes())
    assert written["ProgramArguments"][0] == str(ran), written["ProgramArguments"]


def test_daemon_launchctl_install_check_checks_the_binary_the_operator_ran(
        root, tmp_path, monkeypatch):
    """AC-9. At HEAD: `plist DRIFT …/onpath/rmx is a dev tree` (exit 1) against a plist that
    is in sync with the binary actually run."""
    ran, onpath = _two_binaries(tmp_path, monkeypatch, ran_dev=False)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    _fake_launchd(monkeypatch, tmp_path, loaded=True)
    installed = tmp_path / "agents" / "x.plist"
    installed.parent.mkdir(parents=True, exist_ok=True)
    installed.write_bytes(lc.render_plist(root, rmx=str(ran)))
    r = CliRunner().invoke(cli_mod.main, ["daemon", "launchctl", "install", "--check"])
    assert r.exit_code == 0, r.output
    assert "in sync" in r.output, r.output


def test_daemon_launchctl_install_allow_dev_installs_the_binary_the_operator_ran(
        root, tmp_path, monkeypatch):
    """AC-9. At HEAD `--allow-dev` writes `which rmx` (onpath), not the dev binary run."""
    ran, onpath = _two_binaries(tmp_path, monkeypatch, ran_dev=True)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    _fake_launchd(monkeypatch, tmp_path)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "launchctl", "install", "--allow-dev"])
    assert r.exit_code == 0, r.output
    written = plistlib.loads((tmp_path / "agents" / "x.plist").read_bytes())
    assert written["ProgramArguments"][0] == str(ran), written["ProgramArguments"]


def test_hub_check_and_relaunch_fleet_resolve_through_the_one_resolver(
        root, tmp_path, monkeypatch, deployed_rmx):
    """AC-10. At HEAD both read `sys.argv[0]` directly and ignore RMX_BIN."""
    argv0 = identity_binary(tmp_path, dev_tree=False, name="argv0")
    lc.binary_identity(str(argv0))
    monkeypatch.setattr(sys, "argv", [str(argv0), "hub"])
    seen: list = []
    monkeypatch.setattr(lc, "check_hub",
                        lambda *, rmx=None, **kw: seen.append(("hub", rmx)) or (True, ""))
    r = CliRunner().invoke(cli_mod.main, ["hub", "launchctl", "install", "--check"])
    assert r.exit_code == 0, r.output
    monkeypatch.setattr(discovery, "discover_roots", lambda: [root])
    monkeypatch.setattr(lc, "is_loaded", lambda r: True)
    monkeypatch.setattr(lc, "check", lambda r, *, rmx=None: seen.append(("daemon", rmx)) or (True, ""))
    monkeypatch.setattr(slc, "is_installed", lambda r: False)
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, "relaunch verified pid 1->2", ""))
    r = CliRunner().invoke(cli_mod.main, ["hub", "relaunch-fleet"])
    assert r.exit_code == 0, r.output
    assert seen == [("hub", str(deployed_rmx)), ("daemon", str(deployed_rmx))], seen


def test_restart_bootstrap_reinstalls_with_the_installed_flags_and_the_binary_run(
        root, tmp_path, monkeypatch):
    """AC-11, bug-013 state (plist installed, label not loaded). At HEAD the bootstrap is
    `lc.install(root)`: default flags and `which rmx` — here a dev tree, so it is refused."""
    ran, onpath = _two_binaries(tmp_path, monkeypatch, ran_dev=False)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    ld = _Launchd(monkeypatch, tmp_path)
    p = lc.plist_path(root)
    p.write_bytes(lc.render_plist(root, rmx=str(ran), watch=False, debounce_ms=900))
    assert lc.is_installed(root) and not lc.is_loaded(root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart"])
    assert r.exit_code == 0, r.output
    assert "bootstrapped" in r.output, r.output
    args = plistlib.loads(p.read_bytes())["ProgramArguments"]
    assert args[0] == str(ran), args
    assert "--no-watch" in args and args[args.index("--debounce-ms") + 1] == "900", args
    assert "bootstrap" in ld.verbs(), ld.calls


# ---- AC-12..AC-15 (r5 #s-2): the dev venv reads as a dev tree ---------------------------

def _init(tree: Path) -> Path:
    return tree / "src" / "refmatrix" / "__init__.py"


def test_the_dev_trees_own_venv_eval_is_a_dev_tree(tmp_path, monkeypatch):
    """AC-12. The workstation shape: `<dev>/.venv-eval` editable -> `<dev>/src`, with a separate
    deploy tree. At HEAD venv tree == code tree, so `dev_tree` is False."""
    deploy = deploy_tree(tmp_path, "deploy")
    dev = deploy_tree(tmp_path, "dev", prefix=".venv-eval")
    monkeypatch.setenv("RMX_DEPLOY_ROOT", str(deploy))
    ident = upgrade.runtime_identity(prefix=dev / ".venv-eval", import_file=_init(dev))
    assert ident["dev_tree"] is True, ident
    assert ident.get("dev_reason") == "not-deploy-tree", ident
    assert ident.get("deploy_root") == deploy.resolve(), ident


def test_the_deploy_trees_own_venv_is_not_a_dev_tree(tmp_path, monkeypatch):
    """AC-13 control (GREEN at HEAD): the guard must keep passing the deploy."""
    deploy = deploy_tree(tmp_path, "deploy")
    monkeypatch.setenv("RMX_DEPLOY_ROOT", str(deploy))
    ident = upgrade.runtime_identity(prefix=deploy / ".venv", import_file=_init(deploy))
    assert ident["dev_tree"] is False, ident


def test_the_deploy_root_defaults_to_home_refmatrix(tmp_path, monkeypatch):
    """AC-13. With RMX_DEPLOY_ROOT unset, `~/refmatrix` is the deploy tree. At HEAD the dev
    shape reads clean."""
    home = tmp_path / "home"
    deploy = deploy_tree(home, "refmatrix")
    dev = deploy_tree(tmp_path, "dev", prefix=".venv-eval")
    monkeypatch.delenv("RMX_DEPLOY_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(home))
    assert upgrade.runtime_identity(prefix=deploy / ".venv",
                                    import_file=_init(deploy))["dev_tree"] is False
    ident = upgrade.runtime_identity(prefix=dev / ".venv-eval", import_file=_init(dev))
    assert ident["dev_tree"] is True, ident


def test_no_deploy_tree_fails_closed_for_a_source_tree(tmp_path, monkeypatch):
    """AC-14. No deploy tree exists: a tree-backed editable install is a dev tree (the sandbox
    has no `~/refmatrix`, so every tree classifies alike — M2's goal). At HEAD: False."""
    tree = deploy_tree(tmp_path, "checkout")
    monkeypatch.setenv("RMX_DEPLOY_ROOT", str(tmp_path / "nowhere"))
    ident = upgrade.runtime_identity(prefix=tree / ".venv", import_file=_init(tree))
    assert ident["dev_tree"] is True, ident
    assert ident.get("dev_reason") == "no-deploy-tree", ident
    assert "deploy_root" in ident and ident["deploy_root"] is None, ident


def test_a_wheel_install_is_never_a_dev_tree(tmp_path, monkeypatch):
    """AC-14 control (GREEN at HEAD): a pipx-shaped wheel install has no tree to confuse."""
    prefix = tmp_path / "pipx" / "venvs" / "refmatrix"
    pkg = prefix / "lib" / "python3.14" / "site-packages" / "refmatrix"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "0.0.0"\n')
    monkeypatch.setenv("RMX_DEPLOY_ROOT", str(tmp_path / "nowhere"))
    ident = upgrade.runtime_identity(prefix=prefix, import_file=pkg / "__init__.py")
    assert ident["dev_tree"] is False, ident


def _as_dev_interpreter(tmp_path: Path, monkeypatch) -> Path:
    """`upgrade.runtime_identity` -> the REAL classifier on a tmp dev shape (never the test
    interpreter's own venv). Returns the deploy tree."""
    deploy = deploy_tree(tmp_path, "deploy")
    dev = deploy_tree(tmp_path, "dev", prefix=".venv-eval")
    monkeypatch.setenv("RMX_DEPLOY_ROOT", str(deploy))
    real = upgrade.runtime_identity
    monkeypatch.setattr(upgrade, "runtime_identity",
                        lambda **kw: real(prefix=dev / ".venv-eval", import_file=_init(dev)))
    return deploy


def test_upgrade_refusal_names_the_deploy_root(tmp_path, monkeypatch):
    """AC-15. At HEAD the dev venv passes the guard and `upgrade` reaches git."""
    deploy = _as_dev_interpreter(tmp_path, monkeypatch)
    with pytest.raises(upgrade.UpgradeError) as ei:
        upgrade.upgrade(root=deploy, check=True, log=lambda m: None)
    msg = str(ei.value)
    assert "RMX_DEPLOY_ROOT" in msg, msg
    assert str(deploy.resolve()) in msg or str(deploy) in msg, msg


def test_version_json_carries_the_deploy_root_and_reason(tmp_path, monkeypatch):
    """AC-15. `rmx version -v --json` is what `binary_identity` reads before a plist render."""
    deploy = _as_dev_interpreter(tmp_path, monkeypatch)
    out = CliRunner().invoke(cli_mod.main, ["version", "-v", "--json"]).output
    d = json.loads(out.strip().splitlines()[-1])
    assert d["dev_tree"] is True, d
    assert d.get("dev_reason") == "not-deploy-tree", d
    assert d.get("deploy_root") == str(deploy.resolve()), d


# ---- AC-16..AC-21 (r5 #s-3): the session indexer joins the plist lifecycle -------------

def _session_plist(root: Path, *, exit_timeout: bool = True, **flags) -> Path:
    """Write the session plist rendered for `$RMX_BIN` (optionally WITHOUT ExitTimeOut —
    the 0/6 installed labels' shape)."""
    d = plistlib.loads(slc.render_plist(root, **flags))
    if not exit_timeout:
        d.pop("ExitTimeOut", None)
    p = slc.plist_path(root)
    p.write_bytes(plistlib.dumps(d))
    return p


_UNVERIFIED = {
    "dev": lambda t: identity_binary(t, dev_tree=True),
    "unknown": lambda t: script_binary(t, "old", "echo 'rmx 0.68.0'"),
}


@pytest.mark.parametrize("kind", sorted(_UNVERIFIED))
def test_session_install_refuses_a_binary_that_is_not_verified(kind, root, tmp_path, monkeypatch):
    """AC-16. At HEAD there is no guard: the plist is written and bootstrapped."""
    b = _UNVERIFIED[kind](tmp_path)
    lc.binary_identity(str(b))
    monkeypatch.setenv("RMX_BIN", str(b))
    ld = _Launchd(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="dev tree|identity unknown"):
        slc.install(root)
    assert not slc.plist_path(root).exists(), "plist written before the refusal"
    assert ld.calls == [], f"launchctl called before the refusal: {ld.calls}"


def test_session_install_allow_dev_installs_a_dev_binary(root, tmp_path, monkeypatch):
    """AC-16. At HEAD: TypeError — no `rmx=` / `allow_dev=`."""
    dev = identity_binary(tmp_path, dev_tree=True)
    lc.binary_identity(str(dev))
    _Launchd(monkeypatch, tmp_path)
    p = slc.install(root, rmx=str(dev), allow_dev=True)
    assert plistlib.loads(p.read_bytes())["ProgramArguments"][0] == str(dev)


def test_session_check_reports_a_label_without_exit_timeout(root, tmp_path, monkeypatch,
                                                            deployed_rmx):
    """AC-17. At HEAD `session_launchctl.check` does not exist."""
    ld = _Launchd(monkeypatch, tmp_path)
    _session_plist(root, exit_timeout=False)
    ld.loaded.add(slc.label_for_root(root))
    ok, why = slc.check(root)
    assert ok is False
    assert "ExitTimeOut" in why, why
    assert getattr(why, "kind", None) == "drift", why


def test_session_check_keeps_the_installed_flags_and_sees_an_unloaded_label(
        root, tmp_path, monkeypatch, deployed_rmx):
    """AC-17. A `--interval 120 --all-projects` install is in sync; unloaded is not."""
    ld = _Launchd(monkeypatch, tmp_path)
    _session_plist(root, interval_seconds=120, all_projects=True)
    ok, why = slc.check(root)
    assert ok is False and "not loaded" in why, why
    ld.loaded.add(slc.label_for_root(root))
    ok, why = slc.check(root)
    assert ok is True, why


def test_session_check_calls_a_dev_binary_an_identity_objection(root, tmp_path, monkeypatch,
                                                                deployed_rmx):
    """AC-17 + M1."""
    dev = identity_binary(tmp_path, dev_tree=True, name="dev")
    lc.binary_identity(str(dev))
    ld = _Launchd(monkeypatch, tmp_path)
    _session_plist(root)
    ld.loaded.add(slc.label_for_root(root))
    ok, why = slc.check(root, rmx=str(dev))
    assert ok is False
    assert getattr(why, "kind", None) == "identity", why
    assert "drifted" not in why, why


@pytest.mark.timeout(60)
def test_session_force_install_waits_for_the_in_flight_tick_before_the_bootout(
        root, tmp_path, monkeypatch, deployed_rmx):
    """AC-18. At HEAD the bootout runs at once, under the OLD plist's 5 s ExitTimeOut, while
    the ingest tick is mid-write."""
    tick = subprocess.Popen(["sleep", "1.5"])
    try:
        ld = _Launchd(monkeypatch, tmp_path, tick=tick)
        _session_plist(root, exit_timeout=False)
        ld.loaded.add(slc.label_for_root(root))
        monkeypatch.setenv("RMX_STOP_GRACE_S", "20")
        slc.install(root, force=True)
        bootouts = [c for c in ld.calls if c[0] == "bootout"]
        assert bootouts, ld.calls
        assert bootouts[0][1] is False, f"booted out while tick pid {tick.pid} was running"
        assert "ExitTimeOut" in plistlib.loads(slc.plist_path(root).read_bytes())
    finally:
        if tick.poll() is None:
            tick.kill(); tick.wait()


@pytest.mark.timeout(60)
def test_session_force_install_refuses_while_a_tick_outlives_the_grace(
        root, tmp_path, monkeypatch, deployed_rmx):
    """AC-18. At HEAD: no refusal; the running tick is booted out."""
    tick = subprocess.Popen(["sleep", "60"])
    try:
        ld = _Launchd(monkeypatch, tmp_path, tick=tick)
        p = _session_plist(root, exit_timeout=False)
        before = p.read_bytes()
        ld.loaded.add(slc.label_for_root(root))
        monkeypatch.setenv("RMX_STOP_GRACE_S", "0.5")
        with pytest.raises(RuntimeError, match="still running"):
            slc.install(root, force=True)
        assert "bootout" not in ld.verbs(), ld.calls
        assert p.read_bytes() == before, "the plist was rewritten under a running tick"
    finally:
        tick.kill(); tick.wait()


def test_session_reinstall_rerenders_with_the_installed_flags(root, tmp_path, monkeypatch,
                                                              deployed_rmx):
    """AC-19. At HEAD `session_launchctl.reinstall` does not exist."""
    ld = _Launchd(monkeypatch, tmp_path)
    p = _session_plist(root, exit_timeout=False, interval_seconds=120, all_projects=True)
    ld.loaded.add(slc.label_for_root(root))
    slc.reinstall(root)
    d = plistlib.loads(p.read_bytes())
    assert d.get("ExitTimeOut") == int(lc.EXIT_TIMEOUT_S), d
    assert d["StartInterval"] == 120 and "--all-projects" in d["ProgramArguments"], d
    assert slc.check(root)[0] is True


def test_relaunch_fleet_reinstalls_drifted_session_plists(tmp_path, monkeypatch, deployed_rmx):
    """AC-20. Supervised daemon or not, a drifted session plist is reinstalled. At HEAD
    `relaunch-fleet` never looks at a session plist."""
    a = tmp_path / "a" / ".refmatrix"; b = tmp_path / "b" / ".refmatrix"
    for r in (a, b):
        r.mkdir(parents=True)
    monkeypatch.setattr(discovery, "discover_roots", lambda: [a, b])
    monkeypatch.setattr(lc, "is_loaded", lambda r: Path(r) == a)
    monkeypatch.setattr(lc, "check", lambda r, **kw: (True, ""))
    monkeypatch.setattr(slc, "is_installed", lambda r: True)
    monkeypatch.setattr(slc, "check", lambda r, **kw: (
        False, "ExitTimeOut: installed None != rendered 45"), raising=False)
    seen: list = []
    monkeypatch.setattr(slc, "reinstall", lambda r, **kw: seen.append((Path(r), kw.get("rmx")))
                        or slc.plist_path(r), raising=False)
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, "relaunch verified pid 1->2", ""))
    r = CliRunner().invoke(cli_mod.main, ["hub", "relaunch-fleet"])
    assert r.exit_code == 0, r.output
    assert sorted(seen) == sorted([(a, str(deployed_rmx)), (b, str(deployed_rmx))]), seen
    assert "session-indexer" in r.output, r.output


def test_session_launchctl_install_check_names_exit_timeout(root, tmp_path, monkeypatch,
                                                            deployed_rmx):
    """AC-21. At HEAD: `No such option: --check` (exit 2)."""
    ld = _Launchd(monkeypatch, tmp_path)
    p = _session_plist(root, exit_timeout=False)
    before = p.read_bytes()
    ld.loaded.add(slc.label_for_root(root))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["session", "launchctl", "install", "--check"])
    assert r.exit_code == 1, r.output
    assert "ExitTimeOut" in r.output, r.output
    assert p.read_bytes() == before and ld.calls == [], ld.calls


# ---- AC-22..AC-25 (r5 #m-1): an identity objection is not drift -----------------------

def test_check_reasons_are_typed(root, tmp_path, monkeypatch, deployed_rmx):
    """AC-22. At HEAD `why` is a bare str: no `.kind`."""
    dev = identity_binary(tmp_path, dev_tree=True, name="dev")
    lc.binary_identity(str(dev))
    installed = tmp_path / "installed.plist"
    installed.write_bytes(lc.render_plist(root))
    monkeypatch.setattr(lc, "plist_path", lambda r: installed)
    monkeypatch.setattr(lc, "is_loaded", lambda r: True)
    monkeypatch.setattr(lc, "_loaded_env_drift", lambda r, rendered: [])
    ok, why = lc.check(root, rmx=str(dev))
    assert ok is False and getattr(why, "kind", None) == "identity", why
    d = plistlib.loads(installed.read_bytes())
    del d["EnvironmentVariables"]["RMX_SUPERVISED"]
    installed.write_bytes(plistlib.dumps(d))
    ok, why = lc.check(root)
    assert ok is False and getattr(why, "kind", None) == "drift", why
    hub_plist = tmp_path / "hub.plist"
    hub_plist.write_bytes(lc.render_hub_plist())
    monkeypatch.setattr(lc, "hub_plist_path", lambda: hub_plist)
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: True)
    ok, why = lc.check_hub(rmx=str(dev))
    assert ok is False and getattr(why, "kind", None) == "identity", why


def test_daemon_install_check_calls_an_identity_objection_not_drift(root, tmp_path, monkeypatch):
    """AC-23. At HEAD: `plist DRIFT …` + `fix: rmx daemon launchctl install --force (or rmx hub
    relaunch-fleet)` — both prescribed fixes refuse this binary."""
    dev = identity_binary(tmp_path, dev_tree=True)
    lc.binary_identity(str(dev))
    monkeypatch.setenv("RMX_BIN", str(dev))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "launchctl", "install", "--check"])
    assert r.exit_code == 1, r.output
    assert "not verified" in r.output, r.output
    assert "DRIFT" not in r.output, r.output
    assert "install --force" not in r.output and "relaunch-fleet" not in r.output, r.output


def test_hub_launchctl_status_calls_an_identity_objection_not_drift(tmp_path, monkeypatch):
    """AC-24. At HEAD: `plist drift — … is a dev tree …`."""
    dev = identity_binary(tmp_path, dev_tree=True)
    lc.binary_identity(str(dev))
    monkeypatch.setenv("RMX_BIN", str(dev))
    monkeypatch.setattr(sys, "argv", [str(dev), "hub", "launchctl", "status"])
    monkeypatch.setattr(lc, "hub_status", lambda: {
        "label": lc.HUB_LABEL, "plist_path": str(tmp_path / "hub.plist"),
        "installed": True, "loaded": True})
    r = CliRunner().invoke(cli_mod.main, ["hub", "launchctl", "status"])
    assert "plist drift" not in r.output, r.output
    assert "not verified" in r.output, r.output


def test_relaunch_fleet_refuses_an_unverified_binary_once_and_touches_no_store(
        tmp_path, monkeypatch):
    """AC-25. At HEAD the identity objection reads as drift: `reinstall` runs (and would
    refuse, relaying `--allow-dev`, a flag relaunch-fleet does not have) and every store's
    daemon is restarted with the unverified binary."""
    dev = identity_binary(tmp_path, dev_tree=True)
    lc.binary_identity(str(dev))
    a = tmp_path / "a" / ".refmatrix"; a.mkdir(parents=True)
    monkeypatch.setattr(discovery, "discover_roots", lambda: [a])
    monkeypatch.setattr(lc, "is_loaded", lambda r: True)
    monkeypatch.setattr(slc, "is_installed", lambda r: False)
    reinstalls: list = []
    monkeypatch.setattr(lc, "reinstall", lambda r, **kw: reinstalls.append(r) or lc.plist_path(r))
    restarts: list = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: restarts.append(list(argv))
                        or subprocess.CompletedProcess(argv, 0, "relaunch verified", ""))
    r = CliRunner().invoke(cli_mod.main, ["hub", "relaunch-fleet", "--rmx", str(dev)])
    assert reinstalls == [] and restarts == [], (reinstalls, restarts, r.output)
    assert r.exit_code == 1, r.output
    assert "not verified" in r.output, r.output
    assert "--allow-dev" not in r.output and "drift" not in r.output.lower(), r.output


# ==== r6 amendment (ch-bsd plan-4 r6, a710e48): spec #r6-amend, AC-28..AC-35 ===============

def _clear_rmx_bin(monkeypatch) -> None:
    """Unset RMX_BIN in a way monkeypatch UNDOES: `export_service_binary` writes os.environ
    directly, and a bare `delenv` of an absent var records nothing to restore."""
    monkeypatch.setenv("RMX_BIN", "placeholder")
    monkeypatch.delenv("RMX_BIN")


def _service_binary(tmp_path: Path, monkeypatch) -> Path:
    """A deployed-identity `rmx` this process 'was started as' (argv[0]), RMX_BIN unset."""
    b = identity_binary(tmp_path, dev_tree=False, name="svc")
    lc.binary_identity(str(b))
    _clear_rmx_bin(monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(b), "hub", "start", "--no-detach"])
    return b


def test_export_service_binary_exports_the_binary_the_service_runs(tmp_path, monkeypatch):
    """AC-28. At HEAD: no such function."""
    b = _service_binary(tmp_path, monkeypatch)
    assert lc.export_service_binary() == str(b)
    assert os.environ.get("RMX_BIN") == str(b)
    monkeypatch.setenv("RMX_BIN", "/explicit/bin/rmx")
    assert lc.export_service_binary() == "/explicit/bin/rmx"
    assert os.environ["RMX_BIN"] == "/explicit/bin/rmx", "an operator's RMX_BIN was overwritten"


def test_export_service_binary_never_raises_for_a_module_run_process(tmp_path, monkeypatch):
    """AC-28. A service started as `python -m refmatrix.cli` cannot name its binary: it says
    so (log) and starts anyway. At HEAD: no such function."""
    _clear_rmx_bin(monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(Path(cli_mod.__file__)), "hub", "start"])
    logs: list = []
    assert lc.export_service_binary(log=logs.append) is None
    assert "RMX_BIN" not in os.environ
    assert logs and "RMX_BIN" in logs[0], logs


def test_hub_and_daemon_start_export_their_binary_before_serving(root, tmp_path, monkeypatch):
    """AC-29. The launchd ProgramArguments are `~/bin/rmx hub|daemon start --no-detach`; by the
    time the service runs, every child it spawns would inherit RMX_BIN. At HEAD: None."""
    from refmatrix import hub as hub_mod
    b = _service_binary(tmp_path, monkeypatch)
    seen: dict = {}
    monkeypatch.setattr(hub_mod.Hub, "run",
                        lambda self, **kw: seen.__setitem__("hub", os.environ.get("RMX_BIN")))
    r = CliRunner().invoke(cli_mod.main, ["hub", "start", "--no-detach", "--no-http"])
    assert r.exit_code == 0, r.output
    _clear_rmx_bin(monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(b), "daemon", "start", "--no-detach"])
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dm, "serve_foreground",
                        lambda r, **kw: seen.__setitem__("daemon", os.environ.get("RMX_BIN")))
    r = CliRunner().invoke(cli_mod.main, ["daemon", "start", "--no-detach"])
    assert r.exit_code == 0, r.output
    assert seen == {"hub": str(b), "daemon": str(b)}, seen


@pytest.mark.timeout(180)
def test_hub_ui_supervise_installs_a_plist_naming_the_hubs_binary(tmp_path, monkeypatch):
    """AC-30, the r6 #b-1 path: the Projects tab's "supervise (launchd)" runs
    `python -m refmatrix.cli daemon launchctl install`, whose argv[0] is cli.py. At HEAD the
    child env carries no RMX_BIN and the resolver refuses (`cannot tell which rmx`)."""
    from fastapi.testclient import TestClient
    from refmatrix import hub as hub_mod
    from refmatrix.ui import server as srv
    b = _service_binary(tmp_path, monkeypatch)
    # the hub process starts as the binary (export happens at `rmx hub start`)
    monkeypatch.setattr(hub_mod.Hub, "run", lambda self, **kw: None)
    assert CliRunner().invoke(cli_mod.main, ["hub", "start", "--no-detach", "--no-http"]).exit_code == 0
    proj = Path(tempfile.mkdtemp(prefix="rmx46ui-", dir="/tmp"))
    try:
        children: list = []

        def fake_run(argv, *a, **kw):
            argv = [str(x) for x in argv]
            if argv[:3] == [sys.executable, "-m", "refmatrix.cli"]:
                children.append((argv, dict(kw.get("env") or os.environ), kw.get("cwd")))
                return subprocess.CompletedProcess(argv, 0, "ok", "")
            return _real_run(argv, *a, **kw)
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(discovery, "discover_roots", lambda: [])
        monkeypatch.setattr(discovery, "all_projects", lambda with_footprint=True: [])
        monkeypatch.setattr(discovery, "register_root", lambda r: None)
        resp = TestClient(srv.create_app(hub_mod.Hub(port=0))).post(
            "/api/projects/init", json={"path": str(proj), "hooks": False, "launchd": True})
        assert resp.status_code == 200, resp.text
        sup = [c for c in children if c[0][3:] == ["daemon", "launchctl", "install"]]
        assert sup, children
        argv, env, cwd = sup[0]
        assert env.get("RMX_BIN") == str(b), f"the supervise child gets no binary: {env.get('RMX_BIN')}"
        monkeypatch.setattr(subprocess, "run", _real_run)

        # Replay that child in-process, as it runs: argv[0] = cli.py, the env it was handed.
        store = proj / ".refmatrix"; store.mkdir(exist_ok=True)
        monkeypatch.setattr(sys, "argv", [str(Path(cli_mod.__file__)), *argv[3:]])
        for k in ("RMX_BIN",):
            monkeypatch.setenv(k, env[k])
        monkeypatch.setattr(cli_mod, "_root", lambda: store)
        ld = _Launchd(monkeypatch, tmp_path)
        r = CliRunner().invoke(cli_mod.main, argv[3:])
        assert r.exit_code == 0, r.output
        written = plistlib.loads(lc.plist_path(store).read_bytes())
        assert written["ProgramArguments"][0] == str(b), written["ProgramArguments"]
        assert "bootstrap" in ld.verbs(), ld.calls
        monkeypatch.setattr(subprocess, "run", _real_run)

        # A REAL `-m refmatrix.cli` child with that env resolves the binary (read-only --check).
        real = _real_run([sys.executable, "-m", "refmatrix.cli", "daemon", "launchctl",
                          "install", "--check"], cwd=str(proj), env={**env},
                         capture_output=True, text=True, timeout=120)
        out = real.stdout + real.stderr
        assert "cannot tell which rmx" not in out, out
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_supervised_restart_runs_the_verify_inside_the_pause(root, monkeypatch):
    """AC-31. At HEAD: TypeError — no `after_kick`; the verify ran after the resume."""
    calls = _launchd_fakes(monkeypatch, stopped=True)
    lc.supervised_restart(root, log=lambda m: None,
                          after_kick=lambda: calls.append(("verify", None)))
    ops = [c[0] for c in calls]
    assert ops.index("pause") < ops.index("graceful_stop") < ops.index("kickstart") \
        < ops.index("verify") < ops.index("resume"), calls


def test_supervised_restart_resumes_when_the_verify_raises(root, monkeypatch):
    """AC-31. At HEAD: TypeError — no `after_kick`."""
    calls = _launchd_fakes(monkeypatch, stopped=True)

    class _VerifyFailed(Exception):
        pass

    def verify():
        calls.append(("verify", None))
        raise _VerifyFailed("relaunch did not converge")
    with pytest.raises(_VerifyFailed):
        lc.supervised_restart(root, log=lambda m: None, after_kick=verify)
    ops = [c[0] for c in calls]
    assert ops.index("verify") < ops.index("resume"), calls


def test_daemon_restart_relaunch_verifies_before_the_watchdog_resumes(root, monkeypatch,
                                                                     deployed_rmx):
    """AC-31, the r6 probe: at HEAD the order is pause, graceful_stop, kickstart, RESUME,
    verify — the relaunch window r3 #s-3 paused the watchdog for is unpaused."""
    from refmatrix import __version__
    calls = _launchd_fakes(monkeypatch, stopped=True)
    mine = str(upgrade.runtime_identity()["import_path"])

    def served(r, timeout=2.0):
        calls.append(("verify", None))
        return (777, __version__) if any(c[0] == "kickstart" for c in calls) else None
    monkeypatch.setattr(dm, "served_identity", served)
    monkeypatch.setattr(dm, "call", lambda r, op, args=None, *, timeout=60.0, retries=2:
                        {"ok": True, "result": {"code_path": mine, "dev_tree": False, "pid": 777}})
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch"])
    assert r.exit_code == 0, r.output
    ops = [c[0] for c in calls]
    last_verify = len(ops) - 1 - ops[::-1].index("verify")
    assert ops.index("kickstart") < last_verify < ops.index("resume"), calls


@pytest.mark.parametrize("fails", ["kickstart", "graceful_stop"])
def test_upgrade_restart_resumes_the_watchdog_on_every_failure(fails, root, monkeypatch):
    """AC-32, kills mutant M4 (resume moved out of the `finally`). GREEN at HEAD by design."""
    calls = _supervised(monkeypatch, stopped=True)
    if fails == "kickstart":
        monkeypatch.setattr(lc, "kickstart", _boom_kickstart)
    else:
        def boom(r, *, grace, report=None):
            calls.append(("graceful_stop", grace))
            raise OSError("stop op exploded")
        monkeypatch.setattr(dm, "graceful_stop", boom)
    assert upgrade._default_restart(root, log=lambda m: None) is False
    assert "resume" in [c[0] for c in calls], f"watchdog left paused after a {fails} failure: {calls}"


def test_session_force_install_raises_when_the_bootout_does_not_unload(root, tmp_path, monkeypatch,
                                                                      deployed_rmx):
    """AC-33, kills mutant M10 (the unload wait dropped). GREEN at HEAD by design."""
    ld = _Launchd(monkeypatch, tmp_path)
    p = _session_plist(root, exit_timeout=False)
    before = p.read_bytes()
    label = slc.label_for_root(root)
    ld.loaded.add(label)
    real = ld.run

    def sticky(argv, *a, **kw):
        out = real(argv, *a, **kw)
        if [str(x) for x in argv][:2] == ["launchctl", "bootout"]:
            ld.loaded.add(label)            # the old job is still draining: still loaded
        return out
    monkeypatch.setattr(subprocess, "run", sticky)
    with pytest.raises(RuntimeError, match="did not unload"):
        slc.install(root, force=True)
    assert p.read_bytes() == before, "the plist was rewritten under a still-loaded label"
    assert "bootstrap" not in ld.verbs(), ld.calls


def _dev_ident() -> dict:
    return {"version": "9.9.9", "import_path": Path("/dev/src/refmatrix/__init__.py"),
            "code_root": Path("/dev"), "venv_tree": Path("/dev"),
            "editable_target": Path("/dev/src"), "dev_tree": True,
            "deploy_root": Path("/deploy"), "dev_reason": "not-deploy-tree"}


def test_version_verbose_words_the_dev_tree_through_the_one_message(monkeypatch):
    """AC-34. At HEAD `_print_code_identity` says "this venv belongs to another tree" — rule
    (a)'s words for a venv whose editable install is correct."""
    monkeypatch.setattr(upgrade, "runtime_identity", lambda **kw: _dev_ident())
    monkeypatch.setattr(upgrade, "dev_tree_message", lambda ident: "SENTINEL-DEV-TREE-MESSAGE")
    out = CliRunner().invoke(cli_mod.main, ["version", "-v"]).output
    assert "SENTINEL-DEV-TREE-MESSAGE" in out, out
    assert "this venv belongs to another tree" not in out, out


def test_relaunch_dev_tree_refusal_words_it_through_the_one_message(root, monkeypatch):
    """AC-34. At HEAD: "a venv that belongs to … is running another tree; fix the editable
    install first"."""
    from refmatrix import __version__
    calls = _launchd_fakes(monkeypatch, stopped=True)
    monkeypatch.setattr(upgrade, "runtime_identity", lambda **kw: _dev_ident())
    monkeypatch.setattr(upgrade, "dev_tree_message", lambda ident: "SENTINEL-DEV-TREE-MESSAGE")
    monkeypatch.setattr(dm, "served_identity", lambda r, timeout=2.0: (
        (777, __version__) if any(c[0] == "kickstart" for c in calls) else None))
    monkeypatch.setattr(dm, "call", lambda r, op, args=None, *, timeout=60.0, retries=2: {
        "ok": True, "result": {"code_path": "/dev/src/refmatrix/__init__.py",
                               "dev_tree": True, "dev_reason": "not-deploy-tree", "pid": 777}})
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "restart", "--relaunch"])
    assert r.exit_code != 0, r.output
    assert "SENTINEL-DEV-TREE-MESSAGE" in r.output, r.output
    assert "fix the editable install first" not in r.output, r.output


def test_daemon_ping_carries_the_dev_reason(tmp_path, monkeypatch):
    """AC-35. At HEAD the ping carries `dev_tree` and no reason."""
    monkeypatch.setattr(dm, "_PROCESS_IDENTITY", None)
    monkeypatch.setattr(upgrade, "runtime_identity", lambda **kw: _dev_ident())

    class D:
        root = tmp_path
        store = None
    res = dm._op_ping(D(), {})
    assert res["dev_tree"] is True
    assert res.get("dev_reason") == "not-deploy-tree", res
