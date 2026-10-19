"""Task 21.1 AC-11 (R12): `used` events, one AC per evidence kind -- RED tests.

A `used` event is emitted only by an EXPLICIT call (invocation not `hook`) whose named item is in
the caller session's DELIVERED SET (`telemetry.delivered_in_session`, read backwards from the end
of `recall-events.jsonl`, capped at 4 MB per file). Three evidences: `memory_get_by_name`,
`context_by_name`, `focus_note`. Destination = the delivered event's scope's file.

Every leg runs the REAL delivering surfaces through the GENERATED hook commands (the per-prompt
`memory recall --stdin-json` hook, the UserPromptSubmit `scan-prompt` hook) against a real sandbox
daemon, and a real sandbox GLOBAL daemon (`$RMX_HOME` of 23.0's sandbox) so the recall's global
leg answers (`verbs.global_recall_rows` is a lexical substring search through the global
store's daemon: the global memory's content carries the prompt verbatim). The explicit calls are
real `rmx` children (CLI) or the real `rmx mcp` stdio server.

How the explicit call resolves its session (R9 / R12 "Whose session"): per-call `rmx` children
get `RMX_SESSION=<S>` (R9's per-call order: explicit -> envelope -> `RMX_SESSION` -> pointer);
the long-lived MCP server gets `RMX_SESSION=<S>` in its env (long-lived order: pointer for
`os.getppid()` -> `RMX_SESSION`; the test writes no pointer). Every session id is unique per test
because the sandbox GLOBAL store (and its `recall-events.jsonl`) is shared by every test of one
pytest process; every count is filtered by session.

RED shape: each test records the number of `used` events after EVERY call and asserts the whole
sequence of deltas at once, so the negative legs (hook invocation, by-id lookup, other session,
the recall's internal per-hit read) are never vacuous: at HEAD the sequence is all zeros and the
assertion fails on the positive leg; after GREEN a leaking negative leg fails the same assertion.
Preconditions that HEAD can already show (the hook's stdout names the item it delivers; the
context anchor's kind) are asserted BEFORE, so the recorded failure is the missing `used` /
`delivered` events, never a fixture that delivered nothing.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest

from tests import task21_1_support as h

ALPHA = "feedback_alpha_rule"
BETA = "reference_beta_ref"
GAMMA = "feedback_gamma_rule"
# The per-prompt recall prompt. The GLOBAL leg is a substring search (`search_memories`: name or
# content LIKE %prompt%), so BETA's content carries this prompt verbatim.
RECALL_PROMPT = "apply the alpha rule"
ALPHA_BODY = "Always apply the alpha rule before merging parsers."
BETA_BODY = f"beta guide: {RECALL_PROMPT} with the beta ref"
GAMMA_BODY = "The gamma rule: never merge on red."


# ---- fixtures -------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _live_logs_untouched(monkeypatch):
    """AC preamble: the live query.log / recall-events.jsonl are untouched (stat-only)."""
    for k in h.CLAUDE_ENV:
        monkeypatch.delenv(k, raising=False)
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


@pytest.fixture
def root() -> Path:
    return Path(os.environ["REFMATRIX_ROOT"])


def _sid(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:10]}"


def _seed(root: Path, *, alpha_memory=True, code=(), memories_in_intuition=(),
          concepts=()) -> dict:
    """Seed the sandbox project store BEFORE its daemon starts (the conftest's per-test store).

    code: [(concept_name, code_name)] -- a code entity `code_name` in the project partition,
      reached by a DIFFERENTLY named concept, so scan-prompt delivers the code item (CONTENT
      MATCH) without a same-named concept item that would add a third delivered key.
    memories_in_intuition: [(name, body)] in partition `intuition`.
    concepts: bare concept names in the project partition (11e's thin concept node)."""
    from refmatrix.store import Store
    proj = root.parent
    src = proj / "pkg" / "rules.py"
    src.parent.mkdir(exist_ok=True)
    lines = []
    for _c, nm in code:
        lines += [f"def {nm}():", f"    '''{nm} implementation'''", "    return 1", ""]
    src.write_text("\n".join(lines) or "# empty\n")
    ids: dict = {}
    s = Store(root)
    try:
        for cname, nm in code:
            c = s.add_concept(cname)
            e = s.upsert_entity("code", nm, path=str(src), tldr=f"def {nm}()")
            s.link("defines", c, e)
            s.link("mentions", c, e)
        for cname in concepts:
            s.add_concept(cname)
        if alpha_memory:
            ids[ALPHA] = s.add_memory(ALPHA, ALPHA_BODY, mtype="feedback")
            s.add_memory("unrelated_soup_note", "cooking recipes for soup", mtype="project")
        if memories_in_intuition:
            with s.with_partition("intuition"):
                for nm, body in memories_in_intuition:
                    ids[nm] = s.add_memory(nm, body, mtype="feedback")
        s.flush_fragments()
    finally:
        s.close()
    r = h.run_rmx(["embed", "--kinds", "memory"], root=root, timeout=600)
    assert r.returncode == 0, f"fixture: embed failed: {r.stderr[-800:]}"
    if memories_in_intuition:
        r = h.run_rmx(["embed", "--kinds", "memory"], root=root, timeout=600,
                      RMX_PARTITION="intuition")
        assert r.returncode == 0, f"fixture: intuition embed failed: {r.stderr[-800:]}"
    return ids


def _seed_global() -> Path:
    """reference_beta_ref in the SANDBOX global store (partition `global`), before its daemon."""
    from refmatrix.store import Store
    g = h.global_root()
    gs = Store(g)
    try:
        with gs.with_partition("global"):
            gs.add_memory(BETA, BETA_BODY, mtype="reference")
    finally:
        gs.close()
    return g


# ---- calls ----------------------------------------------------------------------------------

def _prompt_recall(root: Path, session: str, prompt: str = RECALL_PROMPT, **extra) -> list:
    """The GENERATED per-prompt recall hook (`prompt_recall` channel), S's envelope on stdin."""
    cmd = h.generated_cmd(root, "UserPromptSubmit", "memory recall --stdin-json")
    r = h.run_hook(cmd, root=root, timeout=300, envelope={
        "session_id": session, "prompt": prompt, "hook_event_name": "UserPromptSubmit",
        "cwd": str(root.parent)}, **extra)
    assert r.returncode == 0, f"fixture: recall hook failed: {r.stderr[-800:]}"
    rows = json.loads(r.stdout or "[]")
    return rows


def _scan(root: Path, session: str, prompt: str) -> str:
    """The GENERATED UserPromptSubmit scan-prompt hook (`scan_prompt` channel)."""
    cmd = h.generated_cmd(root, "UserPromptSubmit", "scan-prompt")
    r = h.run_hook(cmd, root=root, envelope={
        "session_id": session, "prompt": prompt, "hook_event_name": "UserPromptSubmit",
        "cwd": str(root.parent)})
    return r.stdout


def _agent(root: Path, args, session: str | None, **extra):
    """An AGENT call: `CLAUDECODE=1` (R2 -> invocation `agent`), session via RMX_SESSION."""
    env = {"CLAUDECODE": "1", **extra}
    if session is not None:
        env["RMX_SESSION"] = session
    return h.run_rmx(args, root=root, **env)


def _used(path_root: Path, session: str) -> list:
    return [e for e in h.events(path_root)
            if e.get("stage") == "used" and e.get("session") == session]


def _all_used(root: Path, g: Path, session: str) -> list:
    return _used(root, session) + _used(g, session)


def _delivered(path_root: Path, session: str, name: str, kind: str) -> list:
    return [e for e in h.events(path_root)
            if e.get("stage") == "delivered" and e.get("session") == session
            and e.get("name") == name and e.get("kind") == kind]


def _wait_context_without(root: Path, ref: str, text: str, session: str | None,
                          timeout: float = 30.0) -> None:
    """After a forget, the lock-free replica the CLI context route reads lags the writer. Wait
    until a context call no longer shows `text` (a NON-agent, sessionless probe: it can emit
    nothing that a later assertion counts)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = h.run_rmx(["context", ref], root=root)
        if text not in r.stdout:
            return
        time.sleep(1.0)
    raise AssertionError(f"fixture: {ref!r} still shows {text!r} after {timeout}s")


# ---- AC-11a ---------------------------------------------------------------------------------

def test_ac11a_memory_get_by_name_emits_one_used_and_only_for_the_agent_by_name_in_session(root):
    """AC-11a memory_get_by_name (CLI, both the verb path and -- by the same command -- the
    replica fall-through's emission site). Sequence, `used` delta per call:
      prompt_recall in S (its internal per-hit `memory_get` reads)      -> 0
      `memory get feedback_alpha_rule` with RMX_INVOCATION_SOURCE=hook -> 0
      `memory get <id>` by id (agent, S)                               -> 0
      `memory get feedback_alpha_rule` in session S2 (agent)            -> 0
      `memory get feedback_alpha_rule` in S (agent, CLAUDECODE=1)       -> 1
    The one event: evidence=memory_get_by_name, ref_query_id = the delivering prompt_recall's
    query_id, kind=memory, scope=project, in the PROJECT file (none in the global file)."""
    ids = _seed(root)
    g = _seed_global()
    S, S2 = _sid("S"), _sid("S2")
    cum = []          # cumulative used events of S and S2 after each call

    def _n():
        return len(_all_used(root, g, S)) + len(_all_used(root, g, S2))
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        rows = _prompt_recall(root, S)
        assert ALPHA in [r.get("name") for r in rows], f"fixture: recall did not deliver: {rows}"
        cum.append(_n())
        _agent(root, ["memory", "get", ALPHA], S, RMX_INVOCATION_SOURCE="hook")
        cum.append(_n())
        _agent(root, ["memory", "get", str(ids[ALPHA])], S)
        cum.append(_n())
        _agent(root, ["memory", "get", ALPHA], S2)
        cum.append(_n())
        r = _agent(root, ["memory", "get", ALPHA], S)
        cum.append(_n())
    deltas = [cum[0]] + [b - a for a, b in zip(cum, cum[1:])]
    assert ALPHA_BODY in r.stdout, f"fixture: the agent's memory get failed: {r.stderr[-500:]}"
    assert deltas == [0, 0, 0, 0, 1], (
        "R12 memory_get_by_name: used deltas per call [recall, hook get, by-id get, S2 get, "
        f"agent get in S] = {deltas}; expected exactly one, on the agent's by-name get in S")
    (u,) = _used(root, S)
    assert _used(g, S) == [], "a project memory's use must not land in the GLOBAL file"
    assert u["evidence"] == "memory_get_by_name"
    assert (u["name"], u["kind"], u["scope"]) == (ALPHA, "memory", "project"), u
    (d,) = _delivered(root, S, ALPHA, "memory")[-1:]
    assert u["ref_query_id"] == d["query_id"], (u, d)
    assert u["partition"] == d["partition"], (u, d)
    assert u["invocation"] == "agent", u


def test_ac11a_mcp_rmx_memory_get_action_by_name_emits_used(root):
    """AC-11a, MCP leg: the `rmx_memory` `get` action (`verbs.memory`, verbs.py:1157) through
    the real stdio server, session S via the server's env (`RMX_SESSION`; no pointer exists, so
    the long-lived order falls to it). By id -> 0; by name -> 1, ref_query_id = the recall's."""
    ids = _seed(root)
    g = _seed_global()
    S = _sid("S")
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        _prompt_recall(root, S)
        with h.McpServer(root, RMX_SESSION=S) as m:
            r1 = m.tool("rmx_memory", {"action": "get", "id": ids[ALPHA]})
            after_id = len(_all_used(root, g, S))
            r2 = m.tool("rmx_memory", {"action": "get", "name": ALPHA})
            after_name = len(_all_used(root, g, S))
    assert not r1["isError"] and not r2["isError"], (r1["text"][:300], r2["text"][:300])
    assert (after_id, after_name) == (0, 1), (
        f"R12 MCP memory get: used after by-id get={after_id}, after by-name get={after_name}; "
        "expected (0, 1)")
    (u,) = _used(root, S)
    assert u["evidence"] == "memory_get_by_name" and u["invocation"] == "mcp", u
    assert u["ref_query_id"] == _delivered(root, S, ALPHA, "memory")[-1]["query_id"]


# ---- AC-11b ---------------------------------------------------------------------------------

def test_ac11b_context_by_name_on_the_memory_anchor_emits_one_used(root):
    """AC-11b: `rmx context feedback_alpha_rule` whose anchor resolves to the memory (no concept
    or code of that name in the store) emits ONE `used`, evidence=context_by_name, kind=memory,
    pointing at the prompt_recall delivery. Also through the MCP `rmx_context` route
    (`verbs.context`) in a second session S3: one `used` there too."""
    _seed(root)
    g = _seed_global()
    S, S3 = _sid("S"), _sid("S3")
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        _prompt_recall(root, S)
        r = _agent(root, ["context", ALPHA], S)
        _prompt_recall(root, S3)
        with h.McpServer(root, RMX_SESSION=S3) as m:
            mr = m.tool("rmx_context", {"ref": ALPHA})
    assert f"anchor: {ALPHA}  [memory]" in r.stdout, f"fixture: anchor is not the memory: {r.stdout[:400]}"
    assert not mr["isError"], mr["text"][:300]
    got = (len(_all_used(root, g, S)), len(_all_used(root, g, S3)))
    assert got == (1, 1), (
        f"R12 context_by_name: used events (CLI in S, MCP in S3) = {got}; expected (1, 1)")
    for sess in (S, S3):
        (u,) = _used(root, sess)
        assert u["evidence"] == "context_by_name", u
        assert (u["name"], u["kind"], u["scope"]) == (ALPHA, "memory", "project"), u
        assert u["ref_query_id"] == _delivered(root, sess, ALPHA, "memory")[-1]["query_id"]


def test_ac11b_code_symbol_sharing_a_memory_name_is_a_code_use_not_a_memory_use(root):
    """AC-11b, the kind check: in S a prompt_recall delivers MEMORY feedback_alpha_rule and a
    scan_prompt delivers CODE symbol feedback_alpha_rule. The memory is then forgotten, so
    `rmx context feedback_alpha_rule` anchors on the code symbol and attaches NO memory body:
    exactly one `used` with kind=code, NONE with kind=memory (a matcher without the kind check
    also fires on the delivered memory key)."""
    _seed(root, code=[("alpha_rules", ALPHA)])
    g = _seed_global()
    S = _sid("S")
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        _prompt_recall(root, S)
        out = _scan(root, S, f"fix alpha_rules in {ALPHA} now")
        assert f"{ALPHA}  [code]" in out, f"fixture: scan-prompt did not deliver the code item: {out[:600]}"
        r = h.run_rmx(["memory", "forget", "--yes", ALPHA], root=root)
        assert r.returncode == 0, r.stderr[-400:]
        _wait_context_without(root, ALPHA, ALPHA_BODY, None)
        before = len(_all_used(root, g, S))
        c = _agent(root, ["context", ALPHA], S)
    assert f"anchor: {ALPHA}  [code]" in c.stdout and ALPHA_BODY not in c.stdout, c.stdout[:500]
    kinds = sorted(u["kind"] for u in _all_used(root, g, S))
    assert (before, kinds) == (0, ["code"]), (
        f"R12 context_by_name kind check: used before={before}, kinds after the code-anchored "
        f"context call={kinds}; expected (0, ['code'])")
    (u,) = _used(root, S)
    assert u["evidence"] == "context_by_name"
    assert u["ref_query_id"] == _delivered(root, S, ALPHA, "code")[-1]["query_id"]


# ---- AC-11c ---------------------------------------------------------------------------------

def test_ac11c_focus_note_emits_one_used_per_distinct_name_global_to_global_file(root):
    """AC-11c: in S, prompt_recall delivers project memory feedback_alpha_rule and GLOBAL memory
    reference_beta_ref; scan_prompt delivers code item `run` (below the matchable length). The
    note `applied feedback_alpha_rule, then feedback_alpha_rule again; see
    [[reference_beta_ref#why]]` emits EXACTLY two `used` (one per distinct name, not per
    occurrence): feedback_alpha_rule in the PROJECT file, reference_beta_ref (via the wikilink)
    in the GLOBAL file with scope=global. A second note `see feedback_alpha_rules and run it`
    emits none (a longer token; `run` is too short to match)."""
    _seed(root, code=[("runner_loop", "run")])
    g = _seed_global()
    S = _sid("S")
    note1 = (f"applied {ALPHA}, then {ALPHA} again; see [[{BETA}#why]]")
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        rows = _prompt_recall(root, S)
        assert {ALPHA, BETA} <= {r.get("name") for r in rows}, f"fixture: recall rows {rows}"
        out = _scan(root, S, "check the runner_loop and run it")
        assert "run  [code]" in out, f"fixture: scan-prompt did not deliver `run`: {out[:600]}"
        r1 = _agent(root, ["focus", "note", note1], S)
        n_after_1 = (len(_used(root, S)), len(_used(g, S)))
        r2 = _agent(root, ["focus", "note", f"see {ALPHA}s and run it"], S)
        n_after_2 = (len(_used(root, S)), len(_used(g, S)))
    assert r1.returncode == 0 and r2.returncode == 0, (r1.stderr[-300:], r2.stderr[-300:])
    assert (n_after_1, n_after_2) == ((1, 1), (1, 1)), (
        f"R12 focus_note: (project, global) used after note 1 = {n_after_1}, after note 2 = "
        f"{n_after_2}; expected ((1, 1), (1, 1))")
    (p,) = _used(root, S)
    (gl,) = _used(g, S)
    assert p["evidence"] == gl["evidence"] == "focus_note"
    assert (p["name"], p["kind"], p["scope"]) == (ALPHA, "memory", "project"), p
    assert (gl["name"], gl["kind"], gl["scope"]) == (BETA, "memory", "global"), gl
    assert gl["ref_query_id"] == _delivered(g, S, BETA, "memory")[-1]["query_id"]


# ---- AC-11d ---------------------------------------------------------------------------------

def _filler_events(n_bytes: int, *, root: Path, session: str) -> bytes:
    """Schema-shaped `delivered` events of OTHER sessions (AC-11d's own setup: '6 MB of other
    sessions' events appended after the delivery')."""
    base = {"v": 1, "ts": "2026-10-16T00:00:00.000Z", "turn": 0, "channel": "prompt_recall",
            "invocation": "hook", "kind": "memory", "scope": "project", "partition": "p",
            "cwd": str(root.parent), "root": str(root), "rank": 1, "stage": "delivered",
            "entity_id": 1, "arm": "fixed", "policy": "fixed-v0", "pad": "x" * 200}
    out = bytearray()
    i = 0
    while len(out) < n_bytes:
        ev = {**base, "session": f"{session}-other-{i % 97}", "query_id": uuid.uuid4().hex,
              "name": f"other_memory_{i}"}
        out += (json.dumps(ev) + "\n").encode()
        i += 1
    return bytes(out)


def test_ac11d_lookup_reads_at_most_4mb_and_counts_the_cap_hit(root):
    """AC-11d: with 6 MB of other sessions' events appended after S's delivery of
    feedback_alpha_rule, the agent's `memory get feedback_alpha_rule` in S emits NO `used` (the
    delivery lies beyond the 4 MB backward read) and `rmx telemetry --agent-usage` reports
    `used_lookup_cap_hits` >= 1 (format not fixed by the spec: matched as the name and a
    number on one line)."""
    _seed(root)
    g = _seed_global()
    S = _sid("S")
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        _prompt_recall(root, S)
        with open(root / "recall-events.jsonl", "ab") as f:
            f.write(_filler_events(6 * 1024 * 1024, root=root, session=S))
        _agent(root, ["memory", "get", ALPHA], S)
        rep = h.run_rmx(["telemetry", "--agent-usage"], root=root)
    m = re.search(r"used_lookup_cap_hits\D{0,4}(\d+)", rep.stdout)
    assert m and int(m.group(1)) >= 1, (
        "R12 lookup bound: `rmx telemetry --agent-usage` must count the capped lookup "
        f"(used_lookup_cap_hits >= 1); stdout={rep.stdout[-600:]!r} stderr={rep.stderr[-400:]!r}")
    assert _all_used(root, g, S) == [], "a delivery beyond the 4 MB cap must not be matched"


def test_ac11d_delivered_in_session_is_bounded_backwards_read(root):
    """AC-11d, the lookup itself (in process; the delivery event is the lookup's INPUT, so it is
    written here): S's delivery followed by 1 MB of other sessions' events IS found; the same
    delivery followed by 6 MB is NOT (the backward read stops at 4 MB per file). An unbounded
    lookup finds it in both."""
    from refmatrix import telemetry
    assert hasattr(telemetry, "delivered_in_session"), (
        "R12: telemetry.delivered_in_session (the delivered-set lookup) is not built")
    g = h.global_root()
    S = _sid("S")
    qid = uuid.uuid4().hex
    delivery = {"v": 1, "ts": "2026-10-16T00:00:00.000Z", "session": S, "turn": 0,
                "query_id": qid, "channel": "prompt_recall", "invocation": "hook",
                "name": ALPHA, "entity_id": 7, "kind": "memory", "scope": "project",
                "partition": "p", "cwd": str(root.parent), "root": str(root), "rank": 1,
                "stage": "delivered", "offset_bytes": 0, "bytes": 10, "payload_bytes": 100}
    for pad_mb, found in ((1, True), (6, False)):
        p = root / "recall-events.jsonl"
        p.write_bytes((json.dumps(delivery) + "\n").encode()
                      + _filler_events(pad_mb * 1024 * 1024, root=root, session=S))
        got = telemetry.delivered_in_session(S, root=root, global_root=g)
        assert ((ALPHA, "memory", "project") in got) is found, (
            f"R12 lookup with {pad_mb} MB after the delivery: found="
            f"{(ALPHA, 'memory', 'project') in got}, expected {found}")
        if found:
            assert got[(ALPHA, "memory", "project")]["query_id"] == qid


# ---- AC-11e ---------------------------------------------------------------------------------

def test_ac11e_concept_anchor_with_attached_memory_body(root):
    """AC-11e: memory feedback_gamma_rule in partition `intuition` AND a same-named concept in
    the PROJECT partition (the bridge's shape). `rmx context feedback_gamma_rule` anchors on the
    concept and attaches the memory body; its events are one `delivered` kind=concept (project
    partition) and one `delivered` kind=memory (partition intuition, body span set).
    After a prompt_recall delivered that memory in S, the agent's same context call emits
    exactly one `used`, kind=memory, evidence=context_by_name. With the memory deleted (concept
    only, no body), the call emits no kind=memory `used`.

    The recall hook runs with RMX_PARTITION=intuition so its dense leg reads the partition the
    memory lives in (the generated command reads the project partition by default)."""
    _seed(root, alpha_memory=False, memories_in_intuition=[(GAMMA, GAMMA_BODY)],
          concepts=[GAMMA])
    g = _seed_global()
    from refmatrix.discovery import store_name
    project_partition = store_name(root)
    S0, S = _sid("S0"), _sid("S")
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        c0 = _agent(root, ["context", GAMMA], S0)
        rows = _prompt_recall(root, S, prompt="the gamma rule", RMX_PARTITION="intuition")
        assert GAMMA in [r.get("name") for r in rows], f"fixture: recall rows {rows}"
        c1 = _agent(root, ["context", GAMMA], S)
        used_after_c1 = [u["kind"] for u in _all_used(root, g, S)]
        r = h.run_rmx(["memory", "forget", "--yes", GAMMA], root=root, RMX_PARTITION="intuition")
        assert r.returncode == 0, r.stderr[-400:]
        _wait_context_without(root, GAMMA, GAMMA_BODY, None)
        c2 = _agent(root, ["context", GAMMA], S)
        used_after_c2 = [u["kind"] for u in _all_used(root, g, S)]
    assert f"anchor: {GAMMA}  [concept]" in c0.stdout and GAMMA_BODY in c0.stdout, c0.stdout[:400]
    ctx_delivered = [e for e in h.events(root)
                     if e.get("session") == S0 and e.get("channel") == "context"
                     and e.get("stage") == "delivered" and e.get("name") == GAMMA]
    kinds = sorted((e["kind"], e["partition"]) for e in ctx_delivered)
    assert kinds == sorted([("concept", project_partition), ("memory", "intuition")]), (
        f"R11 context delivers the concept anchor AND the attached body: got {kinds}")
    (mem,) = [e for e in ctx_delivered if e["kind"] == "memory"]
    assert mem["body_offset_bytes"] is not None and mem["body_bytes"], mem
    assert GAMMA_BODY not in c2.stdout, "fixture: the body is still attached after the forget"
    assert (used_after_c1, used_after_c2) == (["memory"], ["memory"]), (
        f"R12 context_by_name on an attached body: used kinds after the context call="
        f"{used_after_c1}, after the concept-only call={used_after_c2}; expected "
        "(['memory'], ['memory'])")
    (u,) = _used(root, S)
    assert u["evidence"] == "context_by_name" and u["partition"] == "intuition", u


# ---- AC-11f ---------------------------------------------------------------------------------

def test_ac11f_focus_note_sentence_final_name_and_one_used_per_key(root):
    """AC-11f: in S with feedback_alpha_rule delivered as a MEMORY (prompt_recall):
      note `applied feedback_alpha_rule.` -> none (`.` is a token character; under-count stated);
    then with a CODE symbol feedback_alpha_rule ALSO delivered by scan_prompt:
      note `applied feedback_alpha_rule now` -> two `used`, one per key (memory, code)."""
    _seed(root, code=[("alpha_rules", ALPHA)])
    g = _seed_global()
    S = _sid("S")
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        _prompt_recall(root, S)
        _agent(root, ["focus", "note", f"applied {ALPHA}."], S)
        after_final = len(_all_used(root, g, S))
        out = _scan(root, S, f"fix alpha_rules in {ALPHA} now")
        assert f"{ALPHA}  [code]" in out, f"fixture: scan-prompt did not deliver the code item: {out[:600]}"
        _agent(root, ["focus", "note", f"applied {ALPHA} now"], S)
        kinds = sorted(u["kind"] for u in _all_used(root, g, S))
    assert (after_final, kinds) == (0, ["code", "memory"]), (
        f"R12 focus_note edges: used after the sentence-final note={after_final}, kinds after "
        f"the plain note={kinds}; expected (0, ['code', 'memory'])")
    for u in _used(root, S):
        d = _delivered(root, S, ALPHA, u["kind"])[-1]
        assert u["ref_query_id"] == d["query_id"], (u, d)


# ---- R12 "Whose session" ----------------------------------------------------------------------

def test_r12_no_resolved_session_emits_no_used(root):
    """R12 'Whose session': an agent call that resolves NO session (no RMX_SESSION, no envelope,
    no pointer for its owner) emits no `used` -- the newest ring is never used; the same call
    with S resolved emits one. Deltas [0, 1]."""
    _seed(root)
    g = _seed_global()
    S = _sid("S")
    with h.SandboxDaemon(g, RMX_PARTITION="global"), h.SandboxDaemon(root):
        _prompt_recall(root, S)
        from refmatrix import stm
        stm.Stm(root, S).record("input", "make S the newest ring on disk")
        _agent(root, ["memory", "get", ALPHA], None)
        unresolved = len([e for e in h.events(root) if e.get("stage") == "used"])
        _agent(root, ["memory", "get", ALPHA], S)
        resolved = len(_all_used(root, g, S))
    assert (unresolved, resolved) == (0, 1), (
        f"R12 whose session: used with no resolved session={unresolved}, with S={resolved}; "
        "expected (0, 1)")


# ---- round 13 #s1: context_by_name sees an EARLIER context call; one write per call ----------

def test_r12_context_by_name_matches_a_key_an_earlier_context_call_delivered(root):
    """Round 13 #s1 (R12 `context_by_name`): only the CURRENT call's own `query_id` is left out
    of the delivered-set lookup. `rmx context feedback_alpha_rule` twice in S (agent): the
    first call has nothing earlier -> 0 `used`; the second matches the key the FIRST context
    call delivered -> exactly 1 `used`, `query_id` = the second call's, `ref_query_id` = the
    first call's. Every event of the second call is written once and in ONE writer call (R11:
    one `ts` per `emit_recall_events` call). RED at HEAD: `context_used_keys` drops every
    `context`-channel delivery, so the deltas are (0, 0)."""
    _seed(root)
    S = _sid("S")
    with h.SandboxDaemon(root):
        r1 = _agent(root, ["context", ALPHA], S)
        n1 = len(_used(root, S))
        r2 = _agent(root, ["context", ALPHA], S)
        n2 = len(_used(root, S))
    for r in (r1, r2):
        assert f"anchor: {ALPHA}  [memory]" in r.stdout, (
            f"fixture: anchor is not the memory: {r.stdout[:400]} {r.stderr[-400:]}")
    qids = [q.get("query_id") for q in h.query_rows(root)
            if q.get("kind") == "context" and q.get("session") == S]
    assert len(qids) == 2 and None not in qids, qids
    q1, q2 = qids
    assert (n1, n2) == (0, 1), (
        f"R12 context_by_name (round 13 #s1): used after the 1st / 2nd context call in S = "
        f"{(n1, n2)}; expected (0, 1) -- an earlier context delivery is evidence")
    (u,) = _used(root, S)
    assert u["evidence"] == "context_by_name", u
    assert (u["name"], u["kind"], u["scope"]) == (ALPHA, "memory", "project"), u
    assert (u["query_id"], u["ref_query_id"]) == (q2, q1), (u, q1, q2)
    evs2 = [e for e in h.events(root) if e.get("query_id") == q2]
    keys = [(e.get("stage"), e.get("name"), e.get("kind"), e.get("entity_id"),
             e.get("offset_bytes")) for e in evs2]
    assert len(keys) == len(set(keys)), f"R11: an event of one call written twice: {keys}"
    assert len({e.get("ts") for e in evs2}) == 1, (
        f"R11: one context call's events came from more than one writer call: "
        f"{sorted({e.get('ts') for e in evs2})}")


@pytest.mark.parametrize("earlier", ["prompt_recall", "context"])
def test_r11_one_context_call_hands_all_its_events_to_the_writer_once(root, monkeypatch,
                                                                      earlier):
    """Round 13 #s1 (R11 "EXACTLY ONCE per call"): `telemetry.emit_context_call` -- the context
    channel's one emission, shared by all four routes -- hands its `retrieved`, `delivered` AND
    `context_by_name` `used` events to `emit_recall_events` in ONE call. The key was delivered
    earlier in S by a `prompt_recall` or by an earlier `context` call (another query_id); both
    are evidence. `emit_recall_events` is wrapped by a pass-through spy (registered), so the
    real writer still writes. RED at HEAD: prompt_recall -> two writer calls (delivered, then
    used); context -> no `used` at all."""
    from refmatrix import telemetry
    S = _sid("S")
    item = {"name": ALPHA, "entity_id": 7, "catalog_kind": "memory", "mtype": "feedback",
            "scope": "project", "partition": "intuition", "rank": 1}
    prior = f"[{ALPHA}]\n".encode()
    telemetry.emit_call(root, channel=earlier, invocation="hook" if earlier != "context"
                        else "agent", session=S, query_id="a" * 32, retrieved=[item],
                        delivered=[{**item, "offset_bytes": 1, "bytes": len(ALPHA)}],
                        payload=prior, block_id=telemetry.RECALL_BLOCK_IDS.get(earlier))
    calls: list[list[dict]] = []
    real = telemetry.emit_recall_events

    def spy(events, **kw):
        calls.append(list(events))
        return real(events, **kw)
    monkeypatch.setattr(telemetry, "emit_recall_events", spy)
    payload = f"anchor: {ALPHA}  [memory]\n".encode()
    off = payload.index(ALPHA.encode())
    telemetry.emit_context_call(root, ref=ALPHA,
                                items=[{**item, "offset_bytes": off, "bytes": len(ALPHA)}],
                                payload=payload, query_id="b" * 32, session=S,
                                invocation="agent")
    stages = [sorted(e.get("stage") for e in c) for c in calls]
    assert stages == [["delivered", "retrieved", "used"]], (
        f"R11 (round 13 #s1): one context call = ONE writer call carrying retrieved, delivered "
        f"and used; writer calls were {stages}")
    (u,) = [e for e in calls[0] if e.get("stage") == "used"]
    assert (u["query_id"], u["ref_query_id"]) == ("b" * 32, "a" * 32), u
