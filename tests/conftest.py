import importlib.util
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

from refmatrix import cli as _cli  # noqa: E402  (the first refmatrix import: after the redirect)


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


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Name the OUTER test in the touches log: an in-process `pytester` inner test overwrites
    `PYTEST_CURRENT_TEST` for the duration of its own run."""
    rmx_sandbox.set_outer_test(item.nodeid)
    try:
        yield
    finally:
        rmx_sandbox.set_outer_test(None)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """d9bo #5: a violation is raised AND recorded per test; a test whose record is non-empty
    FAILS even when the code under test swallowed the raise (`except Exception: pass`, a
    best-effort thread)."""
    outcome = yield
    rep = outcome.get_result()
    hits = rmx_sandbox.RECORD.pop(item.nodeid, None)
    if hits and not rep.failed:
        rep.outcome = "failed"
        rep.longrepr = (f"SandboxViolation (swallowed by the code under test) during "
                        f"{rep.when}: " + "; ".join(hits))


def pytest_sessionfinish(session, exitstatus):
    """A violation outside any test (collection, a thread between tests) fails the run."""
    stray = rmx_sandbox.RECORD.pop(rmx_sandbox.NO_TEST, None)
    if stray:
        session.config.get_terminal_writer().line(
            f"SandboxViolation outside any test: {'; '.join(stray)}", red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
