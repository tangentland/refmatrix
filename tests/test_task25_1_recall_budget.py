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


CHANNELS = {"prompt_recall", "scan_prompt", "curator_status", "focus_input", "session_start",
            "focus_context", "precompact"}
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
    chars, shlex-quoted (a shell metacharacter cannot escape the pointer)."""
    q = "line one of the question\nline two; rm -rf $HOME `x` " + "pad " * 40
    rows = [_urow(i, body=2000) for i in range(12)]
    p = _pack_unit(rows, max_bytes=2000, channel="prompt_recall", query=q, mode="dense",
                   k_more=24)
    pk = s.Pack(p.text.encode())
    assert pk.trailer is not None and pk.more == 12 - len(pk.named) > 0
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
    assert len(got) >= 8, (f"AC-3: the model receives {len(got)} distinct memories "
                           f"({sorted(got)}) from a {len(r.stdout)} B payload")


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
    for the same query, including a `kind=doc` row (the CLI-only doc leg moves into the verb)."""
    from refmatrix import verbs
    r = s.rmx(fx, "memory", "recall", QUESTION, "--json", "-K", "memory,doc", "--k", "8")
    assert r.returncode == 0, r.stderr[-800:]
    cli_rows = json.loads(r.stdout)
    monkeypatch.setenv("RMX_HOME", str(fx.home))
    vres = verbs.memory_recall(fx.root, query=QUESTION, k=8, kinds=["memory", "doc"])
    vnames = [m["name"] for m in vres["memories"]]
    assert [m["name"] for m in cli_rows] == vnames, ([m["name"] for m in cli_rows], vnames)
    assert any((m.get("kind") == "doc") for m in vres["memories"]), (
        f"AC-4 (f): the verb returns no kind=doc row for -K memory,doc: {vnames}")
    t = s.rmx(fx, "memory", "recall", QUESTION, "-K", "memory,doc", "--k", "8",
              COLUMNS="400")
    assert t.returncode == 0, t.stderr[-800:]
    for n in vnames:
        assert n in t.stdout, f"table misses {n}"


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
    """AC-6 (R2): 0 subject rows on the per-prompt argv. HEAD records ≥ 1."""
    r = _q(fx)
    _ok(r, "per-prompt argv")
    named = s.names_in_payload(r.stdout)
    assert not set(named) & set(s.SUBJECTS), f"AC-6: subjects named: {named}"
    _pack(r, "per-prompt argv")


def test_ac6_include_subjects_brings_live_subjects_back_never_the_stale_one(fx):
    r = _q(fx, append=" --include-subjects")
    p = _pack(r, "per-prompt argv --include-subjects")
    assert set(p.named) & set(s.LIVE_SUBJECTS), p.named
    assert s.STALE_SUBJECT not in p.named


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
    from refmatrix import verbs
    monkeypatch.setenv("RMX_HOME", str(fx.home))
    names = [m["name"] for m in verbs.memory_recall(fx.root, query=QUESTION, k=12)["memories"]]
    assert not set(names) & set(s.SUBJECTS), names
    names = [m["name"] for m in verbs.memory_recall(fx.root, query=QUESTION, k=12,
                                                     include_subjects=True)["memories"]]
    assert set(names) & set(s.LIVE_SUBJECTS), names
    assert s.STALE_SUBJECT not in names


# ---- AC-7: the CLI prints the verb ----------------------------------------------------------------------


def test_ac7_cli_prints_the_verbs_text_byte_for_byte(fx, monkeypatch):
    """AC-7: the verb's `text` (query, k=12, scope=both, pack=True) equals the per-prompt argv's
    stdout byte for byte (one trailing newline from click.echo tolerated). Replica leg OFF (no
    worker); the ON leg is AC-4 (d)'s parity."""
    from refmatrix import verbs
    r = _q(fx)
    _ok(r, "per-prompt argv")
    monkeypatch.setenv("RMX_HOME", str(fx.home))
    res = verbs.memory_recall(fx.root, query=QUESTION, k=12, scope="both", pack=True)
    assert "text" in res, f"AC-7: pack=True returned no `text`: keys {sorted(res)}"
    assert r.stdout.rstrip(b"\n") == res["text"].encode("utf-8").rstrip(b"\n")


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
    p = _pack(_ss(fx), "SessionStart argv")
    assert len(p.bodied) >= 2, f"AC-9: {len(p.bodied)} bodied hits on session_start"
    assert set(p.bodied) <= set(p.named)
    last_hook = max(p.text.index(m.group(0)) for m in p.hook_lines)
    first_body = min(p.text.index(f"BODYMARK {b}") for b in p.bodied)
    assert first_body > last_hook
    assert len(p.named) + p.more == 30, (len(p.named), p.more)


# ---- AC-10: delivered events and spans -------------------------------------------------------------


def test_ac10_delivered_events_slice_the_payload_by_bytes(fx):
    """AC-10 (R9): on the SessionStart argv, one `delivered` event per NAMED hit (none for a
    trimmed hit), one query_id with the `retrieved` events; each span slices exactly its hook
    line / body out of the payload BYTES; unbodied hits carry null body fields; a global hit's
    event is in the tmp global root's file with scope=global. The fixed 7-of-12/3-bodied shape
    of 19.1 AC-6 is not forced here (R0 sets the budget the shape depends on)."""
    pe, ge = fx.root / "recall-events.jsonl", fx.home / "recall-events.jsonl"
    n_p, n_g = len(h.jsonl(pe)), len(h.jsonl(ge))
    r = _ss(fx)
    p = _pack(r, "SessionStart argv")
    # This module runs one hook at a time, so the lines appended since n_p/n_g are this call's
    # (`--session-start` reads no envelope, so the event's session is not the test's to pick).
    new_g = [e for e in h.jsonl(ge)[n_g:] if e.get("channel") == "session_start"]
    evs = [e for e in h.jsonl(pe)[n_p:] if e.get("channel") == "session_start"] + new_g
    qids = {e.get("query_id") for e in evs}
    assert len(qids) == 1 and None not in qids, qids
    deliv = [e for e in evs if e.get("stage") == "delivered"]
    assert sorted(e["name"] for e in deliv) == sorted(p.named), (
        [e["name"] for e in deliv], p.named)
    raw = r.stdout
    for e in deliv:
        line = raw[e["offset_bytes"]:e["offset_bytes"] + e["bytes"]]
        assert line == (p.hook_line_of(e["name"]) + "\n").encode("utf-8"), (e["name"], line)
        if e["name"] in p.bodied:
            body = raw[e["body_offset_bytes"]:e["body_offset_bytes"] + e["body_bytes"]]
            assert f"BODYMARK {e['name']}".encode() in body
            assert raw[:e["body_offset_bytes"]].decode().count("—") >= 3
        else:
            assert e.get("body_offset_bytes") is None and e.get("body_bytes") is None, e
        if e["name"] in s.GLOBAL_NAMES:
            assert e.get("scope") == "global"
    g_deliv = [e for e in new_g if e.get("stage") == "delivered"]
    assert all(e.get("scope") == "global" for e in g_deliv)
    assert {e["name"] for e in g_deliv} == {n for n in p.named if n in s.GLOBAL_NAMES}


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
    (no interpolated budget variable), and `--k` SessionStart 30, per-prompt 12, PreCompact 30
    (PreCompact absent only if R0 dropped it); then `rmx install-hooks --apply` → `--check` is
    clean in the sandbox."""
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    (root.parent / ".git").mkdir()
    want = {"UserPromptSubmit": ("memory recall --stdin-json", 12),
            "SessionStart": ("memory recall --session-start", 30),
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
