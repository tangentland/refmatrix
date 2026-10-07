"""ch-bsd r3 #b-4: the `-c` rows for directories, missing files and two
spellings of one file, against `/usr/bin/grep` as the control.

r2 #b-2/#b-3 were closed for NAMED files. Two halves were left:

  (a) the nothing-matched branch's `else: click.echo("0")` lost its
      `with_filename` guard, so `-rc zzz sub` and `-c zzz sub nosuch.txt`
      printed a bare `0` — a number grep never prints for a filename-shaped
      read — where 0.76.0 printed nothing and grep prints a row per file;
  (b) `grep()` turned argv into `Path` objects before any of the fix ran, and
      `str(Path("./f0.txt")) == "f0.txt"`, so `-c alpha ./f0.txt f0.txt` was
      one row with the SUMMED count.

Every exec is `shell=False` with a list argv (a shell control is rewritten to
`rmx` by the PreToolUse hook; see test_grep_argv_order_e2e.py). Order WITHIN a
directory walk is the filesystem's for grep and sorted for rmx (accepted at
r2), so walk rows are compared as sets and argument order as lists.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

RMX = Path(__file__).resolve().parents[1] / ".venv-eval" / "bin" / "rmx"
GREP = "/usr/bin/grep"

pytestmark = pytest.mark.skipif(not RMX.exists() or not Path(GREP).exists(),
                                reason="dev venv rmx or /usr/bin/grep missing")


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "f0.txt").write_text("alpha\n" * 3)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "s1.txt").write_text("alpha\nbeta\n")
    (sub / "s2.txt").write_text("beta\n")
    from refmatrix.store import Store
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    s.close()
    return tmp_path


def _run(argv: list, cwd: Path) -> "tuple[list, int]":
    env = dict(os.environ, RMX_GREP_NOTE="0")
    r = subprocess.run(argv, capture_output=True, text=True, cwd=str(cwd),
                       timeout=120, env=env)
    return [l for l in r.stdout.splitlines() if l.strip()], r.returncode


def _both(args: list, cwd: Path):
    return (_run([str(RMX), "grep", "--no-learn", *args], cwd),
            _run([GREP, *args], cwd))


def test_a_directory_with_no_match_gets_a_zero_row_per_file(tree):
    (rmx, rcode), (grep, gcode) = _both(["-rc", "zzz", "sub"], tree)

    assert "0" not in rmx, f"a bare 0 in a filename-shaped answer: {rmx}"
    assert sorted(rmx) == sorted(grep), (rmx, grep)
    assert rcode == gcode == 1


def test_a_directory_with_some_matches_keeps_its_zero_rows(tree):
    (rmx, _), (grep, _) = _both(["-rc", "alpha", "sub"], tree)

    assert sorted(rmx) == sorted(grep), (rmx, grep)


def test_a_missing_file_beside_a_directory_is_not_a_bare_zero(tree):
    """Without `-r`, BSD grep refuses the directory ("Is a directory") where
    rmx walks it, as rg does — a pre-existing difference, not this finding.
    So the control is `grep -rc` over the directory alone: the walked rows,
    and nothing for the missing file."""
    rmx, _ = _run([str(RMX), "grep", "--no-learn", "-c", "zzz", "sub",
                   "nosuch.txt"], tree)
    grep_walk, _ = _run([GREP, "-rc", "zzz", "sub"], tree)

    assert "0" not in rmx, rmx
    assert "nosuch.txt:0" not in rmx, rmx
    assert sorted(rmx) == sorted(grep_walk), (rmx, grep_walk)


def test_two_spellings_of_one_file_are_two_rows(tree):
    (rmx, _), (grep, _) = _both(["-c", "alpha", "./f0.txt", "f0.txt"], tree)

    assert rmx == grep == ["./f0.txt:3", "f0.txt:3"], (rmx, grep)


def test_two_spellings_keep_their_own_prefix_on_n(tree):
    (rmx, _), (grep, _) = _both(["-n", "alpha", "f0.txt", "./f0.txt"], tree)

    assert rmx == grep, (rmx, grep)
