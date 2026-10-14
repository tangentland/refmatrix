"""bug-109: the long-lived `rmx mcp` server attributed STM writes to the wrong session.

The MCP server is spawned once per Claude Code process, so its `CLAUDE_CODE_SESSION_ID` is frozen
at spawn: after `/clear` (a new session in the same process) it still names the old session, and
`verbs.resolve_session` fell through to the newest ring on disk, which is right only while one
session is active. The fix (d9s, 2026-10-14): the input hook writes a pointer
`<root>/stm/by-pid/<claude_pid>.json` naming the session of the turn it is starting, and the MCP
server resolves through the pointer for its parent Claude process. A pid reuse is caught by the
recorded process start time.
"""
import io
import json
import os
import time

import pytest
from click.testing import CliRunner

from refmatrix import mcp, stm, verbs
from refmatrix.cli import main


@pytest.fixture
def root(tmp_path):
    r = tmp_path / ".refmatrix"
    r.mkdir()
    return r


@pytest.fixture
def long_lived(monkeypatch):
    monkeypatch.setattr(verbs, "_LONG_LIVED", True)


def _ring(root, session, age_s=0.0):
    """Write a one-event STM ring for `session`, its mtime `age_s` in the past."""
    s = stm.Stm(root, session)
    s.record("input", f"prompt in {session}")
    p = stm.stm_dir(root) / f"{session}.jsonl"
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


def test_pointer_round_trips_for_a_live_pid(root):
    pid = os.getpid()
    assert stm.write_pid_pointer(root, pid, "sess-A") is True
    assert stm.read_pid_pointer(root, pid) == "sess-A"
    assert (stm.stm_dir(root) / "by-pid" / f"{pid}.json").is_file()


def test_unchanged_pointer_is_not_rewritten(root):
    pid = os.getpid()
    stm.write_pid_pointer(root, pid, "sess-A")
    assert stm.write_pid_pointer(root, pid, "sess-A") is False
    assert stm.write_pid_pointer(root, pid, "sess-B") is True
    assert stm.read_pid_pointer(root, pid) == "sess-B"


def test_a_pointer_from_a_reused_pid_is_ignored(root):
    pid = os.getpid()
    stm.write_pid_pointer(root, pid, "sess-A")
    p = stm.stm_dir(root) / "by-pid" / f"{pid}.json"
    d = json.loads(p.read_text())
    d["pid_start"] = "Thu Jan  1 00:00:00 1970"   # a different process once held this pid
    p.write_text(json.dumps(d))
    assert stm.read_pid_pointer(root, pid) is None


def test_mcp_resolves_the_pointer_not_its_frozen_env_or_the_newest_ring(
        root, long_lived, monkeypatch):
    """The live failure: session A was cleared into session B in the same Claude process; a
    second, parallel session C wrote the newest ring. The MCP server's env still says A."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-A")
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))   # the owner; see the ancestry test below
    _ring(root, "sess-A", age_s=300)
    _ring(root, "sess-B", age_s=60)
    _ring(root, "sess-C", age_s=0)           # newest ring belongs to ANOTHER session
    stm.write_pid_pointer(root, os.getpid(), "sess-B")
    assert verbs.resolve_session(root, None) == "sess-B"


def test_mcp_with_no_pointer_never_uses_its_frozen_env(root, long_lived, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-A")
    monkeypatch.delenv("RMX_SESSION", raising=False)
    _ring(root, "sess-C", age_s=0)
    assert verbs.resolve_session(root, None) != "sess-A"


def test_explicit_session_still_wins_over_the_pointer(root, long_lived, monkeypatch):
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    stm.write_pid_pointer(root, os.getpid(), "sess-B")
    assert verbs.resolve_session(root, "sess-X") == "sess-X"


def test_cli_resolves_through_the_claude_pid_pointer(root, monkeypatch):
    """A Bash-tool `rmx` run: $CLAUDE_PID names the owning Claude process, so CLI and MCP land in
    the same ring even while another session wrote the newest one."""
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    _ring(root, "sess-B", age_s=60)
    _ring(root, "sess-C", age_s=0)
    stm.write_pid_pointer(root, os.getpid(), "sess-B")
    assert verbs.resolve_session(root, None) == "sess-B"


def test_input_hook_writes_the_pointer(root, monkeypatch):
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    env = {"session_id": "sess-B", "prompt": "fix the resolver please",
           "hook_event_name": "UserPromptSubmit"}
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"], input=json.dumps(env))
    assert r.exit_code == 0, r.output
    assert stm.read_pid_pointer(root, os.getpid()) == "sess-B"


def test_serve_stdio_marks_the_process_long_lived(monkeypatch):
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    mcp.serve_stdio()
    assert verbs._LONG_LIVED is True


def test_owner_is_the_nearest_claude_ancestor_when_claude_pid_is_unset(tmp_path):
    """The MCP server's env has no $CLAUDE_PID; its owner is found by walking up to the process
    whose command is `claude`. A copy of /bin/sh named `claude` runs a Python child (the `; :`
    keeps sh from exec-ing into it), and the child must name sh's pid."""
    import shutil
    import subprocess
    import sys
    fake = tmp_path / "claude"
    shutil.copy("/bin/sh", fake)
    code = "from refmatrix import stm; print(stm.owner_claude_pid())"
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PID"}
    out = subprocess.run(
        [str(fake), "-c", f'echo $$; "{sys.executable}" -c "{code}"; :'],
        capture_output=True, text=True, env=env, timeout=30).stdout.split()
    assert len(out) == 2, out
    assert out[1] == out[0]
