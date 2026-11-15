import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


def _assert_tested_code_is_this_checkout() -> None:
    """Refuse to run when `refmatrix` would import from a different tree than these tests.

    `.venv-eval` holds an editable install of the dev tree, so a suite run from a clone or
    worktree without `PYTHONPATH=<checkout>/src` silently tests the DEV tree's code and reports
    green (seen 2026-10-14 in the bug-105 littlebig clone: the r2 tests failed on missing
    attributes of the wrong module; a clean run would have passed on code it never loaded).

    Resolved with `find_spec`, NOT an import (task 23.0 R9, d9bo #6): importing `refmatrix`
    here would compute `launchctl.LAUNCH_AGENTS_DIR` from the real `$HOME` before the sandbox
    redirect below, and a mis-pointed run must never reach the sandbox at all.
    """
    spec = importlib.util.find_spec("refmatrix")
    if spec is None or spec.origin is None:
        raise pytest.UsageError(
            f"tests in {_REPO} cannot find `refmatrix`; "
            f"set PYTHONPATH={_REPO / 'src'} (prepend) so the checkout under test is imported")
    loaded = Path(spec.origin).resolve().parent
    expected = (_REPO / "src" / "refmatrix").resolve()
    if loaded != expected:
        raise pytest.UsageError(
            f"tests in {_REPO} would exercise refmatrix from {loaded}; "
            f"set PYTHONPATH={_REPO / 'src'} (prepend) so the checkout under test is imported")


_assert_tested_code_is_this_checkout()

# ---- task 23.0: the sandbox (R1-R4), BEFORE the first `refmatrix` import -----------------
#
# bug-088 (72 in-process connects to live sockets in one run) and bug-101 (143,108 facts.log
# events + 235 query.log fixture rows written into the LIVE global store) share one cause: the
# suite ran with the developer's real `$HOME`. `enter()` captures the real paths, writes the
# deny set and turns the audit-hook refusal on; `redirect()` is the R1 env assignments. The
# logic lives once, in tests/sandbox_site/rmx_sandbox.py, shared with every child process
# (sitecustomize.py) and the proof/lane scripts.
sys.path.insert(0, str(_REPO / "tests" / "sandbox_site"))
import rmx_sandbox  # noqa: E402

_SANDBOX = rmx_sandbox.enter(_REPO)
rmx_sandbox.redirect(_SANDBOX)

# The FIRST refmatrix import, and deliberately `launchctl`: `LAUNCH_AGENTS_DIR` is the one path
# computed at IMPORT time, so it is the one a reorder above would freeze on the live home. It
# is checked here, fail-closed, for every run -- a one-file run never reaches AC-1's canary, and
# `launchctl.install` writes plists into that directory.
from refmatrix import launchctl as _launchctl  # noqa: E402
from refmatrix import cli as _cli  # noqa: E402
from refmatrix import daemon as _dm  # noqa: E402

rmx_sandbox.assert_under_sandbox(_SANDBOX, {"launchctl.LAUNCH_AGENTS_DIR":
                                            _launchctl.LAUNCH_AGENTS_DIR})


# ---- task 29.4 R4 item 6: in-process daemons are spawns too ----------------------------------
#
# bug-229 (2026-11-14) is a daemon that outlived its test by 20 hours. A `Daemon` built and
# served INSIDE the pytest process writes no ledger line (nothing is exec'd or forked), so the
# instance itself is recorded: `Daemon.__init__` is wrapped to put each instance, weakly, in
# `rmx_sandbox`'s registry with the test that built it, and changes nothing else. At session
# finish an instance whose serve loop is still running is reported and fails the session --
# never stopped through its `rmxd.pid`, which names THIS process (ruling L142: the reaper never
# signals its own pid or an ancestor); see `_stop_in_process` for why it is not stopped here.
_SERVE_CODE = _dm.Daemon.serve_forever.__code__


def _track_daemon_instances() -> None:
    import functools
    init = _dm.Daemon.__init__
    if getattr(init, "_rmx_tracked", False):          # the conftest executed a second time
        return

    @functools.wraps(init)
    def __init__(self, *args, **kwargs):
        init(self, *args, **kwargs)
        rmx_sandbox.track_inprocess(self, getattr(self, "root", "?"))

    __init__._rmx_tracked = True
    _dm.Daemon.__init__ = __init__


def _serve_thread(d) -> "int | None":
    """The ident of the thread running `d.serve_forever()`, from the live frames: the serve loop
    holds the bound socket, so a running frame IS "still serving" (#r4 item 6)."""
    for tid, frame in sys._current_frames().items():
        f = frame
        while f is not None:
            if f.f_code is _SERVE_CODE and f.f_locals.get("self") is d:
                return tid
            f = f.f_back
    return None


def _stop_in_process(d, emit) -> bool:
    """NOT stopped in-session, and said so. Its own stop path cannot be used here:
    `Daemon.serve_forever` ends every shutdown in `os._exit(0)` (daemon.py, the force-exit after
    "daemon stopped"), so a stop through the registry (`OPS["stop"]`) ends THIS session with exit
    0 before pytest prints its summary, losing the failure it exists to report (found
    2026-11-15, T0.2 GREEN). A signal is ruled out too (ruling L142). The session fails, and the
    daemon ends with the session's process. Open gap: task-29.4 #r4 item 6's "stopped"."""
    emit("  NOT stopped in-session: serve_forever ends its shutdown in os._exit(0), which "
         "would end this session with exit 0; it ends with this process (task-29.4 #r4 item 6, "
         "open gap)")
    return False


_track_daemon_instances()
rmx_sandbox.set_inprocess_ops(lambda d: _serve_thread(d) is not None, _stop_in_process)


def _pyc_guard():
    """Load `tools/pyc_guard.py` by path — `tools/` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "rmx_pyc_guard", _REPO / "tools" / "pyc_guard.py")
    if spec is None or spec.loader is None:      # pragma: no cover - layout bug
        raise RuntimeError("tools/pyc_guard.py is missing")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pytest_sessionstart(session):
    """Refuse timestamp-invalidated bytecode before a single test runs.

    bug-037: a same-length mutation plus a restore left a `.pyc` that the
    interpreter considered valid, and `PROBE_TIMEOUT_S` read 20.0 from a file
    that said 45. Two tests failed for a reason unrelated to their subject,
    and a green run in the same state would have been just as wrong. See
    `tools/pyc_guard.py`.
    """
    _pyc_guard().enforce(_REPO / "src" / "refmatrix")
    if rmx_sandbox.claim_session(session.config):
        _sweep_killed_runs(session.config)


def _emitter(config):
    """Reaper lines go to pytest's terminal (stdout, ahead of the final summary), each on a line
    of its own (`write_line` ends a progress line first), else stderr."""
    rep = config.pluginmanager.get_plugin("terminalreporter")
    if rep is None:
        return rmx_sandbox._stderr_emit
    return rep.write_line


_SWEPT: dict = {"n": None}


def _sweep_killed_runs(config) -> None:
    """task 29.4 R4 item 3 (bug-229): a run killed before teardown cannot reap, so the NEXT
    session's start stops what its sandbox's ledger left alive (`ORPHAN from a killed run`),
    removes its root, logs it to `workflow/review-output/leaked-processes.log`, and counts it in
    the session header. It does not fail this session (plan-29 D13)."""
    res = rmx_sandbox.sweep_killed_runs(_emitter(config))
    _SWEPT["n"] = len(res["orphans"])
    rmx_sandbox.leak_log(_REPO, [rec["line"] for rec in res["orphans"]]
                         + [f"killed run's sandbox removed: {r}" for r in res["roots"]]
                         + [f"killed run's sandbox KEPT (survivors): {r}" for r in res["kept"]])


def pytest_report_header(config):
    """task 29.4 R4 item 3: the count of orphans this session's start swept, in the header
    (format fixed by the RED, ruling L142 (6))."""
    if _SWEPT["n"] is None or rmx_sandbox._STATE["session"] is not config:
        return None
    return f"rmx sandbox: {_SWEPT['n']} orphan process(es) swept from killed runs"


@pytest.fixture
def deployed_rmx(tmp_path, monkeypatch):
    """The deployed environment, pinned (task 4.5; widened by task 4.6 M2).

    Three inputs a plist / upgrade / relaunch test would otherwise take from whichever tree runs
    it — the ambient `rmx` on PATH, `sys.argv[0]`, and the test interpreter's own identity, which
    is "deployed" in the dev tree and "dev tree" in every clone (ch-bsd plan-4 r5 #m-2, #s-2):

    - `RMX_BIN` -> a real script answering the identity JSON with `dev_tree: false` and an
      `import_path` inside a tmp deploy-shaped tree. Its identity is asked for and cached HERE,
      before a test fakes `subprocess.run` (the `_hub_install_fakes` state machine replaces the
      process-wide function `binary_identity` execs through).
    - `RMX_DEPLOY_ROOT` -> that tree (S2's deploy root).
    - `upgrade.runtime_identity` -> the REAL classifier with its DEFAULT `prefix`/`import_file`
      pointed at that tree's `.venv` and `src/refmatrix/__init__.py`. Explicit arguments pass
      through untouched, so identity-under-test calls are unaffected."""
    import functools
    from refmatrix import launchctl
    from refmatrix import upgrade as _up
    from tests.fake_rmx import deploy_tree, identity_binary
    tree = deploy_tree(tmp_path / "deployed-rmx")
    init = tree / "src" / "refmatrix" / "__init__.py"
    b = identity_binary(tmp_path / "deployed-rmx", dev_tree=False, import_path=str(init))
    monkeypatch.setattr(launchctl, "_IDENTITY_CACHE", {})
    ident = launchctl.binary_identity(str(b))
    assert ident.get("dev_tree") is False, ident
    monkeypatch.setenv("RMX_BIN", str(b))
    monkeypatch.setenv("RMX_DEPLOY_ROOT", str(tree))
    real = _up.runtime_identity

    @functools.wraps(real)
    def _deployed_identity(*, prefix=None, import_file=None):
        return real(prefix=prefix if prefix is not None else tree / ".venv",
                    import_file=import_file if import_file is not None else init)
    monkeypatch.setattr(_up, "runtime_identity", _deployed_identity)
    assert _up.runtime_identity()["dev_tree"] is False
    return b


@pytest.fixture(autouse=True)
def _isolate_agent_bashrc(tmp_path, monkeypatch):
    """Keep install() from touching the real ~/.claude/agent-bashrc.sh."""
    monkeypatch.setenv("RMX_AGENT_BASHRC", str(tmp_path / "agent-bashrc.sh"))
    # Never let a test write the real ~/.claude/hooks: an install(apply=True)
    # with search on rewrote the live rewriter with dev-tree paths every
    # full-suite run (found by `rmx install-hooks --check`, 2026-09-14).
    monkeypatch.setenv("RMX_CLAUDE_HOOKS_DIR", str(tmp_path / "claude-hooks"))


@pytest.fixture(autouse=True)
def _reset_cli_partition_override():
    """`cli._partition_override` is a module global the memory subcommands set
    for the life of ONE process (`rmx` is one invocation per process). In
    the suite every CliRunner call shares the process, so a memory command
    on one tmp store pinned the NEXT test's bridge to the wrong partition
    (found 2026-09-14: `test_sync_disk_alias_fails_loud…` → five `live`
    bridge tests looked up rows in a partition nothing wrote to)."""
    yield
    _cli._partition_override = None


def source_of(mod, name: str) -> str:
    """Source of a top-level `def name` READ FROM DISK, sliced by text.

    `inspect.getsource` slices the file as it is NOW using the ALREADY-LOADED
    code object's `co_firstlineno`. Edit `src/` while the suite runs — this
    project's normal state, with a 13-minute suite and remediation commits
    landing during it — and the assertion silently reads lines belonging to a
    different function. That is what produced the phantom sixth failure in
    `pytest-post-bsd-r2.log`: `serve_foreground`'s assertion failed against a
    line from an unrelated function after a +5-line edit at daemon.py:4305,
    and cost a handoff section and a round of audit time to attribute
    (ch-bsd r4 #m-4-r4, #q1-sixth-failure).

    Slicing by NAME cannot be shifted by an edit elsewhere in the file.
    """
    from pathlib import Path

    lines = Path(mod.__file__).read_text().splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith(f"def {name}")), None)
    if start is None:
        raise AssertionError(f"no top-level `def {name}` in {mod.__file__}")
    end = next((j for j in range(start + 1, len(lines))
                if lines[j].startswith(("def ", "class ", "@"))), len(lines))
    return "\n".join(lines[start:end])


# ---- task 23.0 R2/R3: a per-test store root, and a violation fails its test --------------
#
# The record-only connect recorder of 2026-10-07 named bug-088's offenders by evidence and let
# every one of them through. The refusal is now the audit hook `rmx_sandbox.enter()` installed
# above (it also writes workflow/review-output/live-socket-touches.log); what lives here is the
# per-test half.


def _init_store(root: Path) -> None:
    from refmatrix.store import Store
    s = Store(root)
    try:
        s.init()
    finally:
        s.close()


# The sandbox's global store EXISTS, as the live one does: before the sandbox a bare `rmx`
# from a tmp cwd fell back to the live `~/.refmatrix` store (bug-101's 235 query.log rows came
# from exactly that), so tests written against it expect a store there.
_init_store(Path(_SANDBOX["root"]) / "h" / ".refmatrix")


@pytest.fixture(autouse=True)
def _sandbox_store_root(monkeypatch):
    """R2: `REFMATRIX_ROOT` names a fresh per-test store under the sandbox, so `_root()` from
    the repo cwd can never walk to the repo's live `.refmatrix/`. A test that needs the cwd
    walk chdirs into its own tmp dir and `delenv`s this itself.

    The store is INITIALIZED (~40 ms): before the sandbox `_root()` always resolved to a store
    that existed (the repo's live one, or the live global), and R5's grep tests write their
    `query.log` row through it -- into the sandbox now. Removed at teardown (2 MB each)."""
    root = rmx_sandbox.new_store_root(_SANDBOX["root"])
    _init_store(root)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    yield
    rmx_sandbox.remove_tree(root.parent)


def _sandbox_pointer_dir() -> Path:
    """`stm.pointer_dir()`'s location, computed the way it is (21.1 D3: `<hub.global_store_root()>
    /by-pid/`) without calling it -- `pointer_dir()` creates the dir, and a fixture must not."""
    from refmatrix import hub
    return Path(hub.global_store_root()) / "by-pid"


@pytest.fixture(autouse=True)
def _fresh_pointer_dir():
    """21.1 D3 moved the session pointers and their `_errors.jsonl` to USER-level state
    (`<global store root>/by-pid/`): ONE dir for the whole sandbox, shared by every test and
    every child process. Left alone it carried state from test to test (bug-132: a corrupt-sink
    test wrote non-UTF-8 bytes into `_errors.jsonl` and six later AC-4 tests raised
    UnicodeDecodeError; bug-133: an in-process input-hook test left a pointer for the runner's
    real Claude pid that `test_mcp_focus_tool` then resolved). Every test starts with NO pointer
    dir -- the state the sandbox's freshly initialised global store has at session start -- and
    `pointer_dir()` recreates it on first use; children see the same reset because they resolve
    it from the same `$RMX_HOME`. Removing (not symlinking a tmp dir in) keeps the production
    layout. A test that sets its own `RMX_HOME` has its own pointer dir and is untouched."""
    d = _sandbox_pointer_dir()       # captured: teardown must not follow a test's own RMX_HOME
    rmx_sandbox.remove_tree(d)
    yield
    rmx_sandbox.remove_tree(d)


# R6 (ch-bsd r1 b2, 2026-10-15): every skip is NAMED here, or the session fails
# (`rmx_sandbox.SkipGate`). The main-tree baseline run (pytest-baseline-23ad703.log) skips
# none; the one entry is CLONE-ONLY: a littlebig clone's committed `.claude/settings.json`
# names the hooks of another checkout.
#
# bug-215 (T0.1' R1.1/R1.2, 2026-11-15): until then ONE test, `(_REPO / ".venv-eval").is_dir()`,
# switched all 19 pins, and each pin's value was a description ("clone-only: the dev venv rmx …
# is not built", "clone-only: the installed hooks belong to another checkout …") that equalled
# none of the reasons the tests skip with, while `SkipGate` matched by nodeid only. A clone whose
# `.venv-eval` is a SYMLINK to the main tree's passed the `is_dir()` test, every pin was dropped,
# and the hooks skip failed every run there (exit 1, SKIPPED-UNPINNED
# test_installed_hooks_match_generated); a pinned test that began skipping for a NEW reason
# passed unseen. Now each pin is allowed by ITS OWN condition, and its value is the test's own
# `reason=` string verbatim, which `SkipGate` requires to be EQUAL to the skip's reason. A test
# whose `reason=` text changes updates its pin here in the same commit.
#
# bug-253 (T0.2 stage 2, 2026-11-15) retired the 18 dev-venv pins and their condition: the six
# files that skipped on a missing `<checkout>/.venv-eval/bin/rmx` now resolve the dev `rmx` from
# the interpreter running the suite (tests/devbin.py), so a checkout's venv decides no skip.
# Allowed only when the installed hooks belong to another checkout, decided as
# tests/test_repo_hooks_in_sync.py decides it (`_OWNER is not None and _OWNER != REPO`). Its
# other skip, "not an rmx-hooks-managed checkout", is deliberately NOT pinned.
_FOREIGN_HOOKS_PINS = {
    "tests/test_repo_hooks_in_sync.py::test_installed_hooks_match_generated":
        "hooks belong to another checkout of this commit",
}


def allowed_skips(checkout: Path) -> dict:
    """The pins (`nodeid -> the test's own reason`) allowed in `checkout`, each by its own
    condition (bug-215, T0.1' R1.1). Pure: reads the checkout, writes nothing."""
    from refmatrix import hooks as hooks_mod

    checkout = Path(checkout).resolve()      # the hooks test compares against a resolved REPO
    allowed: dict = {}
    owner = hooks_mod.installed_root(checkout)
    if owner is not None and owner != checkout:
        allowed.update(_FOREIGN_HOOKS_PINS)
    return allowed


ALLOWED_SKIPS = allowed_skips(_REPO)

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "sandbox_probe: a DELIBERATE refusal probe (task 23.0). Its touches-log lines (and its "
        "children's) name it as their owner, so AC-4's proof and the child-touch check accept "
        "them; its in-process inner-session violations are expected. Nothing else is exempt.")
    if not config.pluginmanager.has_plugin("rmx_skip_gate"):
        config.pluginmanager.register(rmx_sandbox.SkipGate(ALLOWED_SKIPS), "rmx_skip_gate")
    rmx_sandbox.claim_session(config)


_TOUCHES_AT = pytest.StashKey[int]()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Name the OUTER test in the touches log (an in-process `pytester` inner test overwrites
    `PYTEST_CURRENT_TEST` for the duration of its own run); note where the touches log ended
    (the child-touch check reads from there); a `sandbox_probe` test runs inside
    `probe_scope()`, so its deliberate refusals are flagged as such."""
    rmx_sandbox.set_outer_test(item.nodeid)
    item.stash[_TOUCHES_AT] = rmx_sandbox.touches_size(_SANDBOX["deny"])
    probe = item.get_closest_marker("sandbox_probe") is not None
    try:
        with rmx_sandbox.probe_scope(item.nodeid if probe else None):
            yield
    finally:
        rmx_sandbox.set_outer_test(None)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """d9bo #5: a violation is raised AND recorded per test; a test whose record is non-empty
    FAILS even when the code under test swallowed the raise (`except Exception: pass`, a
    best-effort thread).

    ch-bsd r1 (2026-10-15) added two more ways a refusal could pass unseen:
    - s2: an in-process `pytester` inner test records under its OWN node id, which no report
      hook popped -- it is now charged to the outer test (unless the outer test is a
      `sandbox_probe`, whose inner probes are the point);
    - s1: a CHILD exits `CHILD_EXIT` and writes the touches log; a spawner that ignores the
      code let the test pass. At teardown, an unflagged line from another pid naming this test
      fails it."""
    outcome = yield
    rep = outcome.get_result()
    own, inner = rmx_sandbox.take_record(item.nodeid)
    probe = item.get_closest_marker("sandbox_probe") is not None
    why = []
    if own:
        why.append(f"SandboxViolation (swallowed by the code under test) during {rep.when}: "
                   + "; ".join(own))
    if inner and not probe:
        why.append("SandboxViolation in an in-process inner session: " + "; ".join(inner))
    since = item.stash.get(_TOUCHES_AT, None)       # None: not run through the hook above
    if rep.when == "teardown" and since is not None:
        kids = rmx_sandbox.child_touches(_SANDBOX["deny"]["touches"], since, item.nodeid,
                                         os.getpid())
        if kids:
            why.append(f"SandboxViolation in a child process (it exited "
                       f"{rmx_sandbox.CHILD_EXIT}; its spawner did not fail the test): "
                       + "; ".join(kids[:5]))
    if rep.when == "teardown":
        # task 29.4 R4 item 7 (bug-229): a spawn registered through `register_spawn` is
        # checked when the node owning its fixture has been torn down; one nobody stopped
        # fails THIS test, by name, and is stopped here.
        live_nodes = getattr(getattr(item.session, "_setupstate", None), "stack", {})
        for e in rmx_sandbox.due_spawns(item.nodeid, live_nodes):
            msg = rmx_sandbox.check_spawn(e, _emitter(item.config))
            if msg:
                why.append(msg)
                rmx_sandbox.failure_record(item.nodeid, "teardown", msg)
    if why and not rep.failed:
        rep.outcome = "failed"
        rep.longrepr = "\n".join(why)


def pytest_sessionfinish(session, exitstatus):
    """ANY violation still recorded fails the run (ch-bsd r1 s2): one outside any test
    (collection, a thread between tests), or one under a key no report hook popped (a
    background thread in the window after a test's teardown report).

    task 29.4 R4 (bug-229, 2026-11-14: a test daemon outlived its run by 20 hours): in the
    outermost session only, every process the suite started that is still alive -- spawned
    (the ledger) or served in-process (the `Daemon` registry) -- is printed, stopped, and fails
    the session (`rmx_sandbox.reap_session`)."""
    stray = rmx_sandbox.drain_record()
    if stray:
        session.config.get_terminal_writer().line(
            "SandboxViolation outside any reported test: "
            + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(stray.items())), red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    if rmx_sandbox._STATE["session"] is session.config:
        if rmx_sandbox.reap_session(_REPO, _emitter(session.config)):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
