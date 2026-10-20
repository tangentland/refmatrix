"""Task 21.1 RED: the recall-event emitters (AC-8, AC-8b, AC-8c, AC-8d, AC-10, AC-12).

Spec: workflow/plans/plan-21-agent-context-usage-tasks/task-21.1-context-usage-telemetry.md,
R8-R11 + R10a. Every leg runs a REAL entry point -- the GENERATED hook command line (bash -c,
the envelope on stdin, cwd = the project dir), the real `rmx mcp` stdio server, or the real CLI
-- against a sandbox store served by a real `rmx daemon start --no-detach` child. Nothing in
`src/` is patched.

The fixture store (one per module, AC-8):
- PROJECT partition: an ingested corpus of 3 docs + 3 code files whose text carries `—`
  (U+2014) on every line that scan-prompt renders, so the payload is raw UTF-8 (AC-8d);
- partition `intuition`: 10 embedded memories. 3 are `feedback`, 7 are `session/digest`. The
  generated per-prompt recall runs in hook mode, which hides `session/*` from the PAYLOAD but
  not from the retrieval (ann_k = 3k = 15 > 10), so one real recall retrieves 10 and delivers 3
  -- AC-8's "payload carries 3 of 10" with no test-only knob;
- an STM ring for session `sess-emit` with 5 recorded inputs forming 2 focus topics.

Spec reading recorded (ambiguity): the generated recall hooks carry no `--partition`; at HEAD
the memory commands bind `memory-<project>` / the project partition unless `RMX_PARTITION`
says otherwise. AC-8 seeds the hits in `intuition`, so the recall legs run with
`RMX_PARTITION=intuition` in the hook's environment (the generated command line itself is
unchanged). The bound-partition mutation is therefore not killed on the recall leg by this
file; AC-11e's attached body (a memory in `intuition` under a project-partition concept) is the
leg that kills it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

import pytest

from tests import task21_1_support as h

SESSION = "sess-emit"
SCAN_PROMPT = "how does zorbulate work naïve alpha_topic_a"
RECALL_PROMPT = "quasar ledger reconcile alpha_topic_a"
EVENT_TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
SEED_INPUTS = (
    "work on alpha_topic_a with beta_topic_a",
    "alpha_topic_a beta_topic_a gamma_topic_a",
    "beta_topic_a gamma_topic_a again",
    "delta_topic_b epsilon_topic_b",
    "delta_topic_b epsilon_topic_b zeta_topic_b",
)
N_MEMORIES = 10
N_DELIVERABLE = 3
# The 8b parked call: its refs join topic A (gamma_topic_a) and add a node.
PARKED_REFS = ["gamma_topic_a", "omega_parked_ref"]
# `zorbulate` is a real AC-8 corpus term (_corpus writes it into every doc and module): without
# it scan-prompt matched nothing and emitted no event, so the scan_prompt legs asserted on
# nothing (bug-131).
B8_PROMPT = "please extend alpha_topic_a with omicron_prompt_ref zorbulate"
h.mark_token(SESSION, SCAN_PROMPT, RECALL_PROMPT, B8_PROMPT)   # live-log guard (bug-134)


# ---- the fixture store ------------------------------------------------------------------------


def _corpus(proj: Path) -> Path:
    c = proj / "corpus"
    c.mkdir()
    for i in range(3):
        (c / f"zorb_doc_{i}.md").write_text(
            f"# Zorbulate — notes {i}\n\nzorbulate — the widget pipeline step {i} — flux.\n"
            f"More zorbulate — prose here {i}.\n", encoding="utf-8")
        (c / f"zorb_mod_{i}.py").write_text(
            f'"""zorbulate — module {i} — handles the flux capacitor."""\n\n'
            f"def zorbulate_step_{i}(x):\n    # zorbulate — step {i}\n    return x\n",
            encoding="utf-8")
    return c


def _seed_ring(root: Path) -> None:
    from refmatrix import stm
    s = stm.Stm(root, SESSION)
    for text in SEED_INPUTS:
        s.record("input", text)
    topics = stm.topic_composites(s.focus_graph())
    # Fixture pre-check (not an AC): the seeded ring really has 5 inputs and 2 topics.
    assert s.event_count() == 5, s.event_count()
    assert len(topics) == 2, [t["members"] for t in topics]


@pytest.fixture(scope="module")
def store():
    """The AC-8 store, served by a real daemon for the whole module."""
    import rmx_sandbox
    from refmatrix import daemon as dm
    from refmatrix.store import Store

    root = rmx_sandbox.new_store_root(Path(os.environ["RMX_SANDBOX_ROOT"]))
    s = Store(root)
    s.init()
    s.close()
    proj = root.parent
    r = h.run_rmx(["ingest", str(_corpus(proj))], root=root, timeout=300)
    assert r.returncode == 0, r.stderr
    s = Store(root)
    try:
        with s.with_partition("intuition"):
            for i in range(N_MEMORIES):
                mtype = "feedback" if i < N_DELIVERABLE else "session/digest"
                s.add_memory(name=f"mem_quasar_{i}",
                             content=f"quasar ledger rule {i}: always reconcile — the books",
                             mtype=mtype)
    finally:
        s.close()
    _seed_ring(root)
    d = h.SandboxDaemon(root)
    try:
        res = dm.call(root, "embed", {"kinds": ["memory"], "partition": "intuition"},
                      timeout=600)
        assert res.get("ok"), res
        yield root
    finally:
        d.stop()
        rmx_sandbox.remove_tree(root.parent)


@pytest.fixture(autouse=True)
def _live_logs_untouched():
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


# ---- helpers ----------------------------------------------------------------------------------


def _envelope(prompt: str, session: str = SESSION, event: str = "UserPromptSubmit") -> dict:
    return {"session_id": session, "prompt": prompt, "hook_event_name": event,
            "cwd": "", "transcript_path": ""}


def _new_events(path: Path, before: int) -> list[dict]:
    return h.jsonl(path)[before:]


def _ev_path(root: Path) -> Path:
    return root / "recall-events.jsonl"


def _of_channel(evs: list[dict], channel: str) -> list[dict]:
    return [e for e in evs if e.get("channel") == channel]


def _require_events(evs: list[dict], channel: str, what: str) -> list[dict]:
    got = _of_channel(evs, channel)
    assert got, (f"{what}: no `{channel}` recall event was appended to recall-events.jsonl "
                 f"(R8/R11 emitter missing); new lines: {evs[:3]}")
    return got


def _one_call(evs: list[dict]) -> list[dict]:
    qids = {e.get("query_id") for e in evs}
    seen = [tuple(e.get(k) for k in ("query_id", "stage", "channel", "invocation", "session",
                                     "name")) for e in evs]
    assert len(qids) == 1 and None not in qids, (
        f"events of one call share ONE query_id: {qids}; events (query_id, stage, channel, "
        f"invocation, session, name): {seen}")
    return evs


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run_scan(root: Path, prompt: str = SCAN_PROMPT, **extra):
    cmd = h.generated_cmd(root, "UserPromptSubmit", "scan-prompt")
    return h.run_hook_bytes(cmd, root=root, envelope=_envelope(prompt), **extra)


def _run_prompt_recall(root: Path, prompt: str = RECALL_PROMPT, **extra):
    cmd = h.generated_cmd(root, "UserPromptSubmit", "memory recall --stdin-json")
    extra.setdefault("RMX_PARTITION", "intuition")
    return h.run_hook_bytes(cmd, root=root, envelope=_envelope(prompt), **extra)


def _store_partition(root: Path) -> str:
    from refmatrix import discovery
    return discovery.store_name(root)


# ---- AC-8 ------------------------------------------------------------------------------------


def _check_common(evs: list[dict], *, root: Path, stdout: bytes, channel: str,
                  block_id: str) -> tuple[list[dict], list[dict]]:
    from refmatrix import telemetry
    _one_call(evs)
    retrieved = [e for e in evs if e.get("stage") == "retrieved"]
    delivered = [e for e in evs if e.get("stage") == "delivered"]
    assert retrieved and delivered, (len(retrieved), len(delivered))
    assert hasattr(telemetry, "RECALL_EVENT_FIELDS_V1"), "R10: RECALL_EVENT_FIELDS_V1 not built"
    for e in evs:
        missing = [f for f in telemetry.RECALL_EVENT_FIELDS_V1 if f not in e]
        assert not missing, f"R10: every field is written (null allowed): missing {missing}"
        assert e["v"] == 1 and e["channel"] == channel
        assert e["session"] == SESSION, e
        assert e["cwd"] == str(root.parent) and e["root"] == str(root), (e["cwd"], e["root"])
        assert EVENT_TS.match(e["ts"]), e["ts"]
        assert e["invocation"] == "hook"
        # phase + versioned-injection fields (re-review #s-3)
        assert e["stm_session"] == SESSION
        assert e["stm_events_n"] == len(SEED_INPUTS)
        assert e["focus_topics_n"] == 2
        assert isinstance(e["overlap"], (int, float)) and not isinstance(e["overlap"], bool)
        assert e["arm"] == "fixed" and e["policy"] == "fixed-v0"
        assert e["block_id"] == block_id
        assert e["block_sha"] in (_sha(stdout), _sha(stdout.rstrip(b"\n"))), \
            "block_sha is the sha256 of the block's exact stdout bytes"
    for e in delivered:
        assert e["payload_bytes"] == len(stdout), (e["payload_bytes"], len(stdout))
        off, n = e["offset_bytes"], e["bytes"]
        assert isinstance(off, int) and isinstance(n, int) and off >= 0 and n > 0
        assert off + n <= e["payload_bytes"]
        assert e["name"].encode() in stdout[off:off + n], (
            f"delivered span [{off},{off + n}) does not contain {e['name']!r}: "
            f"{stdout[off:off + n]!r}")
    assert {e["name"] for e in delivered} <= {e["name"] for e in retrieved}
    return retrieved, delivered


def test_ac8_scan_prompt_emits_retrieved_and_delivered_through_the_generated_hook(store):
    """AC-8 (scan_prompt leg): the generated UserPromptSubmit scan-prompt command appends one
    `retrieved` per retrieved item and one `delivered` per emitted item, one query_id shared with
    its query.log row, the envelope's session, byte spans that name each item in the stdout
    BYTES, the project partition and R10a kinds, cwd/root, and the phase fields."""
    root = store
    before_ev = h.line_count(_ev_path(root))
    before_rows = h.line_count(root / "query.log")
    r = _run_scan(root)
    evs = _require_events(_new_events(_ev_path(root), before_ev), "scan_prompt",
                          "AC-8 scan-prompt")
    retrieved, delivered = _check_common(evs, root=root, stdout=r.stdout,
                                         channel="scan_prompt", block_id="scan-prompt")
    part = _store_partition(root)
    for e in evs:
        assert e["kind"] in ("code", "doc", "concept"), e["kind"]
        assert e["partition"] == part, (e["partition"], part)
        assert e["scope"] == "project"
    # Every item line the payload names is a delivered event (one per emitted item).
    text = r.stdout.decode("utf-8")
    named = set(re.findall(r"^  (\S+)  \[(?:code|doc|concept)\]", text, re.M))
    named |= set(re.findall(r"^anchor: (\S+)  \[", text, re.M))
    assert named <= {e["name"] for e in delivered}, named - {e["name"] for e in delivered}
    rows = h.jsonl(root / "query.log")[before_rows:]
    scan_rows = [x for x in rows if x.get("source") == "scan-prompt"]
    assert len(scan_rows) == 1 and scan_rows[0].get("query_id") == evs[0]["query_id"], scan_rows


def test_ac8_prompt_recall_retrieves_10_delivers_3_in_intuition(store):
    """AC-8 (prompt_recall leg): `rmx memory recall --stdin-json` through the generated
    UserPromptSubmit command: exactly 10 `retrieved` and 3 `delivered` (the payload carries 3 of
    10; the 7 `session/digest` rows are retrieved but hook mode keeps them out of the payload),
    every event in partition `intuition`, kind `memory`, the envelope's session, one query_id
    equal to the kind=recall query.log row's."""
    root = store
    before_ev = h.line_count(_ev_path(root))
    before_rows = h.line_count(root / "query.log")
    r = _run_prompt_recall(root)
    evs = _require_events(_new_events(_ev_path(root), before_ev), "prompt_recall",
                          "AC-8 prompt recall")
    retrieved, delivered = _check_common(evs, root=root, stdout=r.stdout,
                                         channel="prompt_recall", block_id="prompt-recall")
    payload = json.loads(r.stdout)
    assert len(payload) == N_DELIVERABLE, payload               # fixture: 3 of 10 carried
    assert len(retrieved) == N_MEMORIES, len(retrieved)
    assert len(delivered) == N_DELIVERABLE, len(delivered)
    assert {e["name"] for e in delivered} == {p["name"] for p in payload}
    for e in evs:
        assert e["partition"] == "intuition", e["partition"]
        assert e["kind"] == "memory" and e["scope"] == "project"
    rows = [x for x in h.jsonl(root / "query.log")[before_rows:] if x.get("kind") == "recall"]
    assert len(rows) == 1 and rows[0].get("query_id") == evs[0]["query_id"], rows


# ---- AC-8d -----------------------------------------------------------------------------------


def test_ac8d_precheck_the_scan_payload_is_multibyte(store):
    """AC-8d pre-check (fixture validity, recorded before GREEN; passes at HEAD by design, not
    counted as RED): the prompt puts a non-ASCII byte into the payload's first line, ahead of
    every item, and the corpus puts >= 3 `—` into the rendered text."""
    out = _run_scan(store).stdout
    first_line = out.split(b"\n", 1)[0]
    assert any(b >= 0x80 for b in first_line), first_line
    assert out.count("—".encode()) >= 3, out[:400]


def test_ac8d_byte_offsets_survive_multibyte_text_before_the_spans(store):
    """AC-8d (scan-prompt leg): a byte >= 0x80 precedes the FIRST delivered span, the multibyte
    excess (bytes minus characters) before the LAST delivered span is >= 6 (three `—`), and
    every span's bytes contain its name -- a character-counted offset misses by >= 6 bytes."""
    root = store
    before_ev = h.line_count(_ev_path(root))
    r = _run_scan(root)
    delivered = [e for e in _require_events(_new_events(_ev_path(root), before_ev),
                                            "scan_prompt", "AC-8d")
                 if e.get("stage") == "delivered"]
    assert delivered, "AC-8d: no delivered scan_prompt events"
    out = r.stdout
    first = min(e["offset_bytes"] for e in delivered)
    last = max(e["offset_bytes"] for e in delivered)
    assert any(b >= 0x80 for b in out[:first]), "guard: no multibyte byte before the first span"
    excess = last - len(out[:last].decode("utf-8", errors="replace"))
    assert excess >= 6, f"multibyte excess before the last span is {excess} (< 6)"
    for e in delivered:
        span = out[e["offset_bytes"]:e["offset_bytes"] + e["bytes"]]
        assert e["name"].encode() in span, (e["name"], span)


# ---- AC-8b -----------------------------------------------------------------------------------


def _stm_dir(root: Path) -> Path:
    return root / "stm"


def _park_call(root: Path, age_s: float = 120.0) -> None:
    from refmatrix import stm
    s = stm.Stm(root, SESSION)
    s.inflight_begin("parked-1", terse="Bash run parked", refs=list(PARKED_REFS))
    p = _stm_dir(root) / f"{SESSION}.inflight.json"
    d = json.loads(p.read_text())
    d["parked-1"]["t"] = time.time() - age_s
    p.write_text(json.dumps(d))


@pytest.fixture(scope="module")
def pristine_stm(store, tmp_path_factory):
    """A copy of the seeded STM dir WITH the 120 s parked call (more than the sweep's 90 s)."""
    root = store
    _park_call(root)
    keep = tmp_path_factory.mktemp("stm-pristine") / "stm"
    shutil.copytree(_stm_dir(root), keep)
    return keep


def _restore_stm(root: Path, pristine: Path) -> None:
    shutil.rmtree(_stm_dir(root))
    shutil.copytree(pristine, _stm_dir(root))


def _input_hook(root: Path, prompt: str):
    cmd = h.generated_cmd(root, "UserPromptSubmit", "focus hook --event input")
    return h.run_hook(cmd, root=root, envelope=_envelope(prompt))


PHASE = ("turn", "stm_events_n", "focus_topics_n", "overlap")


def _phase_of(root: Path, before: int, channel: str) -> dict:
    evs = _require_events(_new_events(_ev_path(root), before), channel, "AC-8b")
    _one_call(evs)
    vals = {(tuple(e.get(k) for k in PHASE), e.get("stm_source")) for e in evs}
    assert len(vals) == 1, f"one call's events disagree on the phase inputs: {vals}"
    (phase, source), = vals
    return {**dict(zip(PHASE, phase)), "stm_source": source}


def _ordering(root: Path, pristine: Path, how: str, reader, prompt: str, channel: str) -> dict:
    from refmatrix import stm
    _restore_stm(root, pristine)
    before = h.line_count(_ev_path(root))
    if how == "i":
        _input_hook(root, prompt)
        reader(root, prompt)
    elif how == "ii":
        reader(root, prompt)
        _input_hook(root, prompt)
    else:
        s = stm.Stm(root, SESSION)
        assert hasattr(s, "snapshot_pre_prompt"), "R9: Stm.snapshot_pre_prompt not built"
        s.snapshot_pre_prompt(prompt)
        if how == "iii":
            reader(root, prompt)
            s.inflight_sweep()
            s.record("input", prompt)
        elif how == "iv":
            s.inflight_sweep()
            reader(root, prompt)
            s.record("input", prompt)
    return _phase_of(root, before, channel)


READERS = {
    "scan_prompt": lambda root, p: _run_scan(root, p),
    "prompt_recall": lambda root, p: _run_prompt_recall(root, p),
}


@pytest.mark.parametrize("channel", ["scan_prompt", "prompt_recall"])
def test_ac8b_every_phase_input_is_order_independent(store, pristine_stm, channel):
    """AC-8b: the same envelope run four ways against copies of the seeded STM state ((i) input
    hook before the reader, (ii) after, (iii) only the snapshot first, (iv) snapshot + sweep
    first) logs identical turn (5), stm_events_n (the seeded count, the swept call EXCLUDED),
    focus_topics_n and overlap, equal to (ii)'s; stm_source is `snapshot` in (i), (iii), (iv)
    and `live` in (ii)."""
    root = store
    reader = READERS[channel]
    got = {how: _ordering(root, pristine_stm, how, reader, B8_PROMPT, channel)
           for how in ("ii", "i", "iii", "iv")}
    base = {k: got["ii"][k] for k in PHASE}
    assert base["turn"] == len(SEED_INPUTS) and base["stm_events_n"] == len(SEED_INPUTS), base
    for how in ("i", "iii", "iv"):
        assert {k: got[how][k] for k in PHASE} == base, (how, got[how], base)
        assert got[how]["stm_source"] == "snapshot", (how, got[how])
    assert got["ii"]["stm_source"] == "live"


@pytest.mark.parametrize("channel", ["scan_prompt", "prompt_recall"])
def test_ac8b_an_older_identical_prompt_outside_the_window_is_not_matched(
        store, pristine_stm, channel):
    """AC-8b: an earlier prompt with IDENTICAL text whose pre.json `wall` is
    PRE_PROMPT_SKEW_S + 1 s old is not matched (stm_source `live`) and is counted in `turn`."""
    from refmatrix import stm
    root = store
    _restore_stm(root, pristine_stm)
    _input_hook(root, B8_PROMPT)                       # the earlier, recorded, identical prompt
    before = h.line_count(_ev_path(root))
    assert hasattr(stm, "PRE_PROMPT_SKEW_S"), "R9: stm.PRE_PROMPT_SKEW_S not built"
    pre = _stm_dir(root) / f"{SESSION}.pre.json"
    assert pre.is_file(), "R9: the input hook wrote no <session>.pre.json snapshot"
    d = json.loads(pre.read_text())
    d["wall"] = time.time() - (stm.PRE_PROMPT_SKEW_S + 1)
    pre.write_text(json.dumps(d))
    READERS[channel](root, B8_PROMPT)
    ph = _phase_of(root, before, channel)
    assert ph["stm_source"] == "live", ph
    assert ph["turn"] == len(SEED_INPUTS) + 1, ph


@pytest.mark.parametrize("channel", ["scan_prompt", "prompt_recall"])
def test_ac8b_ambient_prompt_snapshots_too(store, pristine_stm, channel):
    """AC-8b ambient leg: an ambient prompt (`<task-notification …>`) with the same parked call:
    (i) and (ii) log identical stm_events_n and focus_topics_n, (i) with stm_source=snapshot;
    the ring gains the swept event but no input event."""
    from refmatrix import stm
    root = store
    # `zorbulate` = a real corpus term, so the scan_prompt leg has an event to assert on.
    prompt = "<task-notification>agent alpha_topic_a zorbulate finished</task-notification>"
    got = {}
    for how in ("ii", "i"):
        _restore_stm(root, pristine_stm)
        ring = _stm_dir(root) / f"{SESSION}.jsonl"
        n0 = h.line_count(ring)
        before = h.line_count(_ev_path(root))
        if how == "i":
            _input_hook(root, prompt)
            READERS[channel](root, prompt)
        else:
            READERS[channel](root, prompt)
            _input_hook(root, prompt)
        got[how] = _phase_of(root, before, channel)
        added = h.jsonl(ring)[n0:]
        assert [e.get("kind") for e in added if e.get("abandoned")] == ["tool"], added
        assert not [e for e in added if e.get("kind") == "input"], added
    assert got["i"]["stm_events_n"] == got["ii"]["stm_events_n"], got
    assert got["i"]["focus_topics_n"] == got["ii"]["focus_topics_n"], got
    assert got["i"]["stm_source"] == "snapshot", got


def test_ac8b_precheck_the_input_hook_changes_ring_and_topic(store, pristine_stm):
    """AC-8b pre-check (recorded before GREEN; passes at HEAD by design -- it proves the fixture
    is not vacuous): running the input hook on the seeded copy changes the ring count by 2 (one
    swept, one input) and the member set of the active topic."""
    from refmatrix import stm
    root = store
    _restore_stm(root, pristine_stm)
    s = stm.Stm(root, SESSION)
    n0 = s.event_count()
    members0 = sorted(sorted(t["members"]) for t in stm.topic_composites(s.focus_graph()))
    _input_hook(root, B8_PROMPT)
    s = stm.Stm(root, SESSION)
    members1 = sorted(sorted(t["members"]) for t in stm.topic_composites(s.focus_graph()))
    assert s.event_count() - n0 == 2, (n0, s.event_count())
    assert members1 != members0, members0


# ---- AC-8c -----------------------------------------------------------------------------------


def _check_channel(evs: list[dict], channel: str, *, kind_ok, partition_ok) -> None:
    got = _require_events(evs, channel, f"AC-8c {channel}")
    _one_call(got)
    ret = [e for e in got if e["stage"] == "retrieved"]
    dlv = [e for e in got if e["stage"] == "delivered"]
    assert ret and dlv and len(dlv) <= len(ret), (len(ret), len(dlv))
    for e in got:
        assert kind_ok(e["kind"]), e["kind"]
        assert partition_ok(e["partition"]), e["partition"]


def test_ac8c_session_start_channel_through_the_generated_sessionstart_recall(store):
    """AC-8c session_start: the GENERATED SessionStart recall command, fed a SessionStart
    envelope, appends `session_start` events (retrieved + delivered, kind memory, partition
    intuition, one query_id)."""
    root = store
    cmd = h.generated_cmd(root, "SessionStart", "memory recall --session-start")
    before = h.line_count(_ev_path(root))
    h.run_hook(cmd, root=root, envelope={"session_id": SESSION, "source": "startup",
                                         "hook_event_name": "SessionStart"},
               RMX_PARTITION="intuition")
    _check_channel(_new_events(_ev_path(root), before), "session_start",
                   kind_ok=lambda k: k == "memory", partition_ok=lambda p: p == "intuition")


def test_ac8c_precompact_channel_and_it_is_the_only_generated_recent_recall(store):
    """AC-8c precompact: the GENERATED PreCompact recall command (`--recent`, hook invocation)
    appends `precompact` events; and a scan of the generated config shows it is the ONLY
    generated command combining `memory recall` with `--recent` (R11's recall_channel rule 3)."""
    root = store
    cmd = h.generated_cmd(root, "PreCompact", "memory recall --recent")
    before = h.line_count(_ev_path(root))
    h.run_hook(cmd, root=root, envelope={"session_id": SESSION, "trigger": "auto",
                                         "hook_event_name": "PreCompact"},
               RMX_PARTITION="intuition")
    _check_channel(_new_events(_ev_path(root), before), "precompact",
                   kind_ok=lambda k: k == "memory", partition_ok=lambda p: p == "intuition")
    recents = [(ev, c) for ev, _m, c in h.hook_entries(root)
               if "memory recall" in c and "--recent" in c]
    assert recents == [("PreCompact", cmd)], recents


@pytest.mark.parametrize("argv", [["memory", "recall", "quasar ledger", "--json"],
                                  ["memory", "recall", "--recent", "--since", "30d", "--json"]],
                         ids=["query", "recent"])
def test_ac8c_agent_recall_is_channel_recall_not_precompact(store, argv):
    """AC-8c recall: an agent (`CLAUDECODE=1`) `rmx memory recall <q>` AND an agent
    `rmx memory recall --recent` both log channel `recall` with invocation `agent` -- never
    `precompact` (the `--recent` rule needs invocation == hook)."""
    root = store
    before = h.line_count(_ev_path(root))
    h.run_rmx(argv, root=root, CLAUDECODE="1", RMX_PARTITION="intuition")
    evs = _new_events(_ev_path(root), before)
    assert not _of_channel(evs, "precompact"), "an agent --recent recall logged `precompact`"
    _check_channel(evs, "recall", kind_ok=lambda k: k == "memory",
                   partition_ok=lambda p: p == "intuition")
    assert {e["invocation"] for e in evs} == {"agent"}


def test_ac8c_context_channel_through_mcp_and_cli(store):
    """AC-8c context: an MCP `rmx_context` call through the real stdio server and a CLI
    `rmx context` call each append `context` events (kind by R10a, project partition); the MCP
    call's query_id equals its `context-mcp` query.log row's.

    Neither leg is given a session, so both resolve NONE (R9: null, never a guess) -- asserted,
    because the CLI child's owner lookup walks the RUNNER's process chain: under Claude Code it
    finds the real Claude pid, and a pointer for that pid in the sandbox `by-pid/` (written by
    an AC-8b input hook in this module before `_fresh_pointer_dir` reset it per test, bug-133)
    gave this leg `sess-emit` -- the one-off two-query_id failure of the 2026-10-16 GREEN run
    was this leak, now named instead of surfacing as a query_id mismatch."""
    root = store
    part = _store_partition(root)
    before = h.line_count(_ev_path(root))
    before_rows = h.line_count(root / "query.log")
    with h.McpServer(root) as m:
        out = m.tool("rmx_context", {"ref": "zorbulate"})
        assert not out["isError"], out["text"][:500]
    evs = _new_events(_ev_path(root), before)
    _check_channel(evs, "context", kind_ok=lambda k: k in ("code", "doc", "concept", "memory"),
                   partition_ok=lambda p: bool(p))
    rows = [x for x in h.jsonl(root / "query.log")[before_rows:]
            if x.get("source") == "context-mcp"]
    assert len(rows) == 1 and rows[0].get("query_id") == evs[0]["query_id"], rows
    assert {e["invocation"] for e in evs} == {"mcp"}
    assert {e["session"] for e in evs} == {None}, {e["session"] for e in evs}
    before = h.line_count(_ev_path(root))
    h.run_rmx(["context", "zorbulate"], root=root)
    cli = _new_events(_ev_path(root), before)
    assert {e.get("session") for e in cli} <= {None}, (
        "isolation: the CLI leg resolved a session from a pointer it did not write "
        f"(the runner's Claude pid): {sorted({str(e.get('session')) for e in cli})}")
    _check_channel(cli, "context",
                   kind_ok=lambda k: k in ("code", "doc", "concept", "memory"),
                   partition_ok=lambda p: p == part or p == "intuition")


# ---- the agent `recall` channel's TABLE output (round 13 #b3; ch-bsd r2 b1/s1/m1) ---------

LONG_NAME = "feedback_" + "very_long_memory_name_segment_" * 3 + "end"      # > 80 columns
TABLE_NAMES = ("name", "id", "rank", "score", "1", LONG_NAME)            # r2 #m1 + #s1 (M3c)
SUBJECT = "subject_zebra_rules"
# r3 #s1: one memory whose CONTENT spans several lines -- a table cell that is not made one
# line prints its row over several lines, so later rows can no longer be found by index.
MULTILINE = "multiline_zebra_note"
MULTILINE_BODY = "zebrafish ledger multi-line rule\nsecond line of the body\nthird line"
# r3 #m1: names rich would rewrite (emoji code, trailing backslash, markup-like brackets).
ODD_NAMES = ("fix:smile:now", "trail\\", "[bold]loud")


@pytest.fixture(scope="module")
def table_store():
    """A second store for the table legs: memories in `intuition` whose names collide with
    the table's header and rank cells (`name`, `id`, `rank`, `score`, `1`, r2 #m1) and one
    longer than 80 columns (r2 #s1 M3c: a terminal-width fit cuts it to `…`), all filed under
    one subject (the `--subject` table route, r2 #b1), embedded, served by a real daemon."""
    import rmx_sandbox
    from refmatrix import daemon as dm
    from refmatrix.store import Store
    root = rmx_sandbox.new_store_root(Path(os.environ["RMX_SANDBOX_ROOT"]))
    s = Store(root)
    s.init()
    try:
        with s.with_partition("intuition"):
            subj = s.add_memory(name=SUBJECT, content="zebra rules subject", mtype="subject")
            for i, nm in enumerate(TABLE_NAMES):
                leaf = s.add_memory(name=nm, content=f"zebrafish ledger rule {i}: tally",
                                    mtype="feedback")
                s.link_part_of(leaf, subj)
            leaf = s.add_memory(name=MULTILINE, content=MULTILINE_BODY, mtype="feedback")
            s.link_part_of(leaf, subj)
    finally:
        s.close()
    d = h.SandboxDaemon(root)
    try:
        res = dm.call(root, "embed", {"kinds": ["memory"], "partition": "intuition"},
                      timeout=600)
        assert res.get("ok"), res
        yield root
    finally:
        d.stop()
        rmx_sandbox.remove_tree(root.parent)


def _agent_table(root: Path, argv: list[str], **extra):
    import subprocess
    env = h.rmx_env(root, CLAUDECODE="1", RMX_PARTITION="intuition", **extra)
    return subprocess.run([h.rmx_bin(), *argv], env=env, cwd=str(root.parent),
                          capture_output=True, timeout=180)


def _row_line(out: bytes, off: int) -> bytes:
    start = out.rfind(b"\n", 0, off) + 1
    end = out.find(b"\n", off)
    return out[start:end if end >= 0 else len(out)]


def _check_table_delivery(root: Path, r, before: int, what: str) -> list[dict]:
    """Round 13 #b3 for one TABLE call: delivered events whose byte spans sit on the item's OWN
    row's name cell (after the header rule, `│ ` before, padding after, the row's id cell on
    the same line -- r2 #m1), with `payload_bytes` = len(stdout) and `block_sha` = its sha256;
    every row the table printed is delivered (no `delivered_unspanned`)."""
    out = r.stdout
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0, err[-800:]
    assert not out.lstrip().startswith(b"["), f"fixture: {what} must be the TABLE output"
    assert "delivered_unspanned" not in err, f"{what}: items printed but not delivered: {err}"
    evs = _require_events(_new_events(_ev_path(root), before), "recall", what)
    _one_call(evs)
    delivered = [e for e in evs if e["stage"] == "delivered"]
    assert delivered, f"{what}: the table printed rows but no `delivered` event was emitted"
    body = out.find("┡".encode())
    assert body >= 0, f"fixture: no header rule in {out[:300]!r}"
    for e in delivered:
        assert e["invocation"] == "agent" and e["block_id"] == "recall", e
        assert e["payload_bytes"] == len(out), (
            f"{what}: delivered payload_bytes {e['payload_bytes']!r} != {len(out)} stdout bytes")
        assert e["block_sha"] in (_sha(out), _sha(out.rstrip(b"\n"))), (
            f"{what}: delivered block_sha {e['block_sha']!r} is not the stdout's sha256")
        off, n = e["offset_bytes"], e["bytes"]
        assert isinstance(off, int) and isinstance(n, int) and off >= 0 and n > 0, (off, n)
        name = e["name"].encode()
        assert out[off:off + n] == name, (
            f"{what}: span [{off},{off + n}) is {out[off:off + n]!r}, not {name!r}")
        line = _row_line(out, off)
        assert off > body, f"{what}: {e['name']!r} spanned in the HEADER: {line!r}"
        assert out[off - len("│ ".encode()):off] == "│ ".encode() and out[off + n:off + n + 1] \
            == b" ", f"{what}: {e['name']!r} spanned outside a name cell: {line!r}"
        assert f"│ {e['entity_id']} ".encode() in line, (
            f"{what}: {e['name']!r} spanned on another row (id {e['entity_id']}): {line!r}")
    return evs


@pytest.mark.parametrize("argv", [["memory", "recall", "quasar ledger"],
                                  ["memory", "recall", "--recent", "--k", "5"]],
                         ids=["query", "recent"])
def test_b3_agent_recall_default_table_output_delivers_with_byte_spans(store, argv):
    """Round 13 #b3 (R10/R11, the agent `recall` channel): `rmx memory recall <q>` AND
    `rmx memory recall --recent --k 5` (ch-bsd r2 b1: the sibling table route) in the DEFAULT
    table output deliver every printed memory with byte spans over the stdout BYTES (the box
    characters are multibyte), payload_bytes and block_sha; stderr never says
    `delivered_unspanned`. RED at HEAD: query leg -- null spans (r1); recent leg -- 0
    delivered and `delivered_unspanned=5` (r2 b1-r2)."""
    root = store
    before = h.line_count(_ev_path(root))
    r = _agent_table(root, argv)
    assert any(b >= 0x80 for b in r.stdout), "fixture: the table carries no multibyte byte"
    evs = _check_table_delivery(root, r, before, " ".join(argv[2:]))
    retrieved = [e for e in evs if e["stage"] == "retrieved"]
    printed = {e["name"] for e in retrieved if e["name"].encode() in r.stdout}
    assert printed and printed <= {e["name"] for e in evs if e["stage"] == "delivered"}, printed


@pytest.mark.parametrize("argv", [["memory", "recall", "zebrafish ledger", "--k", "10"],
                                  ["memory", "recall", "--recent", "--k", "10"],
                                  ["memory", "recall", "--subject", SUBJECT, "--k", "10"]],
                         ids=["query", "recent", "subject"])
def test_r2_table_spans_land_on_each_items_own_name_cell(table_store, argv):
    """ch-bsd r2 #m1 + #b1 + #s1 (M3c): memories named `name`, `id`, `rank`, `score` and `1`
    each get their span on their OWN row's name cell -- never the header (`┃ rank ┃ score ┃ id
    ┃ name ┃`) or a rank/id cell -- and a name longer than 80 columns is printed whole (no
    `…`) and spanned, on the query, recent and subject table routes. RED at HEAD: query --
    `name`/`score`/`id`/`rank` span the header; recent/subject -- no delivered events."""
    root = table_store
    before = h.line_count(_ev_path(root))
    r = _agent_table(root, argv)
    evs = _check_table_delivery(root, r, before, " ".join(argv[2:]))
    got = {e["name"] for e in evs if e["stage"] == "delivered"}
    want = set(TABLE_NAMES) | {MULTILINE}
    assert want <= got, f"not delivered: {want - got}"
    assert LONG_NAME.encode() in r.stdout, "M3c: the long name was cut (natural width lost)"


_GMD_HEADING = re.compile(rb"^## (.+) \{#.+\}$", re.M)


@pytest.mark.parametrize("argv", [["memory", "recall", "zebrafish ledger", "--k", "20", "--gmd"],
                                  ["memory", "recall", "--recent", "--k", "20", "--gmd"],
                                  ["memory", "recall", "--subject", SUBJECT, "--k", "20",
                                   "--gmd"]],
                         ids=["query", "recent", "subject"])
def test_r3_gmd_recall_spans_each_name_on_its_own_heading(table_store, argv):
    """ch-bsd r3 #s1: `rmx memory recall --gmd` (query, --recent, --subject) delivers every
    memory with a span that is EXACTLY its name on its OWN `## <name> {#<name>}` heading --
    starting right after `## `, followed by ` {#` -- with payload_bytes = len(stdout) and
    block_sha its sha256; every heading the document prints is delivered, nothing is
    `delivered_unspanned`. Kills: GMD spans None (0 delivered), GMD spans 1 byte off."""
    root = table_store
    before = h.line_count(_ev_path(root))
    r = _agent_table(root, argv)
    out, err = r.stdout, r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0 and out.startswith(b"---"), (out[:200], err[-600:])
    assert "delivered_unspanned" not in err, f"--gmd: items printed but not delivered: {err}"
    evs = _require_events(_new_events(_ev_path(root), before), "recall", "r3 --gmd")
    _one_call(evs)
    delivered = [e for e in evs if e["stage"] == "delivered"]
    for e in delivered:
        assert e["payload_bytes"] == len(out), (e["payload_bytes"], len(out))
        assert e["block_sha"] in (_sha(out), _sha(out.rstrip(b"\n"))), e["block_sha"]
        off, n = e["offset_bytes"], e["bytes"]
        name = e["name"].encode()
        assert isinstance(off, int) and out[off:off + n] == name, (
            f"--gmd: span [{off},{off + n}) is {out[off:off + n]!r}, not {name!r}")
        line_start = out.rfind(b"\n", 0, off) + 1
        assert out[line_start:off] == b"## " and out[off + n:off + n + 3] == b" {#", (
            f"--gmd: {e['name']!r} not spanned on its own heading: "
            f"{_row_line(out, off)!r}")
    headings = {m.decode() for m in _GMD_HEADING.findall(out)}
    got = {e["name"] for e in delivered}
    assert headings and headings <= got, f"--gmd: headings not delivered: {headings - got}"
    assert set(TABLE_NAMES) | {MULTILINE} <= got, set(TABLE_NAMES) | {MULTILINE} - got


@pytest.fixture(scope="module")
def odd_store():
    """r3 #m1: memories whose NAMES rich would rewrite as markup or emoji, embedded, served."""
    import rmx_sandbox
    from refmatrix import daemon as dm
    from refmatrix.store import Store
    root = rmx_sandbox.new_store_root(Path(os.environ["RMX_SANDBOX_ROOT"]))
    s = Store(root)
    s.init()
    try:
        with s.with_partition("intuition"):
            for i, nm in enumerate(ODD_NAMES):
                s.add_memory(name=nm, content=f"walrus ledger rule {i}: tally", mtype="feedback")
    finally:
        s.close()
    d = h.SandboxDaemon(root)
    try:
        res = dm.call(root, "embed", {"kinds": ["memory"], "partition": "intuition"},
                      timeout=600)
        assert res.get("ok"), res
        yield root
    finally:
        d.stop()
        rmx_sandbox.remove_tree(root.parent)


@pytest.mark.parametrize("argv", [["memory", "recall", "walrus ledger", "--k", "10"],
                                  ["memory", "recall", "--recent", "--k", "10"]],
                         ids=["query", "recent"])
def test_r3_table_prints_names_verbatim_and_spans_them_exactly(odd_store, argv):
    """ch-bsd r3 #m1: a memory named `fix:smile:now`, `trail\\` or `[bold]loud` prints in the
    table VERBATIM (no emoji, no doubled backslash, no markup) and its span is exactly the
    name, ending at the cell's padding (a prefix match is not a span). RED at HEAD:
    `fix:smile:now` prints as an emoji (unspanned), `trail\\` prints `trail\\\\`."""
    root = odd_store
    before = h.line_count(_ev_path(root))
    r = _agent_table(root, argv)
    for nm in ODD_NAMES:
        assert f"│ {nm} ".encode() in r.stdout, (
            f"r3 #m1: {nm!r} not printed verbatim in its cell:\n{r.stdout.decode()[:1500]}")
    evs = _check_table_delivery(root, r, before, " ".join(argv[2:]))
    got = {e["name"] for e in evs if e["stage"] == "delivered"}
    assert set(ODD_NAMES) <= got, set(ODD_NAMES) - got


def test_r3_recent_table_labels_global_rows(store, global_daemon):
    """ch-bsd r3 #m2: `--recent --scope both` prints a GLOBAL row with its `[global]` label
    (the one table path owns the label, not the query caller), and its delivered event
    (global file) spans exactly its name on that row. RED at HEAD: the recent cells carry the
    bare name. (`--subject … --scope both` is not a leg: `verbs.memory_recall` asks the global
    store with no query and `recent=False` in subject mode, so it returns no global rows --
    read at HEAD a6c5634+; the label lives in the one table path either way.)"""
    root, groot = store, global_daemon
    before_g = h.line_count(_ev_path(groot))
    r = _agent_table(root, ["memory", "recall", "--recent", "--k", "20", "--scope", "both"])
    out = r.stdout.decode("utf-8")
    lines = [ln for ln in out.splitlines() if "reference_quasar_global" in ln]
    assert lines, f"fixture: no global row in the table: {out[:800]} {r.stderr[-400:]!r}"
    assert all("reference_quasar_global [global]" in ln for ln in lines), (
        f"r3 #m2: the global row has no [global] label: {lines}")
    gev = [e for e in _new_events(_ev_path(groot), before_g)
           if e.get("stage") == "delivered" and e.get("name") == "reference_quasar_global"]
    assert len(gev) == 1 and gev[0]["scope"] == "global", gev
    off, n = gev[0]["offset_bytes"], gev[0]["bytes"]
    assert r.stdout[off:off + n] == b"reference_quasar_global", r.stdout[off:off + n]


def test_r2_global_table_row_is_labelled_global(store, global_daemon):
    """ch-bsd r2 #s1 (M3b): a GLOBAL memory in the agent's table recall prints with its
    `[global]` label (rich read a bare `[global]` as markup and dropped it, so the row printed
    as a project one -- 21.1 r1 #b3), and its delivered event is scope=global in the global
    file with its span on that row. Kills the unescaped-`[global]` mutation."""
    root, groot = store, global_daemon
    before_g = h.line_count(_ev_path(groot))
    r = _agent_table(root, ["memory", "recall", "quasar ledger reconcile", "--k", "20",
                                  "--scope", "both"])
    out = r.stdout.decode("utf-8")
    lines = [ln for ln in out.splitlines() if "reference_quasar_global" in ln]
    assert lines, f"fixture: no global row in the table: {out[:800]} {r.stderr[-400:]!r}"
    assert all("[global]" in ln for ln in lines), (
        f"M3b: the global row lost its [global] label: {lines}")
    gev = [e for e in _new_events(_ev_path(groot), before_g)
           if e.get("stage") == "delivered" and e.get("name") == "reference_quasar_global"]
    assert len(gev) == 1 and gev[0]["scope"] == "global", gev
    span = r.stdout[gev[0]["offset_bytes"]:gev[0]["offset_bytes"] + gev[0]["bytes"]]
    assert span == b"reference_quasar_global", span


def test_r2_unspanned_delivered_items_are_counted_never_written(store, capsys):
    """ch-bsd r2 #s1 (M8), the `call_events` backstop (R10: a delivered event IS a span): an
    item handed as delivered without a span is NOT written as `delivered` (no null-offset
    events) and is counted on stderr (`delivered_unspanned=<n>`); a spanned sibling is
    written. Kills the mutation that writes unspanned items again."""
    from refmatrix import telemetry
    root = store
    payload = b"| mem_spanned_x |"
    spanned = {"name": "mem_spanned_x", "entity_id": 901, "catalog_kind": "memory",
               "mtype": "feedback", "scope": "project", "partition": "intuition", "rank": 1,
               "offset_bytes": 2, "bytes": len("mem_spanned_x")}
    unspanned = {**spanned, "name": "mem_unspanned_y", "entity_id": 902, "rank": 2,
                 "offset_bytes": None, "bytes": None}
    before = h.line_count(_ev_path(root))
    telemetry.emit_call(root, channel="recall", invocation="agent", session=None,
                        query_id="e" * 32, retrieved=[spanned, unspanned],
                        delivered=[spanned, unspanned], payload=payload, block_id="recall")
    evs = _new_events(_ev_path(root), before)
    dl = [e for e in evs if e["stage"] == "delivered"]
    assert [e["name"] for e in dl] == ["mem_spanned_x"], dl
    assert all(e["offset_bytes"] is not None for e in evs if e["stage"] == "delivered")
    assert "delivered_unspanned=1" in capsys.readouterr().err


def test_r2_counting_stream_close_never_flushes_or_closes_the_wrapped_stream():
    """ch-bsd r2 #s1 (M7, plan-9 r5 #m-11): `CountingStream.close()` -- called by `io.IOBase`'s
    finalizer when `cli_entry` drops the proxy -- closes the PROXY only. Flushing the wrapped
    `sys.__stdout__` there printed a SECOND "Exception ignored ... BrokenPipeError" naming
    `telemetry.py` on a closed consumer. Deterministic leg: a wrapped stream whose flush
    raises BrokenPipeError is neither flushed nor closed by close() or by finalization."""
    import gc
    from refmatrix import telemetry

    class Inner:
        flushed = closed = 0

        def write(self, s):
            return len(s)

        def flush(self):
            Inner.flushed += 1
            raise BrokenPipeError(32, "Broken pipe")

        def close(self):
            Inner.closed += 1

    p = telemetry.CountingStream(Inner())
    p.write("x" * 10)
    try:
        p.close()
    except BrokenPipeError as e:
        raise AssertionError(f"M7: close() flushed the wrapped stream and raised {e!r}")
    assert p.closed
    q = telemetry.CountingStream(Inner())
    del q
    gc.collect()                    # IOBase's finalizer calls close(); an error there is ignored
    assert (Inner.flushed, Inner.closed) == (0, 0), (
        f"M7: closing/finalizing the proxy flushed the wrapped stream {Inner.flushed}x and "
        f"closed it {Inner.closed}x")


def test_r2_closed_pipe_reports_the_broken_pipe_once_never_from_telemetry(store):
    """ch-bsd r2 #s1 (M7) end to end: `rmx telemetry --agent-usage` into a pipe whose reader
    closed before the first write reports the broken pipe exactly ONCE (the interpreter's own
    stdout line) and never in a traceback naming `telemetry.py`. (Regression guard: on
    Python 3.14 this leg alone does not kill the close()-flushes mutation -- the wrapped
    buffer is already drained when the proxy is finalized; the unit leg above does.)"""
    import subprocess
    env = h.rmx_env(store, CLAUDECODE="1", RMX_PARTITION="intuition")
    r = subprocess.run(["/bin/bash", "-c", "rmx telemetry --agent-usage | (exec 0<&-; sleep 0.5)"],
                       env=env, cwd=str(store.parent), capture_output=True, text=True,
                       timeout=180)
    err = r.stderr
    assert "telemetry.py" not in err, f"a traceback names telemetry.py:\n{err[-2000:]}"
    n = err.count("Traceback (most recent call last)") + err.count("Exception ignored")
    assert n == 1, f"the broken pipe was reported {n} times (expected once):\n{err[-2000:]}"


# ---- AC-10 -----------------------------------------------------------------------------------


@pytest.fixture
def global_daemon(store):
    """The SANDBOX global store (`$RMX_HOME`, never the live `~/.refmatrix`) holding one
    behaviour memory, served by its own real daemon for the leg."""
    from refmatrix import hub
    from refmatrix.store import Store
    groot = h.global_root()
    assert str(groot).startswith(os.environ["RMX_SANDBOX_ROOT"]), groot
    s = Store(groot)
    try:
        with s.with_partition(hub.GLOBAL_PARTITION):
            if not any(r.get("name") == "reference_quasar_global"
                       for r in s.recent_memories(since_seconds=None, limit=100)):
                s.add_memory(name="reference_quasar_global",
                             content="global rule: quasar ledger reconcile weekly",
                             mtype="reference")
    finally:
        s.close()
    d = h.SandboxDaemon(groot, RMX_PARTITION=hub.GLOBAL_PARTITION)
    try:
        yield groot
    finally:
        d.stop()


def test_ac10_global_hit_goes_to_the_global_file_project_hit_to_the_project_file(
        store, global_daemon):
    """AC-10: a recall returning one project and one global memory appends the global hit to the
    GLOBAL root's recall-events.jsonl with scope=global and `name` set, and the project hit to
    the project file -- never the other way round."""
    root, groot = store, global_daemon
    before_p = h.line_count(_ev_path(root))
    before_g = h.line_count(_ev_path(groot))
    r = _run_prompt_recall(root, "quasar ledger reconcile")
    payload = json.loads(r.stdout or b"[]")
    assert any(p.get("scope") == "global" for p in payload), \
        f"fixture: the recall must return a global hit: {payload} {r.stderr[-400:]!r}"
    gev = _new_events(_ev_path(groot), before_g)
    pev = _new_events(_ev_path(root), before_p)
    assert [e for e in gev if e.get("name") == "reference_quasar_global"], \
        "AC-10: the global hit has no event in the GLOBAL recall-events.jsonl"
    for e in gev:
        assert e["scope"] == "global" and e["name"], e
    assert pev and all(e["scope"] == "project" for e in pev), pev[:2]
    assert not [e for e in pev if e.get("name") == "reference_quasar_global"], \
        "a global hit was written to the PROJECT file"


# ---- AC-12 -----------------------------------------------------------------------------------

R10A = [
    ("code", None, "code"), ("code", "anything", "code"),
    ("doc", None, "doc"), ("doc", "x", "doc"),
    ("concept", None, "concept"), ("concept", "y", "concept"),
    ("memory", "subject", "subject"), ("memory", "session", "session"),
    ("memory", "feedback", "memory"), ("memory", None, "memory"),
    ("memory", "session/digest", "memory"),
]


@pytest.mark.parametrize("entity_kind,mtype,want", R10A)
def test_ac12_event_kind_maps_every_table_row(entity_kind, mtype, want):
    """AC-12: telemetry.event_kind returns R10a's value for every row of its table."""
    from refmatrix import telemetry
    assert hasattr(telemetry, "event_kind"), "R10a: telemetry.event_kind not built"
    assert telemetry.event_kind(entity_kind, mtype) == want


@pytest.mark.parametrize("entity_kind", ["function", "class", "session", "", "weird"])
def test_ac12_unknown_catalog_kind_maps_to_none(entity_kind):
    """AC-12: an unknown catalog kind maps to None (no event for that item), never copied raw."""
    from refmatrix import telemetry
    assert hasattr(telemetry, "event_kind"), "R10a: telemetry.event_kind not built"
    assert telemetry.event_kind(entity_kind, None) is None


def test_ac12_every_kind_in_the_ac8_corpus_maps(store):
    """AC-12: after ingesting AC-8's corpus, every distinct (entity kind, memory mtype) pair the
    catalog holds maps to a non-None event kind, so a new catalog kind fails HERE."""
    import subprocess
    import sys
    from refmatrix import telemetry
    root = store
    code = ("import json,sys;from pathlib import Path;from refmatrix.store import Store\n"
            "s=Store(Path(sys.argv[1]),read_only=True)\n"
            "rows=s._connect().execute(\"SELECT DISTINCT e.kind, mc.mtype FROM entities e "
            "LEFT JOIN memory_content mc ON mc.entity_id = e.id\").fetchall()\n"
            "s.close();print(json.dumps([list(r) for r in rows]))")
    from refmatrix import daemon as dm
    dm.call(root, "snapshot", {"force": True}, timeout=120)
    p = subprocess.run([sys.executable, "-c", code, str(root)], capture_output=True, text=True,
                       env=h.rmx_env(root), timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    pairs = [tuple(x) for x in json.loads(p.stdout.strip().splitlines()[-1])]
    kinds = {k for k, _ in pairs}
    assert {"code", "doc", "concept", "memory"} <= kinds, pairs    # fixture: the corpus is real
    assert hasattr(telemetry, "event_kind"), "R10a: telemetry.event_kind not built"
    unmapped = [pr for pr in pairs if telemetry.event_kind(*pr) is None]
    assert not unmapped, f"catalog (kind, mtype) pairs R10a does not map: {unmapped}"
