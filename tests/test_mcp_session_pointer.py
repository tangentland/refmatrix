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


# ---- r3 (ch-bsd bsd-bug109-r3-261c574) --------------------------------------------------------
# Each pin below names the r3 mutant it kills (workflow/review-output/bug109-r3remedy-mutations.log).

def test_kernel_lookup_reads_the_real_ppid_and_needs_no_subprocess(monkeypatch):
    """r3 #b-1 P1: a wrong `proc_bsdinfo` ppid offset made the walk stop at length 1, and the `ps`
    fallback then hid it. Under a real $CLAUDE_PID the owner lookup runs NO subprocess at all, and
    the struct's ppid is the kernel's."""
    import subprocess
    calls = []
    orig = subprocess.run

    def spy(*a, **kw):
        calls.append(a)
        return orig(*a, **kw)
    monkeypatch.setattr(subprocess, "run", spy)
    monkeypatch.setenv("CLAUDE_PID", str(os.getppid()))
    assert stm._proc_info(os.getpid())[0] == os.getppid()
    assert stm.owner_lookup() == (os.getppid(), "found")
    assert calls == [], calls


def test_hook_records_a_failed_lookup_as_failed_not_no_owner(root, monkeypatch):
    """r3 #b-1 P3: the hook half of r2 #b-1. A lookup that FAILED is unknown, not absent."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.setattr(stm, "owner_lookup", lambda: (None, "failed"))
    stm.stm_dir(root).mkdir(parents=True, exist_ok=True)
    env = {"session_id": "sess-B", "prompt": "a prompt", "hook_event_name": "UserPromptSubmit"}
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"], input=json.dumps(env))
    assert r.exit_code == 0, r.output
    assert _errors(root)[-1]["reason"] == "owner-lookup-failed", _errors(root)


def test_hook_records_a_pointer_write_that_raised(root, monkeypatch):
    """r3 #b-1 P5 (r2 N4): the hook's stderr goes to /dev/null, so an OSError writing the pointer
    must land in the sink as `write-failed`."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.setattr(stm, "owner_lookup", lambda: (os.getpid(), "found"))

    def boom(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(stm, "write_pid_pointer", boom)
    stm.stm_dir(root).mkdir(parents=True, exist_ok=True)
    env = {"session_id": "sess-B", "prompt": "a prompt", "hook_event_name": "UserPromptSubmit"}
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"], input=json.dumps(env))
    assert r.exit_code == 0, r.output
    row = _errors(root)[-1]
    assert row["reason"] == "write-failed" and "disk full" in row["error"], row


def test_a_set_claude_pid_makes_a_guess_recorded(root, monkeypatch):
    """r3 #b-1 P6: with no owner found but $CLAUDE_PID set, this process may run under Claude, so
    the newest-ring guess is recorded (r2 #b-1)."""
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.setenv("CLAUDE_PID", "424242")
    monkeypatch.setattr(stm, "owner_lookup", lambda: (None, "none"))
    _ring(root, "sess-C", age_s=0)
    assert verbs.resolve_session_source(root, None) == ("sess-C", "latest")
    errs = _errors(root)
    assert len(errs) == 1 and errs[0]["reason"] == "pointer-unresolved", errs


def test_the_sink_never_raises_and_neither_does_the_resolve(root, long_lived, monkeypatch):
    """r3 #b-1 P8 (r2 #s-1): an unwritable sink returns False, and the read that recorded through it
    still resolves."""
    monkeypatch.delenv("RMX_SESSION", raising=False)
    (stm.stm_dir(root) / "by-pid" / "_errors.jsonl").mkdir(parents=True)   # open("a") -> OSError
    assert stm.record_pointer_error(root, "pointer-unresolved") is False
    _ring(root, "sess-C", age_s=0)
    assert verbs.resolve_session_source(root, None) == ("sess-C", "latest")


def test_the_sink_is_capped(root):
    """r3 P7: past 256 KiB the oldest half is dropped, so a hook firing every turn cannot grow the
    file without bound."""
    p = stm.stm_dir(root) / "by-pid" / "_errors.jsonl"
    p.parent.mkdir(parents=True)
    line = json.dumps({"t": time.time(), "reason": "pointer-unresolved", "pad": "x" * 200}) + "\n"
    p.write_text(line * ((stm._ERRORS_MAX_BYTES // len(line)) + 50))
    before = p.stat().st_size
    assert before > stm._ERRORS_MAX_BYTES
    assert stm.record_pointer_error(root, "pointer-unresolved") is True
    assert p.stat().st_size < before * 0.6, (before, p.stat().st_size)


def test_the_anomaly_reads_only_the_window(root):
    """r3 P9: a failure older than the window is history, not an anomaly."""
    from refmatrix import handoff
    p = stm.stm_dir(root) / "by-pid" / "_errors.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"t": time.time() - 3 * 86400, "reason": "no-owner"}) + "\n")
    assert handoff.session_pointer_anomalies(root) == []


def test_native_installer_binary_counts_as_claude():
    """r3 P12: the native installer runs `.../claude/versions/<x.y.z>`, whose name is the version."""
    assert stm._is_claude("/Users/u/.local/share/claude/versions/2.1.290")
    assert stm._is_claude("/usr/local/bin/claude")
    assert not stm._is_claude("/Users/u/.local/share/other/versions/2.1.290")
    assert not stm._is_claude("/bin/bash")


@pytest.mark.skipif(not __import__("sys").platform == "darwin", reason="libproc start format")
def test_pid_start_resolves_below_one_second():
    """r3 P13: two incarnations of one pid inside the same second must not share a start stamp."""
    import re
    assert re.fullmatch(r"\d+\.\d{6}", stm._proc_start(os.getpid())), stm._proc_start(os.getpid())


def test_save_state_reports_its_source(root, long_lived, monkeypatch, tmp_path):
    """r3 #b-1 P4 (r2 N5): save_state is a write verb and carries `session_source` too."""
    monkeypatch.delenv("RMX_SESSION", raising=False)
    stm.write_pid_pointer(root, os.getppid(), "sess-B")
    r = verbs.save_state(root, dry_run=True, promote=False, lint=False, sync=False,
                         memory_dir=str(tmp_path / "mem"))
    assert r.get("session") == "sess-B" and r.get("session_source") == "pointer", r


@pytest.mark.parametrize("argv, verb", [
    (["task", "push", "a task"], "task"),
    (["save-state", "--dry-run", "--no-lint", "--no-promote", "--no-sync"], "save_state"),
])
def test_cli_task_and_save_state_let_the_verb_resolve(root, monkeypatch, argv, verb):
    """r3 #b-1 P10/P11 (r2 #s-2): the CLI must hand the verb the raw `--session` (None here), or a
    guess is labelled `explicit`."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_SESSION", raising=False)
    seen = {}

    def spy(r, **kw):
        seen["session"] = kw.get("session", "MISSING")
        raise verbs.VerbError("stop after capture")
    monkeypatch.setattr(verbs, verb, spy)
    r = CliRunner().invoke(main, argv)
    assert "stop after capture" in r.output, r.output
    assert seen == {"session": None}, seen


# ---- r3 SKETCHY / MEH remedies (RED at 261c574) -----------------------------------------------

def test_a_stale_pointer_for_the_current_session_is_rewritten(root):
    """r3 #s-1: the same-session shortcut never compared `pid_start`, so a pointer from an older
    build (r1 wrote `ps lstart`) naming the CURRENT session stayed stale all session, and every
    resolve guessed."""
    pid = os.getpid()
    p = stm.pid_pointer_path(root, pid)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"session": "sess-H", "pid": pid,
                             "pid_start": "Tue Oct  6 22:27:56 2026", "t": 0}))
    assert stm.read_pid_pointer(root, pid) is None
    assert stm.write_pid_pointer(root, pid, "sess-H") is True
    assert stm.read_pid_pointer(root, pid) == "sess-H"
    assert stm.write_pid_pointer(root, pid, "sess-H") is False      # now the shortcut holds


def test_a_malformed_sink_line_does_not_break_recall_state(root, tmp_path):
    """r3 #m-2: a non-dict line or a non-numeric `t` raised out of `read_pointer_errors` and took
    down `rmx recall-state`. Unreadable lines are counted, not skipped silently."""
    from refmatrix import handoff
    s = stm.Stm(root, "sess-B")
    s.record("input", "a prompt")
    p = stm.stm_dir(root) / "by-pid" / "_errors.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2]\n" + json.dumps({"t": "soon", "reason": "x"}) + "\nnot json\n")
    stm.record_pointer_error(root, "pointer-unresolved", owner=1)
    rep = handoff.compose_recall_state(s, root, repo=tmp_path, memdir=tmp_path / "mem")
    msg = [a for a in rep["anomalies"] if "session-pointer" in a]
    assert msg and "pointer-unresolved x1" in msg[0] and "3 unreadable" in msg[0], msg


def test_the_anomaly_says_calls_not_writes(root):
    """r3 #m-1: a READ that guesses records the same row as a write, so the anomaly cannot claim
    writes."""
    from refmatrix import handoff
    stm.stm_dir(root).mkdir(parents=True, exist_ok=True)
    stm.record_pointer_error(root, "pointer-unresolved", owner=1)
    a = handoff.session_pointer_anomalies(root)
    assert a and "STM calls may have used a guessed session" in a[0], a


def test_only_unreadable_lines_still_surface(root):
    """r3 #m-2: a log holding nothing but garbage is itself an anomaly, not an empty report."""
    from refmatrix import handoff
    p = stm.stm_dir(root) / "by-pid" / "_errors.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text("[1, 2]\n")
    assert handoff.session_pointer_anomalies(root) == [
        "session-pointer log has 1 unreadable line(s); see stm/by-pid/_errors.jsonl"]


# ---- r4 (ch-bsd bsd-bug109-r4-ab19016): the remedy's own guards, pinned -------------------------

def _sink(root):
    return stm.stm_dir(root) / "by-pid" / "_errors.jsonl"


def test_the_sink_trim_keeps_the_newest_half(root, monkeypatch):
    """r4 Q1: past the cap the OLDEST half goes; the cap test only measured size."""
    stm.stm_dir(root).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(stm, "_ERRORS_MAX_BYTES", 2000)
    for i in range(80):
        stm.record_pointer_error(root, "pointer-unresolved", seq=i)
    seqs = [json.loads(l)["seq"] for l in _sink(root).read_text().splitlines()]
    assert seqs[-1] == 79 and 0 not in seqs, seqs[:3]


def test_a_non_dict_pointer_is_rewritten_not_fatal(root):
    """r4 Q2 / #m-1: a pointer file holding a JSON list must not crash the hook or the resolve."""
    pid = os.getpid()
    p = stm.pid_pointer_path(root, pid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2]")
    assert stm.read_pid_pointer(root, pid) is None
    assert stm.write_pid_pointer(root, pid, "sess-A") is True
    assert stm.read_pid_pointer(root, pid) == "sess-A"


@pytest.mark.parametrize("bad", [b'{"reason": "no-t"}\n', b'{"t": null}\n', b'{"t": NaN}\n',
                                 b'\xff\xfe not utf-8\n'])
def test_every_corrupt_sink_line_is_counted_never_raised(root, bad):
    """r4 Q10/Q11 + #m-1: missing `t` (KeyError), null `t` (TypeError), NaN `t` (was dropped
    uncounted) and a non-UTF-8 byte (was UnicodeDecodeError out of recall-state)."""
    stm.stm_dir(root).mkdir(parents=True, exist_ok=True)
    _sink(root).parent.mkdir(parents=True, exist_ok=True)
    _sink(root).write_bytes(bad)
    rows = stm.read_pointer_errors(root, since=0.0)
    assert rows == [{"reason": "unreadable-line", "line": 1}], rows
    stm.record_pointer_error(root, "pointer-unresolved")   # the append path must not raise either
