"""Task 25.1 RED: the recall hook byte budget (bug-164) and the MCP unknown-project error
(bug-181).

Spec: workflow/plans/plan-25-cliquedb-field-report-tasks/task-25.1-recall-hook-byte-budget.md
(R0-R10, AC-1..AC-14). Plan: plan-25-cliquedb-field-report (approved 2026-11-09).

Every AC runs in 23.0's sandbox on the FROZEN fixture (`tests/fixtures/plan25/`, copied into a
sandbox memdir and brought in by the real bridge) through the GENERATED hook argv: the command is
taken from `hooks._claude_hook_block(...)` and run by `/bin/bash -c` with the envelope on stdin
(`tests/task21_1_support.py`). Stores are short-root sandbox stores served by real foreground
`rmx daemon` children; the global store is a tmp `RMX_HOME`; the shared model worker is a real
`modelsrv.ModelServer` child. Nothing in `src/` is patched; no recall, verb, packer, fitter,
bridge or hook-generator function is mocked.

Budgets are read from `refmatrix.hook_budget` (R1), never from the R0 probe (spec #r0; the probe
runs in parallel and its table is not an input here). Under d1's provisional numbers that means
`prompt_recall` 4,000 B, `scan_cmd` 5,000 B = `scan_prompt` 4,500 + `curator_status` 500; when
R0 replaces them the tests follow the constants unchanged. The per-command assertions are R0's
outcome (A) (per-hook cap), the outcome the lead's 2026-11-11 transcript evidence points to for
UserPromptSubmit; the (B)/(C) event-sum assertions are written once R0 records an outcome for an
event (see the implementation summary's #red).

HEAD records (bytes, measured on this fixture at f7c0d39) are in
workflow/implementation_summaries/task-25.1-recall-hook-byte-budget.md#red.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests import task21_1_support as h
from tests import task25_1_support as s

QUESTION = s.QUESTION


# ---- module fixtures ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fx():
    """THE AC fixture, daemon-served (project + tmp global store)."""
    f = s.build_full("p25")
    try:
        # Spec #test-strategy: under the sandbox HOME there is no ~/bin/rmx, so the dev venv's
        # `rmx` must be the one HOOK_ENV's PATH resolves -- asserted, not assumed.
        r = s.run_cmd(f, s.HOOK_ENV + "rmx version -v")
        assert r.returncode == 0, r.stderr
        assert str(h.SRC).encode() in r.stdout, (
            f"the hook argv ran an rmx that does not import {h.SRC}: {r.stdout[-600:]!r}")
        yield f
    finally:
        s.stop(f)
        import rmx_sandbox
        rmx_sandbox.remove_tree(f.base)


@pytest.fixture(scope="module")
def offline():
    """Two stores whose daemons are STOPPED after embed + snapshot: replica and vectors on disk,
    nothing answering (AC-4 b/c/e/g). B = 8 fixture memories, A = 6 others (distinct names).
    Both share one tmp RMX_HOME whose registry holds B (AC-4 e: "B is REGISTERED")."""
    from refmatrix import discovery
    base = s.short_base("p25o")
    home = base / "g" / ".refmatrix"
    s.build_global(home)
    b = s.build_offline("p25b", "fxb", {f"fx_mem_{i:02d}" for i in range(10, 18)}, home=home)
    a = s.build_offline("p25a", "fxa", {f"fx_mem_{i:02d}" for i in range(0, 6)}, home=home)
    old = os.environ.get("RMX_HOME")
    os.environ["RMX_HOME"] = str(home)
    try:
        discovery.register_root(b.root)
    finally:
        if old is None:
            os.environ.pop("RMX_HOME", None)
        else:
            os.environ["RMX_HOME"] = old
    yield {"a": a, "b": b, "home": home, "base": base}
    import rmx_sandbox
    for p in (a.base, b.base, base):
        rmx_sandbox.remove_tree(p)


@pytest.fixture(autouse=True)
def _live_logs_untouched():
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


def _q(fx, prompt=QUESTION, *, append: str = "", session: str = s.SESSION, **extra):
    """The generated per-prompt recall command (UserPromptSubmit) on `prompt`."""
    cmd = s.recall_cmd(fx.root, "UserPromptSubmit") + append
    return s.run_cmd(fx, cmd, env_in=s.envelope(prompt, session=session), **extra)


def _ss(fx, *, append: str = "", session: str = s.SESSION, **extra):
    cmd = s.recall_cmd(fx.root, "SessionStart") + append
    return s.run_cmd(fx, cmd, env_in=s.envelope("", session=session, event="SessionStart",
                                                source="resume"), **extra)


def _pc_cmds(fx) -> list[str]:
    return s.precompact_recall_cmds(fx.root)


def _ok(r, what):
    assert r.returncode == 0, (f"{what}: exit {r.returncode}; stderr: "
                               f"{r.stderr.decode('utf-8', 'replace')[-1500:]}")


def _pack(r, what) -> "s.Pack":
    _ok(r, what)
    p = s.Pack(r.stdout)
    assert p.is_pack and p.hook_lines, (
        f"{what}: not a --pack payload (R3): {len(r.stdout)} B starting "
        f"{r.stdout[:160]!r}")
    return p


# ---- R1: the budget module (pure) -----------------------------------------------------------------


# R1's seven channels plus rev 6's `recall_state` (R11: "a CHANNEL_BUDGET_BYTES entry like every
# other producer").
CHANNELS = {"prompt_recall", "scan_prompt", "curator_status", "focus_input", "session_start",
            "focus_context", "precompact", "recall_state"}
EVENTS = {"UserPromptSubmit", "SessionStart"}


def test_r1_hook_budget_table_names_every_channel_event_and_command():
    """R1: one module, one table, keyed by 21.1's channel names; the generated hook COMMAND is
    the unit (d9): `scan_cmd` = scan_prompt + curator_status, `sess_cmd` = curator_status."""
    hb = s.hook_budget_mod()
    assert hb is not None, "R1: refmatrix.hook_budget is not built"
    assert set(hb.CHANNEL_BUDGET_BYTES) == CHANNELS
    for c in CHANNELS:
        b = hb.budget(c)
        assert isinstance(b, int) and b > 0, (c, b)
    assert set(hb.HOOK_COMMAND_CHANNELS["scan_cmd"]) == {"scan_prompt", "curator_status"}
    assert set(hb.HOOK_COMMAND_CHANNELS["sess_cmd"]) == {"curator_status"}
    assert set(hb.EVENT_SPLIT) == EVENTS and set(hb.NON_RMX_RESERVE_BYTES) == EVENTS
    assert set(hb.EVENT_SPLIT["UserPromptSubmit"]) >= {"scan_prompt", "curator_status",
                                                       "focus_input", "prompt_recall"}
    assert set(hb.EVENT_SPLIT["SessionStart"]) >= {"curator_status", "session_start",
                                                   "focus_context"}
    assert hb.MIN_USEFUL_RECALL_BYTES == 2000
    assert hb.budget("prompt_recall") >= hb.MIN_USEFUL_RECALL_BYTES


def test_r1_non_rmx_reserve_is_per_event_and_covers_the_measured_hooks():
    """R0/R1: the reserve is keyed by event and rounded up to 512 B from what R0 read
    (caveman tracker ~250 B on UserPromptSubmit; caveman-activate ~1.2 KB + nudge on
    SessionStart). Kills the AC-14 mutation "a single NON_RMX_RESERVE_BYTES for both events"."""
    hb = s.hook_budget_mod()
    assert hb is not None, "R1: refmatrix.hook_budget is not built"
    r = hb.NON_RMX_RESERVE_BYTES
    assert r["UserPromptSubmit"] >= 250 and r["SessionStart"] >= 1200, r
    assert all(v % 512 == 0 for v in r.values()), r
    assert r["SessionStart"] > r["UserPromptSubmit"], r


def test_r1_env_override_and_non_integer(monkeypatch):
    """R1: RMX_HOOK_BUDGET_BYTES overrides every channel; a non-integer names the variable."""
    hb = s.hook_budget_mod()
    assert hb is not None, "R1: refmatrix.hook_budget is not built"
    monkeypatch.setenv("RMX_HOOK_BUDGET_BYTES", "3000")
    assert {hb.budget(c) for c in CHANNELS} == {3000}
    monkeypatch.setenv("RMX_HOOK_BUDGET_BYTES", "abc")
    with pytest.raises(Exception, match="RMX_HOOK_BUDGET_BYTES"):
        hb.budget("prompt_recall")


# bsd-251 r9 m-a (2026-11-14): `_check_tables`' import guards, each proven to FIRE. The shipped
# table never trips them, so a test of the clean import cannot tell a deleted check from a
# working one (feedback_clean_corpus_hides_a_dead_gate). Each case is ONE edit to the module's
# own source, executed as a fresh module; the control case is the unedited source.
_TABLE_EDITS = {
    "clean": (None, None, None),
    "recall-floor": ('    "prompt_recall": 4_000,\n', '    "prompt_recall": 1_500,\n',
                     "under MIN_USEFUL_RECALL_BYTES"),
    "no-event": ('    "recall_state": 9_000,\n}',
                 '    "recall_state": 9_000,\n    "newchan": 100,\n}',
                 "sit on no EVENT_SPLIT event"),
    "share-over-cap": ("# Bytes the user's NON-rmx hooks add per event",
                       'EVENT_SPLIT["UserPromptSubmit"]["focus_input"] = 99_999\n'
                       "# Bytes the user's NON-rmx hooks add per event",
                       "exceeds the channel's own cap"),
}


@pytest.mark.parametrize("case", sorted(_TABLE_EDITS))
def test_ma_hook_budget_import_checks_fire_on_a_bad_table(case):
    """R1 / bsd-251 m-4 + r9 m-a: a recall channel under MIN_USEFUL_RECALL_BYTES, a channel on
    no EVENT_SPLIT event (precompact aside), and an EVENT_SPLIT share above its channel's cap
    each raise ValueError AT IMPORT; the unedited table imports. The "no-event" edit also gives
    the new channel a hook command, so it is the placement check -- not "belongs to no hook
    command" -- that must catch it."""
    import importlib.util
    import types
    from refmatrix import hook_budget
    src = Path(hook_budget.__file__).read_text(encoding="utf-8")
    old, new, want = _TABLE_EDITS[case]
    if old is not None:
        assert src.count(old) == 1, f"fixture: the {case} edit's anchor is not unique in the source"
        src = src.replace(old, new)
        if case == "no-event":
            cmd_old = '    "recall_state_cmd": ("recall_state",),\n}'
            assert src.count(cmd_old) == 1
            src = src.replace(cmd_old, '    "recall_state_cmd": ("recall_state",),\n'
                                       '    "newchan_cmd": ("newchan",),\n}')
    name = f"_hb_probe_{case.replace('-', '_')}"
    mod = types.ModuleType(name)
    mod.__file__ = hook_budget.__file__
    sys.modules[name] = mod                      # dataclasses resolves annotations through it
    try:
        code = compile(src, hook_budget.__file__, "exec")
        if want is None:
            exec(code, mod.__dict__)
            assert mod.CHANNEL_BUDGET_BYTES == hook_budget.CHANNEL_BUDGET_BYTES
        else:
            with pytest.raises(ValueError, match=re.escape(want)):
                exec(code, mod.__dict__)
    finally:
        sys.modules.pop(name, None)
    assert importlib.util.find_spec("refmatrix.hook_budget") is not None


# ---- AC-9 / AC-2 unit: the fitter -------------------------------------------------------------------


def _n(x) -> int:
    return x if isinstance(x, int) else len(x)


@pytest.mark.parametrize("n", [2000, 4000, 9000])
def test_ac9_fit_blocks_whole_blocks_in_order_bytes_and_trailer(n):
    """`hook_budget.fit_blocks`: whole blocks only, in the given order, ≤ N UTF-8 BYTES (each
    block is `—`/`→`-dense: a chars-counting fitter overflows), a one-line omitted trailer
    naming the dropped count (R0b)."""
    hb = s.hook_budget_mod()
    assert hb is not None, "R0b: refmatrix.hook_budget.fit_blocks is not built"
    blocks = [f"block {i:02d} — " + "→ — " * (40 + 7 * i) + "\n" for i in range(25)]
    assert sum(len(b) for b in blocks) > 9000       # every N drops something
    f = hb.fit_blocks(blocks, n, trailer=lambda k: f"+{k} blocks omitted")
    raw = f.text.encode("utf-8")
    assert len(raw) <= n and f.payload_bytes == len(raw)
    kept, dropped = _n(f.kept), _n(f.dropped)
    assert kept + dropped == len(blocks) and dropped > 0 and kept > 0
    assert f.text.startswith("".join(blocks[:kept]))          # a whole-block prefix
    assert blocks[kept] not in f.text                         # never a cut block after it
    assert f.text.rstrip("\n").splitlines()[-1] == f"+{dropped} blocks omitted"
    # chars-vs-bytes: the kept prefix plus the next block fits in CHARS but not in BYTES
    nxt = "".join(blocks[:kept + 1])
    assert len(nxt.encode("utf-8")) > n


def test_ac9_fit_blocks_everything_fits_has_no_trailer():
    hb = s.hook_budget_mod()
    assert hb is not None, "R0b: refmatrix.hook_budget.fit_blocks is not built"
    blocks = ["a — →\n", "b — →\n"]
    f = hb.fit_blocks(blocks, 1000, trailer=lambda k: f"+{k} blocks omitted")
    assert f.text == "".join(blocks) and _n(f.dropped) == 0


# ---- AC-9 / AC-2 / AC-10 unit: the packer -----------------------------------------------------------


def _urow(i: int, *, scope: str = "project", body: int = 600, name: str | None = None) -> dict:
    name = name or f"u_mem_{i:02d}"
    content = (f"# Unit title {i} {{#root}}\n\nFirst sentence of {name} — → — → unit.\n\n"
               f"BODYMARK {name} — the body → whole.\n" + "body line — → — →\n" * (body // 24))
    return {"id": 9000 + i, "name": name, "mtype": "project", "scope": scope,
            "partition": "global" if scope == "global" else "unitp", "kind": "memory",
            "content": content,
            "metadata": {"title": f"Unit title {i} — row → {i}",
                         "source_path": f"/unit/memory/{name}.md"}}


def _uhooks(rows) -> dict:
    return {r["name"]: f"HOOK-{r['name']} — curated → pointer → {r['id']}" for r in rows}


def _pack_unit(rows, *, max_bytes, hooks=None, channel="session_start", query=None,
               mode="session-start", k_more=30):
    try:
        from refmatrix import recall_pack
    except ImportError:
        pytest.fail("R4: refmatrix.recall_pack is not built")
    return recall_pack.pack(rows, hooks=_uhooks(rows) if hooks is None else hooks,
                            max_bytes=max_bytes, channel=channel, query=query, mode=mode,
                            k_more=k_more)


@pytest.mark.parametrize("n", [2000, 4000, 9000])
def test_ac9_pack_hook_lines_first_whole_bodies_arithmetic_and_bytes(n):
    """R3/R8 on a multibyte fixture: hook lines for ALL named hits before any body; bodies are
    whole and ⊆ named; a body is never a second named hit; named + trailer N = hits given;
    ≤ N UTF-8 bytes; payload_bytes is the byte length (AC-2, AC-9, AC-14)."""
    rows = [_urow(i, body=300 + 120 * i) for i in range(20)]
    p = _pack_unit(rows, max_bytes=n)
    raw = p.text.encode("utf-8")
    assert len(raw) <= n and p.payload_bytes == len(raw)
    pk = s.Pack(raw)
    assert pk.named == list(p.named) and len(set(pk.named)) == len(pk.named)
    assert len(pk.named) + pk.more == len(rows) and p.more == pk.more
    assert set(pk.bodied) <= set(pk.named)
    last_hook = max(p.text.index(m.group(0)) for m in pk.hook_lines)
    for b in pk.bodied:
        content = next(r["content"] for r in rows if r["name"] == b)
        assert content in p.text, f"body of {b} is cut"
        assert p.text.index(content) > last_hook, f"body of {b} precedes a hook line"
    assert pk.header and str(n) in pk.header, pk.header


def test_ac9_pack_curated_hook_else_first_sentence_and_scope_correct_fetch():
    """R3(b)/R6: the curated hook (looked up by the row's memory id) when present, else the
    first sentence; a global row's fetch pointer reads `--scope global` (AC-11's pack leg)."""
    rows = [_urow(0), _urow(1, scope="global"), _urow(2)]
    hooks = _uhooks(rows[:2])                    # u_mem_02 has no curated hook
    p = s.Pack(_pack_unit(rows, max_bytes=9000, hooks=hooks).text.encode())
    assert "HOOK-u_mem_00" in p.hook_line_of("u_mem_00")
    assert "HOOK-u_mem_01" in p.hook_line_of("u_mem_01")
    assert "First sentence of u_mem_02" in p.hook_line_of("u_mem_02")
    assert p.fetch_of("u_mem_00") == "rmx memory get u_mem_00"
    assert p.fetch_of("u_mem_01") == "rmx memory get u_mem_01 --scope global"


def test_ac9_pack_trailer_quotes_a_multiline_query():
    """R3(d): `+N more: rmx memory recall <q> --k M`, the query collapsed to one line, ≤ 120
    chars, shlex-quoted (a shell metacharacter cannot escape the pointer).

    Rev 7 J1 (2026-11-13): 19.1 R3(d) prints the trailer only when a retrieved hit is NOT
    named, so the fixture carries more rows than fit -- 20 hook lines of ~125 B cannot fit
    beside the header in 2,000 B (measured at GREEN: 14 named, 6 in the trailer). 12 rows
    (the RED fixture) all fit, so the trailer's precondition never held."""
    q = "line one of the question\nline two; rm -rf $HOME `x` " + "pad " * 40
    rows = [_urow(i, body=2000) for i in range(20)]
    p = _pack_unit(rows, max_bytes=2000, channel="prompt_recall", query=q, mode="dense",
                   k_more=24)
    pk = s.Pack(p.text.encode())
    assert pk.trailer is not None and pk.more == 20 - len(pk.named) > 0, (pk.named, pk.more)
    toks = shlex.split(pk.trailer.group("cmd"))
    assert toks[:3] == ["rmx", "memory", "recall"]
    assert "\n" not in toks[3] and len(toks[3]) <= 120
    assert toks[3].startswith("line one of the question line two; rm -rf $HOME")
    assert toks[toks.index("--k") + 1] == "24"


def test_ac9_pack_loud_overflow_never_empty_never_over():
    """R8/19.1 R5: header + first hook line > N → the header plus a one-line error naming N."""
    rows = [_urow(0)]
    hooks = {"u_mem_00": "HOOK " + "— → " * 120}
    n = 240
    p = _pack_unit(rows, max_bytes=n, hooks=hooks)
    raw = p.text.encode("utf-8")
    assert raw and len(raw) <= n
    lines = p.text.rstrip("\n").splitlines()
    assert len(lines) == 2 and str(n) in lines[1], lines
    assert list(p.named) == []


def _unreadable_index_memdir(tag: str) -> "tuple[Path, Path]":
    """A project whose sandbox memdir holds a MEMORY.md this process cannot read (mode 000): a
    REAL `load_hooks` failure (`PermissionError` from `_index_hook_records`), nothing patched.
    Returns (root, MEMORY.md); the caller restores the mode."""
    base = s.short_base(tag)
    proj = base / "fxh"
    md = s.copy_memdir(proj, include={f"fx_mem_{i:02d}" for i in range(3)})
    idx = md / "MEMORY.md"
    os.chmod(idx, 0)
    return proj / ".refmatrix", idx


def test_s2_pack_recall_never_drops_a_curated_hooks_failure():
    """bsd-251 s-2 / L68 (2026-11-14): `verbs.pack_recall` with NO warnings list and a
    `load_hooks` that fails must surface the failure -- it raises, or the result carries a
    warning naming it. CLAUDE.md #no-silent-failures: every hook line silently fell back to
    its first sentence. HEAD: the `except` appends only `if warnings is not None`, so nothing
    reaches the caller. A caller that passes a list keeps getting the warning (a guard)."""
    from refmatrix import verbs
    root, idx = _unreadable_index_memdir("p25h")
    rows = [_urow(i) for i in range(3)]
    try:
        try:
            res = verbs.pack_recall(root, rows, mode="dense", query=QUESTION, k=12,
                                    max_bytes=4000, channel="prompt_recall")
        except Exception as e:  # noqa: BLE001 -- raising is one of the two allowed outcomes
            assert "PermissionError" in f"{type(e).__name__}: {e}" or "hook" in str(e).lower(), (
                f"s-2: raised, but not about the curated hooks: {type(e).__name__}: {e}")
        else:
            said = [w for w in res.get("warnings") or [] if "curated hooks unreadable" in w]
            assert said, (f"s-2: pack_recall swallowed a load_hooks failure (no warnings list "
                          f"passed, no raise, result keys {sorted(res)})")
        ws: list[str] = []
        verbs.pack_recall(root, rows, mode="dense", query=QUESTION, k=12, max_bytes=4000,
                          channel="prompt_recall", warnings=ws)
        assert any("curated hooks unreadable" in w and "PermissionError" in w for w in ws), ws
    finally:
        os.chmod(idx, 0o644)


def test_s2_busy_fall_through_says_a_curated_hooks_failure(offline):
    """bsd-251 s-2 / L68: the SessionStart argv's busy/absent fall-through (`cli.py`, the
    lock-free replica serves `--session-start` and packs through `verbs.pack_recall`) SAYS a
    `load_hooks` failure on stderr. Store B of `offline` (replica on disk, no daemon), its
    MEMORY.md made unreadable. HEAD: the fall-through passes no warnings list, the pack falls
    back to first sentences, and nothing names why."""
    b = offline["b"]
    idx = b.memdir / "MEMORY.md"
    mode = idx.stat().st_mode
    os.chmod(idx, 0)
    try:
        r = s.run_cmd(b, s.recall_cmd(b.root, "SessionStart"),
                      env_in=s.envelope("", event="SessionStart", source="resume"),
                      RMX_HOME=str(offline["home"]),
                      RMX_MODEL_SOCK=str(offline["base"] / "none.sock"))
    finally:
        os.chmod(idx, mode)
    err = r.stderr.decode("utf-8", "replace")
    _ok(r, "SessionStart argv (fall-through)")
    assert "reading the replica" in err, f"fixture: the fall-through did not serve: {err[-600:]}"
    p = _pack(r, "SessionStart argv (fall-through)")
    assert p.named, "fixture: the fall-through named no hit"
    assert "curated hooks unreadable" in err, (
        f"s-2: the fall-through dropped a load_hooks failure silently: {err[-800:]!r}")


# bsd-251 r9 m-b (2026-11-14): a child that runs the REAL `cli_entry` with ONE fault injected:
# `verbs.pack_recall` raises `VerbError` (the s-2 contract's raise -- no production caller
# reaches it today, both pass a list). Replaced in the CHILD only; this process is untouched.
_PACK_RAISES_RUN = r"""
import sys
from refmatrix import verbs
def _raise(*a, **kw):
    raise verbs.VerbError("curated hooks unreadable (PermissionError: injected by the m-b test)")
verbs.pack_recall = _raise
from refmatrix.cli import cli_entry
sys.argv = ["rmx", *sys.argv[1:]]
cli_entry()
"""


def test_mb_fall_through_verb_error_is_one_error_line(offline):
    """bsd-251 r9 m-b: the `--session-start` replica fall-through of `rmx memory recall` (the
    path a busy OR absent daemon takes; both land in ONE `except (VerbBusyError,
    VerbAbsentError)` handler) calls `verbs.pack_recall` INSIDE that handler, so a `VerbError`
    raised there escapes its sibling `except VerbError`. The user's 2026-11-10 rule: a failure is
    ONE `Error:` line and a non-zero exit, never a traceback, and the hook injects nothing.

    The generated SessionStart argv runs on store B of `offline` (replica on disk, no daemon:
    `VerbAbsentError`, then the fall-through, proven by "reading the replica" on stderr), in a
    child whose `verbs.pack_recall` raises `VerbError`. HEAD 988e96d: the traceback."""
    b = offline["b"]
    argv = shlex.split(s.after_env(s.recall_cmd(b.root, "SessionStart")))
    assert argv[0] == "rmx", argv
    env = h.rmx_env(b.root, RMX_HOME=str(offline["home"]), RMX_INVOCATION_SOURCE="hook",
                    RMX_MODEL_SOCK=str(offline["base"] / "none.sock"),
                    OBJC_DISABLE_INITIALIZE_FORK_SAFETY="YES")
    r = subprocess.run([sys.executable, "-c", _PACK_RAISES_RUN, *argv[1:]], env=env,
                       cwd=str(b.proj), capture_output=True, timeout=300,
                       input=json.dumps(s.envelope("", event="SessionStart",
                                                   source="resume")).encode())
    err = r.stderr.decode("utf-8", "replace")
    assert "reading the replica" in err, f"fixture: the fall-through did not serve: {err[-800:]}"
    assert "Traceback" not in err, f"m-b: a traceback, not one Error: line: {err[-1500:]}"
    assert r.returncode == 1, (r.returncode, err[-600:])
    errs = [ln for ln in err.splitlines() if ln.startswith("Error:")]
    assert len(errs) == 1 and "curated hooks unreadable" in errs[0], err[-800:]
    assert r.stdout == b"", f"m-b: the hook printed {len(r.stdout)} B: {r.stdout[:200]!r}"


def test_ac10_pack_spans_are_utf8_byte_ranges():
    """R9: per named hit, `offset_bytes`/`bytes` slice its hook line (newline included) and
    `body_offset_bytes`/`body_bytes` its body, in BYTES; ≥ 3 `—` precede the last hook line
    and every body, so character offsets miss (AC-10 pre-check, built into the rows)."""
    rows = [_urow(i, body=300) for i in range(8)]
    p = _pack_unit(rows, max_bytes=4000)
    raw = p.text.encode("utf-8")
    by = {sp["name"]: sp for sp in p.spans}
    assert set(by) == set(p.named) and p.named
    pk = s.Pack(raw)
    bodied = set(pk.bodied)
    assert bodied, "the 4,000 B unit pack carries no body"
    for name, sp in by.items():
        line = raw[sp["offset_bytes"]:sp["offset_bytes"] + sp["bytes"]]
        assert line == (pk.hook_line_of(name) + "\n").encode("utf-8"), (name, line)
        if name in bodied:
            body = raw[sp["body_offset_bytes"]:sp["body_offset_bytes"] + sp["body_bytes"]]
            content = next(r["content"] for r in rows if r["name"] == name)
            assert body.decode("utf-8") == content
            assert raw[:sp["body_offset_bytes"]].decode().count("—") >= 3
        else:
            assert sp["body_offset_bytes"] is None and sp["body_bytes"] is None
    last = max(by.values(), key=lambda sp: sp["offset_bytes"])
    assert raw[:last["offset_bytes"]].decode().count("—") >= 3


def _memdir_rows(md: Path) -> list[dict]:
    """Rows as the bridge stores them: name = GMD id, metadata.source_path = the file."""
    from refmatrix.memory_layout import iter_memory_files
    rows = []
    for i, p in enumerate(iter_memory_files(md)):
        text = p.read_text(encoding="utf-8")
        rows.append({"id": 100 + i, "name": p.stem, "mtype": "project", "scope": "project",
                     "partition": "unitp", "kind": "memory",
                     "content": text.split("---", 2)[2].lstrip("\n"),
                     "metadata": {"title": p.stem, "source_path": str(p)}})
    return rows


@pytest.mark.parametrize("shape", ["path-keyed", "id-keyed"])
def test_ac9_pack_prints_curated_hooks_from_load_hooks(tmp_path, shape):
    """R4 (r3 #m2): `hooks` is `memory_index.load_hooks(memdir)` UNCHANGED -- path-keyed
    (MEMORY.md links + a sidecar keyed by relative path, HEAD's shape) or id-keyed (26.1's
    organised sidecar). In both, every named hit prints its curated hook, never its first
    sentence."""
    from refmatrix import memory_index
    md = tmp_path / "memory"
    md.mkdir()
    names = [f"fx_mem_{i:02d}" for i in range(6)]
    for nme in names:
        (md / f"{nme}.md").write_bytes((s.FIX / "memory" / f"{nme}.md").read_bytes())
    if shape == "path-keyed":
        lines = [ln for ln in (s.FIX / "memory" / "MEMORY.md").read_text().splitlines()
                 if any(f"({n}.md)" in ln for n in names)]
        (md / "MEMORY.md").write_text("\n".join(lines) + "\n")
    else:
        (md / memory_index.HOOKS_SIDECAR).write_text(json.dumps(
            {n: f"HOOK-{n} — curated by id → organised" for n in names}))
    hooks = memory_index.load_hooks(md)
    rows = _memdir_rows(md)
    p = s.Pack(_pack_unit(rows, max_bytes=9000, hooks=hooks, channel="prompt_recall",
                          query=QUESTION, mode="dense", k_more=12).text.encode())
    assert set(p.named) == set(names)
    for n in names:
        line = p.hook_line_of(n)
        assert f"HOOK-{n}" in line and "First sentence" not in line, line


# ---- AC-1 / AC-4 (a): the cliquedb shape on the generated argv ------------------------------------


def test_ac1_ac4a_per_prompt_argv_within_prompt_recall_budget(fx):
    """AC-1 + AC-4 (a): daemon up, `--scope both` with a tmp global store of 10 memories: the
    per-prompt argv on the question prompt prints ≤ budget("prompt_recall"). HEAD: > 10,000 B."""
    r = _q(fx)
    _ok(r, "per-prompt argv")
    s.assert_within(len(r.stdout), "prompt_recall", "AC-1 per-prompt argv (question)")
    p = _pack(r, "per-prompt argv")
    assert any(n in s.GLOBAL_NAMES for n in p.named), (
        f"AC-4 (a): no global row named under --scope both: {p.named}")


def test_ac1_ac4a_ack_prompt_within_budget(fx):
    r = _q(fx, s.ACK)
    _ok(r, "per-prompt argv (ack)")
    s.assert_within(len(r.stdout), "prompt_recall", "AC-1 per-prompt argv (ack)")


def test_ac1_ac4a_session_start_argv_within_budget(fx):
    """AC-1 + AC-4 (a) `--session-start`: ≤ budget("session_start")."""
    r = _ss(fx)
    _ok(r, "SessionStart argv")
    s.assert_within(len(r.stdout), "session_start", "AC-1 SessionStart argv")
    _pack(r, "SessionStart argv")


def test_ac1_ac4a_precompact_argv_within_budget_or_dropped(fx):
    """AC-1 + AC-4 (a) `--recent --since 1h`: ≤ budget("precompact"), or (R0 drops it) the
    generated PreCompact block has no recall command."""
    cmds = _pc_cmds(fx)
    if not cmds:
        return            # R7: R0 found PreCompact stdout does not reach the agent
    (cmd,) = cmds
    r = s.run_cmd(fx, cmd, env_in=s.envelope("", event="PreCompact"))
    _ok(r, "PreCompact argv")
    s.assert_within(len(r.stdout), "precompact", "AC-1 PreCompact argv")
    _pack(r, "PreCompact argv")


# ---- AC-2: --max-bytes N on every channel, multibyte ------------------------------------------------


@pytest.mark.parametrize("n", [2000, 4000, 9000])
@pytest.mark.parametrize("channel", ["prompt_recall", "session_start", "precompact",
                                     "scan_prompt", "focus_context"])
def test_ac2_max_bytes_bounds_every_channel(fx, channel, n):
    """AC-2: `--max-bytes N` caps the payload at N UTF-8 bytes on every channel (the fixture's
    hook lines and bodies carry ≥ 4 `—`/`→` each)."""
    flag = f" --max-bytes {n}"
    if channel == "prompt_recall":
        r = _q(fx, append=flag)
    elif channel == "session_start":
        r = _ss(fx, append=flag)
    elif channel == "precompact":
        cmds = _pc_cmds(fx)
        if not cmds:
            return
        r = s.run_cmd(fx, cmds[0] + flag, env_in=s.envelope("", event="PreCompact"))
    elif channel == "scan_prompt":
        cmd = s.scan_prompt_part(fx.root).replace(" 2>/dev/null || true", "")
        r = s.run_cmd(fx, cmd + flag, env_in=s.envelope(QUESTION))
    else:
        r = s.run_cmd(fx, s.HOOK_ENV + f"rmx focus context --top 15{flag}")
    _ok(r, f"{channel} --max-bytes {n}")
    assert r.stdout, f"{channel} --max-bytes {n}: empty payload (R8: never empty)"
    assert len(r.stdout) <= n, f"{channel}: {len(r.stdout)} B > --max-bytes {n}"


# bsd-251 s-1 (2026-11-14): N small enough that each producer's fitted text is CLIPPED to its
# cap (`fit_blocks`' trailer-alone branch; the pack's loud-overflow branch), so its payload lands
# EXACTLY on the edge. Measured before writing (2026-11-14): at 20 and 30 B every producer lands
# on N; at 60 B scan-prompt's whole trailer (`# [+14 block(s) omitted …]`, 43 B) fits, so it does
# not.
_EDGE_N = (20, 30)


@pytest.mark.parametrize("n", _EDGE_N)
@pytest.mark.parametrize("producer", ["prompt_recall", "scan_prompt", "curator_status"])
def test_s1_max_bytes_is_n_bytes_on_the_wire_newline_counted(fx, producer, n):
    """R8 "never over N" on what the agent RECEIVES, at the one place it can fail: a payload of
    exactly N bytes. Three writers hold back the newline they print -- `_echo_pack`'s
    `nl=False`, and `cap - 1` handed to `fit_blocks` by `curator status` and `scan-prompt` --
    and a fixture that never lands on N cannot see any of them go (bsd-251 m2/m3/m4 survived
    AC-2, AC-7 and AC-12). Each producer runs as the GENERATED hook argv, `--max-bytes N`
    appended; stdout is taken whole (no rstrip). The second assertion is the fixture's: the
    payload IS N bytes, so the first one tests the edge and not the interior."""
    if producer == "prompt_recall":
        r = _q(fx, append=f" --max-bytes {n}")
    elif producer == "scan_prompt":
        cmd = s.scan_prompt_part(fx.root).replace(" 2>/dev/null || true", "")
        r = s.run_cmd(fx, cmd + f" --max-bytes {n}", env_in=s.envelope(QUESTION))
    else:
        r = s.run_cmd(fx, s.HOOK_ENV + f"rmx curator status --max-bytes {n}")
    _ok(r, f"{producer} --max-bytes {n}")
    assert len(r.stdout) <= n, (f"s-1: {producer} put {len(r.stdout)} B on the wire > "
                                f"--max-bytes {n}: {r.stdout!r}")
    assert len(r.stdout) == n, (f"s-1 fixture: {producer} at --max-bytes {n} printed "
                                f"{len(r.stdout)} B, not the edge: {r.stdout!r}")


def test_ac2_fixture_density_precheck():
    """PRE-CHECK (not a RED test; AC-2/AC-10 admit the fixture only if it holds): every hook
    line's curated hook and every body carries ≥ 4 of `—`/`→`, so a chars-counting packer
    overflows by ≥ 8 B per line. The chars-counting MUTATION run is recorded at GREEN."""
    idx = (s.FIX / "memory" / "MEMORY.md").read_text(encoding="utf-8").splitlines()
    for ln in idx:
        hook = ln.split(") — ", 1)[1]
        assert hook.count("—") + hook.count("→") >= 4, ln
    for nme in s.MEM_NAMES:
        body = (s.FIX / "memory" / f"{nme}.md").read_text(encoding="utf-8")
        assert body.count("—") + body.count("→") >= 4, nme


# ---- AC-3: reach ----------------------------------------------------------------------------------


def test_ac3_reach_at_least_8_distinct_memories(fx):
    """AC-3: distinct non-subject, non-session memories the MODEL receives (whole payload ≤ cap,
    else the preview) ≥ 8 on the per-prompt argv. HEAD: 0 (18,880 B → a 2 KB JSON preview)."""
    r = _q(fx)
    _ok(r, "per-prompt argv")
    got = s.distinct_memories_received(r.stdout)
    # The hook's stderr rides the message: an empty payload with exit 0 is a degraded skip
    # (d8), and its cause is said there, never guessed (one 0 B failure at load ~30, 2026-11-13).
    assert len(got) >= 8, (f"AC-3: the model receives {len(got)} distinct memories "
                           f"({sorted(got)}) from a {len(r.stdout)} B payload; stderr: "
                           f"{r.stderr.decode('utf-8', 'replace')[-600:]!r}")


# ---- AC-4 (b)(c)(e)(g): the verb serves every caller --------------------------------------------


def _named_b(offline) -> set[str]:
    return {f"fx_mem_{i:02d}" for i in range(10, 18)}


def _named_a(offline) -> set[str]:
    return {f"fx_mem_{i:02d}" for i in range(0, 6)}


def test_ac4b_verb_reads_the_replica_with_a_shared_worker_and_no_daemon(offline, monkeypatch):
    """AC-4 (b): no daemon, replica + a REAL sandbox shared worker: `verbs.memory_recall(query,
    pack=True)` returns B's rows from the replica within the budget. HEAD: the verb never
    consults the replica and raises VerbAbsentError."""
    from refmatrix import verbs
    b = offline["b"]
    w = s.SharedWorker(offline["base"], home=offline["home"])
    try:
        monkeypatch.setenv("RMX_HOME", str(offline["home"]))
        monkeypatch.setenv("RMX_MODEL_SOCK", str(w.sock))
        cap = s.budget_or_none("prompt_recall") or 4000
        try:
            res = verbs.memory_recall(b.root, query=QUESTION, k=12, pack=True, max_bytes=cap)
        except verbs.VerbError as e:
            pytest.fail(f"AC-4 (b): the verb raised {type(e).__name__}: {e} with a replica "
                        f"and a live shared worker at {w.sock}")
        assert "text" in res, f"AC-4 (b): pack=True returned no `text`: keys {sorted(res)}"
        raw = res["text"].encode("utf-8")
        assert len(raw) <= cap and res["payload_bytes"] == len(raw)
        named = set(s.Pack(raw).named)
        assert named and named <= _named_b(offline), named
        assert any("replica" in w_.lower() for w_ in res.get("warnings") or []), res.get(
            "warnings")
    finally:
        w.stop()


def test_ac4c_hook_mode_no_daemon_no_worker_exits_0_silent_and_counted(offline):
    """AC-4 (c) / d8: no daemon, no hub worker, HOOK mode: the per-prompt argv prints NOTHING,
    exits 0, loads no model and spawns no worker (no `sentence_transformers` import; within the
    5 s hook budget), and its recall row reads outcome "error", error "VerbAbsentError: …".
    HEAD: exit 1, "needs the daemon up …"."""
    b = offline["b"]
    before = len(s.recall_rows(b.root))
    cmd = s.recall_cmd(b.root, "UserPromptSubmit")
    t0 = time.monotonic()
    r = s.run_cmd(b, cmd, env_in=s.envelope(QUESTION), RMX_HOME=str(offline["home"]),
                  RMX_MODEL_SOCK=str(offline["base"] / "none.sock"), PYTHONPROFILEIMPORTTIME="1")
    took = time.monotonic() - t0
    err = r.stderr.decode("utf-8", "replace")
    said = "\n".join(ln for ln in err.splitlines() if not ln.startswith("import time:"))
    assert r.returncode == 0, f"AC-4 (c): exit {r.returncode}: {said[-600:]}"
    assert r.stdout == b"", f"AC-4 (c): stdout not empty: {r.stdout[:200]!r}"
    assert "sentence_transformers" not in err, "AC-4 (c): the hook imported a model"
    assert took < 5.0, f"AC-4 (c): {took:.1f}s -- over the 5 s hook budget"
    rows = s.recall_rows(b.root)[before:]
    assert len(rows) == 1, rows
    assert rows[0].get("outcome") == "error", rows[0]
    assert str(rows[0].get("error", "")).startswith("VerbAbsentError: memory recall needs the "
                                                    "daemon up"), rows[0]


def test_ac4c_verb_hub_only_raises_the_r5_absent_error(offline, monkeypatch):
    from refmatrix import verbs
    b = offline["b"]
    monkeypatch.setenv("RMX_HOME", str(offline["home"]))
    monkeypatch.setenv("RMX_MODEL_SOCK", str(offline["base"] / "none.sock"))
    with pytest.raises(verbs.VerbAbsentError) as ei:
        verbs.memory_recall(b.root, query=QUESTION, k=12, embedder_policy="hub_only")
    assert str(ei.value) == ("memory recall needs the daemon up (dense embedder lives there) "
                             "or a replica + shared model workers"), str(ei.value)


def test_ac4e_mcp_cross_project_reads_the_named_stores_replica(offline, monkeypatch):
    """AC-4 (e): stores A and B, a real shared worker, no daemons; B registered. From A's cwd,
    MCP `rmx_memory_recall` with project=B returns B's rows (none of A's) from B's replica.
    HEAD: the MCP verb never consults a replica and answers an error."""
    from refmatrix import mcp
    a, b = offline["a"], offline["b"]
    monkeypatch.setenv("RMX_HOME", str(offline["home"]))
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    monkeypatch.chdir(a.proj)
    bname = b.partition()
    assert mcp._resolve_root({"project": bname}).resolve() == b.root.resolve()
    w = s.SharedWorker(offline["base"], home=offline["home"])
    try:
        with s.McpChild(cwd=a.proj, RMX_HOME=str(offline["home"]), REFMATRIX_ROOT=None,
                        RMX_MODEL_SOCK=str(w.sock)) as m:
            res = m.tool("rmx_memory_recall", {"query": QUESTION, "k": 8, "project": bname})
    finally:
        w.stop()
    assert not res["isError"] and res["json"] and "error" not in res["json"], res["text"][:600]
    names = {r["name"] for r in res["json"]["memories"]}
    assert names and names <= _named_b(offline), names
    assert not names & _named_a(offline)


# ---- AC-4 (e) R10 (bug-181): an unknown project is an error on every tool ---------------------------


@pytest.fixture(scope="module")
def r10_stores():
    """Stores alpha (the cwd) and bravo (registered), a home whose registry knows only bravo;
    `charlie` names nothing. alpha holds 2 memories. No daemons."""
    from refmatrix import discovery
    from refmatrix.store import Store
    base = s.short_base("r10")
    home = base / "home" / ".refmatrix"
    s._init_store(home, partition="global")
    alpha, bravo = base / "alpha" / ".refmatrix", base / "bravo" / ".refmatrix"
    for r in (alpha, bravo):
        s._init_store(r)
    st = Store(alpha)
    try:
        for i in range(2):
            st.add_memory(name=f"alpha_mem_{i}", content=f"{QUESTION} alpha {i}",
                          mtype="project")
    finally:
        st.close()
    old = os.environ.get("RMX_HOME")
    os.environ["RMX_HOME"] = str(home)
    try:
        discovery.register_root(bravo)
    finally:
        os.environ["RMX_HOME"] = old if old is not None else ""
        if old is None:
            os.environ.pop("RMX_HOME")
    yield {"alpha": alpha, "bravo": bravo, "home": home, "base": base}
    import rmx_sandbox
    rmx_sandbox.remove_tree(base)


@pytest.fixture
def r10(r10_stores, monkeypatch):
    """This process pointed at the R10 stores: RMX_HOME = their home, REFMATRIX_ROOT unset,
    cwd inside alpha."""
    monkeypatch.setenv("RMX_HOME", str(r10_stores["home"]))
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    monkeypatch.chdir(r10_stores["alpha"].parent)
    return r10_stores


def _alpha_count(alpha: Path) -> int:
    from refmatrix.store import Store
    st = Store(alpha)
    try:
        return st._connect().execute(
            "SELECT count(*) FROM entities WHERE kind='memory'").fetchone()[0]
    finally:
        st.close()


def test_ac4e_r10_resolve_root_unknown_project_raises(r10):
    """R10 leg (1): `_resolve_root({"project": "charlie"})` raises VerbUnknownProjectError
    (a VerbArgsError) with R10's words. HEAD: returns alpha's root (bug-181)."""
    from refmatrix import mcp, verbs
    try:
        got = mcp._resolve_root({"project": "charlie"})
    except Exception as e:  # noqa: BLE001 -- the type is the assertion
        err = e
    else:
        pytest.fail(f"R10: project='charlie' names no store, yet _resolve_root returned {got} "
                    f"(bug-181 silent fallback)")
    assert type(err).__name__ == "VerbUnknownProjectError", repr(err)
    assert isinstance(err, verbs.VerbArgsError)
    assert not isinstance(err, (verbs.VerbAbsentError, verbs.VerbBusyError))
    # R10 #r10-words. The known list is every discovered store, sorted; the sandbox may hold
    # other tests' launchd-registered roots, so the list is checked for order and membership.
    msg = str(err)
    head = "project 'charlie' names no registered refmatrix store (known: "
    tail = "); pass a registered project name or root=<path>"
    assert msg.startswith(head) and msg.endswith(tail), msg
    known = msg[len(head):-len(tail)].split(", ")
    assert known == sorted(known) and {"alpha", "bravo", "global"} <= set(known), known
    assert "charlie" not in known


def test_ac4e_r10_recall_tool_answers_iserror_without_cwd_rows(r10):
    """R10 leg (2): MCP tools/call rmx_memory_recall project=charlie → isError, text starting
    `VerbUnknownProjectError:`, none of alpha's rows. HEAD: alpha is read (no isError)."""
    from refmatrix import mcp
    resp = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "rmx_memory_recall",
        "arguments": {"query": QUESTION, "project": "charlie"}}})
    res = resp["result"]
    text = "".join(c.get("text", "") for c in res.get("content") or [])
    assert res.get("isError") is True, text[:400]
    assert text.startswith("VerbUnknownProjectError:"), text[:400]
    assert "alpha_mem_" not in text


_SWEEP = r"""
import json, socket, sys
connects = []
def _hook(ev, args):
    if ev == "socket.connect" and isinstance(args[1], str):
        connects.append(args[1])
sys.addaudithook(_hook)
# Positive control: the counter must SEE a connect, or "0 connects" proves nothing
# (feedback_clean_corpus_hides_a_dead_gate). One AF_UNIX connect to a listener of our own.
import os, tempfile
_d = tempfile.mkdtemp(dir=os.environ["RMX_SANDBOX_ROOT"])
_p = os.path.join(_d, "c.sock")
_srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
_srv.bind(_p)
_srv.listen(1)
_c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
_c.connect(_p)
_c.close()
_srv.close()
control = [c for c in connects if c == _p]
connects.clear()
from refmatrix import mcp
out = {"__control__": control}
for name in sorted(mcp.TOOLS):
    n0 = len(connects)
    resp = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": name, "arguments": {"project": "charlie"}}})
    res = resp.get("result") or {}
    out[name] = {"isError": res.get("isError"),
                 "text": "".join(c.get("text", "") for c in res.get("content") or [])[:300],
                 "connects": connects[n0:]}
n0 = len(connects)
resp = mcp.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
    "name": "rmx_memory_add",
    "arguments": {"project": "charlie", "name": "leaked_into_cwd", "content": "x"}}})
res = resp.get("result") or {}
out["__memory_add_full__"] = {"isError": res.get("isError"),
                              "text": "".join(c.get("text", "") for c in res.get("content") or [])[:300],
                              "connects": connects[n0:]}
print("SWEEP " + json.dumps(out))
"""


@pytest.fixture(scope="module")
def r10_sweep(r10_stores):
    """ONE child sweeps every tool in `mcp.TOOLS` with project="charlie" and no other argument,
    counting AF_UNIX connects per call by audit hook, then calls rmx_memory_add with a name and
    content. A child (not in-process) because at HEAD each verb RUNS against the cwd store."""
    before = _alpha_count(r10_stores["alpha"])
    env = h.clean_env(HOME=os.environ["HOME"], RMX_HOME=str(r10_stores["home"]), REFMATRIX_ROOT=None)
    p = subprocess.run([sys.executable, "-c", _SWEEP], env=env, cwd=str(r10_stores["alpha"].parent),
                       capture_output=True, text=True, timeout=900)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("SWEEP ")), None)
    assert line, f"sweep child produced no result (rc={p.returncode}): {p.stderr[-1500:]}"
    return {"out": json.loads(line[6:]), "before": before, "after": _alpha_count(r10_stores["alpha"])}


def _tool_names() -> list[str]:
    from refmatrix import mcp
    return sorted(mcp.TOOLS)


@pytest.mark.parametrize("tool", _tool_names())
def test_ac4e_r10_every_tool_refuses_an_unknown_project(r10_sweep, tool):
    """R10 leg (3): every MCP tool, project="charlie" and nothing else, answers isError with
    VerbUnknownProjectError BEFORE any verb runs: 0 socket connects."""
    assert r10_sweep["out"]["__control__"], "the sweep's connect counter saw no control connect"
    got = r10_sweep["out"][tool]
    assert got["isError"] is True and got["text"].startswith("VerbUnknownProjectError:"), got
    assert got["connects"] == [], got


def test_ac4e_r10_memory_add_never_bootstraps_into_the_cwd_store(r10_sweep):
    """R10 leg (3): `rmx_memory_add` project="charlie" + name + content → isError, and alpha's
    memory count is unchanged (HEAD: the bootstrap fallback writes into the cwd store)."""
    got = r10_sweep["out"]["__memory_add_full__"]
    assert got["isError"] is True and got["text"].startswith("VerbUnknownProjectError:"), got
    assert r10_sweep["after"] == r10_sweep["before"], (r10_sweep["before"], r10_sweep["after"])


def test_ac4e_r10_no_project_and_explicit_root_are_unchanged(r10):
    """R10 leg (4) -- a GUARD, not RED at HEAD (proved by mutation, see the summary): `{}`
    still resolves to the cwd store; `root` wins over an unknown `project`."""
    from refmatrix import mcp
    alpha, bravo = r10["alpha"].resolve(), r10["bravo"].resolve()
    assert mcp._resolve_root({}).resolve() == alpha
    assert mcp._resolve_root({"project": ""}).resolve() == alpha     # empty = not given
    # root wins: bravo (not the cwd store), whatever `project` says -- known or not
    assert mcp._resolve_root({"root": str(bravo), "project": "charlie"}).resolve() == bravo
    assert mcp._resolve_root({"root": str(bravo.parent), "project": "alpha"}).resolve() == bravo


def test_r10_schema_says_registered_only():
    """R10 #r10-schema: the transport `project` description says a registered store and that
    an unknown name is an error, never a fallback."""
    from refmatrix import verbs
    d = verbs._TRANSPORT_PROPS["project"]["description"].lower()
    assert "registered" in d and "error" in d, d


# ---- AC-4 (d)(f)(g)(h): one rows computation -------------------------------------------------------


def _verb_named(root: Path, **kw) -> list[str]:
    from refmatrix import verbs
    res = verbs.memory_recall(root, query=QUESTION, k=12, scope="both", pack=True, **kw)
    assert "text" in res, f"pack=True returned no `text`: keys {sorted(res)}"
    return list(res["named"])


@pytest.mark.parametrize("leg", ["replica-on", "replica-first-0", "no-worker"])
def test_ac4d_rows_parity_replica_on_and_off(fx, monkeypatch, leg):
    """AC-4 (d): daemon up in all three; with the replica leg forced on (a real worker), off by
    `RMX_RECALL_REPLICA_FIRST=0` in the calling process, and off by no worker: the per-prompt
    argv's named hits equal the verb's named hits."""
    w = s.SharedWorker(fx.base, home=fx.home) if leg != "no-worker" else None
    try:
        extra = {"RMX_MODEL_SOCK": str(w.sock) if w else str(fx.base / "none.sock")}
        if leg == "replica-first-0":
            extra["RMX_RECALL_REPLICA_FIRST"] = "0"
        p = _pack(_q(fx, **extra), f"per-prompt argv ({leg})")
        for k_, v in extra.items():
            monkeypatch.setenv(k_, v)
        monkeypatch.setenv("RMX_HOME", str(fx.home))
        assert p.named == _verb_named(fx.root), leg
    finally:
        if w:
            w.stop()


def test_ac4f_interactive_recall_names_the_verbs_hits_including_a_doc(fx, monkeypatch):
    """AC-4 (f): `rmx memory recall "q"` (table) and `--json` name the same hits as the verb
    for the same query, and the `kind=doc` leg (moved from the CLI into the verb) is reachable:
    `-K doc` returns the fixture's docs from the verb AND from the CLI.

    Rev 7 J2 (2026-11-13): AC-4 (f) is parity plus reachability of the doc leg; it does not
    require a doc in the top 8 of a MIXED recall (measured at GREEN: the first doc ranks 32-33
    of 40 under either rerank setting -- doc distances 0.52-0.57 against 0.29-0.35 for
    memories). The rank assertion the RED wrote is gone; parity is asserted on BOTH kind sets."""
    from refmatrix import verbs
    monkeypatch.setenv("RMX_HOME", str(fx.home))
    for kinds in ("memory,doc", "doc"):
        r = s.rmx(fx, "memory", "recall", QUESTION, "--json", "-K", kinds, "--k", "8")
        assert r.returncode == 0, (kinds, r.stderr[-800:])
        cli_names = [m["name"] for m in json.loads(r.stdout)]
        # The interactive CLI shows session/* rows (`include_session=True`, an operator
        # affordance pinned by test_plan3_remedy and test_verb_parity); the verb's default
        # hides them. Parity is like for like (g7-7, 2026-11-13: after 26.4 types
        # savestate_fx01 session/recall-state, only the CLI side named it).
        vres = verbs.memory_recall(fx.root, query=QUESTION, k=8, kinds=kinds.split(","),
                                   include_session=True)
        vnames = [m["name"] for m in vres["memories"]]
        assert vnames, f"AC-4 (f): the verb returned nothing for -K {kinds}"
        assert cli_names == vnames, (kinds, cli_names, vnames)
        t = s.rmx(fx, "memory", "recall", QUESTION, "-K", kinds, "--k", "8", COLUMNS="400")
        assert t.returncode == 0, (kinds, t.stderr[-800:])
        for n in vnames:
            assert n in t.stdout, f"table (-K {kinds}) misses {n}"
        if kinds == "doc":
            # reachability: every row the doc leg returns is a fixture doc (kind=doc)
            assert all(m.get("kind") == "doc" for m in vres["memories"]), [
                (m["name"], m.get("kind")) for m in vres["memories"]]
            assert all(m.get("kind") == "doc" for m in json.loads(r.stdout))


def test_ac4g_interactive_no_daemon_no_hub_uses_shared_embedder(offline):
    """AC-4 (g): no daemon, no hub worker, INTERACTIVE: `rmx memory recall "q" --json` answers
    from the replica with the query embedded by `recall.shared_embedder` (a private worker in
    the sandbox), exit 0, and the warnings name the private worker. HEAD: exit 1 "needs the
    daemon up …"."""
    b = offline["b"]
    r = s.rmx(b, "memory", "recall", QUESTION, "--json", "--k", "6",
              RMX_HOME=str(offline["home"]), RMX_MODEL_SOCK=str(offline["base"] / "none.sock"))
    assert r.returncode == 0, f"AC-4 (g): exit {r.returncode}: {r.stderr[-600:]}"
    names = {m["name"] for m in json.loads(r.stdout)}
    assert names and names <= _named_b(offline), names
    assert "private" in r.stderr.lower(), f"AC-4 (g): no warning names the private worker: " \
                                          f"{r.stderr[-600:]}"


def test_ac4g_mcp_no_daemon_no_hub_uses_shared_embedder(offline):
    b = offline["b"]
    with s.McpChild(cwd=b.proj, RMX_HOME=str(offline["home"]), REFMATRIX_ROOT=str(b.root),
                    RMX_MODEL_SOCK=str(offline["base"] / "none.sock")) as m:
        res = m.tool("rmx_memory_recall", {"query": QUESTION, "k": 6})
    assert not res["isError"] and res["json"] and "error" not in res["json"], res["text"][:600]
    names = {r["name"] for r in res["json"]["memories"]}
    assert names and names <= _named_b(offline), names
    assert any("private" in w.lower() for w in res["json"].get("warnings") or []), res["json"]


def test_ac4h_legacy_memory_partition_replica_and_rpc_agree(monkeypatch):
    """AC-4 (h): memories in a legacy `memory-<p>` partition: the replica leg (real worker) and
    the daemon RPC leg (`RMX_RECALL_REPLICA_FIRST=0`) return the same named hits. HEAD: the
    replica leg binds the PROJECT partition (cli.py `_resolve_partition`) and returns none."""
    from refmatrix import daemon as dm
    base = s.short_base("p25l")
    home = base / "g" / ".refmatrix"
    s.build_global(home)
    proj = base / "fxleg"
    fx = s.Fixture(base, proj, home)
    s._init_store(fx.root)
    s.copy_memdir(proj, include={f"fx_mem_{i:02d}" for i in range(20, 28)})
    legacy = "memory-fxleg"
    r = s.rmx(fx, "ingest-gmd", "--as-memory", str(fx.memdir), RMX_PARTITION=legacy,
              timeout=600)
    assert r.returncode == 0, r.stderr[-1500:]
    # RMX_RERANK=0 in the daemon AND the calling process: the two legs rerank in different
    # processes over different pools (d7), so with rerank on a set difference would be the
    # rerank's, not the partition's (measured at f7c0d39: 4 of 5 names shared, order differs).
    d = h.SandboxDaemon(fx.root, RMX_HOME=str(home), RMX_RERANK="0")
    w = None
    try:
        d.wait_models_warm()
        assert dm.call(fx.root, "embed", {"kinds": ["memory"], "partition": legacy},
                       timeout=900).get("ok")
        assert dm.call(fx.root, "snapshot", {"force": True}, timeout=300).get("ok")
        monkeypatch.setenv("RMX_HOME", str(home))
        from refmatrix import verbs
        assert verbs.memory_partition(fx.root, timeout=30) == legacy     # fixture pre-check
        w = s.SharedWorker(base, home=home)
        rep = s.run_cmd(fx, s.recall_cmd(fx.root, "UserPromptSubmit"),
                        env_in=s.envelope(QUESTION), RMX_MODEL_SOCK=str(w.sock),
                        RMX_RERANK="0")
        rpc = s.run_cmd(fx, s.recall_cmd(fx.root, "UserPromptSubmit"),
                        env_in=s.envelope(QUESTION), RMX_MODEL_SOCK=str(w.sock),
                        RMX_RECALL_REPLICA_FIRST="0", RMX_RERANK="0")
        _ok(rep, "replica leg")
        _ok(rpc, "rpc leg")
        n_rep, n_rpc = s.names_in_payload(rep.stdout), s.names_in_payload(rpc.stdout)
        assert n_rpc, "fixture: the daemon RPC leg named nothing"
        assert n_rep == n_rpc, f"AC-4 (h): replica leg {n_rep} != rpc leg {n_rpc}"
    finally:
        if w:
            w.stop()
        d.stop()
        import rmx_sandbox
        rmx_sandbox.remove_tree(base)


# ---- AC-4 (i): daemon up, hub down -- the daemon answers, nothing spawns -----------------------

# Runs ONE caller in a child under an audit hook (CPython `sys.addaudithook`): every process the
# child starts (`subprocess.Popen`, `os.posix_spawn`, `os.fork`, `os.exec`) and every import of
# a model stack. A private embed worker is `python -m refmatrix.embed_worker` under
# `subprocess.Popen` (`subproc.py`), so a spawn is SEEN, not inferred from a 5 s overrun (red-251
# a7 could only infer it). The result goes to stderr on one `AUDIT ` line at exit, so the
# caller's stdout stays byte-exact.
_AUDIT_RUN = r"""
import atexit, json, sys
spawned, imported = [], []
def _hook(ev, args):
    if ev == "subprocess.Popen":
        a = args[1]
        spawned.append([str(x) for x in a] if isinstance(a, (list, tuple)) else [str(a)])
    elif ev in ("os.posix_spawn", "os.fork", "os.exec", "os.spawn", "os.forkpty"):
        spawned.append([ev] + [str(x) for x in (args[1] if len(args) > 1 and
                                                 isinstance(args[1], (list, tuple)) else [])])
    elif ev == "import" and str(args[0]).split(".")[0] in ("sentence_transformers", "torch",
                                                          "transformers"):
        imported.append(str(args[0]))
sys.addaudithook(_hook)
atexit.register(lambda: print("AUDIT " + json.dumps({"spawned": spawned,
                                                      "imported": sorted(set(imported))}),
                              file=sys.stderr, flush=True))
mode, argv = sys.argv[1], sys.argv[2:]
if mode == "cli":
    from refmatrix.cli import cli_entry
    sys.argv = ["rmx", *argv]
    cli_entry()
else:
    from refmatrix import mcp
    resp = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "rmx_memory_recall",
                                          "arguments": json.loads(argv[0])}})
    print(json.dumps(resp))
"""


def _audited(fx, mode: str, *args, **extra) -> "tuple[subprocess.CompletedProcess, dict]":
    # The var `cli_entry` re-execs itself to set on macOS (`_reexec_for_fork_safety`): set
    # here, as the re-exec'd `rmx` and a launchd plist have it, so the audited process is the
    # one that serves the call (a re-exec would run `python rmx …` outside the hook).
    env = h.rmx_env(fx.root, RMX_HOME=str(fx.home), OBJC_DISABLE_INITIALIZE_FORK_SAFETY="YES",
                    **extra)
    r = subprocess.run([sys.executable, "-c", _AUDIT_RUN, mode, *map(str, args)], env=env,
                       cwd=str(fx.proj), capture_output=True, text=True, timeout=300)
    line = next((ln for ln in r.stderr.splitlines() if ln.startswith("AUDIT ")), None)
    assert line, f"the audited child wrote no AUDIT line (rc={r.returncode}): {r.stderr[-1500:]}"
    return r, json.loads(line[6:])


def _assert_nothing_spawned_or_loaded(audit: dict, what: str) -> None:
    workers = [a for a in audit["spawned"]
               if any("embed_worker" in x or "modelsrv" in x or "rerank" in x for x in a)
               or a[:1] in (["os.fork"], ["os.forkpty"])]
    assert not workers, f"AC-4 (i) {what}: the caller spawned a model worker: {workers}"
    assert not audit["imported"], f"AC-4 (i) {what}: the caller imported {audit['imported']}"


def test_ac4i_daemon_up_hub_down_daemon_serves_and_nothing_spawns(fx):
    """AC-4 (i) (r4 #n1; F3, rev 7, 2026-11-13): a sandbox daemon is up, no `models.sock`
    worker. `rmx memory recall "q" --json` and MCP `rmx_memory_recall` are served by the
    daemon RPC (the verb's `warnings` name the daemon leg), and the calling process spawns no
    model worker and imports no `sentence_transformers` (the same two facts as AC-4 (c), here
    observed by an audit hook).

    A GUARD, not RED at HEAD (the spec says so: HEAD's leg order already asks the daemon
    first); killed by AC-14's mutation "`shared_embedder` tried before the daemon", which
    spawns the private worker this test sees. Before this test that mutation was killed only
    indirectly, through AC-4 (d)/AC-7 parity (green-251b F3)."""
    none_sock = str(fx.base / "none.sock")
    r, audit = _audited(fx, "cli", "memory", "recall", QUESTION, "--json", "--k", "6",
                        RMX_MODEL_SOCK=none_sock)
    assert r.returncode == 0, r.stderr[-1500:]
    names = [m["name"] for m in json.loads(r.stdout)]
    assert names, "AC-4 (i): the interactive recall returned no rows"
    _assert_nothing_spawned_or_loaded(audit, "interactive CLI")
    r, audit = _audited(fx, "mcp", json.dumps({"query": QUESTION, "k": 6}),
                        RMX_MODEL_SOCK=none_sock)
    assert r.returncode == 0, r.stderr[-1500:]
    res = json.loads(r.stdout.strip().splitlines()[-1])["result"]
    text = "".join(c.get("text", "") for c in res.get("content") or [])
    assert not res.get("isError"), text[:600]
    body = json.loads(text)
    assert body["memories"], body
    assert any(w.startswith("recall leg: daemon RPC") for w in body.get("warnings") or []), (
        body.get("warnings"))
    _assert_nothing_spawned_or_loaded(audit, "MCP")


# ---- AC-5: the mis-typed save-state on the packed path ----------------------------------------------


def test_ac5_mistyped_savestate_not_named_on_the_packed_argv(fx, monkeypatch):
    """AC-5 (R2b): `savestate_fx01.md` (metadata.type: project, the best body for the question)
    is not named by the packed per-prompt argv and the trailer does not count it. After 26.4
    merges this is a regression guard (the bridge types it session/recall-state); at HEAD it is
    RED twice over: no --pack, and HEAD's JSON names it first (bug-164's 7c4e19d2a8f3 shape)."""
    p = _pack(_q(fx), "per-prompt argv")
    assert s.SAVESTATE not in p.named
    # The trailer counts the rows the pack was given (R4: the verb's final list, after the
    # merge and the exclusion): that list must not hold the save-state either.
    from refmatrix import verbs
    monkeypatch.setenv("RMX_HOME", str(fx.home))
    rows = verbs.memory_recall(fx.root, query=QUESTION, k=12, scope="both")["memories"]
    assert s.SAVESTATE not in [m["name"] for m in rows]
    assert len(p.named) + p.more == len(rows) == 12, (len(p.named), p.more, len(rows))


# ---- AC-6: subjects are not hits ----------------------------------------------------------------------


def test_ac6_no_subject_rows_on_the_per_prompt_argv(fx):
    """AC-6 (R2): 0 subject rows on the per-prompt argv, on BOTH legs: the replica leg (a real
    shared worker, the live default whenever the hub is up) and the daemon RPC leg. HEAD record
    (f7c0d39): the replica leg names subject_quasar_ledger_0 FIRST; the RPC leg's project half
    of the `--scope both` merge (6 of 12 at GREEN, 3 of 5 at HEAD) held none."""
    w = s.SharedWorker(fx.base, home=fx.home)
    try:
        legs = {"replica": _q(fx, RMX_MODEL_SOCK=str(w.sock))}
    finally:
        w.stop()
    legs["rpc"] = _q(fx, RMX_MODEL_SOCK=str(fx.base / "none.sock"))
    for leg, r in legs.items():
        _ok(r, f"per-prompt argv ({leg} leg)")
        named = s.names_in_payload(r.stdout)
        assert not set(named) & set(s.SUBJECTS), f"AC-6 ({leg} leg): subjects named: {named}"
        _pack(r, f"per-prompt argv ({leg} leg)")


def _project_non_subjects(p: "s.Pack") -> list[str]:
    """The pack's PROJECT, non-subject hits in order (a global hit's pointer reads
    `--scope global`, R6)."""
    return [m.group("name") for m in p.hook_lines
            if "--scope global" not in m.group("fetch") and m.group("name") not in s.SUBJECTS]


def test_ac6_include_subjects_brings_live_subjects_back_never_the_stale_one(fx):
    """AC-6 on the per-prompt argv: with `--include-subjects`, live subjects are named and the
    stale one never is.

    Rev 7 J3 (2026-11-13, spec #j3-subjects-exempt, a PRODUCT fix): a subject row is a label a
    cross-encoder cannot score against a prompt (the daemon's default rerank put the 4 live
    subjects at ranks 32-35 of 36, so the opt-in never showed one). With `include_subjects`
    subjects are EXEMPT from the rerank; non-subject rows rerank AS TODAY. So the fix cannot
    be "turn the rerank off": the project non-subject hits of the opt-in run are a prefix of
    the default run's (which excludes subjects and is reranked), the subjects only taking
    slots. The rerank is per (query, doc) pair, so the order among non-subjects cannot depend
    on whether subjects ride along."""
    p = _pack(_q(fx, append=" --include-subjects"), "per-prompt argv --include-subjects")
    assert set(p.named) & set(s.LIVE_SUBJECTS), p.named
    assert s.STALE_SUBJECT not in p.named
    base = _project_non_subjects(_pack(_q(fx), "per-prompt argv"))
    inc = _project_non_subjects(p)
    assert inc and inc == base[:len(inc)], (
        "J3: the opt-in changed the order of the non-subject rows (rerank lost?)", inc, base)


def test_ac6_session_start_argv_has_no_subject_and_no_stale_subject(fx):
    """AC-6 on the SessionStart argv (HEAD names all 5 seeded subjects: they are the newest)."""
    for append in ("", " --include-subjects"):
        r = _ss(fx, append=append)
        _ok(r, f"SessionStart argv{append}")
        named = s.names_in_payload(r.stdout)
        assert s.STALE_SUBJECT not in named, (append, named)
        if not append:
            assert not set(named) & set(s.SUBJECTS), named
        _pack(r, f"SessionStart argv{append}")


def test_ac6_verb_hides_subjects_and_the_stale_one_even_with_the_opt_in(fx, monkeypatch):
    """AC-6 on the verb: no subject by default; with `include_subjects` the live subjects come
    back and the stale one never does.

    Rev 7 J4 (2026-11-13, spec #j3-subjects-exempt): subjects are EXEMPT from the cross-encoder
    rerank and keep their PRE-rerank rank; non-subject rows rerank as today. Asserted three
    ways, so neither "rerank off" nor "subjects appended at the end" passes:
    - pre-check: on this fixture the rerank does reorder the non-subject rows (else the next
      assertion could not tell a disabled rerank from a working one);
    - the opt-in's non-subject rows are a prefix of the default (reranked) run's;
    - each subject sits at the rank it has with `rerank=False` (its pre-rerank rank)."""
    from refmatrix import verbs
    monkeypatch.setenv("RMX_HOME", str(fx.home))

    def names(**kw) -> list[str]:
        return [m["name"] for m in verbs.memory_recall(fx.root, query=QUESTION, k=12,
                                                       **kw)["memories"]]
    base = names()
    assert not set(base) & set(s.SUBJECTS), base
    plain = [n for n in names(rerank=False) if n not in s.SUBJECTS]
    assert plain != base, ("fixture pre-check: the rerank does not reorder the non-subject "
                           "rows, so a disabled rerank would pass", base)
    inc = names(include_subjects=True)
    assert set(inc) & set(s.LIVE_SUBJECTS), inc
    assert s.STALE_SUBJECT not in inc
    non = [n for n in inc if n not in s.SUBJECTS]
    assert non == base[:len(non)], ("J4: non-subject rows not reranked as without the opt-in",
                                    non, base)
    pre = names(include_subjects=True, rerank=False)
    for subj in (n for n in inc if n in s.SUBJECTS):
        assert subj in pre and inc.index(subj) == pre.index(subj), (
            "J4: a subject did not keep its pre-rerank rank", subj, inc, pre)


@pytest.fixture(scope="module")
def few():
    """A daemon-served store SMALLER than the rerank pool: 3 memories and 1 live subject. The
    reranked answer (`ranked`) then reaches past every texted row to the subject itself, which
    the 30-memory fixture never shows (its rerank buries all 5 subjects below k)."""
    from refmatrix import daemon as dm
    base = s.short_base("p25f")
    home = base / "g" / ".refmatrix"
    s.build_global(home)
    proj = base / "fxfew"
    fx = s.Fixture(base, proj, home)
    s._init_store(fx.root)
    s.copy_memdir(proj, include={f"fx_mem_{i:02d}" for i in range(3)})
    r = s.rmx(fx, "ingest-gmd", "--as-memory", str(fx.memdir), timeout=600)
    assert r.returncode == 0, r.stderr[-1500:]
    d = h.SandboxDaemon(fx.root, RMX_HOME=str(home))
    try:
        d.wait_models_warm()
        part = s._verbs_partition(fx)
        res = dm.call(fx.root, "memory_add", {
            "name": "subject_few_0", "mtype": "subject", "metadata": {"subject": True},
            "partition": part, "content": f"{QUESTION} — subject group → members"},
            timeout=120)
        assert res.get("ok"), res
        assert dm.call(fx.root, "embed", {"kinds": ["memory"], "partition": part},
                       timeout=900).get("ok")
        assert dm.call(fx.root, "snapshot", {"force": True}, timeout=300).get("ok")
        yield fx
    finally:
        d.stop()
        import rmx_sandbox
        rmx_sandbox.remove_tree(base)


def test_m1_include_subjects_never_names_a_subject_twice(few, monkeypatch):
    """bsd-251 m-1 / green flag g7-2 (2026-11-14): under `include_subjects` the exempt pass
    places each subject at its unreranked index and fills the other slots from the reranked
    answer WITHOUT subjects. Drop that filter (bsd-251 m8) and a subject the reranked answer
    also reaches is named twice (`place_rerank_exempt([s1, a, b], [s1, b, a], 3)` →
    `[s1, s1, b]`). Preconditions: the rerank ran and the exempt pass placed the subject
    (`rerank_exempt` on its row)."""
    from refmatrix import verbs
    monkeypatch.setenv("RMX_HOME", str(few.home))
    monkeypatch.setenv("RMX_MODEL_SOCK", str(few.base / "none.sock"))
    res = verbs.memory_recall(few.root, query=QUESTION, k=12, include_subjects=True)
    names = [m["name"] for m in res["memories"]]
    subj = [m for m in res["memories"] if m["name"] == "subject_few_0"]
    assert subj and subj[0].get("rerank_exempt") is True, (
        "fixture: the exempt pass did not place the subject (no rerank ran?)", names,
        res.get("warnings"))
    assert len(names) == len(set(names)), f"m-1: a row is named twice: {names}"
    assert len(names) == 4, names                    # 3 memories + 1 subject, each once


# ---- AC-7: the CLI prints the verb ----------------------------------------------------------------------


def test_ac7_cli_prints_the_verbs_text_byte_for_byte(fx, monkeypatch):
    """AC-7: the verb's `text` (query, k=12, scope=both, pack=True) equals the per-prompt argv's
    stdout byte for byte. Replica leg OFF (no worker); the ON leg is AC-4 (d)'s parity.

    bsd-251 s-1 (2026-11-14): no newline is tolerated any more. The pack carries and counts its
    own final newline and the CLI writes the text `nl=False`; the RED's `rstrip(b"\n")` on both
    sides was exactly the byte a regressed `nl=True` brings back (bsd-251 mutation m2 survived
    it)."""
    from refmatrix import verbs
    r = _q(fx)
    _ok(r, "per-prompt argv")
    monkeypatch.setenv("RMX_HOME", str(fx.home))
    res = verbs.memory_recall(fx.root, query=QUESTION, k=12, scope="both", pack=True)
    assert "text" in res, f"AC-7: pack=True returned no `text`: keys {sorted(res)}"
    assert r.stdout == res["text"].encode("utf-8"), (len(r.stdout), res["payload_bytes"])


def test_ac7_schema_has_pack_params_and_never_embedder_policy():
    """AC-7 / r4 #n2: `pack`, `max_bytes`, `include_subjects` are verb params (MCP schema) and
    CLI options; `embedder_policy` rides `**internal` and is absent from the schema."""
    from refmatrix import cli, mcp
    props = mcp.TOOLS["rmx_memory_recall"]["schema"]["properties"]
    assert {"pack", "max_bytes", "include_subjects"} <= set(props), sorted(props)
    assert "embedder_policy" not in props
    opts = {o for p in cli.memory_recall.params for o in getattr(p, "opts", [])}
    assert {"--pack", "--max-bytes", "--include-subjects"} <= opts, sorted(opts)


def test_ac7_mcp_embedder_policy_argument_is_dropped(offline):
    """AC-7: an MCP call carrying embedder_policy="hub_only" behaves as "shared" (the arg is
    dropped by Verb.call): no daemon, no hub worker, and it still answers (AC-4 g's leg)."""
    b = offline["b"]
    with s.McpChild(cwd=b.proj, RMX_HOME=str(offline["home"]), REFMATRIX_ROOT=str(b.root),
                    RMX_MODEL_SOCK=str(offline["base"] / "none.sock")) as m:
        res = m.tool("rmx_memory_recall", {"query": QUESTION, "k": 4,
                                           "embedder_policy": "hub_only"})
    assert not res["isError"] and res["json"] and "error" not in res["json"], res["text"][:600]
    assert res["json"]["memories"], res["json"]


# ---- F6 (rev 7): the leg line is said under --verbose, never as a warning -----------------------


def test_f6_recall_leg_line_only_under_verbose_never_a_warning(fx):
    """Rev 7 F6 (2026-11-13, spec #f6-leg-line): the `recall leg: …` line stays in the verb's
    `warnings` (R5; AC-4 (i) reads it there), but the CLI prints leg-served lines only with
    `--verbose`, and never under the `warning:` prefix; real warnings are unchanged
    (tests/test_rerank_warning_routes.py::test_cli_recall_daemon_branch_prints_the_warnings).

    HEAD (measured 2026-11-13): every recall -- interactive and the per-prompt hook -- prints
    `# rmx: warning: recall leg: daemon RPC (the daemon's embedder and rerank default)` on
    stderr, and `memory recall` has no `--verbose`."""
    none_sock = str(fx.base / "none.sock")
    plain = s.rmx(fx, "memory", "recall", QUESTION, "--json", "--k", "4",
                  RMX_MODEL_SOCK=none_sock)
    assert plain.returncode == 0, plain.stderr[-800:]
    assert "recall leg" not in plain.stderr, (
        f"F6: a normal interactive recall printed the leg line: {plain.stderr[-600:]!r}")
    hook = _q(fx, RMX_MODEL_SOCK=none_sock)
    _ok(hook, "per-prompt argv")
    assert b"recall leg" not in hook.stderr, (
        f"F6: the per-prompt hook printed the leg line: {hook.stderr[-600:]!r}")
    v = s.rmx(fx, "memory", "recall", QUESTION, "--json", "--k", "4", "--verbose",
              RMX_MODEL_SOCK=none_sock)
    assert v.returncode == 0, f"F6: --verbose exit {v.returncode}: {v.stderr[-600:]}"
    legs = [ln for ln in v.stderr.splitlines() if "recall leg:" in ln]
    assert any("daemon RPC" in ln for ln in legs), (
        f"F6: --verbose did not say which leg served: {v.stderr[-600:]!r}")
    assert not [ln for ln in legs if "warning" in ln.lower()], legs
    # --verbose says more on stderr; it changes no row
    assert [m["name"] for m in json.loads(v.stdout)] == [
        m["name"] for m in json.loads(plain.stdout)]


# ---- AC-8: environment -------------------------------------------------------------------------------


def test_ac8_env_unset_within_the_table(fx):
    r = _q(fx, RMX_HOOK_BUDGET_BYTES=None)
    _ok(r, "per-prompt argv, RMX_HOOK_BUDGET_BYTES unset")
    s.assert_within(len(r.stdout), "prompt_recall", "AC-8 unset")


def test_ac8_env_3000_caps_every_recall_argv(fx):
    for what, r in (("per-prompt", _q(fx, RMX_HOOK_BUDGET_BYTES="3000")),
                    ("SessionStart", _ss(fx, RMX_HOOK_BUDGET_BYTES="3000"))):
        _ok(r, f"{what} RMX_HOOK_BUDGET_BYTES=3000")
        assert 0 < len(r.stdout) <= 3000, f"AC-8 {what}: {len(r.stdout)} B > 3000"


def test_ac8_env_non_integer_fails_naming_the_variable(fx):
    r = _q(fx, RMX_HOOK_BUDGET_BYTES="abc")
    assert r.returncode != 0, f"AC-8: RMX_HOOK_BUDGET_BYTES=abc exited 0 ({len(r.stdout)} B)"
    assert b"RMX_HOOK_BUDGET_BYTES" in r.stderr, r.stderr[-400:]


# ---- AC-9 integration: bodies on session_start, pointers on prompt_recall, arithmetic ---------------


def test_ac9_prompt_recall_is_pointers_only_and_arithmetic_holds(fx):
    """d3: 12 hook lines, no body, at the default prompt_recall budget; R8 arithmetic: distinct
    named + trailer N = the k=12 hits (the fixture has > 12 eligible rows); every hook line is
    the CURATED hook (path-keyed MEMORY.md, R4)."""
    p = _pack(_q(fx), "per-prompt argv")
    assert p.bodied == [], f"d3: bodies on prompt_recall: {p.bodied}"
    assert len(set(p.named)) == len(p.named)
    assert len(p.named) + p.more == 12, (p.named, p.more)
    for n in p.named:
        if n in s.MEM_NAMES:
            assert f"HOOK-{n}" in p.hook_line_of(n), p.hook_line_of(n)


def test_ac9_session_start_carries_bodies_after_all_hook_lines(fx):
    """AC-9 / d3: the SessionStart argv carries ≥ 2 bodied hits, every body after every hook
    line and each a NAMED hit, and named + trailer N = the generated `--k`.

    Rev 7 J5 (2026-11-13, R7 amended, spec #j5-session-start-k): SessionStart `--k 12`, not 30
    (30 hook lines took 5,961 of the 9,000 B). The count the test checks against is 12.
    Rev 7 J6's rule applies here too: a body is the `## <name>` block the pack printed after
    its hook lines, any scope; the RED counted only `BODYMARK` (project) bodies. Measured on
    the fixture before GREEN (`--k 12` appended, 2026-11-13): 12 named, 6 bodies, all GLOBAL
    rows (`fx_dup_x`, `gx_mem_9` … `gx_mem_5`) -- no project body (4.9-8.7 KB) fits after
    the globals in rank order (see the implementation summary's #red-rev7 a-j5)."""
    p = _pack(_ss(fx), "SessionStart argv")
    assert len(p.body_blocks) >= 2, f"AC-9: {p.body_blocks} bodied hits on session_start"
    assert set(p.body_blocks) <= set(p.named)
    last_hook = max(p.text.index(m.group(0)) for m in p.hook_lines)
    first_body = min(p.text.index(f"## {b}\n") for b in p.body_blocks)
    assert first_body > last_hook
    assert len(p.named) + p.more == 12, (len(p.named), p.more)


# ---- AC-10: delivered events and spans -------------------------------------------------------------


_GLOBAL_CONTENT = {r["name"]: r["content"] for r in s.GLOBAL_ROWS}


def _ss_events(fx, append: str = ""):
    """Run the SessionStart argv (plus `append`) and return (result, pack, project events,
    global events) appended by THIS call on the `session_start` channel. This module runs one
    hook at a time, so the lines appended since the counts were taken are this call's
    (`--session-start` reads no envelope, so the event's session is not the test's to pick)."""
    pe, ge = fx.root / "recall-events.jsonl", fx.home / "recall-events.jsonl"
    n_p, n_g = len(h.jsonl(pe)), len(h.jsonl(ge))
    r = _ss(fx, append=append)
    p = _pack(r, f"SessionStart argv{append}")
    new_p = [e for e in h.jsonl(pe)[n_p:] if e.get("channel") == "session_start"]
    new_g = [e for e in h.jsonl(ge)[n_g:] if e.get("channel") == "session_start"]
    return r, p, new_p, new_g


def _assert_delivered_spans(raw: bytes, p: "s.Pack", evs: list) -> list:
    """AC-10 / R9 over one payload: one `delivered` event per NAMED hit and none for any other
    (a trimmed hit has none), one query_id with the `retrieved` events, each hook-line span
    slicing exactly its line (newline included) out of the payload BYTES.

    A body is identified by its SPAN (rev 7 J6, 2026-11-13), never by a marker string: global
    bodies carry no `BODYMARK`, and the RED detector read a real global body as "no body". An
    event with body offsets must slice exactly the text the pack printed under `## <name>`
    (a whole block: it ends at the next block, the trailer, or the end), naming its row, with
    ≥ 3 `—` in front of it (the AC-10 character-vs-byte pre-check); an event without them must
    have no `## <name>` block in the payload. Returns the delivered events."""
    qids = {e.get("query_id") for e in evs}
    assert len(qids) == 1 and None not in qids, qids
    deliv = [e for e in evs if e.get("stage") == "delivered"]
    assert sorted(e["name"] for e in deliv) == sorted(p.named), (
        "AC-10: delivered events != named hits (a trimmed hit must have none)",
        sorted(e["name"] for e in deliv), sorted(p.named))
    retrieved = {e["name"] for e in evs if e.get("stage") == "retrieved"}
    assert set(p.named) <= retrieved, set(p.named) - retrieved
    last_hook_end = max(raw.index((m.group(0) + "\n").encode("utf-8")) + len(
        (m.group(0) + "\n").encode("utf-8")) for m in p.hook_lines)
    bodied = 0
    for e in deliv:
        line = raw[e["offset_bytes"]:e["offset_bytes"] + e["bytes"]]
        assert line == (p.hook_line_of(e["name"]) + "\n").encode("utf-8"), (e["name"], line)
        head = f"## {e['name']}\n".encode("utf-8")
        if e.get("body_offset_bytes") is None:
            assert e.get("body_bytes") is None, e
            assert head not in raw[last_hook_end:], (
                f"AC-10: {e['name']} has a body block in the payload but null body fields")
            continue
        bodied += 1
        off, n = e["body_offset_bytes"], e["body_bytes"]
        assert off >= last_hook_end, (e["name"], off, last_hook_end)
        assert raw[off - len(head):off] == head, (e["name"], raw[off - len(head):off])
        rest = raw[off + n:]
        assert rest in (b"", b"\n") or rest.lstrip(b"\n").startswith((b"## ", b"+")), (
            e["name"], rest[:80])
        body = raw[off:off + n].decode("utf-8")
        if e.get("scope") == "global":
            assert body == _GLOBAL_CONTENT[e["name"]], (e["name"], body[:120])
        else:
            assert e["name"] in body, (e["name"], body[:120])
        assert raw[:off].decode("utf-8").count("—") >= 3
    return deliv


def _assert_global_events_in_the_global_file(p: "s.Pack", new_p: list, new_g: list) -> None:
    """19.1 AC-6's global leg: a NAMED global hit's events are in the tmp global root's file with
    scope=global; the project file carries no global-scope event."""
    named_global = [m.group("name") for m in p.hook_lines
                    if "--scope global" in m.group("fetch")]
    g_deliv = [e for e in new_g if e.get("stage") == "delivered"]
    assert all(e.get("scope") == "global" for e in new_g), new_g[:3]
    assert sorted(e["name"] for e in g_deliv) == sorted(named_global), (
        [e["name"] for e in g_deliv], named_global)
    assert not [e for e in new_p if e.get("scope") == "global"], (
        "AC-10: a global hit's event was written to the PROJECT file",
        [e["name"] for e in new_p if e.get("scope") == "global"])


def test_ac10_delivered_events_slice_the_payload_by_bytes(fx):
    """AC-10 (R9): on the SessionStart argv, one `delivered` event per NAMED hit, one query_id
    with the `retrieved` events; each span slices exactly its hook line / body out of the
    payload BYTES; unbodied hits carry null body fields; a global hit's event is in the tmp
    global root's file with scope=global. The fixed 7-of-12/3-bodied shape of 19.1 AC-6 is not
    forced here (R0 sets the budget the shape depends on)."""
    r, p, new_p, new_g = _ss_events(fx)
    deliv = _assert_delivered_spans(r.stdout, p, new_p + new_g)
    assert any(e.get("body_offset_bytes") is not None for e in deliv), (
        "AC-10: the SessionStart payload carries no body; the body spans are untested")
    _assert_global_events_in_the_global_file(p, new_p, new_g)


# F4's shape, measured on the fixture before GREEN (2026-11-13, SessionStart argv with these
# two flags appended): 9 of 12 named (`+3 more`), four of them GLOBAL (fx_dup_x, gx_mem_9,
# gx_mem_8, gx_mem_7), 1,875 B.
F4_K = 12
F4_BYTES = 2000


def test_ac10_trimmed_hits_get_no_delivered_event_and_global_hits_stay_global(fx):
    """F4 (rev 7, 2026-11-13): a SessionStart payload with a NON-ZERO trailer, so two AC-14
    mutations are decidable -- "a `delivered` event for a trimmed hit" (an extra delivered
    event, or one per retrieved row) and "a global hit's `delivered` event in the project file".
    The default SessionStart pack names every hit (trailer 0), so it could kill neither.
    `--k F4_K --max-bytes F4_BYTES` are appended (click keeps the last), fixing the shape whatever
    the generator's `--k`; preconditions: some hit trimmed, some GLOBAL hit named."""
    r, p, new_p, new_g = _ss_events(fx, append=f" --k {F4_K} --max-bytes {F4_BYTES}")
    assert p.more > 0, f"F4 fixture: nothing trimmed ({len(p.named)} named, trailer 0)"
    assert any("--scope global" in m.group("fetch") for m in p.hook_lines), (
        f"F4 fixture: no global hit named: {p.named}")
    _assert_delivered_spans(r.stdout, p, new_p + new_g)
    _assert_global_events_in_the_global_file(p, new_p, new_g)


# ---- AC-11: the global pointer --------------------------------------------------------------------------


def test_ac11_memory_get_scope_global_returns_the_global_row(fx):
    """AC-11 (R6): a project row and a global row both named fx_dup_x: `rmx memory get fx_dup_x
    --scope global` returns the GLOBAL row; no scope returns the project row. HEAD: no --scope."""
    g = s.rmx(fx, "memory", "get", "fx_dup_x", "--scope", "global")
    assert g.returncode == 0, f"AC-11: exit {g.returncode}: {g.stderr[-400:]}"
    assert "GLOBAL-COPY fx_dup_x" in g.stdout and "PROJECT-COPY" not in g.stdout, g.stdout[:400]
    p = s.rmx(fx, "memory", "get", "fx_dup_x")
    assert p.returncode == 0 and "PROJECT-COPY fx_dup_x" in p.stdout, p.stdout[:400]


def test_ac11_the_packs_global_fetch_pointer_returns_the_global_row(fx):
    p = _pack(_q(fx), "per-prompt argv")
    globals_named = [n for n in p.named if n in s.GLOBAL_NAMES]
    assert globals_named, p.named
    for n in globals_named:
        fetch = p.fetch_of(n)
        assert fetch == f"rmx memory get {n} --scope global", fetch
        r = s.run_cmd(fx, s.HOOK_ENV + fetch)
        _ok(r, fetch)
        assert f"GLOBAL-COPY {n}".encode() in r.stdout


# ---- AC-12 / AC-12b: every rmx producer on the event --------------------------------------------------


def test_ac12_scan_prompt_alone_within_its_budget(fx):
    """AC-12 (R0b): the generated scan-prompt command on the question prints ≤
    budget("scan_prompt"). HEAD: 6,720 B on this fixture."""
    r = s.run_cmd(fx, s.scan_prompt_part(fx.root), env_in=s.envelope(QUESTION))
    _ok(r, "scan-prompt argv")
    assert r.stdout, "scan-prompt printed nothing on the fixture question"
    s.assert_within(len(r.stdout), "scan_prompt", "AC-12 scan-prompt argv")


def test_ac12_curator_status_alone_within_its_budget(fx):
    """AC-12: `rmx curator status` with 30 queued paths > 120 chars ≤ budget("curator_status").
    HEAD: 1,885 B."""
    r = s.run_cmd(fx, s.HOOK_ENV + "rmx curator status")
    _ok(r, "curator status")
    assert r.stdout, "fixture: the curator queue printed nothing"
    s.assert_within(len(r.stdout), "curator_status", "AC-12 curator status")


def test_ac12_each_user_prompt_submit_command_within_its_command_budget(fx):
    """AC-12 under R0 outcome (A): each generated UserPromptSubmit COMMAND's stdout ≤ its
    command budget (`scan_cmd` = scan_prompt + curator_status; focus input; recall)."""
    got = {}
    for _ev, _m, cmd in h.hook_entries(fx.root, "UserPromptSubmit"):
        r = s.run_cmd(fx, cmd, env_in=s.envelope(QUESTION))
        got[cmd] = len(r.stdout)
    assert len(got) == 3, list(got)
    for cmd, n in got.items():
        if "scan-prompt" in cmd:
            b = s.command_budget("scan_cmd")
        elif "focus hook --event input" in cmd:
            b = s.budget_or_none("focus_input")
        else:
            b = s.budget_or_none("prompt_recall")
        assert b is not None, f"R1 not built; {s.after_env(cmd)[:60]!r} printed {n} B"
        assert n <= b, f"{s.after_env(cmd)[:60]!r}: {n} B > {b} B"


def test_ac12b_focus_context_within_its_budget(fx):
    """AC-12b (R0b): the generated resume `rmx focus context --top N` (STM ring sized > 3,000 B
    at HEAD: 3,319 B) ≤ budget("focus_context")."""
    cmds = [c for _e, m, c in h.hook_entries(fx.root, "SessionStart") if "focus context" in c]
    assert len(cmds) == 1, cmds
    r = s.run_cmd(fx, cmds[0], env_in=s.envelope("", event="SessionStart", source="resume"))
    _ok(r, "focus context")
    assert r.stdout, "fixture: focus context printed nothing"
    s.assert_within(len(r.stdout), "focus_context", "AC-12b focus context")


def test_ac12b_each_session_start_command_within_its_budget(fx):
    """AC-12b under outcome (A), resume matcher, in order: `sess_cmd` ≤ its command budget,
    recall ≤ session_start, focus context ≤ focus_context. (`ingest-gmd --detach` is a one-line
    job handoff and is not run here: it would enqueue a re-ingest on the shared fixture
    daemon mid-module.)"""
    env_in = s.envelope("", event="SessionStart", source="resume")
    sess = [c for _e, m, c in h.hook_entries(fx.root, "SessionStart")
            if "curator status" in c and "primer" in c]
    assert len(sess) == 1, sess
    checks = [(sess[0], s.command_budget("sess_cmd")),
              (s.recall_cmd(fx.root, "SessionStart"), s.budget_or_none("session_start")),
              ([c for _e, m, c in h.hook_entries(fx.root, "SessionStart")
                if "focus context" in c][0], s.budget_or_none("focus_context"))]
    for cmd, b in checks:
        r = s.run_cmd(fx, cmd, env_in=env_in)
        assert b is not None, f"R1 not built; {s.after_env(cmd)[:60]!r} printed {len(r.stdout)} B"
        assert len(r.stdout) <= b, f"{s.after_env(cmd)[:60]!r}: {len(r.stdout)} B > {b} B"


# ---- AC-13: generator and isolation ----------------------------------------------------------------------


def test_ac13_generator_emits_pack_raised_k_and_no_variable(tmp_path):
    """AC-13 / R7: the three recall commands carry `--pack`, no `--json`, no `$` after HOOK_ENV
    (no interpolated budget variable), and `--k` SessionStart 12, per-prompt 12, PreCompact 30
    (PreCompact absent only if R0 dropped it); then `rmx install-hooks --apply` → `--check` is
    clean in the sandbox.

    Rev 7 J5 (2026-11-13, R7 amended, spec #j5-session-start-k): SessionStart `--k 12`, not 30.
    R3 puts every hook line before any body; 30 lines took 5,961 of the 9,000 B, so no project
    body (2.0-8.7 KB) could ever follow them."""
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    (root.parent / ".git").mkdir()
    want = {"UserPromptSubmit": ("memory recall --stdin-json", 12),
            "SessionStart": ("memory recall --session-start", 12),
            "PreCompact": ("memory recall --recent", 30)}
    for ev, (needle, k) in want.items():
        hits = [c for e, _m, c in h.hook_entries(root, ev) if needle in c]
        if ev == "PreCompact" and not hits:
            continue
        assert len(hits) == 1, (ev, hits)
        tail = s.after_env(hits[0])
        assert "--pack" in tail and "--json" not in tail, (ev, tail)
        assert "$" not in tail, (ev, tail)
        assert f"--k {k} " in tail + " ", (ev, tail)
    env = h.rmx_env(root)
    a = subprocess.run([h.rmx_bin(), "install-hooks", "--apply"], cwd=str(root.parent),
                       env=env, capture_output=True, text=True, timeout=300)
    assert a.returncode == 0, a.stderr[-800:]
    c = subprocess.run([h.rmx_bin(), "install-hooks", "--check"], cwd=str(root.parent),
                       env=env, capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, (c.stdout[-800:], c.stderr[-800:])


# ---- AC-15 (rev 6, R11): recall-state after compaction and /clear -----------------------------------


@pytest.fixture(scope="module")
def rs():
    """A sandbox store (no daemon) whose newest save-state is written by the GENERATED PreCompact
    checkpoint command (`rmx save-state --no-promote --no-sync -m "auto: pre-compact
    checkpoint"`), plus an STM ring, so recall-state has a handoff, git, STM and memories."""
    from refmatrix.memory_layout import iter_savestates
    base = s.short_base("p25r")
    home = base / "g" / ".refmatrix"
    s.build_global(home)
    proj = base / "fxrs"
    fx = s.Fixture(base, proj, home)
    s._init_store(fx.root)
    s.copy_memdir(proj, include={f"fx_mem_{i:02d}" for i in range(0, 4)})
    s.seed_ring(fx.root, n=12)
    ck = [c for _e, _m, c in h.hook_entries(fx.root, "PreCompact") if "save-state" in c]
    assert len(ck) == 1, ck
    # The checkpoint resolves its session from $RMX_SESSION here: the generated command reads no
    # envelope, and a sandbox child has no Claude pid pointer (measured: SessionUnresolved).
    r = s.run_cmd(fx, ck[0], env_in=s.envelope("", event="PreCompact"), RMX_SESSION=s.SESSION)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-1500:]
    saves = iter_savestates(fx.memdir)
    assert saves, f"the PreCompact checkpoint wrote no save-state under {fx.memdir}"
    fx.checkpoint = Path(saves[0]).stem
    assert "auto: pre-compact checkpoint" in Path(saves[0]).read_text(encoding="utf-8")
    yield fx
    import rmx_sandbox
    rmx_sandbox.remove_tree(base)


def _rs_entry(root: Path) -> "tuple[str | None, str]":
    hits = [(m, c) for _e, m, c in h.hook_entries(root, "SessionStart") if "recall-state" in c]
    assert len(hits) == 1, f"R11: expected ONE SessionStart entry running recall-state; got {hits}"
    return hits[0]


def test_ac15a_generator_emits_one_unchained_compact_clear_recall_state_entry(tmp_path):
    """AC-15 (a): exactly one SessionStart entry whose matcher covers compact AND clear, whose
    command is `rmx recall-state --max-bytes N` (N = budget("recall_state") ≤ 9,000), alone
    (not chained to another command); startup|resume keep their entries."""
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    matcher, cmd = _rs_entry(root)
    assert {"compact", "clear"} <= set((matcher or "").split("|")), matcher
    tail = s.after_env(cmd)
    n = s.budget_or_none("recall_state")
    assert n is not None and n <= 9000, f"R1 recall_state budget: {n}"
    assert tail == f"rmx recall-state --max-bytes {n}", tail
    entries = [e for e in h.hook_block(root)["hooks"]["SessionStart"]
               if any("recall-state" in x["command"] for x in e["hooks"])]
    assert len(entries) == 1 and len(entries[0]["hooks"]) == 1, entries
    starts = [e for e in h.hook_block(root)["hooks"]["SessionStart"]
              if "startup" in (e.get("matcher") or "")]
    assert starts, "startup|resume entries vanished"


def test_ac15b_compact_runs_recall_state_naming_the_checkpoint_within_n(rs):
    """AC-15 (b): run through bash -c with a SessionStart {"source": "compact"} envelope: stdout
    ≤ N bytes, it names the PreCompact checkpoint as the handoff, exit 0."""
    _m, cmd = _rs_entry(rs.root)
    r = s.run_cmd(rs, cmd, env_in=s.envelope("", event="SessionStart", source="compact"))
    _ok(r, "recall-state entry (compact)")
    n = s.budget_or_none("recall_state")
    assert n is not None and len(r.stdout) <= n, (len(r.stdout), n)
    assert rs.checkpoint.encode() in r.stdout, (rs.checkpoint, r.stdout[:600])


def test_ac15c_recall_state_over_n_keeps_whole_blocks_head_and_a_trailer(rs):
    """AC-15 (c): a recall-state larger than N: whole blocks only, the head kept, a trailer
    naming `rmx recall-state`. N is forced below the full size by appending a smaller
    `--max-bytes` (click keeps the last); the full size is measured first."""
    full = s.run_cmd(rs, s.HOOK_ENV + "rmx recall-state")
    _ok(full, "rmx recall-state (full)")
    n = 700
    assert len(full.stdout) > n, f"fixture: full recall-state is only {len(full.stdout)} B"
    _m, cmd = _rs_entry(rs.root)
    r = s.run_cmd(rs, cmd + f" --max-bytes {n}",
                  env_in=s.envelope("", event="SessionStart", source="compact"))
    _ok(r, f"recall-state --max-bytes {n}")
    out = r.stdout.decode("utf-8")
    assert 0 < len(r.stdout) <= n, len(r.stdout)
    assert out.splitlines()[0] == full.stdout.decode("utf-8").splitlines()[0]
    assert "rmx recall-state" in out.rstrip("\n").splitlines()[-1], out[-300:]


def test_ac15d_no_daemon_prints_the_file_blocks_and_exits_0(rs):
    """AC-15 (d): no daemon: exit 0 and the file-based blocks (the handoff, git) printed; the
    missing daemon leg is SAID (the spec's "counted" names no recorder; see the summary)."""
    _m, cmd = _rs_entry(rs.root)
    r = s.run_cmd(rs, cmd, env_in=s.envelope("", event="SessionStart", source="clear"))
    _ok(r, "recall-state entry (clear, no daemon)")
    out = r.stdout.decode("utf-8")
    assert rs.checkpoint in out and "git" in out, out[:600]
    said = (out + r.stderr.decode("utf-8", "replace")).lower()
    assert "daemon" in said, said[-600:]


def test_ac15e_unreadable_memdir_fails_with_one_error_line(rs):
    """AC-15 (e): a forced failure (the memdir unreadable): exit != 0, ONE `Error:` line, no
    Traceback (the user's 2026-11-10 rule)."""
    _m, cmd = _rs_entry(rs.root)
    mode = rs.memdir.stat().st_mode
    os.chmod(rs.memdir, 0)
    try:
        r = s.run_cmd(rs, cmd, env_in=s.envelope("", event="SessionStart", source="compact"))
    finally:
        os.chmod(rs.memdir, mode)
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode != 0, f"exit 0 on an unreadable memdir: {r.stdout[:300]!r}"
    assert "Traceback" not in err, err[-1200:]
    assert len([ln for ln in err.splitlines() if ln.startswith("Error:")]) == 1, err[-600:]


def test_ac15f_max_bytes_is_a_recall_state_verb_parameter():
    """AC-15 (f): `max_bytes` is a parameter of the recall_state VERB (MCP schema) and the CLI
    flag `--max-bytes` (verb parity)."""
    from refmatrix import cli, mcp
    props = mcp.TOOLS["rmx_recall_state"]["schema"]["properties"]
    assert "max_bytes" in props, sorted(props)
    opts = {o for p_ in cli.recall_state.params for o in getattr(p_, "opts", [])}
    assert "--max-bytes" in opts, sorted(opts)


def test_ac15g_recall_state_is_counted_as_producer_recall_state(rs):
    """R11's last bullet (F2, rev 7, 2026-11-13): the compact|clear recall-state is "counted as
    producer `recall_state` in `rmx telemetry --context`".

    The contract this test pins (red-251b's reading; the spec names the producer, not the
    shape -- see the summary's #red-rev7): `rmx telemetry --context --format json` carries
    `by_producer`, keyed by `hook_budget.CHANNEL_BUDGET_BYTES` names, whose `recall_state`
    entry counts the HOOK-invoked `rmx recall-state` runs in `cli.log` (`source == "hook"`,
    `out_bytes` recorded) as `n`, `total_bytes`, `max_bytes`, with `budget` =
    `budget("recall_state")` beside them; an interactive `rmx recall-state` is not a producer
    run. The text form names `recall_state`.

    HEAD (measured 2026-11-13): the run IS in `by_command` as `recall-state` (n 1, 4,946 B),
    but nothing names the producer or reads it against its budget; there is no
    `by_producer`."""
    _m, cmd = _rs_entry(rs.root)
    r = s.run_cmd(rs, cmd, env_in=s.envelope("", event="SessionStart", source="compact"))
    _ok(r, "recall-state entry (compact)")
    i = s.rmx(rs, "recall-state")                       # interactive: not a producer run
    assert i.returncode == 0, i.stderr[-600:]
    rows = [x for x in h.jsonl(rs.root / "cli.log")
            if x.get("phase") != "start" and (x.get("argv") or [None])[0] == "recall-state"
            and isinstance(x.get("out_bytes"), int)]
    hook_rows = [x for x in rows if x.get("source") == "hook"]
    assert hook_rows and len(hook_rows) < len(rows), (
        "fixture: cli.log must hold hook AND interactive recall-state rows",
        [(x.get("source"), x.get("out_bytes")) for x in rows])
    assert len(r.stdout) in [x["out_bytes"] for x in hook_rows]
    j = s.rmx(rs, "telemetry", "--context", "--format", "json")
    assert j.returncode == 0, j.stderr[-600:]
    data = json.loads(j.stdout)
    assert "by_producer" in data, f"F2: no producer view in telemetry --context: {sorted(data)}"
    got = data["by_producer"].get("recall_state")
    assert got is not None, sorted(data["by_producer"])
    assert got["n"] == len(hook_rows), (got, len(hook_rows))
    assert got["total_bytes"] == sum(x["out_bytes"] for x in hook_rows), got
    assert got["max_bytes"] == max(x["out_bytes"] for x in hook_rows), got
    assert got["budget"] == s.budget_or_none("recall_state"), got
    txt = s.rmx(rs, "telemetry", "--context", COLUMNS="200")
    assert txt.returncode == 0 and "recall_state" in txt.stdout, txt.stdout[-1200:]


def test_ac15h_any_failure_is_one_error_line_never_a_traceback():
    """bsd-251 m-5 / L68 (2026-11-14): R11 -- "a real failure exits non-zero with ONE clean
    `Error:` line and no traceback" -- for ANY exception, not only the `VerbError`s the verb
    converts (an unreadable memdir, an `OSError` from `compose_recall_state`). The forced
    failure is real and not an OSError: the newest save-state holds bytes that are not UTF-8,
    so reading it raises `UnicodeDecodeError` (a ValueError). Run through the GENERATED
    compact|clear entry. HEAD: a traceback, `UnicodeDecodeError` uncaught. The `Error:` line
    names the exception type, so the cause is said."""
    base = s.short_base("p25e")
    home = base / "g" / ".refmatrix"
    s._init_store(home, partition="global")
    proj = base / "fxe"
    fx = s.Fixture(base, proj, home)
    s._init_store(fx.root)
    md = fx.memdir
    md.mkdir(parents=True, exist_ok=True)
    (md / "savestate_bad01.md").write_bytes(
        b"---\ngmd: \"0.1\"\nid: savestate_bad01\ntitle: \"bad bytes\"\nmetadata:\n"
        b"  type: session/recall-state\n  updated: 2026-11-14\n---\n\n# bad {#root}\n\n"
        b"resume \xff\xfe\xfd here\n")
    try:
        _m, cmd = _rs_entry(fx.root)
        r = s.run_cmd(fx, cmd, env_in=s.envelope("", event="SessionStart", source="compact"))
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode != 0, f"m-5: exit 0 on an unreadable save-state: {r.stdout[:300]!r}"
        assert "Traceback" not in err, f"m-5: a traceback, not one Error: line: {err[-1500:]}"
        errs = [ln for ln in err.splitlines() if ln.startswith("Error:")]
        assert len(errs) == 1, err[-800:]
        assert "UnicodeDecodeError" in errs[0], errs[0]
    finally:
        import rmx_sandbox
        rmx_sandbox.remove_tree(base)


# Every budgeted hook producer, found in the GENERATED config by the command it runs, and the
# `hook_budget.CHANNEL_BUDGET_BYTES` producer its HOOK run must count as (spec R1/R11).
_PRODUCER_OF = (
    ("UserPromptSubmit", "rmx scan-prompt", "scan_prompt"),
    ("UserPromptSubmit", "rmx curator status", "curator_status"),
    ("UserPromptSubmit", "rmx focus hook --event input", "focus_input"),
    ("UserPromptSubmit", "rmx memory recall --stdin-json", "prompt_recall"),
    ("SessionStart", "rmx memory recall --session-start", "session_start"),
    ("SessionStart", "rmx focus context", "focus_context"),
    ("PreCompact", "rmx memory recall --recent", "precompact"),
    ("SessionStart", "rmx recall-state", "recall_state"),
)


def _generated_argv(root: Path, event: str, needle: str) -> list[str]:
    """The cli.log `argv` (after `rmx`) of the generated hook segment that runs `needle`: the
    command split on `;` / `&&` / `||`, the segment shlex-split, redirections dropped."""
    for _e, _m, cmd in h.hook_entries(root, event):
        for seg in re.split(r"\s*(?:;|&&|\|\|)\s*", s.after_env(cmd)):
            if needle in seg:
                toks = shlex.split(seg)
                toks = toks[toks.index("rmx") + 1:]
                return [x for x in toks if not re.match(r"^\d?>|^&$|^<", x)]
    raise AssertionError(f"no generated {event} segment runs {needle!r}")


def test_m2_by_producer_counts_every_hook_producer(tmp_path):
    """bsd-251 m-2 / L68 (2026-11-14): `by_producer` is pinned for all 8 channels, not only
    `recall_state`. A cli.log is written whose rows carry the argv of each GENERATED hook
    producer (source "hook", a distinct size each, two for `prompt_recall`), plus rows that
    must count nowhere: the same commands run interactively, a hook `focus hook --event tool`,
    and a hook `memory recall` with none of the three channel flags. Kills bsd-251 m5
    (`--stdin-json` → None) and any other mis-mapped channel."""
    from refmatrix import hook_budget, telemetry
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    rows, want = [], {}
    for i, (ev, needle, prod) in enumerate(_PRODUCER_OF):
        argv = _generated_argv(root, ev, needle)
        sizes = [100 + i] + ([300 + i] if prod == "prompt_recall" else [])
        for sz in sizes:
            rows.append({"ts": f"2026-11-14T01:00:{i:02d}", "argv": argv, "source": "hook",
                         "exit_code": 0, "outcome": "ok", "out_bytes": sz})
        rows.append({"ts": f"2026-11-14T02:00:{i:02d}", "argv": argv, "source": "unknown",
                     "exit_code": 0, "outcome": "ok", "out_bytes": 9999})
        want[prod] = sizes
    for argv in (["focus", "hook", "--event", "tool"], ["memory", "recall", "q", "--pack"]):
        rows.append({"ts": "2026-11-14T03:00:00", "argv": argv, "source": "hook",
                     "exit_code": 0, "outcome": "ok", "out_bytes": 7777})
    (root / telemetry.CLI_LOG_NAME).write_text("".join(json.dumps(x) + "\n" for x in rows))
    bp = telemetry.summarize_context(root)["by_producer"]
    assert set(bp) == set(hook_budget.CHANNEL_BUDGET_BYTES) == set(want), (sorted(bp),
                                                                           sorted(want))
    for prod, sizes in want.items():
        got = bp[prod]
        assert (got["n"], got["total_bytes"], got["max_bytes"]) == (
            len(sizes), sum(sizes), max(sizes)), (prod, got, sizes)
        assert got["budget"] == hook_budget.budget(prod) and got["over_budget"] == 0, got


# ---- F1 (rev 7): #r10-bus -- `rmx_bus_pub`'s `about` field, `project` is transport only ----------


@pytest.fixture
def bus(r10, monkeypatch):
    """The R10 stores (cwd alpha, bravo registered, `charlie` unknown) plus a REAL bus: the
    `_MiniHub` of tests/test_verbs_migrated.py binds `hub.hub_sock_path()` under the R10 home
    and serves the real `Hub._op_bus_*` handlers over a real `Bus()`. Nothing in `src/` is
    patched; RMX_AGENT is unset so the sender default (the store's name) is observable."""
    from refmatrix import hub as hub_mod
    from tests.test_verbs_migrated import _MiniHub
    monkeypatch.delenv("RMX_AGENT", raising=False)
    mh = _MiniHub()
    assert hub_mod.is_running()
    try:
        yield r10
    finally:
        mh.close()
        try:
            hub_mod.hub_sock_path().unlink()
        except FileNotFoundError:
            pass


def _mcp_tool(name: str, arguments: dict) -> "tuple[bool, str]":
    from refmatrix import mcp
    resp = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": name, "arguments": arguments}})
    res = resp["result"]
    return bool(res.get("isError")), "".join(c.get("text", "") for c in res.get("content") or [])


def _last_on(root: Path, channel: str) -> dict:
    from refmatrix import verbs
    msgs = verbs.bus_history(root, channel)["messages"]
    assert msgs, f"nothing was published on {channel}"
    return msgs[-1]


def test_r10_bus_pub_about_tags_the_message_and_is_never_a_lookup(bus):
    """#r10-bus (user decision 2026-11-10; F1, rev 7): the message field is `about`. With no
    store named Y, `about="Y"` publishes and the hub row's `project` is `Y` -- on the verb and
    through MCP. Kills the spec's mutation "`about` ignored (row `project` empty)": MCP's
    `Verb.call` drops an argument the verb does not name, which is HEAD's behaviour."""
    from refmatrix import verbs
    alpha = bus["alpha"]
    try:
        verbs.bus_pub(alpha, "global:t1", "b", about="Y")
    except TypeError as e:
        pytest.fail(f"#r10-bus: verbs.bus_pub has no `about` parameter ({e})")
    assert _last_on(alpha, "global:t1")["project"] == "Y"
    err, text = _mcp_tool("rmx_bus_pub", {"channel": "global:t2", "body": "b", "about": "Y"})
    assert not err, text[:400]
    assert _last_on(alpha, "global:t2")["project"] == "Y", (
        "#r10-bus: MCP `about` did not reach the hub row (dropped as an unknown argument)")


def test_r10_bus_pub_project_is_the_transport_target_only(bus):
    """#r10-bus: `project` on `rmx_bus_pub` is the MCP TRANSPORT target, under R10 like every
    tool: an unknown name raises `VerbUnknownProjectError` (a guard: R10 already holds at
    HEAD); a KNOWN name publishes from that store -- its name is the default sender -- and is
    never the message's `project` tag (HEAD: the same key filled both, so the row read
    `project: bravo`). The verb has an `about` parameter and no `project` parameter of its
    own (the schema's `project` is the transport property)."""
    import inspect
    from refmatrix import mcp, verbs
    alpha = bus["alpha"]
    err, text = _mcp_tool("rmx_bus_pub", {"channel": "global:t3", "body": "b", "project": "Y"})
    assert err and text.startswith("VerbUnknownProjectError:"), text[:400]
    err, text = _mcp_tool("rmx_bus_pub", {"channel": "global:t4", "body": "b",
                                          "project": "bravo"})
    assert not err, text[:400]
    row = _last_on(alpha, "global:t4")
    assert row["from"] == "bravo", row
    assert row["project"] is None, (
        "#r10-bus: the transport target leaked into the message's project tag", row)
    params = inspect.signature(verbs.bus_pub).parameters
    assert "about" in params and "project" not in params, list(params)
    props = mcp.TOOLS["rmx_bus_pub"]["schema"]["properties"]
    assert "about" in props and "project" in props, sorted(props)


def test_r10_bus_pub_proj_channel_still_tags_its_project(bus):
    """#r10-bus: a `proj:X:t` channel with neither `about` nor `project` still tags `X` (the
    default moves to `about`; a GUARD, true at HEAD)."""
    from refmatrix import verbs
    alpha = bus["alpha"]
    verbs.bus_pub(alpha, "proj:X:t5", "b")
    row = _last_on(alpha, "proj:X:t5")
    assert row["project"] == "X" and row["from"] == "alpha", row


def test_r10_bus_pub_cli_about_option(bus):
    """#r10-bus: `rmx bus pub` gains `--about` (verb parity: the verb's `about` has its CLI
    twin). HEAD: no such option (exit 2)."""
    from click.testing import CliRunner
    from refmatrix import cli
    alpha = bus["alpha"]
    r = CliRunner().invoke(cli.main, ["bus", "pub", "global:t6", "hello", "--about", "Y"])
    assert r.exit_code == 0, (r.exit_code, r.output)
    assert _last_on(alpha, "global:t6")["project"] == "Y"

