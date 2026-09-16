"""`memory_brief` against a REAL spawned daemon — the test ch-bsd r1 #b-8 asked for.

Every other daemon-op test in this range monkeypatches `daemon._read_with_fallback`,
which is the exact function whose use IS the claim ("derivation runs on the read
path"). Per CLAUDE.md #no-mocks, a test that patches the thing under test is not
a test. This one spawns a daemon on a short tmp root and drives the op over the
socket.

Short root: macOS `sun_path` is ~104 bytes (CLAUDE.md #system-dependent-tests).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

RMX = Path(__file__).resolve().parents[1] / ".venv-eval" / "bin" / "rmx"
pytestmark = pytest.mark.skipif(not RMX.exists(), reason="dev rmx not built")


@pytest.fixture
def daemon_root():
    tmp = Path(tempfile.mkdtemp(prefix="/tmp/bd."))
    root = tmp / ".refmatrix"
    env = {**os.environ, "REFMATRIX_ROOT": str(root),
           "RMX_INVOCATION_SOURCE": "eval"}
    subprocess.run([str(RMX), "init", "--path", str(tmp), "--no-hooks",
                    "--no-agents", "--no-memory-hooks"],
                   env=env, capture_output=True, timeout=120)
    subprocess.run([str(RMX), "daemon", "start", "--no-watch"],
                   env=env, capture_output=True, timeout=180)
    for _ in range(60):
        if list(root.glob("*.sock")):
            break
        time.sleep(1)
    yield root, env
    subprocess.run([str(RMX), "daemon", "stop"], env=env,
                   capture_output=True, timeout=120)
    shutil.rmtree(tmp, ignore_errors=True)


def _rmx(env, *args, timeout=180):
    return subprocess.run([str(RMX), *args], env=env, capture_output=True,
                          text=True, timeout=timeout)


def test_brief_runs_end_to_end_through_a_real_daemon(daemon_root):
    root, env = daemon_root
    assert list(root.glob("*.sock")), "daemon never bound"

    _rmx(env, "memory", "add", "note-a", "the daemon owns the duckdb catalog")
    _rmx(env, "memory", "add", "note-b", "the catalog is owned by one writer")

    p = _rmx(env, "memory", "brief", "--json")
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert "briefs" in payload and "stats" in payload


def test_the_gmd_flag_does_not_crash_through_a_real_daemon(daemon_root):
    """#b-1 died here on every real invocation while a unit test passed."""
    root, env = daemon_root
    _rmx(env, "memory", "add", "note-a", "a body long enough to matter")
    p = _rmx(env, "memory", "brief", "--gmd")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "AttributeError" not in (p.stdout + p.stderr)


def test_saved_briefs_do_not_grow_the_corpus_on_rerun(daemon_root):
    """#b-4 live: the tool reported its own rows back as a coverage gap."""
    root, env = daemon_root
    for i in range(5):
        _rmx(env, "memory", "add", f"m{i}", f"shared orphanterm body {i}")

    first = json.loads(_rmx(env, "memory", "brief", "--json",
                            "--min-mentions", "2", "--save").stdout)
    second = json.loads(_rmx(env, "memory", "brief", "--json",
                             "--min-mentions", "2").stdout)
    assert second["stats"]["memories"] == first["stats"]["memories"], (
        "a saved brief re-entered its own corpus")


def test_an_unknown_class_fails_loudly_through_the_daemon(daemon_root):
    """#m-17: the MCP schema has no enum, so this path is reachable."""
    root, env = daemon_root
    p = _rmx(env, "memory", "brief", "--json", "--class", "bogus-class")
    assert p.returncode != 0
