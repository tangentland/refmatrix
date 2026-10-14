import importlib.util
import os
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


def _assert_tested_code_is_this_checkout() -> None:
    """Refuse to run when `refmatrix` imports from a different tree than these tests.

    `.venv-eval` holds an editable install of the dev tree, so a suite run from a clone or
    worktree without `PYTHONPATH=<checkout>/src` silently tests the DEV tree's code and reports
    green (seen 2026-10-14 in the bug-105 littlebig clone: the r2 tests failed on missing
    attributes of the wrong module; a clean run would have passed on code it never loaded).
    """
    import refmatrix
    loaded = Path(refmatrix.__file__).resolve().parent
    expected = (_REPO / "src" / "refmatrix").resolve()
    if loaded != expected:
        raise pytest.UsageError(
            f"tests in {_REPO} would exercise refmatrix from {loaded}; "
            f"set PYTHONPATH={_REPO / 'src'} (prepend) so the checkout under test is imported")


_assert_tested_code_is_this_checkout()


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
    from refmatrix import cli as _cli
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


# ---- the suite must not reach LIVE sockets (2026-10-07) ----------------------
#
# Two project-daemon wedges on 2026-10-07 (bug-085) each happened during a
# full-suite run, and the stuck daemon held 10 client connections on its live
# socket. Nothing here isolates `_root()`: tests run from the repo, so a CLI
# call that does not chdir resolves the LIVE `.refmatrix/`. This guard RECORDS
# every connect to a live socket with the test that made it, so the offenders
# are named by evidence, not guessed. (Record mode; refusing comes after the
# list is known.)

_LIVE_UNIX = {
    str(_REPO / ".refmatrix" / "rmxd.sock"),
    str(Path.home() / ".refmatrix" / "rmxd.sock"),
    str(Path.home() / ".refmatrix" / "hub.sock"),
    str(Path.home() / ".refmatrix" / "models.sock"),
}
_LIVE_TCP = {("127.0.0.1", 7777), ("localhost", 7777)}
_LIVE_LOG = _REPO / "workflow" / "review-output" / "live-socket-touches.log"
_current_test = {"id": "<collection>"}


def pytest_runtest_setup(item):
    _current_test["id"] = item.nodeid


def pytest_configure(config):
    import socket as _socket
    real = _socket.socket.connect

    def _recording_connect(self, address):
        hit = None
        if self.family == _socket.AF_UNIX and str(address) in _LIVE_UNIX:
            hit = str(address)
        elif isinstance(address, tuple) and tuple(address[:2]) in _LIVE_TCP:
            hit = f"{address[0]}:{address[1]}"
        if hit is not None:
            with open(_LIVE_LOG, "a") as fh:
                fh.write(f"{os.getpid()}\t{_current_test['id']}\t{hit}\n")
        return real(self, address)

    _socket.socket.connect = _recording_connect
