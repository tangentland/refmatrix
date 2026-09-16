import importlib.util
import os
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


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
