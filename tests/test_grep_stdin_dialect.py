"""rmx grep stdin + dialect regressions (bus report 85e22d5d06dd, orderly).

BUG A: `rg A file | rg -v B` — both stages python-backed wrappers — raced
`_is_stdin_piped`'s zero-timeout peek: the downstream stage checked before the
upstream wrote its first byte, read the live pipe as "not piped", and silently
searched the project tree instead of the pipe. The probe now blocks until
data-or-EOF on a FIFO, and explicit path args always win over a pipe.

BUG B: rg's dialect is Rust-regex/ERE; rmx grep's default is substring, so
`alpha|beta` matched nothing through rmxrg. rmxrg now injects -E unless -F is
present, and GNU BRE escapes (`a\|b`) fail loud (exit 2 → wrapper falls back
to the real tool) instead of matching nothing.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from refmatrix.cli import _is_stdin_piped

REPO = Path(__file__).resolve().parent.parent
RMXRG = REPO / "bin" / "rmxrg"


class _FakeStdin:
    """sys.stdin stand-in backed by a real pipe fd."""

    def __init__(self, fd):
        self._f = os.fdopen(fd, "r")
        self.buffer = self._f.buffer

    def isatty(self):
        return False

    def fileno(self):
        return self._f.fileno()

    def close(self):
        self._f.close()


@pytest.fixture
def pipe_stdin(monkeypatch):
    r, w = os.pipe()
    fake = _FakeStdin(r)
    monkeypatch.setattr(sys, "stdin", fake)
    yield w  # caller owns the write end
    fake.close()


def test_a_closed_empty_pipe_IS_piped(pipe_stdin):
    """SUPERSEDED CONTRACT (bug-062, 2026-10-06). This asserted `is False`.

    That was the defect written as a test. An empty pipe read as "not piped",
    so `{ true; } | rmx grep hello` fell through to index exploration and
    returned repo hits with exit 0 where grep prints nothing and exits 1 —
    `if cmd | rmx grep PAT` took the wrong branch, and the graph was taught
    from a tree search nobody asked for.

    The old contract rested on bug-062's assumption that a bare command and an
    empty pipeline are indistinguishable ("both a FIFO at EOF"), so treating a
    FIFO as a pipe would break exploration. Measured, they differ: under the
    Claude Bash tool a bare command gets fd 0 = CHR (/dev/null), a pipeline
    gets a FIFO (`tests/test_grep_empty_pipe.py` pins it). A FIFO is a pipe
    whether or not the producer wrote anything, which is how grep treats one.
    """
    os.close(pipe_stdin)
    assert _is_stdin_piped() is True


def test_pipe_with_data_is_piped(pipe_stdin):
    os.write(pipe_stdin, b"hello\n")
    os.close(pipe_stdin)
    assert _is_stdin_piped() is True


def test_slow_writer_still_detected_as_piped(pipe_stdin):
    # The 0.65.1 regression: an upstream stage writes its first byte AFTER the
    # probe runs. It used to need a blocking wait; since bug-062 the answer is
    # the fd's SHAPE, so a slow writer cannot be misread as "no pipe" and this
    # passes for a structural reason rather than a timing one. Kept because the
    # behaviour it protects is the same.
    def _late_write():
        time.sleep(0.3)
        os.write(pipe_stdin, b"late\n")
        os.close(pipe_stdin)

    t = threading.Thread(target=_late_write)
    t.start()
    try:
        assert _is_stdin_piped() is True
    finally:
        t.join()


def test_a_slow_close_without_data_IS_piped(pipe_stdin):
    """SUPERSEDED with its sibling above; this asserted `is False` too.

    It also no longer tests timing: the probe does not wait for the producer at
    all now. Emptiness left the judgement, so there is nothing to wait out —
    which is why the 0.65.1 slow-producer race cannot return through this
    function. The late close is kept to prove the answer does not depend on
    when it happens.
    """
    def _late_close():
        time.sleep(0.3)
        os.close(pipe_stdin)

    t = threading.Thread(target=_late_close)
    t.start()
    try:
        assert _is_stdin_piped() is True
    finally:
        t.join()


def _run_grep_pipe(stdin_text: str, args: list[str], cwd: Path,
                   delay: float = 0.0) -> subprocess.CompletedProcess:
    """Run `rmx grep <args>` with a REAL pipe on stdin (CliRunner can't make
    one). Pipe mode exits before any store/root resolution, so a bare tmp
    cwd is safe."""
    feed = cwd / "stdin.txt"
    feed.write_text(stdin_text)
    feeder = f"cat {feed}"
    if delay:
        feeder = f"sleep {delay}; {feeder}"
    cmd = (f"{{ {feeder}; }} | "
           f"{sys.executable} -m refmatrix.cli grep " + " ".join(args))
    return subprocess.run(["sh", "-c", cmd], capture_output=True,
                          text=True, cwd=cwd)


def test_pipe_ere_alternation(tmp_path):
    res = _run_grep_pipe("alpha\nbeta\ngamma\n", ["-E", "'alpha|beta'"],
                         tmp_path)
    assert res.stdout.splitlines() == ["alpha", "beta"]
    assert res.returncode == 0


def test_pipe_inverted_ere_alternation(tmp_path):
    res = _run_grep_pipe("alpha\nbeta\ngamma\n",
                         ["-v", "-E", "'alpha|beta'"], tmp_path)
    assert res.stdout.splitlines() == ["gamma"]


def test_pipe_survives_slow_upstream(tmp_path):
    # The two-stage-pipeline race: data arrives well after process start.
    res = _run_grep_pipe("keep me\ndrop zzz\n", ["-v", "zzz"],
                         tmp_path, delay=0.8)
    assert res.stdout.splitlines() == ["keep me"]


def test_bre_alternation_fails_loud(tmp_path):
    res = _run_grep_pipe("alpha\nbeta\ngamma\n", [r"'alpha\|beta'"],
                         tmp_path)
    assert res.returncode == 2
    assert "BRE escape" in res.stderr


@pytest.fixture
def rmxrg_env(tmp_path):
    """Project dir + stub rmx that echoes its argv, wired into rmxrg."""
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    stub = tmp_path / "rmx-stub"
    stub.write_text("#!/bin/sh\necho \"STUB:$*\"\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, RMXGREP_RMX=str(stub), RMXGREP_MODE="rich")
    return proj, env


def test_rmxrg_injects_ere(rmxrg_env):
    proj, env = rmxrg_env
    res = subprocess.run([str(RMXRG), "alpha|beta"], capture_output=True,
                         text=True, cwd=proj, env=env)
    assert res.stdout.strip() == "STUB:grep -E alpha|beta"


def test_rmxrg_respects_fixed_strings(rmxrg_env):
    proj, env = rmxrg_env
    for argv in (["-F", "a|b"], ["-nF", "a|b"], ["--fixed-strings", "a|b"]):
        res = subprocess.run([str(RMXRG), *argv], capture_output=True,
                             text=True, cwd=proj, env=env)
        assert res.stdout.startswith("STUB:grep " + argv[0]), res.stdout
        assert " -E " not in res.stdout


def test_bre_fallback_preserves_stdin_for_the_real_tool(tmp_path):
    """exit-2 fail-loud must not consume the pipe: the wrapper execs the
    real grep on the SAME stdin, which must still hold every byte (the
    buffered-peek probe used to slurp it, leaving the fallback EOF)."""
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    rmx = tmp_path / "rmx-real"
    rmx.write_text(f"#!/bin/sh\nexec {sys.executable} -m refmatrix.cli \"$@\"\n")
    rmx.chmod(rmx.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, RMXGREP_RMX=str(rmx), RMXGREP_MODE="rich")
    rmxgrep = REPO / "bin" / "rmxgrep"
    cmd = (f"printf 'alpha\\nbeta\\ngamma\\n' | "
           f"{rmxgrep} -v 'alpha\\|beta'")
    res = subprocess.run(["sh", "-c", cmd], capture_output=True,
                         text=True, cwd=proj, env=env)
    assert res.stdout.splitlines() == ["gamma"]
    assert res.returncode == 0
