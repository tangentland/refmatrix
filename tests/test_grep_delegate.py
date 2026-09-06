"""Full flag compatibility: flags the index can't express bypass it and run
the real tool (rg, then grep for grep-only dialects) with the original argv.
`rmx grep` must never reject a valid grep/rg flag."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _rmx(args, cwd, stdin=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    )
    env.pop("RMX_PARTITION", None)
    return subprocess.run(
        [sys.executable, "-c",
         "from refmatrix.cli import main; main()", *args],
        cwd=cwd, env=env, input=stdin,
        capture_output=True, text=True, timeout=60)


def _proj(tmp_path):
    (tmp_path / ".refmatrix").mkdir()
    (tmp_path / "code.py").write_text(
        "def alpha():\n    beta = 1\n    return beta\n", encoding="utf8")
    (tmp_path / "notes.txt").write_text("alpha in prose\n", encoding="utf8")
    return tmp_path


def test_include_glob_delegates_and_filters(tmp_path):
    proj = _proj(tmp_path)
    got = _rmx(["grep", "-rn", "--include=*.py", "alpha", "."], cwd=proj)
    assert got.returncode == 0, got.stderr
    assert "code.py" in got.stdout
    assert "notes.txt" not in got.stdout
    assert "delegated" in got.stderr


def test_context_flag_delegates_with_context_lines(tmp_path):
    proj = _proj(tmp_path)
    got = _rmx(["grep", "-n", "-A", "1", "alpha", "code.py"], cwd=proj)
    assert got.returncode == 0, got.stderr
    assert "alpha" in got.stdout
    assert "beta" in got.stdout  # the -A 1 context line
    assert "delegated" in got.stderr


def test_rg_glob_flag_delegates(tmp_path):
    proj = _proj(tmp_path)
    got = _rmx(["grep", "-g", "*.py", "alpha", "."], cwd=proj)
    # rg handles -g natively; if rg is absent the grep retry exits 2 and
    # surfaces the tool's own error — either way no UsageError from rmx.
    assert "unsupported flag" not in got.stderr
    if got.returncode == 0:
        assert "code.py" in got.stdout


def test_delegated_no_match_exits_1(tmp_path):
    proj = _proj(tmp_path)
    got = _rmx(["grep", "--include=*.py", "zzznope", "."], cwd=proj)
    assert got.returncode == 1
    assert got.stdout == ""


def test_genuinely_invalid_flag_surfaces_tool_error(tmp_path):
    proj = _proj(tmp_path)
    got = _rmx(["grep", "--definitely-not-a-flag", "alpha", "."], cwd=proj)
    assert got.returncode == 2
    assert got.stderr  # the real tool's usage error, not a silent pass
