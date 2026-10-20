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

rmx_sandbox.assert_under_sandbox(_SANDBOX, {"launchctl.LAUNCH_AGENTS_DIR":
                                            _launchctl.LAUNCH_AGENTS_DIR})


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
# none; the entries are CLONE-ONLY: a littlebig clone has no `.venv-eval/` of its own (the
# dev `rmx` those end-to-end tests spawn) and its hooks are installed for another checkout.
# They are allowed ONLY in a checkout without `.venv-eval/`: in the main tree each of them
# skipping fails the session like any other unpinned skip.
_CLONE_NO_VENV = "clone-only: the dev venv rmx (<checkout>/.venv-eval/bin/rmx) is not built"
_CLONE_HOOKS = "clone-only: the installed hooks belong to another checkout of this commit"
_CLONE_ONLY_SKIPS = {
    "tests/test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon":
        _CLONE_NO_VENV,
    "tests/test_brief_real_daemon.py::test_brief_runs_end_to_end_through_a_real_daemon":
        _CLONE_NO_VENV,
    "tests/test_brief_real_daemon.py::test_saved_briefs_do_not_grow_the_corpus_on_rerun":
        _CLONE_NO_VENV,
    "tests/test_brief_real_daemon.py::test_the_gmd_flag_does_not_crash_through_a_real_daemon":
        _CLONE_NO_VENV,
    "tests/test_grep_argv_order_e2e.py::test_a_directory_walk_keeps_its_files_GROUPED":
        _CLONE_NO_VENV,
    "tests/test_grep_argv_order_e2e.py::test_a_named_file_still_wins_its_argv_slot_against_a_walk":
        _CLONE_NO_VENV,
    "tests/test_grep_argv_order_e2e.py::test_named_paths_come_back_in_argument_order_not_fanout_order":
        _CLONE_NO_VENV,
    "tests/test_grep_argv_order_e2e.py::test_the_tool_itself_is_the_one_that_scrambles":
        _CLONE_NO_VENV,
    "tests/test_grep_count_rows_e2e.py::test_a_directory_with_no_match_gets_a_zero_row_per_file":
        _CLONE_NO_VENV,
    "tests/test_grep_count_rows_e2e.py::test_a_directory_with_some_matches_keeps_its_zero_rows":
        _CLONE_NO_VENV,
    "tests/test_grep_count_rows_e2e.py::test_a_missing_file_beside_a_directory_is_not_a_bare_zero":
        _CLONE_NO_VENV,
    "tests/test_grep_count_rows_e2e.py::test_a_missing_file_beside_a_match_still_exits_2":
        _CLONE_NO_VENV,
    "tests/test_grep_count_rows_e2e.py::test_a_missing_file_exits_2_and_says_so":
        _CLONE_NO_VENV,
    "tests/test_grep_count_rows_e2e.py::test_two_spellings_keep_their_own_prefix_on_n":
        _CLONE_NO_VENV,
    "tests/test_grep_count_rows_e2e.py::test_two_spellings_of_one_file_are_two_rows":
        _CLONE_NO_VENV,
    "tests/test_grep_evidence_verified.py::test_a_fully_filtered_answer_falls_through_to_the_floor":
        _CLONE_NO_VENV,
    "tests/test_grep_learning_replay.py::test_arm_a_learns_and_arm_b_learns_exactly_nothing":
        _CLONE_NO_VENV,
    "tests/test_grep_no_flag_bundle.py::test_the_documented_pipe_count_works_with_a_bare_flag":
        _CLONE_NO_VENV,
    "tests/test_repo_hooks_in_sync.py::test_installed_hooks_match_generated":
        _CLONE_HOOKS,
}
ALLOWED_SKIPS = {} if (_REPO / ".venv-eval").is_dir() else dict(_CLONE_ONLY_SKIPS)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "sandbox_probe: a DELIBERATE refusal probe (task 23.0). Its touches-log lines (and its "
        "children's) name it as their owner, so AC-4's proof and the child-touch check accept "
        "them; its in-process inner-session violations are expected. Nothing else is exempt.")
    if not config.pluginmanager.has_plugin("rmx_skip_gate"):
        config.pluginmanager.register(rmx_sandbox.SkipGate(ALLOWED_SKIPS), "rmx_skip_gate")


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
    if why and not rep.failed:
        rep.outcome = "failed"
        rep.longrepr = "\n".join(why)


def pytest_sessionfinish(session, exitstatus):
    """ANY violation still recorded fails the run (ch-bsd r1 s2): one outside any test
    (collection, a thread between tests), or one under a key no report hook popped (a
    background thread in the window after a test's teardown report)."""
    stray = rmx_sandbox.drain_record()
    if stray:
        session.config.get_terminal_writer().line(
            "SandboxViolation outside any reported test: "
            + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(stray.items())), red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
