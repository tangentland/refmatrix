"""`rmx grep` has no `-f/--flags` bundle (user, 2026-10-07: "change the grep to
not use -flags").

The bundle predated bare grep flags (0.25.7) and collided with grep's own
`-f FILE` (pattern file): plan-16 spec review r3/r4 found the documented
`git diff | rmx grep -f '-c' "^+"` would be read two ways. Bare flags have
worked for months, so the bundle goes; `-f FILE` / `--file=FILE` now mean what
they mean to grep, and `--flags` is refused with a pointer instead of being
silently treated as something else.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix.store import Store

GREP = "/usr/bin/grep"


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_GREP_NOTE", "0")
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    p = tmp_path / "proj"
    p.mkdir()
    s = Store(p / ".refmatrix", backend="duckdb")
    s.init()
    s.close()
    (p / "t.txt").write_text("alpha one\nbeta two\ngamma three\n")
    (p / "pats.txt").write_text("alpha\ngamma\n")
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(p)
    return p


def _grep(args, cwd):
    return subprocess.run([GREP, *args], capture_output=True, text=True, cwd=str(cwd))


def test_the_flags_bundle_is_refused_with_a_pointer(proj):
    res = CliRunner().invoke(cli_mod.main, ["grep", "--flags", "-c", "alpha", "t.txt"])

    assert res.exit_code == 2, res.output
    assert "--flags" in res.output and "removed" in res.output, res.output


@pytest.mark.parametrize("argv", [["-f", "pats.txt", "t.txt"],
                                  ["--file=pats.txt", "t.txt"]])
def test_dash_f_is_greps_pattern_file(proj, argv):
    control = _grep(argv, proj)
    assert control.returncode == 0 and control.stdout.count("\n") == 2, "control"

    res = CliRunner().invoke(cli_mod.main, ["grep", "--no-learn", *argv])

    assert res.stdout == control.stdout, (res.stdout, control.stdout)
    assert res.exit_code == control.returncode


RMX = Path(__file__).resolve().parents[1] / ".venv-eval" / "bin" / "rmx"


@pytest.mark.skipif(not RMX.exists(), reason="dev venv rmx not built")
def test_the_documented_pipe_count_works_with_a_bare_flag(proj):
    """A REAL pipe (CliRunner's `input` is not one, so rmx's pipe probe would
    never see it). A LITERAL pattern: the old doc example's `^+` is a BRE
    anchor, and rmx's stdin filter reads a non-`-E` pattern as a fixed string,
    so it counts 0 where grep counts 2 — bug-081 on the pipe path, fixed by
    plan-16 task 16.5 R2 (a pipe execs the real grep), not here."""
    import os
    r = subprocess.run([str(RMX), "grep", "-c", "added"], cwd=str(proj),
                       input="+ added\n- removed\n+ added again\n",
                       capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, RMX_GREP_NOTE="0"))

    assert r.stdout.strip() == "2", (r.stdout, r.stderr)
