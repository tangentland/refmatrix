"""bug-109: the long-lived `rmx mcp` server attributed STM writes to the wrong session.

The MCP server is spawned once per Claude Code process, so its `CLAUDE_CODE_SESSION_ID` is frozen
at spawn: after `/clear` (a new session in the same process) it still names the old session, and
`verbs.resolve_session` fell through to the newest ring on disk, which is right only while one
session is active. The fix (d9s, 2026-10-14): the input hook writes a pointer
`<root>/stm/by-pid/<claude_pid>.json` naming the session of the turn it is starting, and the MCP
server resolves through the pointer for its parent Claude process. A pid reuse is caught by the
recorded process start time.

Task 21.1 (R9 deltas D1-D8) re-pins these tests to the extended API: the pointer and its error log
live under the USER-level `stm.pointer_dir()` (`<global store root>/by-pid/`, D3), keyed by the
Claude pid only (`write_pid_pointer(pid, session, *, root)`, `read_pid_pointer(pid, *, root)`, where
`root` only scopes the error rows); `record_pointer_error(reason, *, root, owner, **fields)` writes
scoped rows (D8); `read_pointer_errors(*, root=, owner=, since=)` (D6); and
`verbs.resolve_session_source(root, session, *, envelope=None, purpose=...)` with a REQUIRED
`purpose` (D1) whose `event` tail is `(None, "none")` and whose `write` tail raises (D2). The str
wrapper `verbs.resolve_session` is removed (Files-to-modify, verbs row).
"""
import io
import json
import os
import time
from pathlib import Path

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


def _global_by_pid():
    """D3's location, computed from the hub's global root (the sandbox's `$RMX_HOME`), not
    from `stm.pointer_dir()`, so a helper never fails on the function it is testing."""
    from refmatrix import hub
    return Path(hub.global_store_root()) / "by-pid"


@pytest.fixture(autouse=True)
def _no_pointer_for_this_process(monkeypatch):
    """D3 makes pointers user-level: one file per Claude pid for EVERY store. The suite runs
    every test in one process, so a pointer an earlier test wrote for `os.getpid()` (or its
    parent) would resolve in the next one. Removed before and after each test; and the
    Claude-session env the suite inherits from its own runner is stripped."""
    for k in ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_CODE_SESSION_ID", "RMX_SESSION",
              "RMX_INVOCATION_SOURCE"):
        monkeypatch.delenv(k, raising=False)

    def _clear():
        for pid in (os.getpid(), os.getppid()):
            try:
                (_global_by_pid() / f"{pid}.json").unlink()
            except FileNotFoundError:
                pass
    _clear()
    yield
    _clear()


def _ring(root, session, age_s=0.0):
    """Write a one-event STM ring for `session`, its mtime `age_s` in the past."""
    s = stm.Stm(root, session)
    s.record("input", f"prompt in {session}")
    p = stm.stm_dir(root) / f"{session}.jsonl"
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


def test_pointer_round_trips_for_a_live_pid(root):
    """21.1 D3 re-pin: the pointer lives under the user-level `stm.pointer_dir()`, not under
    the store's `stm/by-pid/`."""
    pid = os.getpid()
    assert stm.write_pid_pointer(pid, "sess-A", root=root) is True
    assert stm.read_pid_pointer(pid, root=root) == "sess-A"
    assert (stm.pointer_dir() / f"{pid}.json").is_file()
    assert stm.pointer_dir() == _global_by_pid()
    assert not (stm.stm_dir(root) / "by-pid" / f"{pid}.json").exists()


def test_unchanged_pointer_is_not_rewritten(root):
    pid = os.getpid()
    stm.write_pid_pointer(pid, "sess-A", root=root)
    assert stm.write_pid_pointer(pid, "sess-A", root=root) is False
    assert stm.write_pid_pointer(pid, "sess-B", root=root) is True
    assert stm.read_pid_pointer(pid, root=root) == "sess-B"


def test_a_pointer_from_a_reused_pid_is_ignored(root):
    pid = os.getpid()
    stm.write_pid_pointer(pid, "sess-A", root=root)
    p = stm.pid_pointer_path(pid)
    d = json.loads(p.read_text())
    d["pid_start"] = "Thu Jan  1 00:00:00 1970"   # a different process once held this pid
    p.write_text(json.dumps(d))
    assert stm.read_pid_pointer(pid, root=root) is None


def test_mcp_resolves_the_pointer_not_its_frozen_env_or_the_newest_ring(
        root, long_lived, monkeypatch):
    """The live failure: session A was cleared into session B in the same Claude process; a
    second, parallel session C wrote the newest ring. The MCP server's env still says A."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-A")
    monkeypatch.delenv("RMX_SESSION", raising=False)
    _ring(root, "sess-A", age_s=300)
    _ring(root, "sess-B", age_s=60)
    _ring(root, "sess-C", age_s=0)           # newest ring belongs to ANOTHER session
    stm.write_pid_pointer(os.getppid(), "sess-B", root=root)   # the server's owner is its parent
    for purpose in ("read", "write", "event"):
        assert verbs.resolve_session_source(root, None, purpose=purpose) == ("sess-B", "pointer")


def test_mcp_with_no_pointer_falls_back_LOUDLY(root, long_lived, monkeypatch):
    """r1 #b-1/#s-2, re-pinned for 21.1 D1/D2: with no pointer the long-lived server guesses
    ONLY for a `read` (labelled `latest`); an `event` resolves to `(None, "none")` (the round-4
    #m-2 rule: never the newest ring) and a `write` raises `SessionUnresolved`. Each miss is
    recorded (round-7 #s-4), scoped to this root (D8)."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-A")
    monkeypatch.delenv("RMX_SESSION", raising=False)
    _ring(root, "sess-C", age_s=0)
    sess, source = verbs.resolve_session_source(root, None, purpose="read")
    assert sess != "sess-A"
    assert source == "latest"
    assert verbs.resolve_session_source(root, None, purpose="event") == (None, "none")
    with pytest.raises(verbs.SessionUnresolved):
        verbs.resolve_session_source(root, None, purpose="write")
    errs = _errors(root)
    assert [e["reason"] for e in errs] == ["pointer-unresolved"] * 3, errs


def _errors(root):
    """The rows of the ONE user-level log scoped to `root` (D6/D8), oldest first."""
    p = stm.errors_log_path()
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return [r for r in rows if isinstance(r, dict) and r.get("root") == str(root)]


def test_mcp_owner_is_its_parent_pid_not_an_inherited_claude_pid(root, long_lived, monkeypatch):
    """r1 #s-1: the spec keys the long-lived server on os.getppid(); an inherited $CLAUDE_PID
    naming some other Claude must not win."""
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.setenv("CLAUDE_PID", "1")
    stm.write_pid_pointer(os.getppid(), "sess-parent", root=root)
    assert verbs.resolve_session_source(root, None, purpose="read") == ("sess-parent", "pointer")


def test_a_claude_pid_that_is_not_an_ancestor_is_ignored(monkeypatch):
    """r1 #s-1: a stale or foreign $CLAUDE_PID (here pid 1, launchd) is not this process's owner."""
    monkeypatch.setenv("CLAUDE_PID", "1")
    assert stm.owner_claude_pid() != 1


def test_ps_failure_never_writes_a_pointer_that_reads_as_absent(root):
    """r1 #b-1: a pointer stored with pid_start null is ignored forever, silently. A pid with no
    process (so `ps` reports nothing) is refused and recorded instead."""
    dead = 999_999
    assert stm.write_pid_pointer(dead, "sess-X", root=root) is False
    assert not stm.pid_pointer_path(dead).exists()
    row = _errors(root)[-1]
    assert row["reason"] == "ps-failed"
    assert row["owner"] == dead and row["owner_start"] is None, row     # D8: unowned (#nm-1)


def test_write_verbs_report_where_their_session_came_from(root, long_lived, monkeypatch):
    monkeypatch.delenv("RMX_SESSION", raising=False)
    stm.write_pid_pointer(os.getppid(), "sess-B", root=root)
    r = verbs.focus_note(root, "why the resolver changed")
    assert r["session"] == "sess-B" and r["session_source"] == "pointer", r


def test_explicit_session_still_wins_over_the_pointer(root, long_lived, monkeypatch):
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    stm.write_pid_pointer(os.getpid(), "sess-B", root=root)
    for purpose in ("read", "write", "event"):
        assert verbs.resolve_session_source(root, "sess-X", purpose=purpose) == (
            "sess-X", "explicit")


def test_cli_resolves_through_the_claude_pid_pointer(root, monkeypatch):
    """A Bash-tool `rmx` run: $CLAUDE_PID names the owning Claude process (an ANCESTOR, r1 #s-1;
    the test's own pid counts as its own chain), so CLI and MCP land in the same ring even while
    another session wrote the newest one."""
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.delenv("RMX_SESSION", raising=False)
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    _ring(root, "sess-B", age_s=60)
    _ring(root, "sess-C", age_s=0)
    stm.write_pid_pointer(os.getpid(), "sess-B", root=root)
    assert verbs.resolve_session_source(root, None, purpose="read").session == "sess-B"


def test_input_hook_writes_the_pointer(root, monkeypatch):
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    env = {"session_id": "sess-B", "prompt": "fix the resolver please",
           "hook_event_name": "UserPromptSubmit"}
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"], input=json.dumps(env))
    assert r.exit_code == 0, r.output
    assert stm.read_pid_pointer(os.getpid(), root=root) == "sess-B"
    assert json.loads(stm.pid_pointer_path(os.getpid()).read_text())["hook"] == "input"   # D4


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
    stm.write_pid_pointer(os.getpid(), "sess-B", root=root)
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
    sess, source = verbs.resolve_session_source(root, None, purpose="read")
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
    assert verbs.resolve_session_source(root, None, purpose="read") == ("sess-C", "latest")
    assert _errors(root) == []


def test_a_read_never_creates_a_store(tmp_path, long_lived, monkeypatch):
    """r2 #s-1: recording an error must not mkdir <cwd>/.refmatrix (it would hijack cli._root())
    nor fail the read when the root is unwritable."""
    monkeypatch.delenv("RMX_SESSION", raising=False)
    ghost = tmp_path / "nostore" / ".refmatrix"
    verbs.resolve_session_source(ghost, None, purpose="read")
    verbs.resolve_session_source(ghost, None, purpose="event")
    assert not ghost.exists()


def test_cli_note_reports_the_real_source_not_explicit(root, monkeypatch):
    """r2 #s-2: the CLI resolved the session itself and passed it in as explicit, so a guess was
    labelled `explicit`. It now lets the verb resolve and label."""
    from refmatrix import verbs as v
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    # 21.1 D2: an unresolved WRITE now raises, so the session must resolve for the note to
    # land; $RMX_SESSION supplies it and the CLI must STILL pass session=None to the verb.
    monkeypatch.setenv("RMX_SESSION", "sess-env")
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
    stm.write_pid_pointer(os.getppid(), "sess-B", root=root)
    r = verb_call(root)
    assert r.get("session_source") == "pointer", r


def test_cli_lets_an_explicit_rmx_session_beat_the_pointer(root, monkeypatch):
    """r2 #s-3 (N9): per-call CLI order is env before pointer; the server's is the reverse."""
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.setenv("RMX_SESSION", "sess-env")
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    stm.write_pid_pointer(os.getpid(), "sess-B", root=root)
    assert verbs.resolve_session_source(root, None, purpose="read") == ("sess-env", "env")


def test_hook_without_an_owner_records_no_owner(root, monkeypatch):
    """r2 #s-3 (N3)."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.setattr(stm, "owner_lookup", lambda: (None, "none"))
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
    stm.record_pointer_error("pointer-unresolved", root=root, owner=1)
    anomalies = handoff.session_pointer_anomalies(root)
    assert anomalies and "pointer" in anomalies[0], anomalies


def test_recall_state_report_carries_the_pointer_anomaly(root, tmp_path):
    """r2 #s-2, through the real composer (M16): the reader is wired into recall-state's
    anomalies, not merely defined."""
    from refmatrix import handoff
    s = stm.Stm(root, "sess-B")
    s.record("input", "a prompt")
    stm.record_pointer_error("pointer-unresolved", root=root, owner=1)
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
    assert verbs.resolve_session_source(root, None, purpose="read") == ("sess-C", "latest")
    errs = _errors(root)
    assert len(errs) == 1 and errs[0]["reason"] == "pointer-unresolved", errs


def test_the_sink_never_raises_and_neither_does_the_resolve(root, long_lived, monkeypatch):
    """r3 #b-1 P8 (r2 #s-1): an unwritable sink returns False, and the read that recorded through it
    still resolves."""
    monkeypatch.delenv("RMX_SESSION", raising=False)
    p = stm.errors_log_path()
    moved = p.with_name(p.name + ".t21-aside")
    if p.exists():
        p.replace(moved)
    p.mkdir(parents=True)                                  # open("a") -> OSError
    try:
        assert stm.record_pointer_error("pointer-unresolved", root=root, owner=None) is False
        _ring(root, "sess-C", age_s=0)
        assert verbs.resolve_session_source(root, None, purpose="read") == ("sess-C", "latest")
    finally:
        p.rmdir()
        if moved.exists():
            moved.replace(p)


def test_the_sink_is_capped(root):
    """r3 P7: past 256 KiB the oldest half is dropped, so a hook firing every turn cannot grow the
    file without bound."""
    p = stm.errors_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"t": time.time(), "reason": "pointer-unresolved", "root": str(root),
                       "owner": None, "owner_start": None, "pad": "x" * 200}) + "\n"
    p.write_text(line * ((stm._ERRORS_MAX_BYTES // len(line)) + 50))
    before = p.stat().st_size
    assert before > stm._ERRORS_MAX_BYTES
    assert stm.record_pointer_error("pointer-unresolved", root=root, owner=None) is True
    assert p.stat().st_size < before * 0.6, (before, p.stat().st_size)


def test_the_anomaly_reads_only_the_window(root):
    """r3 P9: a failure older than the window is history, not an anomaly."""
    from refmatrix import handoff
    p = stm.errors_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"t": time.time() - 3 * 86400, "reason": "no-owner",
                            "root": str(root), "owner": None, "owner_start": None}) + "\n")
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
    stm.write_pid_pointer(os.getppid(), "sess-B", root=root)
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
    p = stm.pid_pointer_path(pid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"session": "sess-H", "pid": pid,
                             "pid_start": "Tue Oct  6 22:27:56 2026", "t": 0}))
    assert stm.read_pid_pointer(pid, root=root) is None
    assert stm.write_pid_pointer(pid, "sess-H", root=root) is True
    assert stm.read_pid_pointer(pid, root=root) == "sess-H"
    assert stm.write_pid_pointer(pid, "sess-H", root=root) is False      # now the shortcut holds


def test_a_malformed_sink_line_does_not_break_recall_state(root, tmp_path):
    """r3 #m-2: a non-dict line or a non-numeric `t` raised out of `read_pointer_errors` and took
    down `rmx recall-state`. Unreadable lines are counted, not skipped silently."""
    from refmatrix import handoff
    s = stm.Stm(root, "sess-B")
    s.record("input", "a prompt")
    p = stm.errors_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2]\n" + json.dumps({"t": "soon", "reason": "x", "root": str(root)})
                 + "\nnot json\n")
    stm.record_pointer_error("pointer-unresolved", root=root, owner=1)
    rep = handoff.compose_recall_state(s, root, repo=tmp_path, memdir=tmp_path / "mem")
    msg = [a for a in rep["anomalies"] if "session-pointer" in a]
    assert msg and "pointer-unresolved x1" in msg[0] and "3 unreadable" in msg[0], msg


def test_the_anomaly_says_calls_not_writes(root):
    """r3 #m-1, re-pinned for 21.1 D6: the session-pointer clause now states what each purpose
    did with the miss ("the session could not be resolved: reads used the labelled newest
    ring, writes were refused, events carry `session: null`"); the r3 "STM calls may have used
    a guessed session" wording is replaced by it."""
    from refmatrix import handoff
    stm.record_pointer_error("pointer-unresolved", root=root, owner=1)
    a = handoff.session_pointer_anomalies(root)
    assert a and "could not be resolved" in a[0] and "writes were refused" in a[0], a


def test_only_unreadable_lines_still_surface(root):
    """r3 #m-2: a log holding nothing but garbage is itself an anomaly, not an empty report."""
    from refmatrix import handoff
    p = stm.errors_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2]\n")
    a = handoff.session_pointer_anomalies(root)
    # 21.1 D6: the text names the NEW user-level path, never the store's stm/by-pid/.
    assert len(a) == 1 and "1 unreadable" in a[0], a
    assert "by-pid/_errors.jsonl" in a[0] and "stm/by-pid" not in a[0], a


# ---- r4 (ch-bsd bsd-bug109-r4-ab19016): the remedy's own guards, pinned -------------------------

def _sink(root):
    return stm.errors_log_path()


def test_the_sink_trim_keeps_the_newest_half(root, monkeypatch):
    """r4 Q1: past the cap the OLDEST half goes; the cap test only measured size."""
    monkeypatch.setattr(stm, "_ERRORS_MAX_BYTES", 2000)
    if _sink(root).exists():
        _sink(root).unlink()
    for i in range(80):
        stm.record_pointer_error("pointer-unresolved", root=root, owner=None, seq=i)
    rows = [json.loads(l) for l in _sink(root).read_text().splitlines()]
    seqs = [r["seq"] for r in rows if "seq" in r]    # D6: `errors-truncated` rows carry none
    assert seqs[-1] == 79 and 0 not in seqs, seqs[:3]


def test_a_non_dict_pointer_is_rewritten_not_fatal(root):
    """r4 Q2 / #m-1: a pointer file holding a JSON list must not crash the hook or the resolve."""
    pid = os.getpid()
    p = stm.pid_pointer_path(pid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2]")
    assert stm.read_pid_pointer(pid, root=root) is None
    assert _errors(root)[-1]["reason"] == "pointer-unreadable"          # D5: not silent
    assert stm.write_pid_pointer(pid, "sess-A", root=root) is True
    assert stm.read_pid_pointer(pid, root=root) == "sess-A"


@pytest.mark.parametrize("bad", [b'{"reason": "no-t"}\n', b'{"t": null}\n', b'{"t": NaN}\n',
                                 b'\xff\xfe not utf-8\n'])
def test_every_corrupt_sink_line_is_counted_never_raised(root, bad):
    """r4 Q10/Q11 + #m-1: missing `t` (KeyError), null `t` (TypeError), NaN `t` (was dropped
    uncounted) and a non-UTF-8 byte (was UnicodeDecodeError out of recall-state)."""
    _sink(root).parent.mkdir(parents=True, exist_ok=True)
    _sink(root).write_bytes(bad)
    rows = stm.read_pointer_errors(root=root, since=0.0)
    assert rows == [{"reason": "unreadable-line", "line": 1}], rows
    # the append path must not raise either
    stm.record_pointer_error("pointer-unresolved", root=root, owner=None)


# ==== task 21.1: AC-1b (session switch under ONE long-lived server) and AC-4 (session never
# guessed). Real children throughout: the generated hook commands, `rmx mcp`, `rmx scan-prompt`,
# `rmx focus note|tail`, run inside 23.0's sandbox with the per-test store root. ===============

import subprocess  # noqa: E402

from tests import task21_1_support as h  # noqa: E402


@pytest.fixture
def t21_root(live_guard_21):
    """The per-test sandbox store root (`REFMATRIX_ROOT`, short /tmp path for `sun_path`)."""
    return Path(os.environ["REFMATRIX_ROOT"])


@pytest.fixture
def live_guard_21():
    """AC preamble: the live query.log / recall-events.jsonl files did not move."""
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


def _t21_session_start_cmd(root):
    """The GENERATED SessionStart pointer writer (D4); when the generator lacks it (HEAD) the
    literal command the spec names, so a leg's recorded failure is its own state assertion and
    not the generator lookup (the generator leg asserts the entry itself)."""
    hits = [c for ev, _m, c in h.hook_entries(root, "SessionStart")
            if "focus hook --event session-start" in c]
    if hits:
        return hits[0]
    from refmatrix.hooks import HOOK_ENV
    return HOOK_ENV + "rmx focus hook --event session-start"


def _t21_session_start(root, session, source):
    return h.run_hook(_t21_session_start_cmd(root), root=root,
                      envelope={"session_id": session, "source": source,
                                "hook_event_name": "SessionStart"},
                      CLAUDE_PID=os.getpid())


def _t21_ring_lines(root, session):
    return h.line_count(stm.stm_dir(root) / f"{session}.jsonl")


def _t21_errors_path():
    return _global_by_pid() / "_errors.jsonl"


def _t21_err_lines():
    return h.line_count(_t21_errors_path())


def _t21_new_err_rows(before, root):
    """Rows appended to the user-level log since line `before`, scoped to `root` (D8)."""
    p = _t21_errors_path()
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text().splitlines()[before:] if l.strip()]
    return [r for r in rows if isinstance(r, dict) and r.get("root") == str(root)]


def _t21_compat_err_rows(root):
    """For the spec-named GREEN regression guards only: the miss rows wherever this build
    writes them (the user-level log scoped to `root` after D3/D8, bug-109's per-store
    `stm/by-pid/_errors.jsonl` at HEAD), so the guard pins the ROW, not its location."""
    p = _t21_errors_path()
    rows = []
    if p.exists():
        rows += [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        rows = [r for r in rows if isinstance(r, dict) and r.get("root") == str(root)]
    legacy = stm.stm_dir(root) / "by-pid" / "_errors.jsonl"
    if legacy.exists():
        rows += [json.loads(l) for l in legacy.read_text().splitlines() if l.strip()]
    return rows


def _t21_context_mcp_rows(root, before):
    return [r for r in h.query_rows(root)[before:] if r.get("source") == "context-mcp"]


# ---- AC-1b ---------------------------------------------------------------------------------

def test_ac1b_generator_has_the_session_start_pointer_entry(t21_root):
    """AC-1b generator leg (RED: the entry is absent). The generated hook config holds a
    SessionStart entry, matcher `startup|resume|clear|compact`, running
    `rmx focus hook --event session-start` with stderr kept (a memory path: no 2>/dev/null)."""
    hits = [(m, c) for ev, m, c in h.hook_entries(t21_root, "SessionStart")
            if "focus hook --event session-start" in c]
    assert len(hits) == 1, f"D4: no generated SessionStart pointer writer: {h.hook_entries(t21_root, 'SessionStart')}"
    matcher, cmd = hits[0]
    assert matcher == "startup|resume|clear|compact", matcher
    assert "2>/dev/null" not in cmd, cmd


def test_ac1b_switch_before_any_prompt_repoints_the_long_lived_server(t21_root):
    """AC-1b switch-before-prompt leg (RED; failing assertion: the row's `session == B`).
    ONE `rmx mcp` started with CLAUDE_CODE_SESSION_ID=A. The generated SessionStart command
    fed {A, startup} then {B, clear} with this process as the Claude owner, and NO input hook
    after the clear: `rmx_context` logs a context-mcp row with session B; `rmx_focus_note`
    lands in B's ring, A's ring unchanged; the pointer's `hook` field is `session-start:clear`."""
    root = t21_root
    stm.Stm(root, "A").record("input", "a prompt in A")       # A is the newest ring on disk
    a_before = _t21_ring_lines(root, "A")
    with h.SandboxDaemon(root), h.McpServer(root, CLAUDE_CODE_SESSION_ID="A") as srv:
        _t21_session_start(root, "A", "startup")
        _t21_session_start(root, "B", "clear")
        before = len(h.query_rows(root))
        srv.tool("rmx_context", {"ref": "anything_at_all"})
        note = srv.tool("rmx_focus_note", {"text": "a reason after the clear"})
    rows = _t21_context_mcp_rows(root, before)
    assert [r.get("session") for r in rows] == ["B"], (
        f"R9/D4: the context-mcp row must name B (pointer re-pointed by the clear): {rows}")
    assert _t21_ring_lines(root, "A") == a_before, f"the note landed in A: {note['text']}"
    assert _t21_ring_lines(root, "B") >= 1, note["text"]
    ptr = json.loads((_global_by_pid() / f"{os.getpid()}.json").read_text())
    assert ptr["session"] == "B" and ptr["hook"] == "session-start:clear", ptr


def test_ac1b_used_after_the_switch_lands_in_B(t21_root):
    """AC-1b used-after-switch leg (RED: no `used` events exist). With memory
    `feedback_alpha_rule` delivered in B (a prompt_recall through the GENERATED per-prompt
    recall hook with B's envelope), an `rmx_focus_note` naming it emits ONE `used` event with
    session B and `ref_query_id` = that delivery's `query_id`."""
    root = t21_root
    stm.Stm(root, "A").record("input", "a prompt in A")
    recall_cmd = h.generated_cmd(root, "UserPromptSubmit", "memory recall --stdin-json")
    with h.SandboxDaemon(root), h.McpServer(root, CLAUDE_CODE_SESSION_ID="A") as srv:
        add = h.run_rmx(["memory", "add", "feedback_alpha_rule", "-c",
                         "feedback alpha rule: always pin the alpha parser before release"],
                        root=root)
        assert add.returncode == 0, add.stderr
        emb = h.run_rmx(["embed"], root=root)          # recall is dense: vectors first
        assert emb.returncode == 0, emb.stderr
        _t21_session_start(root, "A", "startup")
        _t21_session_start(root, "B", "clear")
        rec = h.run_hook(recall_cmd, root=root, CLAUDE_PID=os.getpid(),
                         envelope={"session_id": "B", "hook_event_name": "UserPromptSubmit",
                                   "prompt": "feedback alpha rule alpha parser release"})
        srv.tool("rmx_focus_note", {"text": "applied feedback_alpha_rule now"})
    assert "feedback_alpha_rule" in rec.stdout, f"fixture: B's recall delivered nothing: {rec.stdout}"
    evs = h.events(root)
    used = [e for e in evs if e.get("stage") == "used"]
    assert len(used) == 1, f"R12: expected one used event; events={evs}; recall={rec.stdout[:300]}"
    delivered = [e for e in evs if e.get("stage") == "delivered"
                 and e.get("name") == "feedback_alpha_rule" and e.get("session") == "B"]
    assert delivered, evs
    assert used[0]["session"] == "B", used
    assert used[0]["ref_query_id"] == delivered[-1]["query_id"], (used, delivered)
    assert used[0]["evidence"] == "focus_note", used


def test_ac1b_unresolved_write_is_refused_not_routed_to_the_newest_ring(t21_root):
    """AC-1b unresolved-write leg (RED; failing assertion: A's ring line count unchanged).
    Pointer deleted, no RMX_SESSION: the next rmx_context row carries `session: null`, and
    `rmx_focus_note` returns a SessionUnresolved tool error. bug-109 writes the note to the
    newest ring (A) instead (D2)."""
    root = t21_root
    stm.Stm(root, "A").record("input", "a prompt in A")
    a_before = _t21_ring_lines(root, "A")
    with h.SandboxDaemon(root), h.McpServer(root, CLAUDE_CODE_SESSION_ID="A") as srv:
        _t21_session_start(root, "B", "clear")
        try:
            (_global_by_pid() / f"{os.getpid()}.json").unlink()
        except FileNotFoundError:
            pass
        legacy = stm.stm_dir(root) / "by-pid" / f"{os.getpid()}.json"
        if legacy.exists():
            legacy.unlink()
        note = srv.tool("rmx_focus_note", {"text": "a note nobody owns"})
        before = len(h.query_rows(root))
        srv.tool("rmx_context", {"ref": "anything_at_all"})
    assert _t21_ring_lines(root, "A") == a_before, (
        f"D2: an unresolved write must not reach the newest ring: {note['text']}")
    assert note["isError"] and "SessionUnresolved" in note["text"], note
    rows = _t21_context_mcp_rows(root, before)
    assert len(rows) == 1 and "session" in rows[0] and rows[0]["session"] is None, rows


def test_ac1b_input_hook_repoint_still_switches_the_server(t21_root):
    """AC-1b regression guard -- GREEN regression guard, not counted as RED. The input hook
    (generated `focus hook --event input`) with B's envelope re-points the long-lived server
    (started with CLAUDE_CODE_SESSION_ID=A) to B."""
    root = t21_root
    stm.Stm(root, "A").record("input", "a prompt in A")
    cmd = h.generated_cmd(root, "UserPromptSubmit", "focus hook --event input")
    with h.McpServer(root, CLAUDE_CODE_SESSION_ID="A") as srv:
        r = h.run_hook(cmd, root=root, CLAUDE_PID=os.getpid(),
                       envelope={"session_id": "B", "prompt": "a prompt in B",
                                 "hook_event_name": "UserPromptSubmit"})
        note = srv.tool("rmx_focus_note", {"text": "after the input hook"})
    assert r.returncode == 0, r.stderr
    assert note["json"] and note["json"].get("session") == "B", note


# ---- AC-4 ----------------------------------------------------------------------------------

def _t21_scan(root, *, envelope=None, raw=None, **extra):
    cmd = h.generated_cmd(root, "UserPromptSubmit", "rmx scan-prompt")
    before = len(h.query_rows(root))
    r = h.run_hook(cmd, root=root, envelope=envelope, raw=raw, CLAUDE_PID=os.getpid(), **extra)
    rows = [x for x in h.query_rows(root)[before:] if x.get("source") == "scan-prompt"]
    return r, rows


def _t21_three_rings(root):
    stm.Stm(root, "sess-one").record("input", "first prompt")
    stm.Stm(root, "sess-two").record("input", "second prompt")
    time.sleep(0.05)
    stm.Stm(root, "sess-third").record("input", "the newest ring belongs to a third id")


def test_ac4_scan_prompt_rows_carry_their_own_envelope_sessions(t21_root):
    """AC-4 (RED: rows carry no `session`). Two `rmx scan-prompt` runs in ONE root with
    different envelope session_ids, plus a NEWER ring for a third id: the rows carry disjoint
    sessions equal to their own envelopes' ids. CLAUDE_PID = this test pid on every child."""
    root = t21_root
    _t21_three_rings(root)
    _, r1 = _t21_scan(root, envelope={"session_id": "sess-one", "prompt": "parser rank alpha",
                                      "hook_event_name": "UserPromptSubmit"})
    _, r2 = _t21_scan(root, envelope={"session_id": "sess-two", "prompt": "parser rank beta",
                                      "hook_event_name": "UserPromptSubmit"})
    assert len(r1) == 1 and len(r2) == 1, (r1, r2)
    assert r1[0].get("session") == "sess-one" and r2[0].get("session") == "sess-two", (r1, r2)


def test_ac4_no_envelope_no_pointer_is_null_and_recorded(t21_root):
    """AC-4 (RED: no `session` on the row / bug-109's newest-ring guess). No envelope (prose
    on stdin), no pointer for the owner, no RMX_SESSION, CLAUDE_CODE_SESSION_ID = the third id
    (which no path reads): `session` is null, not the third ring's id, and the USER-level
    `_errors.jsonl` gains exactly one `pointer-unresolved` row with owner = this test pid,
    root = the tmp root and owner_start = this process's start (D8)."""
    root = t21_root
    _t21_three_rings(root)
    before = _t21_err_lines()
    _, rows = _t21_scan(root, raw="parser rank gamma please",
                        CLAUDE_CODE_SESSION_ID="sess-third")
    assert len(rows) == 1, rows
    assert "session" in rows[0] and rows[0]["session"] is None, (
        f"R9 event tail: never the newest ring: {rows[0]}")
    new = _t21_new_err_rows(before, root)
    assert [r["reason"] for r in new] == ["pointer-unresolved"], new
    assert new[0]["owner"] == os.getpid(), new
    assert new[0]["owner_start"] == stm._proc_start(os.getpid()), new


def test_ac4_stale_pointer_is_ignored_and_recorded(t21_root):
    """AC-4 (RED: bug-109 returns None silently). A pointer for this owner whose `pid_start`
    does not match the live process's start time is ignored (`session` null) and recorded as
    `pointer-stale` (D5)."""
    root = t21_root
    _t21_three_rings(root)
    d = _global_by_pid()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{os.getpid()}.json").write_text(json.dumps(
        {"session": "sess-stale", "pid": os.getpid(), "pid_start": "0.000001", "t": 0,
         "hook": "input"}))
    before = _t21_err_lines()
    _, rows = _t21_scan(root, raw="parser rank delta please")
    assert len(rows) == 1 and "session" in rows[0] and rows[0]["session"] is None, rows
    reasons = [r["reason"] for r in _t21_new_err_rows(before, root)]
    assert "pointer-stale" in reasons, reasons


def test_ac4_lookup_failed_resolves_to_none(root, monkeypatch):
    """AC-4 lookup-failed leg, the return (RED: bug-109 returns the newest ring, `latest`).
    `stm._proc_info` and `stm._ps_comm_chain` -> None (registered mocks: dependencies of the
    resolver, not the resolver): `resolve_session_source(root, None, purpose="event")` is
    `(None, "none")`."""
    import inspect
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.setattr(stm, "_proc_info", lambda pid: None)
    monkeypatch.setattr(stm, "_ps_comm_chain", lambda: None)
    _ring(root, "sess-C", age_s=0)
    assert "purpose" in inspect.signature(verbs.resolve_session_source).parameters, (
        "D1: resolve_session_source takes no `purpose`")
    assert tuple(verbs.resolve_session_source(root, None, purpose="event")) == (None, "none")


def test_ac4_lookup_failed_records_one_row_regression_guard(root, monkeypatch):
    """AC-4 lookup-failed leg, the row -- GREEN regression guard, not counted as RED (bug-109
    writes `owner-lookup-failed` today, verbs.py:561-562). Exactly one row per resolve."""
    import inspect
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.setattr(stm, "_proc_info", lambda pid: None)
    monkeypatch.setattr(stm, "_ps_comm_chain", lambda: None)
    stm.stm_dir(root).mkdir(parents=True, exist_ok=True)       # bug-109 records only into a STM dir
    before = len(_t21_compat_err_rows(root))
    kw = ({"purpose": "event"}
          if "purpose" in inspect.signature(verbs.resolve_session_source).parameters else {})
    verbs.resolve_session_source(root, None, **kw)
    new = _t21_compat_err_rows(root)[before:]
    assert [r["reason"] for r in new] == ["owner-lookup-failed"], new


def _t21_two_rings(root):
    stm.Stm(root, "sess-old").record("input", "an older ring")
    time.sleep(0.05)
    stm.Stm(root, "sess-new").record("input", "the newest ring")


def test_ac4_write_leg_refuses_an_unresolved_note(t21_root):
    """AC-4 write leg (a) (RED; failing assertion: the newer ring's line count -- bug-109 writes
    the note there and exits 0). `rmx focus note x` with CLAUDE_PID = this pid, no pointer, no
    RMX_SESSION, two rings: exits 2 with ONE stderr line naming the sources tried; both rings
    unchanged; exactly one `pointer-unresolved` row with owner = this pid, root = the tmp root,
    owner_start = this process's start."""
    root = t21_root
    _t21_two_rings(root)
    counts = (_t21_ring_lines(root, "sess-old"), _t21_ring_lines(root, "sess-new"))
    before = _t21_err_lines()
    r = h.run_rmx(["focus", "note", "x"], root=root, CLAUDE_PID=os.getpid())
    assert (_t21_ring_lines(root, "sess-old"), _t21_ring_lines(root, "sess-new")) == counts, (
        f"D2: an unresolved write reached a ring: {r.stdout}{r.stderr}")
    assert r.returncode == 2, (r.returncode, r.stderr)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert len(lines) == 1 and "pointer" in lines[0], lines
    new = _t21_new_err_rows(before, root)
    assert [x["reason"] for x in new] == ["pointer-unresolved"], new
    assert new[0]["owner"] == os.getpid(), new
    assert new[0]["owner_start"] == stm._proc_start(os.getpid()), new


def test_ac4_read_leg_labels_the_newest_ring(t21_root):
    """AC-4 read leg (b) label (RED: bug-109 prints no label). `rmx focus tail` with no
    pointer prints the newest ring labelled `(newest ring; not resolved)`."""
    root = t21_root
    _t21_two_rings(root)
    r = h.run_rmx(["focus", "tail"], root=root, CLAUDE_PID=os.getpid())
    assert "(newest ring; not resolved)" in r.stdout, r.stdout
    assert "sess-new" in r.stdout, r.stdout


def test_ac4_read_leg_records_one_row_regression_guard(t21_root):
    """AC-4 read leg (b) row -- GREEN regression guard, not counted as RED (bug-109 records it
    on its `latest` fall-through). Exactly one `pointer-unresolved` row naming this owner."""
    root = t21_root
    _t21_two_rings(root)
    before = len(_t21_compat_err_rows(root))
    h.run_rmx(["focus", "tail"], root=root, CLAUDE_PID=os.getpid())
    new = _t21_compat_err_rows(root)[before:]
    assert [x["reason"] for x in new] == ["pointer-unresolved"], new
    assert new[0].get("owner") == os.getpid(), new


def test_ac4_read_and_write_rows_are_scoped_and_reach_recall_state(t21_root, tmp_path):
    """AC-4 read + write legs (RED: rows carry no `root` / `owner_start`, and live in the old
    per-store file). Each command adds exactly one row (counted per command), each row carries
    root = the tmp root and owner_start = this process's start (D8), and both appear in
    `handoff.compose_recall_state`'s anomalies for that root under the session-pointer clause."""
    from refmatrix import handoff
    root = t21_root
    _t21_two_rings(root)
    b0 = _t21_err_lines()
    h.run_rmx(["focus", "note", "x"], root=root, CLAUDE_PID=os.getpid())
    b1 = _t21_err_lines()
    h.run_rmx(["focus", "tail"], root=root, CLAUDE_PID=os.getpid())
    w = _t21_new_err_rows(b0, root)[: max(0, b1 - b0)]
    rd = _t21_new_err_rows(b1, root)
    assert len(w) == 1 and len(rd) == 1, (w, rd)
    for row in w + rd:
        assert row["root"] == str(root) and row["owner"] == os.getpid(), row
        assert row["owner_start"] == stm._proc_start(os.getpid()), row
    s = stm.Stm(root, "sess-new")
    rep = handoff.compose_recall_state(s, root, repo=tmp_path, memdir=tmp_path / "mem")
    clause = [a for a in rep["anomalies"] if "could not be resolved" in a]
    assert clause and "pointer-unresolved x2" in clause[0], rep["anomalies"]
