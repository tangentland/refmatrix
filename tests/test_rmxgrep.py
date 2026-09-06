"""rmxgrep wrapper: alias-safe grep drop-in.

Contract (user: "I should be able to alias grep=rmxgrep system wide"):
outside an rmx project it IS grep — byte-exact output, grep exit codes,
no python; inside a project a tty gets the learning `rmx grep` (with a
real-grep fallback when rmx grep fail-louds), a pipe gets real grep plus
a detached teach ping.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

RMXGREP = Path(__file__).resolve().parents[1] / "bin" / "rmxgrep"


def _run(args, cwd, env_extra=None, stdin=None):
    import os
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [str(RMXGREP), *args], cwd=cwd, env=env, input=stdin,
        capture_output=True, text=True, timeout=30)


def test_outside_project_matches_real_grep_bytes_and_exit(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("alpha\nbeta\ngamma\n", encoding="utf8")
    got = _run(["-n", "beta", str(f)], cwd=tmp_path)
    ref = subprocess.run(["grep", "-n", "beta", str(f)], cwd=tmp_path,
                         capture_output=True, text=True)
    assert got.stdout == ref.stdout
    assert got.returncode == ref.returncode == 0


def test_outside_project_no_match_exits_1(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("alpha\n", encoding="utf8")
    got = _run(["zzz", str(f)], cwd=tmp_path)
    assert got.returncode == 1
    assert got.stdout == ""


def test_outside_project_pipe_filter(tmp_path):
    got = _run(["-c", "b"], cwd=tmp_path, stdin="a\nb\nb\n")
    assert got.stdout.strip() == "2"
    assert got.returncode == 0


def test_inside_project_piped_is_still_byte_exact_grep(tmp_path):
    (tmp_path / ".refmatrix").mkdir()
    f = tmp_path / "code.py"
    f.write_text("def alpha():\n    pass\n", encoding="utf8")
    # RMXGREP_TEACH=0: no daemon in this sandbox; the answer path must not
    # depend on the ping either way.
    got = _run(["-n", "alpha", str(f)], cwd=tmp_path,
               env_extra={"RMXGREP_TEACH": "0"})
    ref = subprocess.run(["grep", "-n", "alpha", str(f)], cwd=tmp_path,
                         capture_output=True, text=True)
    assert got.stdout == ref.stdout
    assert got.returncode == 0


def test_missing_rmx_degrades_to_grep_inside_project(tmp_path):
    (tmp_path / ".refmatrix").mkdir()
    f = tmp_path / "a.txt"
    f.write_text("hit\n", encoding="utf8")
    got = _run(["hit", str(f)], cwd=tmp_path,
               env_extra={"RMXGREP_RMX": "/nonexistent/rmx"})
    assert got.returncode == 0
    assert "hit" in got.stdout


def test_rich_mode_forces_rmx_even_when_piped(tmp_path):
    """RMXGREP_MODE=rich: agent shells are never a tty but want the index
    path. Fake rmx proves delegation; exit 2 proves fallback still guards."""
    (tmp_path / ".refmatrix").mkdir()
    fake = tmp_path / "fakermx"
    fake.write_text("#!/bin/sh\n[ \"$1\" = grep ] && { echo RMXPATH; exit 0; }\nexit 9\n")
    fake.chmod(0o755)
    got = _run(["pat", "f"], cwd=tmp_path,
               env_extra={"RMXGREP_MODE": "rich",
                          "RMXGREP_RMX": str(fake)})
    assert got.stdout.strip() == "RMXPATH"


def test_rich_mode_exit2_falls_back_to_real_grep(tmp_path):
    (tmp_path / ".refmatrix").mkdir()
    f = tmp_path / "a.txt"
    f.write_text("hit\n", encoding="utf8")
    fake = tmp_path / "fakermx"
    fake.write_text("#!/bin/sh\nexit 2\n")
    fake.chmod(0o755)
    got = _run(["hit", str(f)], cwd=tmp_path,
               env_extra={"RMXGREP_MODE": "rich",
                          "RMXGREP_RMX": str(fake)})
    assert "hit" in got.stdout
    assert got.returncode == 0


def test_plain_mode_teach_ping_writes_throttle_stamp(tmp_path):
    (tmp_path / ".refmatrix").mkdir()
    f = tmp_path / "a.txt"
    f.write_text("hit\n", encoding="utf8")
    fake = tmp_path / "fakermx"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    got = _run(["hit", str(f)], cwd=tmp_path,
               env_extra={"RMXGREP_MODE": "plain",
                          "RMXGREP_RMX": str(fake)})
    assert got.returncode == 0 and "hit" in got.stdout
    stamps = list((tmp_path / ".refmatrix" / ".rmxgrep-teach").glob("*"))
    assert stamps, "throttle stamp not written"


def test_teach_disabled_writes_no_stamp(tmp_path):
    (tmp_path / ".refmatrix").mkdir()
    f = tmp_path / "a.txt"
    f.write_text("hit\n", encoding="utf8")
    fake = tmp_path / "fakermx"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    _run(["hit", str(f)], cwd=tmp_path,
         env_extra={"RMXGREP_MODE": "plain", "RMXGREP_TEACH": "0",
                    "RMXGREP_RMX": str(fake)})
    assert not (tmp_path / ".refmatrix" / ".rmxgrep-teach").exists()


def test_rmxrg_outside_project_is_rg_or_absent(tmp_path):
    import shutil
    rmxrg = RMXGREP.parent / "rmxrg"
    if shutil.which("rg") is None:
        pytest.skip("no rg on PATH")
    f = tmp_path / "a.txt"
    f.write_text("alpha\n", encoding="utf8")
    got = subprocess.run([str(rmxrg), "alpha", str(f)], cwd=tmp_path,
                         capture_output=True, text=True, timeout=30)
    assert got.returncode == 0
    assert "alpha" in got.stdout
