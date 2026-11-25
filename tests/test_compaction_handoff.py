"""task-compaction-as-handoff (L195, queue row C1): compaction and /clear as a handoff.

Spec: `workflow/plans/task-compaction-as-handoff.md` (R1-R5, R3b, AC-1/2/4/5). RED, written
before `src/`; every test fails at base `e4913e51` for the reason named in its docstring.

HOW THE HOOKS ARE DRIVEN (rule 3, through the entry point). Each test fires an EVENT the way
Claude Code does: every command of the GENERATED config (`hooks._claude_hook_block`, or the
`.claude/settings.json` that `rmx install-hooks --apply` wrote) whose matcher matches the event's
value, each run by `/bin/bash -c` with the hook envelope as JSON on stdin and cwd = the project.
The tests do NOT name the new commands: the PreCompact printer, the gate, the marker writer and
the re-injection are found by what they do when the event fires. One needle is used, on a command
that exists today: `recall-state` (the SessionStart compact|clear producer, task 25.1 R11, which
`telemetry.hook_producer` and 25.1's AC-15 tests also key on).

THE CONTRACT THESE TESTS PIN FOR GREEN (behaviour, not names):

- PreCompact (R1, R2, R4, AC-1, AC-4). Exactly one generated PreCompact command prints, and it
  is the one that saves: the session's `savestate_<slug>.md` exists before its first stdout byte,
  and the STM digest was promoted (`focus_summary_<slug>`). The session comes from the
  envelope's `session_id` (no `RMX_SESSION` is set; `stm.read_hook_envelope` is the one parser).
  Its stdout is the instruction only: at most 3 lines, <= 1,000 B, naming "one line",
  "authoritative", "do not restate", the save-state it wrote and the handoff file the
  SessionStart(compact) entry will write for this session. With `trigger: manual` and non-empty
  `custom_instructions` the R2 instruction is NOT printed (the save still happens). A failed
  save prints its cause on stderr, still exits 0 and the instruction names the last good
  save-state.
- SessionStart compact|clear (R3, AC-2). The command that runs `recall-state` writes the FULL
  `rmx recall-state --session <envelope session>` stdout, byte for byte, to a per-session file
  under `<store>/.refmatrix/handoffs/` (one path per session, overwritten by the next write),
  and prints only a pointer block (<= 1,024 B): the file's absolute path, its byte count, and
  "before any other action" + "authoritative". If the write fails the stdout says so (a line
  naming the handoff and "fail"/"could not") and carries the budgeted inline recall-state
  (`--max-bytes N` with its trailer), exit 0.
- The gate (R3b, AC-5). Once that file is written for session S, a PreToolUse event of S is
  DENIED for every tool except a `Read` of that exact path: exit 2 with the reason on stderr, or
  exit 0 with `hookSpecificOutput.permissionDecision == "deny"` (either form is Claude Code's
  deny). The reason names the path, "first" and "authoritative". A PostToolUse `Read` of the path
  lifts it; until then every UserPromptSubmit of S prints one line holding the path and
  "authoritative". A missing or unreadable file lets every call through with exactly one
  stand-down line naming the path. Other sessions are never gated.
- Telemetry (R3b). `rmx telemetry --context --format json` carries `handoff`:
  `{"pulls": [{"session", "path", "bytes", "seconds"}, ...],
    "stand_downs": [{"session", "path", ...}, ...]}`.
- The briefing (R3b, R5). `rmx install-hooks --apply` writes `.refmatrix/CLAUDE.md` (the
  generated briefing) with ONE line stating the rule: it names `.refmatrix/handoffs/` and
  "authoritative".
- Generated and installed (R5). After `rmx install-hooks --apply`, `--check` is clean and the
  INSTALLED settings gate a cleared session.

No process boundary is faked: real `rmx` children on a throwaway store under
`rmx_sandbox.short_root`, no daemon (every hook here runs daemon-less in well under a second,
measured 2026-11-23). No waits: nothing sleeps; the one blocking read has a kill deadline.
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import threading
from pathlib import Path

import pytest

import rmx_sandbox
from tests import task21_1_support as h
from tests import task25_1_support as s

SESSION = "cahsess01"          # alnum and <= 12 chars: the save-state slug IS the session id
OTHER = "cahother01"
CLEAR_SESSION = "cahclear01"   # /clear starts a new session id
PRE_LINE = "recall-state · session"   # the first line of every recall-state report
LONG_N = 8                     # recall-state lists 8 recent memories; long titles push it > N
DENY_TOOLS = (
    ("Bash", {"command": "ls"}),
    ("Edit", {"file_path": "/x/a.py", "old_string": "a", "new_string": "b"}),
    ("Grep", {"pattern": "x"}),
    ("Agent", {"description": "d", "prompt": "p"}),
    ("mcp__refmatrix__rmx_context", {"ref": "x"}),
)


@pytest.fixture(autouse=True)
def _live_logs_untouched():
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


# ---- the fixture store --------------------------------------------------------------------------


class Fx:
    def __init__(self, base: Path):
        self.base = base
        self.home = base / "g" / ".refmatrix"
        self.proj = base / "p"
        self.root = self.proj / ".refmatrix"
        self.memdir = s.memdir_of(self.proj)
        self.transcript = base / "t.jsonl"


def _long_memory(md: Path, i: int) -> None:
    title = f"Long handoff note {i} — " + "quasar ledger reconcile flux batch " * 40
    (md / f"cah_long_{i}.md").write_text(
        f'---\ngmd: "0.1"\nid: cah_long_{i}\ntitle: "{title.strip()}"\ntags: [project]\n'
        f"metadata:\n  node_type: memory\n  type: project\n  created: 2026-11-23\n"
        f"  updated: 2026-11-23\n---\n\n# Long handoff note {i} {{#root}}\n\nbody {i}\n",
        encoding="utf-8")


@pytest.fixture
def fx():
    """A store with a prior save-state (`savestate_fx01`, the committed plan25 fixture), eight
    memories whose long titles make the full recall-state larger than the recall_state budget
    (so the full report and the budgeted one differ), and an STM ring for SESSION."""
    base = Path(rmx_sandbox.short_root("cah-"))
    f = Fx(base)
    s._init_store(f.home, partition="global")
    s._init_store(f.root)
    s.copy_memdir(f.proj, include={"savestate_fx01"})
    for i in range(LONG_N):
        _long_memory(f.memdir, i)
    s.seed_ring(f.root, session=SESSION, n=12)
    f.transcript.write_text("")
    yield f
    for p in [base, *base.rglob("*")]:          # undo any chmod a test left before removal
        try:
            if p.is_dir() and not p.is_symlink():
                os.chmod(p, 0o755)
        except OSError:
            pass
    rmx_sandbox.remove_tree(base)


def _budget() -> int:
    from refmatrix.hook_budget import CHANNEL_BUDGET_BYTES
    return int(CHANNEL_BUDGET_BYTES["recall_state"])


# ---- firing an event as Claude Code does --------------------------------------------------------


def _matches(matcher, value) -> bool:
    if matcher in (None, "", "*") or value is None:
        return True
    return re.fullmatch(matcher, value) is not None


def envelope(fx: Fx, event: str, session: str, **kw) -> dict:
    return {"session_id": session, "hook_event_name": event, "cwd": str(fx.proj),
            "transcript_path": str(fx.transcript), **kw}


def fire(fx: Fx, event: str, value, env: dict, *, hooks: "dict | None" = None
         ) -> "list[tuple[str, subprocess.CompletedProcess]]":
    """Every command `event` binds whose matcher matches `value`, in config order."""
    hooks = hooks if hooks is not None else h.hook_block(fx.root)["hooks"]
    out = []
    for e in hooks.get(event, []):
        if not _matches(e.get("matcher"), value):
            continue
        for hk in e["hooks"]:
            out.append((hk["command"], run(fx, hk["command"], env)))
    return out


def run(fx: Fx, cmd: str, env: dict) -> subprocess.CompletedProcess:
    return h.run_hook_bytes(cmd, root=fx.root, envelope=env, RMX_HOME=str(fx.home))


def stdout_of(results) -> str:
    return "".join(r.stdout.decode("utf-8", "replace") for _c, r in results)


def said_of(results) -> str:
    return "".join(r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
                   for _c, r in results)


def denials(results) -> "list[str]":
    """The deny reasons of a PreToolUse fan-out: exit 2 (reason on stderr) or exit 0 with a
    JSON `permissionDecision: deny` (or the older `decision: block`)."""
    out = []
    for _c, r in results:
        if r.returncode == 2:
            out.append(r.stderr.decode("utf-8", "replace"))
            continue
        if r.returncode != 0:
            continue
        try:
            j = json.loads(r.stdout.decode("utf-8", "replace") or "null")
        except ValueError:
            continue
        if not isinstance(j, dict):
            continue
        hso = j.get("hookSpecificOutput") or {}
        if hso.get("permissionDecision") == "deny":
            out.append(str(hso.get("permissionDecisionReason") or ""))
        elif j.get("decision") == "block":
            out.append(str(j.get("reason") or ""))
    return out


def pre_tool(fx: Fx, session: str, tool: str, tool_input: dict, *, hooks=None, **extra):
    """`extra` adds envelope fields: `agent_id` / `agent_type` make it a subagent's or a
    teammate's call (Claude Code's common hook input carries the PARENT's `session_id` plus
    `agent_id: g?.agentId, agent_type`, bsd-cah r1 #b-1)."""
    return fire(fx, "PreToolUse", tool,
                envelope(fx, "PreToolUse", session, tool_name=tool, tool_input=tool_input,
                         **extra),
                hooks=hooks)


def read_envelope(fx: Fx, session: str, path: Path, **extra) -> dict:
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return envelope(
        fx, "PostToolUse", session, tool_name="Read", tool_input={"file_path": str(path)},
        tool_response={"type": "text", "file": {
            "filePath": str(path), "content": content, "numLines": content.count("\n"),
            "startLine": 1, "totalLines": content.count("\n")}}, **extra)


def post_read(fx: Fx, session: str, path: Path, **extra) -> None:
    res = fire(fx, "PostToolUse", "Read", read_envelope(fx, session, path, **extra))
    for cmd, r in res:
        assert r.returncode == 0, (s.after_env(cmd)[:80], r.stderr.decode()[-600:])


def prompt(fx: Fx, session: str, text: str = "next step please") -> str:
    return stdout_of(fire(fx, "UserPromptSubmit", None,
                          envelope(fx, "UserPromptSubmit", session, prompt=text)))


def precompact(fx: Fx, session: str, *, trigger: str = "auto", custom: str = ""):
    return fire(fx, "PreCompact", trigger, envelope(
        fx, "PreCompact", session, trigger=trigger, custom_instructions=custom))


def session_start(fx: Fx, source: str, session: str):
    return fire(fx, "SessionStart", source, envelope(fx, "SessionStart", session, source=source))


# ---- reading what the hooks said ----------------------------------------------------------------


def _handoffs_dirs(fx: Fx) -> "list[str]":
    return sorted({str(fx.root / "handoffs"), str(fx.root.resolve() / "handoffs")})


def handoff_path(fx: Fx, text: str) -> "Path | None":
    """The first absolute path under `<store>/handoffs/` that `text` names."""
    for m in re.finditer(r"/[^\s`'\"()<>]+", text):
        p = m.group(0).rstrip(".,:;")
        if any(p.startswith(d + "/") for d in _handoffs_dirs(fx)):
            return Path(p)
    return None


def pointer_lines(fx: Fx, text: str, path: Path) -> "list[str]":
    """Lines that carry the one-line pointer: the path AND "authoritative". A line naming the
    path alone (an STM composite listing the file it read) is not the pointer."""
    spellings = {str(path), str(path.resolve()) if path.exists() else str(path)}
    return [ln for ln in text.splitlines()
            if any(sp in ln for sp in spellings) and "authoritative" in ln.lower()]


def savestates_of(fx: Fx, session: str) -> "list[Path]":
    return sorted(fx.memdir.rglob(f"savestate_{session}.md")) if fx.memdir.exists() else []


def recall_state_full(fx: Fx, session: str) -> bytes:
    r = h.run_rmx(["recall-state", "--session", session], root=fx.root, RMX_HOME=str(fx.home))
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.encode("utf-8")


def handoff_cmd(fx: Fx, source: str) -> str:
    hits = [c for _e, m, c in h.hook_entries(fx.root, "SessionStart")
            if "recall-state" in c and _matches(m, source)]
    assert len(hits) == 1, f"expected one SessionStart({source}) recall-state command: {hits}"
    return hits[0]


def written_handoff(fx: Fx, source: str, session: str) -> "tuple[Path, str]":
    """Fire SessionStart(source) for `session`; the handoff file it points at, and the text of
    the pointer command's stdout. Fails (the RED line) when no pointer names a file."""
    res = session_start(fx, source, session)
    out = stdout_of(res)
    p = handoff_path(fx, out)
    assert p is not None, (
        f"R3: SessionStart({source}) named no file under {_handoffs_dirs(fx)[0]}/; it printed "
        f"{len(out.encode())} B starting {out[:300]!r}")
    return p, out


def telemetry_handoff(fx: Fx) -> dict:
    r = h.run_rmx(["telemetry", "--context", "--format", "json"], root=fx.root,
                  RMX_HOME=str(fx.home))
    assert r.returncode == 0, r.stderr[-600:]
    data = json.loads(r.stdout)
    assert "handoff" in data, f"R3b telemetry: no `handoff` view in telemetry --context: {sorted(data)}"
    return data["handoff"]


def _make_tree_read_only(top: Path) -> None:
    for p in sorted(top.rglob("*"), reverse=True):
        os.chmod(p, 0o555 if p.is_dir() else 0o444)
    os.chmod(top, 0o555)


def _restore_tree(top: Path) -> None:
    os.chmod(top, 0o755)
    for p in top.rglob("*"):
        os.chmod(p, 0o755 if p.is_dir() else 0o644)


# ---- R1 / R2 / AC-1: PreCompact saves first, then prints the one instruction --------------------


def _printing(results) -> "list[tuple[str, subprocess.CompletedProcess]]":
    return [(c, r) for c, r in results if r.stdout.strip()]


def test_precompact_prints_only_the_one_line_instruction(fx):
    """R2 / AC-1: of every generated PreCompact command (auto trigger), exactly ONE prints, and
    what it prints is the instruction and nothing else: <= 3 lines, <= 1,000 B (under the
    10,000-unit hook cap), no recall pack, no STM digest, no save-state progress lines; it says
    "one line", "authoritative" and "do not restate", and names the save-state it wrote and the
    handoff file (R3: "names the same first action"). Mutation: a second stdout writer fails.
    HEAD: two commands print (the `memory recall --recent` pack and save-state's progress) and
    neither is an instruction."""
    res = precompact(fx, SESSION)
    printing = _printing(res)
    assert len(printing) == 1, (
        "R2: exactly one generated PreCompact command may print (its stdout becomes summary "
        "instructions); printing: "
        + repr([(s.after_env(c)[:70], r.stdout[:120]) for c, r in printing]))
    out = printing[0][1].stdout.decode("utf-8")
    assert len(out) < 10_000 and len(out.encode()) <= 1000, len(out.encode())
    assert len(out.strip().splitlines()) <= 3, out
    low = out.lower()
    for phrase in ("one line", "authoritative", "do not restate"):
        assert phrase in low, (phrase, out)
    for marker in ("# rmx recall", "session summary", "promoted", "memory bridge", "lint"):
        assert marker not in low, (marker, out)
    assert f"savestate_{SESSION}" in out, f"R1: the instruction names no handoff: {out!r}"
    assert "handoffs/" in out, f"R3: the instruction does not name the handoff file: {out!r}"


def test_precompact_saves_state_and_promotes_before_its_first_byte(fx):
    """R1 / AC-1: the printing PreCompact command, run ALONE (Claude Code runs an event's
    commands in parallel, so a sibling cannot be what saved), has written
    `savestate_<session>.md` by the time its first stdout byte is readable, and promoted the
    STM digest (`focus_summary_<session>`), with the session taken from the envelope. HEAD: no
    PreCompact command both saves and prints (the save-state entry prints progress and cannot
    resolve the envelope's session: SessionUnresolved)."""
    printing = _printing(precompact(fx, OTHER))
    assert len(printing) == 1, [s.after_env(c)[:70] for c, _r in printing]
    cmd = printing[0][0]
    assert not savestates_of(fx, SESSION)
    env = h.rmx_env(fx.root, RMX_HOME=str(fx.home))
    errf = open(fx.base / "pc.stderr", "wb")
    proc = subprocess.Popen(["/bin/bash", "-c", cmd], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=errf, env=env, cwd=str(fx.proj))
    killer = threading.Timer(120, proc.kill)          # deadline on the blocking read
    killer.start()
    try:
        proc.stdin.write(json.dumps(envelope(fx, "PreCompact", SESSION, trigger="auto",
                                             custom_instructions="")).encode())
        proc.stdin.close()
        first = proc.stdout.read(1)
        saved_at_first_byte = bool(savestates_of(fx, SESSION))
        rest = proc.stdout.read()
        proc.wait(timeout=120)
    finally:
        killer.cancel()
        errf.close()
    err = (fx.base / "pc.stderr").read_text(errors="replace")
    assert first, f"the printing command printed nothing for {SESSION}; stderr: {err[-800:]}"
    assert saved_at_first_byte, (
        f"R1: no savestate_{SESSION}.md existed when the instruction's first byte was printed "
        f"(stdout {(first + rest)[:200]!r}; stderr {err[-600:]!r})")
    g = h.run_rmx(["memory", "get", f"focus_summary_{SESSION}"], root=fx.root,
                  RMX_HOME=str(fx.home))
    assert g.returncode == 0 and f"focus_summary_{SESSION}" in g.stdout, (
        f"R1: PreCompact's save-state did not promote the STM digest: {g.stderr[-400:]}")


def test_precompact_save_failure_says_why_and_names_the_last_good_handoff(fx):
    """R1 / AC-4: a save-state that cannot write (the memory dir read-only) prints its cause on
    stderr, still exits 0 with the instruction on stdout, and the instruction names the LAST
    GOOD save-state (OTHER's, written by the first PreCompact), never the one that failed.
    HEAD: no PreCompact command prints an instruction at all."""
    ok = precompact(fx, OTHER)
    assert savestates_of(fx, OTHER), (
        "R1: the first PreCompact saved no state for the envelope's session: "
        + repr([(s.after_env(c)[:50], r.stderr[-200:]) for c, r in ok]))
    _make_tree_read_only(fx.memdir)
    try:
        res = precompact(fx, SESSION)
    finally:
        _restore_tree(fx.memdir)
    assert not savestates_of(fx, SESSION)
    printing = _printing(res)
    assert len(printing) == 1, ("AC-4: the instruction must still print when save-state fails",
                                [(s.after_env(c)[:60], r.returncode, r.stderr[-300:])
                                 for c, r in res])
    _cmd, r = printing[0]
    out = r.stdout.decode("utf-8")
    assert r.returncode == 0, f"stdout is only summary instructions on exit 0: rc {r.returncode}"
    assert f"savestate_{OTHER}" in out and f"savestate_{SESSION}" not in out, out
    assert "authoritative" in out.lower(), out
    err = r.stderr.decode("utf-8", "replace")
    assert err.strip() and "Traceback" not in err, err[-800:]
    assert re.search(r"(?i)save-state|could not|permission|error", err), err[-800:]


# ---- R4: a manual /compact keeps the user's instructions ----------------------------------------


@pytest.mark.parametrize("trigger,custom,want_instruction", [
    ("auto", "", True),
    ("manual", "", True),
    ("manual", "keep the parser bug details and the failing test names", False),
])
def test_manual_compact_with_text_keeps_the_users_instructions(fx, trigger, custom,
                                                                  want_instruction):
    """R4: the R2 instruction applies to `auto`, and to a manual /compact with no text; a
    manual /compact WITH text gets no competing instruction. The save happens on every
    trigger. HEAD: no trigger prints the instruction, and no save lands for the envelope's
    session."""
    res = precompact(fx, SESSION, trigger=trigger, custom=custom)
    out = stdout_of(res).lower()
    has = all(p in out for p in ("one line", "authoritative", "do not restate"))
    assert has == want_instruction, (trigger, custom, out[:400])
    if not want_instruction:
        assert "one line" not in out and "do not restate" not in out, out[:400]
    assert savestates_of(fx, SESSION), f"R1: {trigger} PreCompact saved no state"


# ---- R3 / AC-2: SessionStart compact|clear writes the full handoff and points at it --------------


@pytest.mark.parametrize("source,session", [("compact", SESSION), ("clear", CLEAR_SESSION)])
def test_session_start_writes_the_full_recall_state_to_a_per_session_file(fx, source, session):
    """R3 / AC-2: the compact|clear recall-state command writes the FULL `rmx recall-state`
    stdout (byte-identical, larger than the recall_state budget, so never the fitted text) to a
    file under `<store>/handoffs/`, and prints a pointer block <= 1,024 B naming the file, its
    byte count, "before any other action" and "authoritative". HEAD: it prints the fitted
    report inline and writes no file."""
    cmd = handoff_cmd(fx, source)
    r = run(fx, cmd, envelope(fx, "SessionStart", session, source=source))
    assert r.returncode == 0, r.stderr.decode()[-800:]
    out = r.stdout.decode("utf-8")
    p = handoff_path(fx, out)
    assert p is not None, (f"R3: no handoff file named; the {source} entry printed "
                           f"{len(r.stdout)} B starting {out[:200]!r}")
    assert p.is_file(), p
    body = p.read_bytes()
    full = recall_state_full(fx, session)
    assert len(full) > _budget(), f"fixture: the full recall-state is only {len(full)} B"
    assert body == full, (f"AC-2: the handoff file ({len(body)} B) is not the full "
                          f"`rmx recall-state` stdout ({len(full)} B)")
    assert b"savestate_fx01" in body
    assert len(r.stdout) <= 1024, f"R3: the pointer block is {len(r.stdout)} B"
    n = len(body)
    assert str(n) in out or f"{n:,}" in out, f"R3: the pointer does not give {n} B: {out!r}"
    low = out.lower()
    assert "before any other action" in low and "authoritative" in low, out
    assert PRE_LINE not in out, "R3: the pointer carries the report inline"


@pytest.mark.parametrize("source,session", [("compact", SESSION), ("clear", CLEAR_SESSION)])
def test_session_start_injects_the_pointer_never_the_inline_handoff(fx, source, session):
    """R3 / AC-2 mutations "inline handoff on compact" and "`clear` left inline": everything the
    SessionStart(source) event prints carries the pointer and NOT the recall-state report or
    the save-state body. HEAD: the report is printed inline on both triggers."""
    p, out = written_handoff(fx, source, session)
    assert PRE_LINE not in out, f"R3: {source} still injects recall-state inline"
    assert "SAVESTATE-fx01" not in out, f"R3: {source} injects the save-state body"
    assert p.is_file()


def test_precompact_names_the_file_session_start_compact_writes(fx):
    """R3: "The PreCompact summary instruction (R2) names the same first action": the handoff
    path in the PreCompact instruction is the path SessionStart(compact) then writes for the
    same session. HEAD: PreCompact names no handoff file."""
    pre = stdout_of(precompact(fx, SESSION))
    named = handoff_path(fx, pre)
    assert named is not None, f"R3: the PreCompact instruction names no handoff file: {pre!r}"
    p, _out = written_handoff(fx, "compact", SESSION)
    assert p == named, (named, p)


def test_one_handoff_file_per_session_the_newest_kept(fx):
    """R3: one file per session, the newest kept: a second compact of the same session writes
    the same path with the new report; another session gets its own path. HEAD: no file."""
    p1, _ = written_handoff(fx, "compact", SESSION)
    _long_memory(fx.memdir, 99)                 # the report changes between the two writes
    p2, _ = written_handoff(fx, "compact", SESSION)
    assert p1 == p2, (p1, p2)
    assert p2.read_bytes() == recall_state_full(fx, SESSION)
    assert b"cah_long_99" in p2.read_bytes()
    q, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    assert q != p1 and q.is_file() and p1.is_file(), (q, p1)


def test_handoff_write_failure_says_so_and_falls_back_inline(fx):
    """R3: when the file cannot be written (`<store>/handoffs` is a regular file here), the
    injected block says so and carries 25.1's budgeted inline recall-state (its trailer, since
    the full report is over budget), exit 0; and with no file there is nothing to gate (R3b).
    HEAD: the inline report prints, but nothing says a handoff write failed."""
    (fx.root / "handoffs").write_text("not a directory\n")
    cmd = handoff_cmd(fx, "compact")
    r = run(fx, cmd, envelope(fx, "SessionStart", SESSION, source="compact"))
    assert r.returncode == 0, r.stderr.decode()[-800:]
    out = r.stdout.decode("utf-8")
    said = [ln for ln in out.splitlines()
            if "handoff" in ln.lower() and re.search(r"(?i)fail|could not", ln)]
    assert said, f"R3: the fallback block does not say the handoff write failed: {out[:400]!r}"
    assert PRE_LINE in out, "R3: no inline recall-state fallback"
    assert "full: rmx recall-state" in out, "R3: the fallback is not the budgeted (fitted) form"
    assert len(r.stdout) <= _budget() + 512, len(r.stdout)
    assert not denials(pre_tool(fx, SESSION, "Bash", {"command": "ls"})), (
        "R3b: the gate held although no handoff file was written")


# ---- R3b / AC-5: the gate, the marker and the re-injection ---------------------------------------


@pytest.mark.parametrize("source,session", [("compact", SESSION), ("clear", CLEAR_SESSION)])
def test_gate_denies_every_tool_but_a_read_of_the_handoff(fx, source, session):
    """AC-5 (mutation: the gate removed): after SessionStart(source) wrote the handoff, every
    non-Read tool call of that session is DENIED with "read <path> first: it is the
    authoritative state"; a Read of another file is denied too; a Read of the handoff is
    allowed. HEAD: nothing is denied."""
    p, _ = written_handoff(fx, source, session)
    for tool, ti in DENY_TOOLS + (("Read", {"file_path": str(fx.proj / "other.md")}),):
        reasons = denials(pre_tool(fx, session, tool, ti))
        assert reasons, f"AC-5: {tool} was allowed before {p} was read"
        why = " ".join(reasons)
        assert str(p) in why and "first" in why.lower() and "authoritative" in why.lower(), why
    assert not denials(pre_tool(fx, session, "Read", {"file_path": str(p)})), (
        "AC-5: the Read of the handoff itself was denied")


def test_reading_the_handoff_lifts_the_gate_and_stops_the_reinjection(fx):
    """AC-5 / R3b: until the handoff is read, every prompt of the session re-injects the
    one-line pointer, and the gate holds; a PostToolUse Read of ANOTHER file changes nothing; a
    PostToolUse Read of the handoff writes the marker: the same Bash call is then allowed and
    the next prompt carries no pointer. HEAD: no pointer is injected and nothing is gated."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    for _turn in range(2):
        lines = pointer_lines(fx, prompt(fx, CLEAR_SESSION), p)
        assert len(lines) == 1, f"R3b: the prompt did not re-inject the one-line pointer: {lines}"
    other = fx.proj / "notes.md"
    other.write_text("unrelated\n")
    post_read(fx, CLEAR_SESSION, other)
    assert denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})), (
        "R3b: reading another file lifted the gate")
    post_read(fx, CLEAR_SESSION, p)
    assert not denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})), (
        "AC-5: the gate still holds after the handoff was read")
    assert not pointer_lines(fx, prompt(fx, CLEAR_SESSION), p), (
        "R3b: the pointer is still re-injected after the read")


@pytest.mark.parametrize("how", ["missing", "unreadable"])
def test_gate_stands_down_on_a_missing_or_unreadable_handoff(fx, how):
    """AC-5 (mutation: the gate holds on a missing file): the handoff gone or unreadable lets
    every call through with exactly ONE stand-down line naming the path, and the stand-down is
    recorded in telemetry. HEAD: no handoff file is ever written, so the fixture step fails."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    if how == "missing":
        p.unlink()
    else:
        os.chmod(p, 0)
    try:
        first = pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})
        assert not denials(first), f"AC-5: the gate trapped the session on a {how} handoff"
        lines = [ln for ln in said_of(first).splitlines() if str(p) in ln]
        assert len(lines) == 1, f"AC-5: want one stand-down line naming {p}; got {lines}"
        for tool, ti in DENY_TOOLS:
            assert not denials(pre_tool(fx, CLEAR_SESSION, tool, ti)), tool
    finally:
        if p.exists():
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    downs = telemetry_handoff(fx).get("stand_downs") or []
    assert any(d.get("session") == CLEAR_SESSION and d.get("path") == str(p) for d in downs), (
        f"R3b: the stand-down was not recorded: {downs}")


def test_gate_is_scoped_to_the_session_that_was_handed_off(fx):
    """R3b: the gate never traps another session: after a clear handed off CLEAR_SESSION, a
    call of OTHER (no handoff) and of a freshly started session is allowed, and their prompts
    carry no pointer, while CLEAR_SESSION stays gated. HEAD: CLEAR_SESSION is not gated."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    session_start(fx, "startup", OTHER)
    assert not denials(pre_tool(fx, OTHER, "Bash", {"command": "ls"}))
    assert not pointer_lines(fx, prompt(fx, OTHER), p)
    assert denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})), (
        "AC-5: the handed-off session is not gated")


def test_each_pull_is_recorded_with_path_bytes_and_seconds(fx):
    """R3b: "telemetry records each pull (path, bytes, seconds from session start to the read)":
    after the clear and the Read, `rmx telemetry --context --format json` lists the pull.
    HEAD: telemetry has no `handoff` view."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    post_read(fx, CLEAR_SESSION, p)
    pulls = telemetry_handoff(fx).get("pulls") or []
    mine = [x for x in pulls if x.get("session") == CLEAR_SESSION]
    assert len(mine) == 1, pulls
    row = mine[0]
    assert row.get("path") == str(p) and row.get("bytes") == p.stat().st_size, row
    assert isinstance(row.get("seconds"), (int, float)) and row["seconds"] >= 0, row


# ---- R3b CLAUDE.md line, R5 generated + installed -----------------------------------------------


def _install(fx: Fx, *extra: str) -> subprocess.CompletedProcess:
    (fx.proj / ".git").mkdir(exist_ok=True)
    return subprocess.run([h.rmx_bin(), "install-hooks", "--no-git", *extra],
                          cwd=str(fx.proj), env=h.rmx_env(fx.root, RMX_HOME=str(fx.home)),
                          capture_output=True, text=True, timeout=300)


def test_generated_briefing_states_the_read_the_handoff_rule(fx):
    """R3b: "one CLAUDE.md line states the rule" (CLAUDE.md is re-read after compaction and
    /clear). The generated briefing `rmx install-hooks --apply` writes (`.refmatrix/CLAUDE.md`)
    holds exactly one line naming `.refmatrix/handoffs/` and "authoritative". HEAD: no line."""
    a = _install(fx, "--apply", "--force")
    assert a.returncode == 0, a.stderr[-800:]
    text = (fx.root / "CLAUDE.md").read_text(encoding="utf-8")
    rule = [ln for ln in text.splitlines()
            if ".refmatrix/handoffs/" in ln and "authoritative" in ln.lower()]
    assert len(rule) == 1, f"R3b: want one briefing line stating the rule; got {rule}"


def test_installed_hooks_gate_a_cleared_session_and_check_is_clean(fx):
    """R5: emitted by `hooks.py` and installed by `rmx install-hooks --apply`; `--check` is then
    clean, and the INSTALLED `.claude/settings.json` (search hooks included) hands off a clear
    and gates the session's first Bash call. HEAD: the installed config gates nothing."""
    a = _install(fx, "--apply")
    assert a.returncode == 0, a.stderr[-800:]
    c = _install(fx, "--check")
    assert c.returncode == 0, (c.stdout[-800:], c.stderr[-800:])
    hooks = json.loads((fx.proj / ".claude" / "settings.json").read_text())["hooks"]
    res = fire(fx, "SessionStart", "clear",
               envelope(fx, "SessionStart", CLEAR_SESSION, source="clear"), hooks=hooks)
    p = handoff_path(fx, stdout_of(res))
    assert p is not None and p.is_file(), "R5: the installed clear entry wrote no handoff"
    assert denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"}, hooks=hooks)), (
        "R5: the installed PreToolUse hooks do not gate the cleared session")


# ---- R6 / AC-6: the active /goal rides the handoff ----------------------------------------------
#
# The transcript shape (probed 2026-11-23, read-only, on the two real transcripts that hold a
# `/goal`; recorded as shape + hashes only, no text): the command is a JSONL record with
# `"type": "user"`, `message.role == "user"` and `message.content` a STRING that is exactly
#   <command-name>/goal</command-name>\n<command-message>goal</command-message>\n
#   <command-args>TEXT</command-args>
# (both observed instances: args 46 chars, sha256[:12] 96ab8d893a6c), with an ISO `timestamp`;
# the next record is a `type: user` string `<local-command-stdout>…` and then an `isMeta` user
# record. The same command text recurs later inside `api-request-blob` records (list content), and
# subagent transcripts quote the tags inside tool results (list content): neither is a command.
# Every fixture transcript below is synthetic.

GOAL_X = "draft the C1 spec review"
GOAL_Y = 'ship C1 — the "pulled" handoff, verify set green;  then T0.7 (twice-spaced)'
GOAL_DECOY = "a quoted goal inside a tool result, never a command"
T_X = "2026-11-23T09:01:02.345Z"
T_Y = "2026-11-23T10:15:30.123Z"
T_Y_SECONDS = "2026-11-23T10:15:30"


def _goal_cmd(args: str) -> str:
    return (f"<command-name>/goal</command-name>\n<command-message>goal</command-message>\n"
            f"<command-args>{args}</command-args>")


def _rec(kind: str, ts: str, content, **extra) -> dict:
    role = "assistant" if kind == "assistant" else "user"
    return {"type": kind, "timestamp": ts, "sessionId": SESSION, "isSidechain": False,
            "uuid": f"u-{ts}-{kind}", "parentUuid": None, "userType": "external",
            "message": {"role": role, "content": content}, **extra}


def goal_transcript(fx: Fx, records: "list[dict]", name: str = "goal.jsonl") -> Path:
    p = fx.base / name
    p.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return p


def x_then_y(extra_after: "list[dict] | None" = None) -> "list[dict]":
    """`/goal X`, work, `/goal Y`, then a tool result QUOTING a goal command (not a command)."""
    return [
        _rec("user", T_X, _goal_cmd(GOAL_X)),
        _rec("user", "2026-11-23T09:01:02.400Z",
             "<local-command-stdout>Goal set</local-command-stdout>"),
        _rec("assistant", "2026-11-23T09:05:00.000Z", [{"type": "text", "text": "working"}]),
        _rec("user", T_Y, _goal_cmd(GOAL_Y)),
        _rec("user", "2026-11-23T10:15:30.200Z",
             "<local-command-stdout>Goal set</local-command-stdout>"),
        _rec("user", "2026-11-23T10:20:00.000Z", [{
            "type": "tool_result", "tool_use_id": "t1",
            "content": "quoted: " + _goal_cmd(GOAL_DECOY)}]),
        *(extra_after or []),
    ]


def precompact_with(fx: Fx, session: str, transcript: Path):
    env = envelope(fx, "PreCompact", session, trigger="auto", custom_instructions="")
    env["transcript_path"] = str(transcript)
    return fire(fx, "PreCompact", "auto", env)


def start_with(fx: Fx, source: str, session: str, transcript: Path) -> "tuple[Path, str]":
    """The recall-state SessionStart command alone, with `transcript_path` set: (file, stdout)."""
    env = envelope(fx, "SessionStart", session, source=source)
    env["transcript_path"] = str(transcript)
    r = run(fx, handoff_cmd(fx, source), env)
    assert r.returncode == 0, r.stderr.decode()[-800:]
    out = r.stdout.decode("utf-8")
    p = handoff_path(fx, out)
    assert p is not None, f"R3: the {source} entry named no handoff file: {out[:300]!r}"
    return p, out


def active_goal_block(fx: Fx, session: str) -> str:
    """The `{#active-goal}` block of `savestate_<session>.md`: from the anchor's line to the next
    heading. Fails (the RED line) when the save-state or the block is missing."""
    saves = savestates_of(fx, session)
    assert saves, f"R1/R6: PreCompact wrote no savestate_{session}.md"
    text = saves[0].read_text(encoding="utf-8")
    i = text.find("{#active-goal}")
    assert i >= 0, f"R6: savestate_{session}.md has no {{#active-goal}} block"
    start = text.rfind("\n", 0, i) + 1
    nxt = re.search(r"^#{1,6} ", text[i:], re.M)
    end = i + nxt.start() if nxt else len(text)
    return text[start:end]


def goal_lines(text: str) -> "list[str]":
    return [ln for ln in text.splitlines() if "active goal: /goal" in ln]


def test_newest_goal_rides_the_save_state_the_handoff_file_and_the_pointer(fx):
    """AC-6 (mutations: the first goal taken, not the newest; the pointer line dropped): with
    `/goal X` then `/goal Y` (and a tool result quoting a third goal after them), PreCompact's
    save-state holds Y verbatim in its `{#active-goal}` block with Y's set time; the compact
    handoff file (= `rmx recall-state`) carries Y; the pointer block has exactly one line
    `active goal: /goal <Y verbatim>` and says to re-issue it when a bare `/goal` shows none.
    X and the quoted goal appear nowhere. HEAD: no save-state from the PreCompact envelope."""
    tr = goal_transcript(fx, x_then_y())
    pre = precompact_with(fx, SESSION, tr)
    block = active_goal_block(fx, SESSION)
    assert GOAL_Y in block, f"R6: the block does not hold the newest goal verbatim: {block!r}"
    assert T_Y_SECONDS in block, f"R6: the block does not carry the goal's set time: {block!r}"
    assert GOAL_X not in block and GOAL_DECOY not in block, block
    assert GOAL_Y not in stdout_of(pre), "R2: the goal must not ride the PreCompact instruction"
    p, out = start_with(fx, "compact", SESSION, tr)
    body = p.read_text(encoding="utf-8")
    assert GOAL_Y in body and GOAL_X not in body, "R6: the handoff file lacks the newest goal"
    rs = recall_state_full(fx, SESSION).decode("utf-8")
    assert GOAL_Y in rs, "R6: `rmx recall-state` does not carry the {#active-goal} block"
    lines = goal_lines(out)
    assert len(lines) == 1, f"R6: want one `active goal:` line in the pointer: {out!r}"
    tail = lines[0].split("active goal: /goal ", 1)[1]
    assert tail.startswith(GOAL_Y), f"R6: the pointer line is not verbatim: {lines[0]!r}"
    assert GOAL_X not in out and GOAL_DECOY not in out, out
    assert re.search(r"(?i)re-?issue", out) and "/goal" in out, (
        f"R6: the pointer does not say to re-issue the goal when none is active: {out!r}")


def test_clear_takes_the_goal_from_the_newest_save_state_with_its_time(fx):
    """AC-6 on `clear`: the new session's transcript is not the one that set the goal (here an
    empty file), so the pointer line comes from the newest save-state's `{#active-goal}` block,
    labelled with its time. HEAD: no save-state from the envelope, no goal line."""
    precompact_with(fx, SESSION, goal_transcript(fx, x_then_y()))
    assert GOAL_Y in active_goal_block(fx, SESSION)
    fresh = goal_transcript(fx, [], name="fresh.jsonl")
    _p, out = start_with(fx, "clear", CLEAR_SESSION, fresh)
    lines = goal_lines(out)
    assert len(lines) == 1, f"R6: no `active goal:` line on clear: {out!r}"
    assert lines[0].split("active goal: /goal ", 1)[1].startswith(GOAL_Y), lines[0]
    assert T_Y_SECONDS in out, f"R6: the clear pointer does not label the goal with its time: {out!r}"


@pytest.mark.parametrize("how", ["garbage", "missing"])
def test_unreadable_transcript_says_so_in_one_line_and_guesses_no_goal(fx, how):
    """AC-6: a transcript that cannot be parsed (not JSON) or read (missing) is SAID in one line
    of the save-state's `{#active-goal}` block naming the transcript, never a guessed or empty
    goal; the save and the R2 instruction still happen, and the pointer has no goal line.
    HEAD: no save-state from the envelope."""
    tr = fx.base / "broken.jsonl"
    if how == "garbage":
        tr.write_bytes(b"\x00\xff not json {\n" + _goal_cmd(GOAL_Y).encode() + b"\n")
    pre = precompact_with(fx, SESSION, tr)
    block = active_goal_block(fx, SESSION)
    assert "authoritative" in stdout_of(pre).lower(), "R2: the instruction did not print"
    said = [ln for ln in block.splitlines()
            if "transcript" in ln.lower() and re.search(r"(?i)could not|cannot|unreadable|"
                                                         r"not (be )?(read|pars)|missing", ln)]
    assert len(said) == 1, f"R6: want one line saying the transcript was unreadable: {block!r}"
    assert GOAL_Y not in block and not goal_lines(block), block
    _p, out = start_with(fx, "compact", SESSION, tr)
    assert not goal_lines(out), f"R6: a goal line from an unreadable transcript: {out!r}"


# The clearing form comes from Claude Code's docs (https://code.claude.com/docs/en/goal.md, read
# 2026-11-23): "`/goal clear`" with "`stop`, `off`, `reset`, `none`, and `cancel` ... accepted as
# aliases for `clear`", printing "Goal cleared:" (a bare `/goal` only SHOWS the state). No real
# transcript holds a clear (probe 2026-11-23), so its record is the observed slash-command record
# above with that argument; the lead has this flagged.
CLEAR_ALIASES = ("clear", "stop", "off", "reset", "none", "cancel")


@pytest.mark.parametrize("arg", CLEAR_ALIASES)
def test_a_cleared_goal_gives_no_line(fx, arg):
    """AC-6 (mutation: the clear ignored): `/goal X`, `/goal Y`, then `/goal <clear alias>` leaves
    no active goal: the save-state block names neither goal and the compact pointer has no
    `active goal:` line, never an empty or guessed one. A bare `/goal` (show) after the clear
    changes nothing. HEAD: no save-state from the envelope."""
    after = [_rec("user", "2026-11-23T11:00:00.000Z", _goal_cmd(arg)),
             _rec("user", "2026-11-23T11:00:00.100Z",
                  f"<local-command-stdout>Goal cleared: {GOAL_Y}</local-command-stdout>"),
             _rec("user", "2026-11-23T11:05:00.000Z", _goal_cmd(""))]
    tr = goal_transcript(fx, x_then_y(after))
    precompact_with(fx, SESSION, tr)
    block = active_goal_block(fx, SESSION)
    assert not goal_lines(block), block
    stated = block.replace(f"Goal cleared: {GOAL_Y}", "")
    assert GOAL_Y not in stated and GOAL_X not in stated, (
        f"R6: a cleared goal is still recorded as active: {block!r}")
    _p, out = start_with(fx, "compact", SESSION, tr)
    assert not goal_lines(out), f"R6: an `active goal:` line after `/goal {arg}`: {out!r}"


@pytest.mark.parametrize("case", ["never-set", "set-after-clear"])
def test_no_goal_gives_no_line_and_a_goal_set_after_a_clear_wins(fx, case):
    """AC-6: a transcript with no `/goal` gives no line; `/goal X`, `/goal clear`, `/goal Y`
    gives Y (the clear only ends the goals before it). HEAD: no save-state from the envelope."""
    if case == "never-set":
        recs = [_rec("user", T_X, "plain prompt, no command"),
                _rec("assistant", T_Y, [{"type": "text", "text": "ok"}])]
    else:
        recs = [_rec("user", T_X, _goal_cmd(GOAL_X)),
                _rec("user", "2026-11-23T09:30:00.000Z", _goal_cmd("clear")),
                _rec("user", T_Y, _goal_cmd(GOAL_Y))]
    tr = goal_transcript(fx, recs)
    precompact_with(fx, SESSION, tr)
    block = active_goal_block(fx, SESSION)
    _p, out = start_with(fx, "compact", SESSION, tr)
    if case == "never-set":
        assert not goal_lines(out) and not goal_lines(block), (block, out)
    else:
        lines = goal_lines(out)
        assert len(lines) == 1 and lines[0].split("active goal: /goal ", 1)[1].startswith(
            GOAL_Y), (lines, out)
        assert GOAL_Y in block and GOAL_X not in block, block


# ---- L202 fold: bsd-cah r1 findings on cbbe9e3f ---------------------------------------------------
#
# Report: workflow/bullshit/2026-11-24-0400-cah-r1-cbbe9e3f.md. Envelopes are real-shaped: a
# subagent's or a teammate's hook input is the LEAD's `session_id` plus `agent_id` and
# `agent_type` (Claude Code 2.1.331's hook-input builder, `agent_id:g?.agentId,agent_type:h`;
# its PreCompact input carries `agentId` too; bsd-cah p5).

TEAMMATE = {"agent_id": "a123", "agent_type": "ch-bsd"}
SUBAGENT = {"agent_id": "a999", "agent_type": "ch-implementer"}
SIBLING = {"agent_id": "a777", "agent_type": "ch-test-engineer"}
TEAMMATE_TOOLS = (("Bash", {"command": "ls"}),
                  ("Edit", {"file_path": "/x/a.py", "old_string": "a", "new_string": "b"}),
                  ("mcp__refmatrix__rmx_context", {"ref": "x"}))


def fire_with(fx: Fx, event: str, value, env: dict, **env_extra):
    """`fire` with extra process environment (a test-sized knob)."""
    out = []
    for e in h.hook_block(fx.root)["hooks"].get(event, []):
        if not _matches(e.get("matcher"), value):
            continue
        for hk in e["hooks"]:
            out.append((hk["command"], h.run_hook_bytes(
                hk["command"], root=fx.root, envelope=env, RMX_HOME=str(fx.home), **env_extra)))
    return out


def lead_pulls(fx: Fx, session: str) -> "list[dict]":
    return [x for x in (telemetry_handoff(fx).get("pulls") or []) if x.get("session") == session]


# -- b-1 / b-2 (bug-307): the gate is the lead's; subagents and teammates never trip or lift it --


@pytest.mark.parametrize("tool,ti", TEAMMATE_TOOLS, ids=[t for t, _ in TEAMMATE_TOOLS])
def test_teammate_calls_pass_a_gated_lead_session(fx, tool, ti):
    """b-1: after the LEAD's /clear armed its gate, a teammate's call (same `session_id`,
    `agent_id` set) is allowed, while the lead's own call is still denied. cbbe9e3f: the
    teammate is denied with "read …/handoffs/<lead>.txt first"."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    got = denials(pre_tool(fx, CLEAR_SESSION, tool, ti, **TEAMMATE))
    assert not got, f"b-1: the lead's gate denied a teammate's {tool}: {got}"
    assert denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})), (
        "the lead itself must stay gated")
    assert p.is_file()


def test_teammate_read_does_not_lift_the_leads_gate_nor_count_as_its_pull(fx):
    """b-1: a teammate's Read of the lead's handoff lifts nothing and is not the lead's pull in
    telemetry; the lead is still denied and still reminded; the lead's OWN Read then lifts the
    gate and is the one pull. cbbe9e3f: the teammate's Read lifts the lead's gate and telemetry
    logs it as the lead's pull."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    post_read(fx, CLEAR_SESSION, p, **TEAMMATE)
    assert denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})), (
        "b-1: a teammate's Read lifted the lead's gate")
    assert pointer_lines(fx, prompt(fx, CLEAR_SESSION), p), (
        "b-1: the lead's reminder stopped after a teammate's Read")
    assert not lead_pulls(fx, CLEAR_SESSION), (
        f"b-1: telemetry counts the teammate's Read as the lead's pull: {lead_pulls(fx, CLEAR_SESSION)}")
    post_read(fx, CLEAR_SESSION, p)
    assert not denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"}))
    pulls = lead_pulls(fx, CLEAR_SESSION)
    assert len(pulls) == 1 and not pulls[0].get("agent_id"), pulls


def test_subagent_compact_writes_no_handoff_and_arms_no_gate(fx):
    """b-1 / b-2: a subagent's own auto-compaction fires SessionStart(compact) with the lead's
    `session_id` and its `agent_id`: it names no handoff file, and neither the lead nor a
    sibling is denied or reminded. cbbe9e3f: it writes handoffs/<lead>.txt and arms the gate,
    so the lead and every sibling are denied."""
    res = fire(fx, "SessionStart", "compact",
               envelope(fx, "SessionStart", SESSION, source="compact", **SUBAGENT))
    out = stdout_of(res)
    named = handoff_path(fx, out)
    assert named is None, f"b-2: a subagent's compaction wrote the lead's handoff {named}"
    for who, extra in (("lead", {}), ("sibling", SIBLING)):
        got = denials(pre_tool(fx, SESSION, "Bash", {"command": "git status"}, **extra))
        assert not got, f"b-1: a subagent's compaction gated the {who}: {got}"
    remind = [ln for ln in prompt(fx, SESSION).splitlines()
              if "handoffs/" in ln and "authoritative" in ln.lower()]
    assert not remind, f"b-1: the lead is reminded of a subagent's handoff: {remind}"


def test_subagent_precompact_prints_nothing_and_saves_no_lead_state(fx):
    """b-2: a subagent's PreCompact (lead's `session_id`, `agent_id` set) prints nothing, so
    Claude Code's own summary stands, and writes no save-state for the lead's session.
    cbbe9e3f: it prints the lead's one-line instruction and writes savestate_<lead>."""
    res = fire(fx, "PreCompact", "auto", envelope(
        fx, "PreCompact", SESSION, trigger="auto", custom_instructions="", **SUBAGENT))
    out = stdout_of(res)
    assert not out.strip(), f"b-2: a subagent's PreCompact printed summary instructions: {out!r}"
    assert not savestates_of(fx, SESSION), "b-2: a subagent's PreCompact saved the lead's state"


# -- b-3 (bug-308): a gate that cannot be lifted stands down; never a 24 h trap --------------------


def test_unwritable_handoffs_dir_after_arming_never_traps_the_session(fx):
    """b-3: the gate is armed, then `handoffs/` is made unwritable. The Read lifts the gate or
    stands it down (at most one line naming the file), and the next non-Read calls are
    allowed. cbbe9e3f: `pulled` fails (exit 1, PermissionError on the marker) and every later
    Bash is denied until the 24 h expiry."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    hd = p.parent
    os.chmod(hd, 0o555)
    try:
        said = fire(fx, "PostToolUse", "Read", read_envelope(fx, CLEAR_SESSION, p))
        for _turn in range(3):
            calls = pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})
            said += calls
            got = denials(calls)
            assert not got, f"b-3: the session is trapped behind an unliftable gate: {got}"
    finally:
        os.chmod(hd, 0o755)
    lines = [ln for ln in said_of(said).splitlines() if str(p) in ln]
    assert len(lines) <= 1, f"b-3: want at most one line about the stand-down: {lines}"


def test_next_handoff_after_an_unwritable_stand_down_is_gated_again(fx):
    """bsd-cah confirm-lite #m-5 (L208, 2026-11-24): the b-3 stand-down (an unwritable
    `handoffs/`) is remembered beside the dir. Once the dir is writable again, the SAME
    session's next /clear writes a new handoff and its pointer says "denied until it is
    read", so the gate must hold. 4784cdd5: the stale stand-down marker outlived the episode,
    and the first call after the new handoff silently dropped the new gate."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    os.chmod(p.parent, 0o555)
    try:
        fire(fx, "PostToolUse", "Read", read_envelope(fx, CLEAR_SESSION, p))
        assert not denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"}))
    finally:
        os.chmod(p.parent, 0o755)
    q, out = written_handoff(fx, "clear", CLEAR_SESSION)
    assert "denied until it is read" in out, out
    got = denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"}))
    assert got, "m-5: the new handoff's gate was dropped by the earlier stand-down's marker"
    assert denials(pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})), (
        "m-5: the gate held for one call only")


# -- s-1 (bug-308): deny is JSON at exit 0; any other failure of the gate allows ------------------


def test_deny_is_json_at_exit_0_never_exit_2(fx):
    """s-1: a deny is `hookSpecificOutput.permissionDecision: "deny"` on stdout at exit 0, so
    exit 2 is never the deny channel. cbbe9e3f: the gate denies by exiting 2."""
    written_handoff(fx, "clear", CLEAR_SESSION)
    res = pre_tool(fx, CLEAR_SESSION, "Bash", {"command": "ls"})
    assert not [s.after_env(c)[:60] for c, r in res if r.returncode == 2], (
        "s-1: a PreToolUse command exited 2 (the deny channel must be JSON at exit 0)")
    json_denies = []
    for _c, r in res:
        try:
            j = json.loads(r.stdout.decode("utf-8", "replace") or "null")
        except ValueError:
            continue
        if isinstance(j, dict) and (j.get("hookSpecificOutput") or {}).get(
                "permissionDecision") == "deny" and r.returncode == 0:
            json_denies.append(j)
    assert len(json_denies) == 1, f"s-1: want one JSON deny at exit 0: {json_denies}"
    hso = json_denies[0]["hookSpecificOutput"]
    assert hso.get("hookEventName") == "PreToolUse" and "authoritative" in str(
        hso.get("permissionDecisionReason")).lower(), hso


_OLD_RMX = """#!/bin/sh
# An older deployed rmx with no `handoff` group (bsd-cah p7: a rollback while a gate exists).
echo "Usage: rmx [OPTIONS] COMMAND [ARGS]..." >&2
echo "Try 'rmx --help' for help." >&2
echo "" >&2
echo "Error: No such command 'handoff'." >&2
exit 2
"""


def test_a_failing_gate_command_allows_the_call(fx):
    """s-1: with a gate file present and an `rmx` on the hook PATH that exits 2 ("No such
    command"), no PreToolUse command exits 2 and nothing denies: a broken gate allows, loudly
    (non-zero, not 2). cbbe9e3f: the wrapper passes click's exit 2 through, a block on every
    tool with no way out."""
    written_handoff(fx, "clear", CLEAR_SESSION)
    home = fx.base / "oldhome"
    (home / "bin").mkdir(parents=True)
    stub = home / "bin" / "rmx"
    stub.write_text(_OLD_RMX)
    stub.chmod(0o755)
    env = h.rmx_env(fx.root, RMX_HOME=str(fx.home))
    env["HOME"] = str(home)                      # HOOK_ENV puts $HOME/bin first on PATH
    data = json.dumps(envelope(fx, "PreToolUse", CLEAR_SESSION, tool_name="Bash",
                               tool_input={"command": "ls"})).encode()
    res = []
    for e in h.hook_block(fx.root)["hooks"].get("PreToolUse", []):
        if _matches(e.get("matcher"), "Bash"):
            for hk in e["hooks"]:
                res.append((hk["command"], subprocess.run(
                    ["/bin/bash", "-c", hk["command"]], input=data, env=env, cwd=str(fx.proj),
                    capture_output=True, timeout=120)))
    twos = [s.after_env(c)[:70] for c, r in res if r.returncode == 2]
    assert not twos, f"s-1: a failing gate command exited 2 and blocks every tool: {twos}"
    assert not denials(res), denials(res)


# -- s-2: PreCompact's save-state has one overall time bound --------------------------------------


# The margin a Claude Code hook `timeout` needs above the save-state budget, for the instruction
# print and interpreter start after the budget is spent. A test contract, not a measured budget:
# L203 leaves the budget itself (`hooks.PRECOMPACT_SAVE_TIMEOUT_S`) to green-cah's measurement.
PRECOMPACT_PRINT_MARGIN_S = 5


def precompact_save_entry(root: Path) -> "tuple[dict, int]":
    """The generated PreCompact hook entry (`{"type", "command", "timeout"?}`) and the N of its
    ONE `--timeout N`. Fails (the RED line) on anything else."""
    hooks_ = [hk for e in h.hook_block(root)["hooks"].get("PreCompact", []) for hk in e["hooks"]]
    assert len(hooks_) == 1, [hk["command"] for hk in hooks_]
    found = re.findall(r"--timeout (\d+)", hooks_[0]["command"])
    assert len(found) == 1, (
        f"s-2: want exactly one --timeout N on the PreCompact save-state: {hooks_[0]['command']!r}")
    return hooks_[0], int(found[0])


def test_precompact_save_state_budget_is_one_named_constant_inside_the_hook_timeout(tmp_path):
    """s-2 (shape only, L203: the number is measured, not pinned): the generated PreCompact
    save-state carries exactly one `--timeout N`; N is `hooks.PRECOMPACT_SAVE_TIMEOUT_S`; and
    the entry's Claude Code `timeout` (seconds) exceeds N plus the print margin, so the
    harness never kills the hook before its own budget fires and the instruction prints.
    cbbe9e3f: no `--timeout`, no constant, no entry timeout."""
    from refmatrix import hooks as hooks_mod
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    entry, n = precompact_save_entry(root)
    const = getattr(hooks_mod, "PRECOMPACT_SAVE_TIMEOUT_S", None)
    assert const is not None, "s-2: hooks.PRECOMPACT_SAVE_TIMEOUT_S is not defined"
    assert n == const, (n, const)
    ht = entry.get("timeout")
    assert isinstance(ht, (int, float)) and ht > n + PRECOMPACT_PRINT_MARGIN_S, (
        f"s-2: the PreCompact entry's hook timeout {ht!r} is not above {n} + "
        f"{PRECOMPACT_PRINT_MARGIN_S} s")


@pytest.mark.parametrize("spool", ["writable", "unwritable"])
def test_precompact_overrun_still_instructs_and_never_loses_the_commit(spool):
    """s-2 / L203 ("an overrun never loses the commit"): with a held writer (a seeded
    `_PingOnlyDaemon`: answers ping, stalls every other op) and the budget knob test-sized
    (`--timeout 2` in place of N), the PreCompact command exits 0 with the instruction naming
    a save-state, and `savestate_<session>.md` is on disk. No elapsed assert: the subprocess
    deadline is the hang guard (rule 6). cbbe9e3f: no `--timeout` on the command.

    task-hook-writes-queue (L212, 2026-11-24; R11.4-R11.5) split the held-writer outcome:
    - `writable`: the promote no longer overruns, it QUEUES. stderr carries the queued note
      (`QUEUED_WRITE_MSG`) and no "deferred" / "FAILED"; one spool entry waits for the drain.
      Decided: a queued promote is NOT a deferral, so L204's `handoff.precompact_deferred`
      stays 0 (the metric counts commits that did not reach the store or a durable queue).
    - `unwritable`: the spool directory cannot be written, the enqueue fails, and the original
      L203/L204 path holds: stderr says the store commit was deferred and the deferral is
      counted (1, with the session); a later in-time PreCompact adds nothing."""
    import os
    from refmatrix import verbs
    from tests.held_writer import flat, spool_dir, spool_files
    from tests.test_plan2_remedy import _PingOnlyDaemon
    d = _PingOnlyDaemon(seeded=True)
    sp = spool_dir(d.root)
    if spool == "unwritable":
        sp.mkdir()
        os.chmod(sp, 0o500)
    try:
        entry, n = precompact_save_entry(d.root)
        cmd = entry["command"].replace(f"--timeout {n}", "--timeout 2")
        proj = d.root.parent
        s.copy_memdir(proj, include={"savestate_fx01"})
        s.seed_ring(d.root, session=SESSION, n=4)
        home = d.base / "g" / ".refmatrix"
        s._init_store(home, partition="global")
        r = h.run_hook_bytes(cmd, root=d.root, envelope={
            "session_id": SESSION, "hook_event_name": "PreCompact", "trigger": "auto",
            "custom_instructions": "", "cwd": str(proj), "transcript_path": ""},
            RMX_HOME=str(home), timeout=120)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (r.returncode, err[-800:])
        assert "authoritative" in out.lower() and "savestate_" in out, out
        md = s.memdir_of(proj)
        assert list(md.rglob(f"savestate_{SESSION}.md")), (
            f"L203: the overrun lost the save-state file; stderr {err[-600:]!r}")
        if spool == "writable":
            name = "focus_summary_" + re.sub(r"[^A-Za-z0-9]+", "", SESSION)[:12]
            assert not re.search(r"(?i)deferred|FAILED", err), (
                f"a queued promote is neither deferred nor failed: {err[-800:]!r}")
            assert flat(verbs.QUEUED_WRITE_MSG.format(name=name)) in flat(err), err[-800:]
            assert len(spool_files(d.root)) == 1, list(d.root.iterdir())
            expected = (0, set())
        else:
            assert re.search(r"(?i)(store )?commit\b.*\bdeferred|deferred.*\bcommit", err), (
                f"L203: stderr does not say the store commit was deferred: {err[-800:]!r}")
            expected = (1, {SESSION})
        # L204: the deferral is counted (the post-release no-go signal), with its session; a
        # PreCompact that completes in time adds nothing. The writer is released first, so
        # the second PreCompact (another session, the generated budget) runs in time.
        _release(d)
        if sp.exists():
            os.chmod(sp, 0o700)
        assert _deferred(d.root, home) == expected, _deferred(d.root, home)
        s.seed_ring(d.root, session=OTHER, n=4)
        r2 = h.run_hook_bytes(entry["command"], root=d.root, envelope={
            "session_id": OTHER, "hook_event_name": "PreCompact", "trigger": "auto",
            "custom_instructions": "", "cwd": str(proj), "transcript_path": ""},
            RMX_HOME=str(home), timeout=120)
        assert r2.returncode == 0 and list(md.rglob(f"savestate_{OTHER}.md")), (
            r2.returncode, r2.stderr.decode("utf-8", "replace")[-600:])
        assert _deferred(d.root, home) == expected, (
            "L204: an in-time PreCompact changed the deferred count", _deferred(d.root, home))
    finally:
        if sp.exists():
            os.chmod(sp, 0o700)
        d.close()


def _release(d) -> None:
    """Stop a `_PingOnlyDaemon` holding the writer WITHOUT removing its tree (its `close()`
    deletes the base): connections and socket closed, the lookalike process reaped, the held
    writer closed, the socket and pid files removed, so the store is daemon-less."""
    from refmatrix import daemon as daemon_mod
    d._stop = True
    for c in d.held:
        try:
            c.close()
        except OSError:
            pass
    d.sock.close()
    d.proc.kill()
    d.proc.wait()
    if d.writer is not None:
        d.writer.close()
        d.writer = None
    for f in (daemon_mod.socket_path(d.root), daemon_mod.pid_path(d.root)):
        Path(f).unlink(missing_ok=True)


def _deferred(root: Path, home: Path) -> "tuple[int, set]":
    """`handoff.precompact_deferred` from `rmx telemetry --context --format json` (L204; the
    field name is green-cah's to confirm): (count, sessions). A list of rows, or a mapping
    with a count (`n` / `count`) and its rows or sessions, are both read."""
    r = h.run_rmx(["telemetry", "--context", "--format", "json"], root=root,
                  RMX_HOME=str(home))
    assert r.returncode == 0, r.stderr[-600:]
    hv = json.loads(r.stdout).get("handoff")
    assert isinstance(hv, dict) and "precompact_deferred" in hv, (
        f"L204: telemetry has no handoff.precompact_deferred: {hv!r}"[:600])
    v = hv["precompact_deferred"]
    if isinstance(v, list):
        return len(v), {x.get("session") for x in v if isinstance(x, dict)}
    assert isinstance(v, dict), v
    n = v.get("n", v.get("count"))
    rows = v.get("rows") or v.get("sessions") or []
    sess = {x.get("session") if isinstance(x, dict) else x for x in rows}
    return int(n), sess


# -- m-1: the gate resolves the baked store, whatever the cwd -------------------------------------


def test_gate_holds_with_the_cwd_outside_the_project(fx):
    """m-1: the shell fast path tests `<baked root>/handoffs`; Python must decide on the SAME
    store when the hook's cwd is outside the project (no REFMATRIX_ROOT in a real hook).
    cbbe9e3f: Python walks up from the cwd, consults another store, and allows."""
    p, _ = written_handoff(fx, "clear", CLEAR_SESSION)
    elsewhere = fx.base / "elsewhere"
    elsewhere.mkdir()
    env = h.rmx_env(fx.root, RMX_HOME=str(fx.home))
    env.pop("REFMATRIX_ROOT")
    env_in = envelope(fx, "PreToolUse", CLEAR_SESSION, tool_name="Bash",
                      tool_input={"command": "ls"})
    env_in["cwd"] = str(elsewhere)
    res = []
    for e in h.hook_block(fx.root)["hooks"].get("PreToolUse", []):
        if _matches(e.get("matcher"), "Bash"):
            for hk in e["hooks"]:
                res.append((hk["command"], subprocess.run(
                    ["/bin/bash", "-c", hk["command"]], input=json.dumps(env_in).encode(),
                    env=env, cwd=str(elsewhere), capture_output=True, timeout=120)))
    assert denials(res), f"m-1: with the cwd outside the project the gate allowed ({p})"


# -- m-2: install-hooks help ----------------------------------------------------------------------


def test_precompact_checkpoint_help_names_the_current_command(fx):
    """m-2: `rmx install-hooks --help` describes `--precompact-checkpoint` without the old
    `--no-promote` checkpoint. cbbe9e3f: "PreCompact `rmx save-state --no-promote --no-sync`
    checkpoint"."""
    r = h.run_rmx(["install-hooks", "--help"], root=fx.root, RMX_HOME=str(fx.home),
                  COLUMNS="200")
    assert r.returncode == 0, r.stderr[-400:]
    i = r.stdout.find("--precompact-checkpoint")
    assert i >= 0, r.stdout[:400]
    nxt = r.stdout.find("\n  --", i + 1)
    block = r.stdout[i:nxt if nxt > 0 else None]
    assert "--no-promote" not in block, f"m-2: stale help: {block!r}"


# -- m-3: SessionStart reaps expired gates and week-old handoffs ----------------------------------

DAY = 86_400


def test_session_start_reaps_expired_gates_and_week_old_handoffs(fx):
    """m-3: a SessionStart that writes a handoff reaps what no session will consult again.
    `RMX_HANDOFF_NOW` (epoch seconds) is the test clock knob. At now+6 d: an unread gate past
    its 24 h expiry is gone (that session is no longer denied), a 6-day-old handoff file stays.
    At now+8 d: handoff files older than 7 days and their telemetry rows are gone; the file
    just written stays. cbbe9e3f: nothing is reaped (the expired session stays denied until it
    consults its own gate)."""
    import time as _time
    a, _ = written_handoff(fx, "clear", "cahreapa01")        # read: a pull row, no gate
    post_read(fx, "cahreapa01", a)
    c, _ = written_handoff(fx, "clear", "cahreapc01")        # never read: an armed gate
    assert lead_pulls(fx, "cahreapa01")
    now = int(_time.time())

    def start_at(session: str, days: int) -> Path:
        res = fire_with(fx, "SessionStart", "clear",
                        envelope(fx, "SessionStart", session, source="clear"),
                        RMX_HANDOFF_NOW=str(now + days * DAY))
        p = handoff_path(fx, stdout_of(res))
        assert p is not None and p.is_file(), f"no handoff written for {session}"
        return p

    start_at("cahreapb01", 6)
    assert not denials(pre_tool(fx, "cahreapc01", "Bash", {"command": "ls"})), (
        "m-3: an expired, unread gate was not reaped by the next SessionStart")
    assert a.is_file() and c.is_file(), "m-3: a 6-day-old handoff file was reaped"
    b8 = start_at("cahreapd01", 8)
    assert not a.exists() and not c.exists(), "m-3: handoff files older than 7 days remain"
    assert b8.is_file(), "m-3: the reap removed the handoff it had just written"
    assert not lead_pulls(fx, "cahreapa01"), "m-3: week-old handoff telemetry rows remain"


# -- m-4: no generated precompact recall channel or budget ----------------------------------------


def test_no_precompact_budget_channel_or_producer_remains(fx):
    """m-4: R2 removed the generated PreCompact recall, so its budget channel goes too: no
    `precompact` in `hook_budget.CHANNEL_BUDGET_BYTES` / `HOOK_COMMAND_CHANNELS`, none in
    `rmx telemetry --context`'s `by_producer`, and no generated `--recent` recall. cbbe9e3f:
    `"precompact": 9_000` and `precompact_recall_cmd` remain."""
    from refmatrix import hook_budget
    assert "precompact" not in hook_budget.CHANNEL_BUDGET_BYTES, sorted(
        hook_budget.CHANNEL_BUDGET_BYTES)
    assert not [k for k, v in hook_budget.HOOK_COMMAND_CHANNELS.items() if "precompact" in v]
    r = h.run_rmx(["telemetry", "--context", "--format", "json"], root=fx.root,
                  RMX_HOME=str(fx.home))
    assert r.returncode == 0, r.stderr[-400:]
    assert "precompact" not in json.loads(r.stdout)["by_producer"]
    assert not [c for _e, _m, c in h.hook_entries(fx.root)
                if "memory recall" in c and "--recent" in c]


# ---- bug-318: the handoff file is bounded under the Read cap and its milestones are capped ----

HANDOFF_MAX = 40_000          # bytes: ~20k tokens at the measured 2 B/token, under the 25k Read cap


def _seed_milestones(fx: Fx, session: str, n: int = 200, dup: int = 10) -> int:
    """`n` git milestones in the session ring (the shape the capture writes now), `dup` of them
    repeating an earlier sha. Returns the distinct-sha count."""
    from refmatrix import stm
    s = stm.Stm(fx.root, session)
    for i in range(n):
        k = i if i < n - dup else i - (n - dup)
        s.record("git", f"commit {k:07x} " + f"milestone {k} " + "reconcile quasar ledger " * 10,
                 refs=[])
    return n - dup


def test_handoff_file_caps_milestones_and_states_the_cut(fx):
    from refmatrix import stm
    """200 milestones (10 repeating a sha): the file lists the newest 30 distinct ones, says how
    many older were cut and where the full list is, and stays <= 40,000 B with its head kept.
    HEAD: every milestone is listed and the file is over the cap."""
    distinct = _seed_milestones(fx, SESSION)
    p, _out = written_handoff(fx, "compact", SESSION)
    body = p.read_text(encoding="utf-8")
    n = len(body.encode("utf-8"))
    assert n <= HANDOFF_MAX, f"bug-318: the handoff file is {n} B > {HANDOFF_MAX}"
    ms = [ln for ln in body.splitlines() if re.match(r"- commit [0-9a-f]{7} milestone", ln)]
    assert len(ms) == 30, f"bug-318: {len(ms)} milestone lines, want the newest 30"
    assert len({ln.split()[2] for ln in ms}) == 30, "milestones are deduped by sha"
    evs = [e for e in stm.Stm(fx.root, SESSION).all_events() if e["kind"] == "git"]
    # the digest's key is the sha, or the whole terse for an event without one (the ring seed's)
    total = len({e["terse"].split()[1] if e["terse"].startswith("commit ") else e["terse"]
                 for e in evs})
    assert total >= distinct
    assert re.search(rf"{total - 30} older milestones? cut.*rmx focus (context|export)", body), \
        body[-600:]
    assert "savestate_fx01" in body and body.startswith(PRE_LINE)


def test_handoff_file_is_cut_to_the_cap_in_reverse_priority_and_says_so(fx):
    """Recent-memory titles so long that the report is over 40,000 B whatever the digest holds:
    the cut is stated in the file; the session line, git state and handoff head stay."""
    _seed_milestones(fx, SESSION)
    for i in range(LONG_N):
        f = fx.memdir / f"cah_long_{i}.md"
        f.write_text(re.sub(r'(?m)^title: ".*"$', 'title: "' + "quasar ledger flux " * 400 + '"',
                            f.read_text(encoding="utf-8")), encoding="utf-8")
    p, _out = written_handoff(fx, "compact", SESSION)
    body = p.read_text(encoding="utf-8")
    n = len(body.encode("utf-8"))
    assert n <= HANDOFF_MAX, f"bug-318: the handoff file is {n} B > {HANDOFF_MAX}"
    assert re.search(r"omitted to fit 40000 B", body), body[-400:]
    assert body.startswith(PRE_LINE) and "\ngit branch " in body and "savestate_fx01" in body


@pytest.mark.parametrize("order", [("commit", "push"), ("push", "commit")])
def test_digest_keeps_one_line_per_sha_and_the_content_verb(fx, order):
    """G2/M3: `commit X s` and `push X s` are ONE milestone line, and it is the commit's."""
    from refmatrix import stm
    s = stm.Stm(fx.root, SESSION)
    for verb in order:
        s.record("git", f"{verb} abc1234 feat: the same commit", refs=[])
    p, _out = written_handoff(fx, "compact", SESSION)
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if "abc1234" in ln]
    assert lines == ["- commit abc1234 feat: the same commit"], lines


def test_a_digest_over_the_cap_loses_milestones_before_topics_and_arc(fx):
    """G1: the digest alone pushes the file over 40,000 B: the cut falls on Milestones
    (reverse priority) and leaves Top, Topics and Arc."""
    from refmatrix import stm
    s = stm.Stm(fx.root, SESSION)
    for i in range(40):
        s.record("git", f"commit {i:07x} " + "x" * 440, refs=[])
    for i in range(LONG_N):
        f = fx.memdir / f"cah_long_{i}.md"
        f.write_text(re.sub(r'(?m)^title: ".*"$', 'title: "' + "q" * 3300 + '"',
                            f.read_text(encoding="utf-8")), encoding="utf-8")
    p, _out = written_handoff(fx, "compact", SESSION)
    body = p.read_text(encoding="utf-8")
    assert len(body.encode("utf-8")) <= HANDOFF_MAX
    assert "omitted to fit 40000 B" in body
    assert "## Milestones" not in body, "the milestones are cut first"
    assert "## Top" in body and "## Topics worked on" in body and "## Arc" in body, body[-900:]
