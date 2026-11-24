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


def pre_tool(fx: Fx, session: str, tool: str, tool_input: dict, *, hooks=None):
    return fire(fx, "PreToolUse", tool,
                envelope(fx, "PreToolUse", session, tool_name=tool, tool_input=tool_input),
                hooks=hooks)


def post_read(fx: Fx, session: str, path: Path) -> None:
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    res = fire(fx, "PostToolUse", "Read", envelope(
        fx, "PostToolUse", session, tool_name="Read", tool_input={"file_path": str(path)},
        tool_response={"type": "text", "file": {
            "filePath": str(path), "content": content, "numLines": content.count("\n"),
            "startLine": 1, "totalLines": content.count("\n")}}))
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
