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
    _ring(root, "sess-A", age_s=300)
    _ring(root, "sess-B", age_s=60)
    _ring(root, "sess-C", age_s=0)           # newest ring belongs to ANOTHER session
    stm.write_pid_pointer(root, os.getppid(), "sess-B")   # the server's owner is its parent
    assert verbs.resolve_session(root, None) == "sess-B"


def test_mcp_with_no_pointer_falls_back_LOUDLY(root, long_lived, monkeypatch):
    """r1 #b-1/#s-2: with no pointer the long-lived server can only guess (the newest ring). The
    guess must be labelled and recorded where the hook's `2>/dev/null` cannot swallow it; the old
    version of this test blessed the misroute and passed on unfixed code."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-A")
    monkeypatch.delenv("RMX_SESSION", raising=False)
    _ring(root, "sess-C", age_s=0)
    sess, source = verbs.resolve_session_source(root, None)
    assert sess != "sess-A"
    assert source == "latest"
    errs = _errors(root)
    assert errs and errs[-1]["reason"] == "pointer-unresolved", errs


def _errors(root):
    p = stm.stm_dir(root) / "by-pid" / "_errors.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_mcp_owner_is_its_parent_pid_not_an_inherited_claude_pid(root, long_lived, monkeypatch):
    """r1 #s-1: the spec keys the long-lived server on os.getppid(); an inherited $CLAUDE_PID
    naming some other Claude must not win."""
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.setenv("CLAUDE_PID", "1")
    stm.write_pid_pointer(root, os.getppid(), "sess-parent")
    assert verbs.resolve_session_source(root, None) == ("sess-parent", "pointer")


def test_a_claude_pid_that_is_not_an_ancestor_is_ignored(monkeypatch):
    """r1 #s-1: a stale or foreign $CLAUDE_PID (here pid 1, launchd) is not this process's owner."""
    monkeypatch.setenv("CLAUDE_PID", "1")
    assert stm.owner_claude_pid() != 1


def test_ps_failure_never_writes_a_pointer_that_reads_as_absent(root):
    """r1 #b-1: a pointer stored with pid_start null is ignored forever, silently. A pid with no
    process (so `ps` reports nothing) is refused and recorded instead."""
    dead = 999_999
    assert stm.write_pid_pointer(root, dead, "sess-X") is False
    assert not stm.pid_pointer_path(root, dead).exists()
    assert _errors(root)[-1]["reason"] == "ps-failed"


def test_write_verbs_report_where_their_session_came_from(root, long_lived, monkeypatch):
    monkeypatch.delenv("RMX_SESSION", raising=False)
    stm.write_pid_pointer(root, os.getppid(), "sess-B")
    r = verbs.focus_note(root, "why the resolver changed")
    assert r["session"] == "sess-B" and r["session_source"] == "pointer", r


def test_explicit_session_still_wins_over_the_pointer(root, long_lived, monkeypatch):
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    stm.write_pid_pointer(root, os.getpid(), "sess-B")
    assert verbs.resolve_session(root, "sess-X") == "sess-X"


def test_cli_resolves_through_the_claude_pid_pointer(root, monkeypatch):
    """A Bash-tool `rmx` run: $CLAUDE_PID names the owning Claude process (an ANCESTOR, r1 #s-1;
    the test's own pid counts as its own chain), so CLI and MCP land in the same ring even while
    another session wrote the newest one."""
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


def test_promote_edges_sends_the_resolved_session_to_the_daemon(root, monkeypatch):
    """r1 #s-3: `focus promote-edges --apply` resolved its session INSIDE the daemon, which has
    neither $CLAUDE_PID nor a claude ancestor, so it always took the newest ring. The CLI now
    resolves it and passes it."""
    from refmatrix import cli as cli_mod
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    _ring(root, "sess-B", age_s=60)
    _ring(root, "sess-C", age_s=0)
    stm.write_pid_pointer(root, os.getpid(), "sess-B")
    sent = {}

    def fake_call(op, args, timeout=0.0):
        sent.update(args)
        return {"ok": True, "result": {"would_promote": 0, "pairs": []}}
    monkeypatch.setattr(cli_mod, "_memory_daemon_call", fake_call)
    r = CliRunner().invoke(main, ["focus", "promote-edges"])
    assert r.exit_code == 0, r.output
    assert sent.get("session") == "sess-B", sent


# ---- r2 (ch-bsd bsd-bug109-r2-320dc82) --------------------------------------------------------

def test_a_failed_process_lookup_is_recorded_not_mistaken_for_a_plain_terminal(root, monkeypatch):
    """r2 #b-1: when the process lookup itself fails, the owner is UNKNOWN, not absent. The resolve
    must record it, not fall silently to the newest ring the way a plain terminal does."""
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.setattr(stm, "_proc_info", lambda pid: None)       # every lookup fails
    monkeypatch.setattr(stm, "_ps_comm_chain", lambda: None)        # and so does the ps fallback
    _ring(root, "sess-C", age_s=0)
    sess, source = verbs.resolve_session_source(root, None)
    assert source == "latest"
    assert _errors(root)[-1]["reason"] == "owner-lookup-failed", _errors(root)


def test_outside_claude_nothing_is_recorded(root, monkeypatch):
    """r2 #s-2 / N1: a plain terminal (no $CLAUDE_PID, no claude ancestor) guesses silently, by
    design: there is no pointer to miss."""
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    monkeypatch.setattr(stm, "owner_lookup", lambda: (None, "none"))
    _ring(root, "sess-C", age_s=0)
    assert verbs.resolve_session_source(root, None) == ("sess-C", "latest")
    assert _errors(root) == []


def test_a_read_never_creates_a_store(tmp_path, long_lived, monkeypatch):
    """r2 #s-1: recording an error must not mkdir <cwd>/.refmatrix (it would hijack cli._root())
    nor fail the read when the root is unwritable."""
    monkeypatch.delenv("RMX_SESSION", raising=False)
    ghost = tmp_path / "nostore" / ".refmatrix"
    verbs.resolve_session_source(ghost, None)
    assert not ghost.exists()


def test_cli_note_reports_the_real_source_not_explicit(root, monkeypatch):
    """r2 #s-2: the CLI resolved the session itself and passed it in as explicit, so a guess was
    labelled `explicit`. It now lets the verb resolve and label."""
    from refmatrix import verbs as v
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_SESSION", raising=False)
    seen = {}
    orig = v.focus_note

    def spy(r, text, *, session=None):
        seen["session"] = session
        return orig(r, text, session=session)
    monkeypatch.setattr(v, "focus_note", spy)
    r = CliRunner().invoke(main, ["focus", "note", "a reason"])
    assert r.exit_code == 0, r.output
    assert seen["session"] is None


@pytest.mark.parametrize("verb_call", [
    lambda root: verbs.task(root, action="push", desc="t1"),
    lambda root: verbs.change_subject(root, "a subject"),
])
def test_every_stm_write_verb_reports_its_source(root, long_lived, monkeypatch, verb_call):
    """r2 #s-3 (N5-N7): `session_source` rides on every write verb, not only focus_note."""
    monkeypatch.delenv("RMX_SESSION", raising=False)
    stm.write_pid_pointer(root, os.getppid(), "sess-B")
    r = verb_call(root)
    assert r.get("session_source") == "pointer", r


def test_cli_lets_an_explicit_rmx_session_beat_the_pointer(root, monkeypatch):
    """r2 #s-3 (N9): per-call CLI order is env before pointer; the server's is the reverse."""
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.setenv("RMX_SESSION", "sess-env")
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    stm.write_pid_pointer(root, os.getpid(), "sess-B")
    assert verbs.resolve_session_source(root, None) == ("sess-env", "env")


def test_hook_without_an_owner_records_no_owner(root, monkeypatch):
    """r2 #s-3 (N3)."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.setattr(stm, "owner_lookup", lambda: (None, "none"))
    (stm.stm_dir(root)).mkdir(parents=True, exist_ok=True)
    env = {"session_id": "sess-B", "prompt": "a prompt", "hook_event_name": "UserPromptSubmit"}
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"], input=json.dumps(env))
    assert r.exit_code == 0, r.output
    assert _errors(root)[-1]["reason"] == "no-owner"


def test_owner_walk_reaches_claude_through_a_deep_chain(tmp_path):
    """r2 #s-3 (N10): a real hook is python -> sh -> claude, a Bash-tool CLI is python -> bash ->
    bash -> claude. Three shell layers between the child and `claude` must still resolve."""
    import shutil
    import subprocess
    import sys
    fake = tmp_path / "claude"
    shutil.copy("/bin/sh", fake)
    code = "from refmatrix import stm; print(stm.owner_claude_pid())"
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PID"}
    inner = f'"{sys.executable}" -c "{code}"; :'
    cmd = f"echo $$; /bin/sh -c '/bin/sh -c '\"'\"'{inner}'\"'\"'; :'; :"
    out = subprocess.run([str(fake), "-c", cmd], capture_output=True, text=True, env=env,
                         timeout=30).stdout.split()
    assert len(out) == 2 and out[1] == out[0], out


def test_recall_state_surfaces_pointer_errors(root):
    """r2 #s-2: `_errors.jsonl` had no reader. recall-state names recent pointer failures as an
    anomaly."""
    from refmatrix import handoff
    stm.stm_dir(root).mkdir(parents=True, exist_ok=True)
    stm.record_pointer_error(root, "pointer-unresolved", owner=1)
    anomalies = handoff.session_pointer_anomalies(root)
    assert anomalies and "pointer" in anomalies[0], anomalies


def test_recall_state_report_carries_the_pointer_anomaly(root, tmp_path):
    """r2 #s-2, through the real composer (M16): the reader is wired into recall-state's
    anomalies, not merely defined."""
    from refmatrix import handoff
    s = stm.Stm(root, "sess-B")
    s.record("input", "a prompt")
    stm.record_pointer_error(root, "pointer-unresolved", owner=1)
    rep = handoff.compose_recall_state(s, root, repo=tmp_path, memdir=tmp_path / "mem")
    assert any("session-pointer" in a for a in rep["anomalies"]), rep["anomalies"]
