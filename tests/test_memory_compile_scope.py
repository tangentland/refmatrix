"""Task 26.6 (plan-26, building plan-19's 19.4) — RED on the production path.

Every behavioural test here drives the REAL `rmx` CLI (click, in-process) or the REAL
`rmx_memory_compile` verb against a REAL spawned daemon (`spawn_daemon_subprocess`) over a
throwaway store under a short `mkdtemp()` root, inside task 23.0's sandbox (tmp `HOME`, the
conftest's live-socket refusal). No mock of compile, of `apply_plan` or of the bridge. The
one in-process test (single-flight) drives the registered `OPS["memory_compile"]` handler on a
`Daemon` object over a tmp store, because holding a SPAWNED daemon's writer lock from a test
is impossible; it is the same handler the socket dispatches.

What is NOT here, and where it went (task-26.6 `#plan-19-delta`):
- 19.4 R1's tick registration and AC-2 (armed/unarmed days, `runs.jsonl`, `hub maintain arm`)
  land with task 17.2;
- 19.4 R3 (compile regenerates `MEMORY.md`), AC-3 and the marker-ON leg of AC-6 need 26.7's
  subject render (task-26.6 header: "R3 and AC-3 of 19.4 also need task-26.7");
- 19.4 AC-4's recall leg is 25.1 AC-6's (r2 s1).

Seeds are written through `Store` BEFORE the daemon opens the (throwaway) store, with
deterministic vectors — the same technique as tests/test_memory_compile.py and
tests/test_brief_real_daemon.py — because the sandbox has no embedding model.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery, handoff, memory_index, verbs
from refmatrix.store import Store

if importlib.util.find_spec("lance") is None:
    pytest.skip("lance not installed", allow_module_level=True)

DIM = 8
# Small-corpus knobs: the defaults (`--hub-df-frac 0.10`, adaptive threshold) are tuned for
# hundreds of memories; on eight they would drop every concept as a hub.
P = ["--threshold", "0.5", "--k", "4", "--min-size", "2", "--hub-df-frac", "0.5",
     "--bridge-min", "0.35"]
VP = {"threshold": 0.5, "k": 4, "min_size": 2, "hub_df_frac": 0.5, "bridge_min": 0.35}

GMD = ('---\ngmd: "0.1"\nid: {id}\ntitle: "{id}"\ntags: [project]\nmetadata:\n'
       '  type: {t}\n---\n# {id} {{#root}}\n\n{body}\n')


def _unit(*components: float) -> np.ndarray:
    v = np.zeros(DIM, dtype="float32")
    for i, c in enumerate(components):
        v[i] = c
    return v / (np.linalg.norm(v) or 1.0)


def _cid(names) -> str:
    """19.4 R6 / 19.6 R9's member-set hash, written out here on purpose: the test must not
    trust `stm.cluster_cid` to define its own expected value."""
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------- seeds ---

def _seed_plain(s: Store, part: str) -> None:
    """`_seed_scopes` without impressions and without `tag: pattern` docs: the R5 tests do
    not depend on R-A's corpus split, so their RED at HEAD reaches the stale assertions."""
    _seed_scopes(s, part, full=False)


def _seed_scopes(s: Store, part: str, *, full: bool = True) -> None:
    """Project memories AND impressions, each forming clusters, plus one `tag: pattern` doc in
    each corpus that NEITHER scope may take (R-A corpus selection). The memory corpus and the
    pattern corpus both cluster under the concept `daemon_ops`, so B3's identity collision
    (`subject_daemon_ops` for both) is reachable."""
    with s.with_partition(part):
        ops = s.add_concept("daemon_ops")
        jet = s.add_concept("jetsam")
        lock = s.add_concept("store_lock")
        rmx = s.add_concept("rmx")
        spec = [
            # name, mtype, tags, concepts, vector
            ("m_ops_a", "project", None, [ops, rmx], _unit(1.0, 0.02)),
            ("m_ops_b", "project", None, [ops, rmx], _unit(1.0, 0.03)),
            ("m_jet_a", "project", None, [jet, rmx], _unit(0, 1.0, 0.02)),
            ("m_jet_b", "feedback", None, [jet, rmx], _unit(0, 1.0, 0.03)),
            ("m_hub_a", "project", None, [rmx], _unit(0, 0, 0, 0, 0, 0, 1.0)),
            ("m_hub_b", "project", None, [rmx], _unit(0, 0, 0, 0, 0, 0, 0, 1.0)),
            # a non-impression doc tagged `pattern`: out of BOTH scopes
            ("m_pat", "project", ["pattern"], [jet, rmx], _unit(0, 1.0, 0.025)),
            ("i_ops_a", "impression", None, [ops], _unit(0, 0, 1.0, 0.02)),
            ("i_ops_b", "impression", None, [ops], _unit(0, 0, 1.0, 0.03)),
            ("i_lock_a", "impression", None, [lock], _unit(0, 0, 0, 1.0, 0.02)),
            ("i_lock_b", "impression", None, [lock], _unit(0, 0, 0, 1.0, 0.03)),
            # an impression tagged `pattern` (a written pattern doc): out of BOTH scopes
            ("i_pat", "impression", ["pattern"], [ops], _unit(0, 0, 1.0, 0.025)),
        ]
        if not full:
            spec = [r for r in spec if r[1] != "impression" and not r[2]]
        ids = {}
        for name, mtype, tags, concepts, _v in spec:
            ids[name] = s.add_memory(name, f"body of {name}", mtype=mtype, tags=tags)
            for c in concepts:
                s.link("mentions", c, ids[name])
        s.upsert_vector([ids[n] for n, *_ in spec], np.vstack([r[4] for r in spec]),
                        kind="memory", dim=DIM)
        s.flush_fragments()


def _seed_tandem(s: Store, part: str) -> None:
    """Two clusters that share their ONLY label `tandem` (r2 m7: duplicate labels), plus a
    third memory of mtype `late` that joins cluster A when it is not excluded (AC-4b)."""
    with s.with_partition(part):
        t = s.add_concept("tandem")
        spec = [
            ("ta1", "project", _unit(1.0, 0.02)), ("ta2", "project", _unit(1.0, 0.03)),
            ("tb1", "project", _unit(0, 0, 1.0, 0.02)), ("tb2", "project", _unit(0, 0, 1.0, 0.03)),
            ("tc", "late", _unit(1.0, 0.025)),
        ]
        ids = {}
        for name, mtype, _v in spec:
            ids[name] = s.add_memory(name, f"body of {name}", mtype=mtype)
            s.link("mentions", t, ids[name])
        s.upsert_vector([ids[n] for n, *_ in spec], np.vstack([r[2] for r in spec]),
                        kind="memory", dim=DIM)
        s.flush_fragments()


# -------------------------------------------------------------- harness ---

@pytest.fixture
def spawn(monkeypatch):
    """`spawn(seed_fn)` -> ctx: a throwaway store under a SHORT mkdtemp root (macOS sun_path),
    seeded, then served by a real spawned daemon. The CLI resolves it through
    `REFMATRIX_ROOT`; the snapshot debounce is 60 s (19.4 round-6 #s-3) so a reader that goes
    through the replica sees nothing the op just wrote."""
    made = []

    def _make(seed=None, *, pre=None):
        base = Path(tempfile.mkdtemp(prefix="r266-"))
        root = base / "proj" / ".refmatrix"
        root.mkdir(parents=True)
        s = Store(root)
        s.init()
        part = discovery.store_name(root)
        try:
            if seed is not None:
                seed(s, part)
            if pre is not None:
                pre(s, part)
        finally:
            s.close()
        monkeypatch.setenv("REFMATRIX_ROOT", str(root))
        monkeypatch.delenv("RMX_PARTITION", raising=False)
        monkeypatch.setenv("RMX_SNAPSHOT_DEBOUNCE_MS", "60000")
        monkeypatch.setenv("COLUMNS", "250")
        dm.spawn_daemon_subprocess(root, watch_root=[])
        assert dm.ping(root), "sandbox daemon never answered"
        made.append((base, root))
        return SimpleNamespace(base=base, root=root, part=part)

    yield _make
    for base, root in made:
        try:
            dm.stop_daemon(root)
        finally:
            shutil.rmtree(base, ignore_errors=True)


def _cli(*argv: str):
    r = CliRunner().invoke(cli_mod.main, list(argv))
    out = r.output + (getattr(r, "stderr", "") or "")
    return r.exit_code, out


def _ok(*argv: str) -> str:
    code, out = _cli(*argv)
    assert code == 0, f"`rmx {' '.join(argv)}` exited {code}:\n{out}"
    return out


def _fresh(ctx) -> None:
    """Force the read snapshot. The daemon's read ops (`subject_list`, `memory_get`,
    `memory_iter`) answer from the mirror / snapshot, which the 60 s debounce holds back; the
    READ surfaces are not what these tests are about, so the harness refreshes them
    explicitly rather than sleeping."""
    r = dm.call(ctx.root, "snapshot", {"force": True}, timeout=60, retries=0)
    assert r.get("ok"), r


def _subjects(ctx) -> dict:
    """{subject row name: {"metadata": ..., "leaves": [sorted leaf names]}} read through the
    daemon's read-routed ops, after a forced snapshot."""
    _fresh(ctx)
    r = dm.call(ctx.root, "subject_list", {"partition": ctx.part}, timeout=30, retries=0)
    assert r.get("ok"), r
    out = {}
    for row in r["result"]["rows"]:
        lv = dm.call(ctx.root, "subject_leaves", {"subject": row["id"], "partition": ctx.part},
                     timeout=30, retries=0)
        assert lv.get("ok"), lv
        out[row["name"]] = {"metadata": row["metadata"],
                            "leaves": sorted(m["name"] for m in lv["result"]["rows"])}
    return out


def _scoped(subjects: dict, scope: str) -> dict:
    return {n: v for n, v in subjects.items()
            if (v["metadata"] or {}).get("compiled_scope") == scope}


def _canon(d: dict) -> str:
    return json.dumps(d, sort_keys=True, default=str)


def _compile_verb(ctx, **kw) -> dict:
    """The MCP surface: `rmx_memory_compile` run exactly as the MCP transport runs it."""
    assert "rmx_memory_compile" in verbs.VERBS, "no `rmx_memory_compile` verb (19.4 R1 op half)"
    return verbs.VERBS["rmx_memory_compile"].run(ctx.root, {**VP, "partition": ctx.part, **kw})


# ======================================================= AC-A (R-A, B3) ===

def test_ac_a_pattern_apply_leaves_every_memory_subject_byte_identical(spawn):
    ctx = spawn(_seed_scopes)
    _ok("memory", "compile", "--apply", *P)
    first = _subjects(ctx)
    mem = _scoped(first, "memory")
    assert mem.get("subject_daemon_ops", {}).get("leaves") == ["m_ops_a", "m_ops_b"], first
    assert mem.get("subject_jetsam", {}).get("leaves") == ["m_jet_a", "m_jet_b"], first
    filed = {leaf for v in mem.values() for leaf in v["leaves"]}
    # R-A corpus: scope `memory` takes no impression and no `tag: pattern` doc.
    assert not {x for x in filed if x.startswith("i_")}, filed
    assert "m_pat" not in filed, filed

    _ok("memory", "compile", "--apply", "--scope", "pattern", *P)
    second = _subjects(ctx)
    for name, before in mem.items():
        assert _canon(second.get(name)) == _canon(before), (
            f"the pattern compile touched memory-scope subject {name}: "
            f"{before} -> {second.get(name)}")
    pat = _scoped(second, "pattern")
    assert pat.get("subject_pattern_daemon_ops", {}).get("leaves") == ["i_ops_a", "i_ops_b"], second
    assert pat.get("subject_pattern_store_lock", {}).get("leaves") == ["i_lock_a", "i_lock_b"]
    assert all(n.startswith("subject_pattern_") for n in pat), sorted(pat)
    taken = {leaf for v in pat.values() for leaf in v["leaves"]}
    assert taken <= {"i_ops_a", "i_ops_b", "i_lock_a", "i_lock_b"}, taken   # never m_*, never i_pat


def test_ac_a_memory_apply_leaves_every_pattern_subject_byte_identical(spawn):
    ctx = spawn(_seed_scopes)
    _ok("memory", "compile", "--apply", "--scope", "pattern", *P)
    pat = _scoped(_subjects(ctx), "pattern")
    assert set(pat) == {"subject_pattern_daemon_ops", "subject_pattern_store_lock"}, pat
    _ok("memory", "compile", "--apply", *P)
    after = _subjects(ctx)
    for name, before in pat.items():
        assert _canon(after.get(name)) == _canon(before), (
            f"the memory compile touched pattern subject {name}: {before} -> {after.get(name)}")
    # The two scopes' `daemon_ops` subjects are two rows, not one identity (store.py slug).
    assert after["subject_daemon_ops"]["leaves"] == ["m_ops_a", "m_ops_b"]
    assert after["subject_pattern_daemon_ops"]["leaves"] == ["i_ops_a", "i_ops_b"]


def _legacy_subject(s: Store, part: str) -> None:
    """A pre-26.6 compiled row: `compiled_by` set, no `compiled_scope` (R-A: scope `memory`)."""
    with s.with_partition(part):
        rec = s.upsert_subject("legacy topic", metadata={
            "compiled_by": "memory-compile", "compiled_at": 1.0})
        hub = s.get_memory("m_hub_a")
        s.link_part_of(int(hub["id"]), int(rec["id"]))
        s.flush_fragments()


def test_ac_a_a_row_without_compiled_scope_belongs_to_scope_memory(spawn):
    ctx = spawn(_seed_scopes, pre=_legacy_subject)
    before = _subjects(ctx)["subject_legacy_topic"]
    assert before["leaves"] == ["m_hub_a"]
    _ok("memory", "compile", "--apply", "--scope", "pattern", *P)
    assert _canon(_subjects(ctx)["subject_legacy_topic"]) == _canon(before), \
        "a pattern compile pruned or marked a pre-26.6 (scope `memory`) row"
    _ok("memory", "compile", "--apply", *P)
    legacy = _subjects(ctx)["subject_legacy_topic"]
    # The memory compile owns it: its leaf is re-filed away (m_hub_a clusters nowhere) and the
    # emptied row is marked stale, never deleted.
    assert legacy["leaves"] == [], legacy
    assert legacy["metadata"].get("stale") is True, legacy
    assert legacy["metadata"].get("stale_since"), legacy


# ================================================ AC-0: 19.4 AC-4 (R5) ===

def test_ac4_a_subject_left_empty_is_marked_stale_kept_protected_and_listed(spawn):
    ctx = spawn(_seed_plain)
    _ok("memory", "compile", "--apply", *P)
    assert _subjects(ctx)["subject_jetsam"]["leaves"] == ["m_jet_a", "m_jet_b"]
    # m_jet_b is the only `feedback` row: leaving it out empties `jetsam` (a 1-member group is
    # no cluster). `--exclude-mtype` REPLACES the default globs, so they are restated.
    out = _ok("memory", "compile", "--apply", "--exclude-mtype", "feedback",
              "--exclude-mtype", "session*", "--exclude-mtype", "digest*",
              "--exclude-mtype", "subject", *P)
    m = re.search(r"(\d+) marked stale", out)
    assert m and int(m.group(1)) == 1, f"R7: the apply must say how many it marked stale:\n{out}"

    subj = _subjects(ctx)
    jet = subj.get("subject_jetsam")
    assert jet is not None, "compile removed the emptied subject row (R4/R5: never removed)"
    assert jet["leaves"] == []
    assert jet["metadata"].get("stale") is True, jet
    assert jet["metadata"].get("stale_since"), jet
    assert not subj["subject_daemon_ops"]["metadata"].get("stale"), "a live subject was marked"

    # `rmx memory get subject_jetsam` (the verb the CLI and MCP share) still returns it.
    _fresh(ctx)
    got = verbs.memory(ctx.root, action="get", name="subject_jetsam", partition=ctx.part)
    assert (got.get("memory") or {}).get("metadata", {}).get("stale") is True, got
    # R-D: the `rmx_memory` subject listing carries the mark, so CLI and MCP agree.
    rows = verbs.memory(ctx.root, action="list", mtype="subject", partition=ctx.part)["rows"]
    by = {r["name"]: r for r in rows}
    assert by["subject_jetsam"]["metadata"].get("stale") is True
    assert by["subject_jetsam"]["metadata"].get("stale_since")
    assert not by["subject_daemon_ops"]["metadata"].get("stale")
    # R-D: `rmx memory list --type subject` SHOWS the mark on the stale row only.
    listing = _ok("memory", "list", "--type", "subject")
    lines = {ln for ln in listing.splitlines() if "subject_" in ln}
    jet_line = [ln for ln in lines if "subject_jetsam" in ln]
    ops_line = [ln for ln in lines if "subject_daemon_ops" in ln]
    assert jet_line and "stale" in jet_line[0].lower(), listing
    assert ops_line and "stale" not in ops_line[0].lower(), listing

    # Still `protected` (19.4 R5). Read from the throwaway catalog once its daemon is gone.
    dm.stop_daemon(ctx.root)
    s = Store(ctx.root)
    try:
        with s.with_partition(ctx.part):
            row = s._read().execute(
                "SELECT protected FROM entities WHERE partition_id=? AND name=?",
                (s._partition_id, "subject_jetsam")).fetchone()
    finally:
        s.close()
    assert row is not None and bool(row[0]) is True


def test_r5_a_stale_subject_that_regains_members_is_unmarked(spawn):
    ctx = spawn(_seed_plain)
    excl = ["feedback", "session*", "digest*", "subject"]
    _compile_verb(ctx, apply=True)
    marked = _compile_verb(ctx, apply=True, exclude_mtypes=excl)
    assert marked["stale_new"] == 1, marked
    assert _subjects(ctx)["subject_jetsam"]["metadata"].get("stale") is True
    back = _compile_verb(ctx, apply=True)
    assert back["stale_unmarked"] == 1, back
    jet = _subjects(ctx)["subject_jetsam"]
    assert jet["leaves"] == ["m_jet_a", "m_jet_b"]
    assert not jet["metadata"].get("stale"), jet
    assert "stale_since" not in jet["metadata"], jet


# ===================================== AC-0: 19.4 AC-4b / AC-5 (R5, R6) ===

def test_ac4b_one_member_gained_mints_one_subject_and_marks_one_stale(spawn):
    ctx = spawn(_seed_tandem)
    late_out = ["late", "session*", "digest*", "subject"]
    kw = {"hub_df_frac": 1.0}
    r1 = _compile_verb(ctx, apply=True, exclude_mtypes=late_out, **kw)
    s1 = _subjects(ctx)
    a_old = f"subject_tandem_{_cid(['ta1', 'ta2'])}"
    b = f"subject_tandem_{_cid(['tb1', 'tb2'])}"
    # r2 m7: BOTH duplicated labels carry the member-set hash, never `-2` by cluster order.
    assert set(s1) == {a_old, b}, sorted(s1)

    r2 = _compile_verb(ctx, apply=True, **kw)            # `tc` joins cluster A
    s2 = _subjects(ctx)
    a_new = f"subject_tandem_{_cid(['ta1', 'ta2', 'tc'])}"
    assert set(s2) - set(s1) == {a_new}, sorted(s2)
    assert s2[a_old]["leaves"] == [] and s2[a_old]["metadata"].get("stale") is True
    assert s2[b]["leaves"] == ["tb1", "tb2"] and not s2[b]["metadata"].get("stale")
    assert r2["stale_new"] == 1, r2
    assert r2["stale_total"] == r1["stale_total"] + 1, (r1, r2)

    r3 = _compile_verb(ctx, apply=True, **kw)            # no membership change
    assert set(_subjects(ctx)) == set(s2)
    assert r3["stale_new"] == 0 and r3["stale_total"] == r2["stale_total"], r3


# ============================================ R1 op half (19.4, R-D verb) ===

def test_verb_dry_run_plans_writes_nothing_and_says_who_invoked_it(spawn):
    ctx = spawn(_seed_scopes)
    res = _compile_verb(ctx)                              # default: apply=False
    assert res["dry_run"] is True and res["applied"] is False, res
    assert res["scope"] == "memory" and res["invoked_by"] == "mcp", res
    labels = {c["label"] for c in res["plan"]["clusters"]}
    assert {"daemon_ops", "jetsam"} <= labels, labels
    assert _subjects(ctx) == {}, "a dry run wrote subjects"


def _inproc_daemon(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    part = discovery.store_name(root)
    _seed_scopes(s, part)
    d = dm.Daemon(root)
    d.store = s
    d._bg_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="t266-bg")
    return d, s, part


def test_single_flight_second_call_answers_already_running_and_status_is_lock_free(tmp_path):
    """19.4 R1 / 17.1 R11: a call arriving while a compile runs starts nothing and answers
    `already_running`; `status=True` answers without the store lock. The test HOLDS the writer
    lock so the first compile cannot finish; every probe runs in a thread with a bound, so a
    guard that is missing FAILS here instead of hanging (feedback_mutation_must_fail_not_hang)."""
    assert "memory_compile" in dm.OPS, "no `memory_compile` daemon op (19.4 R1 op half)"
    op = dm.OPS["memory_compile"]
    d, s, part = _inproc_daemon(tmp_path)
    args = {**VP, "partition": part, "dry_run": False, "invoked_by": "cli"}
    box: dict = {}

    def _run(key, a):
        try:
            box[key] = op(d, a)
        except Exception as e:            # noqa: BLE001 — recorded, asserted below
            box[key] = e

    first = threading.Thread(target=_run, args=("first", args), daemon=True)
    try:
        with d._store_lock:
            first.start()
            deadline = time.monotonic() + 10
            running = False
            while time.monotonic() < deadline and not running:
                st = threading.Thread(target=_run, args=("status", {"status": True,
                                                                    "partition": part}),
                                      daemon=True)
                st.start()
                st.join(timeout=3)
                assert not st.is_alive(), "status=True blocked on the store lock (not lock-free)"
                res = box.pop("status")
                assert not isinstance(res, Exception), res
                running = bool(res.get("running"))
                if not running:
                    time.sleep(0.05)
            assert running, "status=True never reported the first compile as running"
            second = threading.Thread(target=_run, args=("second", args), daemon=True)
            second.start()
            second.join(timeout=5)
            assert not second.is_alive(), (
                "the second call blocked behind the first instead of answering already_running")
            got = box["second"]
            assert not isinstance(got, Exception), got
            assert got.get("already_running") is True, got
            assert got.get("run_id") and got.get("started_at"), got
    finally:
        first.join(timeout=60)
        d._bg_pool.shutdown(wait=True)
    assert not first.is_alive()
    done = box["first"]
    assert not isinstance(done, Exception), done
    assert done["applied"] is True and done["subjects"], done
    idle = op(d, {"status": True, "partition": part})
    assert idle.get("running") is False, idle
    s.close()


def test_verb_and_cli_twin_are_registered_and_compile_left_legacy():
    """R-D: `memory compile` leaves LEGACY_UNPAIRED; `rmx_memory_compile` is its verb, and its
    `scope` parameter is the parity surface 26.9 uses."""
    v = verbs.VERBS.get("rmx_memory_compile")
    assert v is not None, "no `rmx_memory_compile` verb"
    assert verbs.CLI_MAP.get("rmx_memory_compile") == ("memory", "compile")
    assert ("memory", "compile") not in verbs.LEGACY_UNPAIRED
    assert v.schema["properties"]["scope"].get("enum") == ["memory", "pattern"]
    assert v.defaults.get("scope") == "memory"
    assert v.defaults.get("apply") is False
    code, out = _cli("memory", "compile", "--help")
    assert code == 0 and "--scope" in out, out


# =============================================== AC-0: 19.4 AC-1 (R2) ===

def _marker(memdir: Path) -> None:
    """ADR-0005 `#marker` encoding, written by hand: only `rmx memory organise --apply` (26.5)
    writes it in production."""
    (memdir / ".memory-layout").write_text(json.dumps(
        {"layout": 1, "organised": "2026-11-09T00:00:00-08:00",
         "backup": "/nonexistent/backup.tar.gz"}), encoding="utf-8")


def _memdir(ctx, *, organised: bool) -> Path:
    """The store's memory root, resolved the way 19.4 R2 resolves it."""
    memdir = handoff.default_memory_dir(ctx.root.parent)
    memdir.mkdir(parents=True, exist_ok=True)
    (memdir / "impressions").mkdir(exist_ok=True)
    if organised:
        _marker(memdir)
    (memdir / "old_note.md").write_text(GMD.format(id="old_note", t="project", body="older"))
    (memdir / "impressions" / "imp_one.md").write_text(
        GMD.format(id="imp_one", t="impression", body="one"))
    # A hand index from an earlier save-state: names old_note, one impression.
    (memdir / "MEMORY.md").write_text(
        "- [old_note](old_note.md) — older\n"
        "- [ch-bsd impressions (1)](impressions/) — pointer\n")
    return memdir


def test_ac1_bridge_regenerates_the_index_in_an_organised_dir(spawn):
    ctx = spawn()
    memdir = _memdir(ctx, organised=True)
    (memdir / "new_note.md").write_text(GMD.format(id="new_note", t="project", body="newest"))
    _ok("ingest-gmd", "--as-memory", str(memdir))
    idx = (memdir / "MEMORY.md").read_text()          # no sleep, no retry
    assert "](new_note.md)" in idx, idx
    assert "](old_note.md)" in idx, idx
    assert memory_index.check(memdir), "MEMORY.md is not what the index writer renders"


def test_ac1_the_sessionstart_detached_bridge_regenerates_the_index(spawn):
    ctx = spawn()
    memdir = _memdir(ctx, organised=True)
    (memdir / "new_note.md").write_text(GMD.format(id="new_note", t="project", body="newest"))
    _ok("ingest-gmd", "--as-memory", "--detach", str(memdir))     # the SessionStart hook argv
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        r = dm.call(ctx.root, "ingest_gmd_status", {}, timeout=10, retries=0)
        jobs = (r.get("result") or {}).get("jobs") or []
        if jobs and all(j.get("status") in ("done", "error") for j in jobs):
            break
        time.sleep(0.1)
    else:
        pytest.fail("the detached bridge job never finished")
    assert all(j.get("status") == "done" for j in jobs), jobs
    idx = (memdir / "MEMORY.md").read_text()
    assert "](new_note.md)" in idx, idx


def test_ac1_a_subdirectory_target_regenerates_the_memory_roots_index(spawn):
    """R2: the memdir is the STORE's memory root, never the bridge's target path."""
    ctx = spawn()
    memdir = _memdir(ctx, organised=True)
    (memdir / "impressions" / "imp_two.md").write_text(
        GMD.format(id="imp_two", t="impression", body="two"))
    _ok("ingest-gmd", "--as-memory", str(memdir / "impressions"))
    idx = (memdir / "MEMORY.md").read_text()
    assert "impressions (2)" in idx, idx
    assert not (memdir / "impressions" / "MEMORY.md").exists(), "an index was written in the target"


def test_ac1_twin_an_unorganised_dir_keeps_its_index_and_sidecar_byte_identical(spawn):
    """r2 s2 marker-OFF twin. GREEN at HEAD by design (HEAD's bridge writes no index); it is
    the guard that fails an UNGATED R2."""
    ctx = spawn()
    memdir = _memdir(ctx, organised=False)
    before = (memdir / "MEMORY.md").read_bytes()
    (memdir / "new_note.md").write_text(GMD.format(id="new_note", t="project", body="newest"))
    _ok("ingest-gmd", "--as-memory", str(memdir))
    assert (memdir / "MEMORY.md").read_bytes() == before
    assert not (memdir / memory_index.HOOKS_SIDECAR).exists()


# ================================ AC-0: 19.4 AC-6, marker-OFF twin (R3) ===

def test_ac6_twin_compile_leaves_an_unorganised_index_byte_identical(spawn):
    """r3 m3. The marker-ON leg of AC-6 waits for 26.7 (R3 needs its subject render). GREEN
    at HEAD by design (HEAD's compile writes no index); it fails an UNGATED R3. Driven through
    the verb as well as the CLI so the new op path is the one exercised."""
    ctx = spawn(_seed_scopes)
    memdir = _memdir(ctx, organised=False)
    (memdir / memory_index.HOOKS_SIDECAR).write_text('{"old_note.md": "older"}')
    idx, side = (memdir / "MEMORY.md").read_bytes(), (memdir / memory_index.HOOKS_SIDECAR).read_bytes()
    _ok("memory", "compile", "--apply", *P)
    _compile_verb(ctx, apply=True)
    assert (memdir / "MEMORY.md").read_bytes() == idx
    assert (memdir / memory_index.HOOKS_SIDECAR).read_bytes() == side


# ============================================ AC-D (R-C): the status line ===

STATUS_LINE = "memory-compile: behind code"
STATUS_FIX = "rmx memory compile --apply"


def _hash_from_copy(tmp: Path, *, edit: tuple, monkeypatch) -> str:
    """`derive_code_hash("memory-compile")` as a DIFFERENT checkout would have stamped it: the
    deriving modules are copied and `edit` ones are changed (`_DERIVE_SRC_DIR`, the seam that
    exists for this). Editing ingest.py/store.py but NOT consolidate.py is a release that did
    not touch the compile code."""
    import refmatrix.store as store_mod
    src = Path(store_mod.__file__).resolve().parent
    d = tmp / "src"
    d.mkdir(parents=True, exist_ok=True)
    for name in ("consolidate.py", "ingest.py", "ingest_gmd.py", "store.py"):
        body = (src / name).read_bytes()
        if name in edit:
            body += b"\n# a later edit\n"
        (d / name).write_bytes(body)
    store_mod._DERIVE_CODE_HASH_CACHE.clear()
    monkeypatch.setattr(store_mod, "_DERIVE_SRC_DIR", d)
    try:
        return store_mod.derive_code_hash("memory-compile")
    finally:
        monkeypatch.setattr(store_mod, "_DERIVE_SRC_DIR", None)
        store_mod._DERIVE_CODE_HASH_CACHE.clear()


def _compiled_subject(s: Store, part: str, *, stamp: "dict | None") -> None:
    with s.with_partition(part):
        s.upsert_subject("daemon_ops", metadata={
            "compiled_by": "memory-compile", "compiled_scope": "memory", "compiled_at": 1.0})
        if stamp is not None:
            s.stamp_derive("memory-compile", **stamp)


def _status(ctx) -> str:
    return _ok("daemon", "status")


def test_acd_consolidate_changed_since_the_compile_prints_the_line(spawn, tmp_path, monkeypatch):
    h = _hash_from_copy(tmp_path, edit=("consolidate.py",), monkeypatch=monkeypatch)
    ctx = spawn(pre=lambda s, p: _compiled_subject(s, p, stamp={"code_hash": h}))
    out = _status(ctx)
    assert STATUS_LINE in out and STATUS_FIX in out, out
    assert f"derive[{ctx.part}]" not in out, f"the partition verdict moved:\n{out}"


def test_acd_a_version_bump_with_consolidate_unchanged_prints_nothing(spawn, tmp_path,
                                                                       monkeypatch):
    h = _hash_from_copy(tmp_path, edit=("ingest.py", "ingest_gmd.py", "store.py"),
                        monkeypatch=monkeypatch)
    ctx = spawn(pre=lambda s, p: _compiled_subject(
        s, p, stamp={"code_hash": h, "version": "0.0.1"}))
    out = _status(ctx)
    assert "memory-compile" not in out, out
    assert f"derive[{ctx.part}]" not in out, f"the partition verdict moved:\n{out}"


def test_acd_compiled_subjects_with_no_stamp_print_the_line(spawn):
    """The 2026-07-31 case: subjects compiled before any stamp existed."""
    ctx = spawn(pre=lambda s, p: _compiled_subject(s, p, stamp=None))
    out = _status(ctx)
    assert STATUS_LINE in out and STATUS_FIX in out, out


def test_acd_no_compiled_subjects_and_no_stamp_print_nothing(spawn):
    ctx = spawn(_seed_scopes)
    out = _status(ctx)
    assert "memory-compile" not in out, out


def test_acd_a_real_apply_stamps_the_pass_and_keeps_the_verdict(spawn):
    """The wiring test: the REAL compile stamps `memory-compile` with its per-pass hash, so the
    status line stays quiet and the partition verdict does not move. Fails the 'stamp call
    skipped' mutation (task-26.6 #test-strategy)."""
    import refmatrix.store as store_mod
    ctx = spawn(_seed_scopes)
    _ok("memory", "compile", "--apply", *P)
    out = _status(ctx)
    assert "memory-compile" not in out, out
    assert f"derive[{ctx.part}]" not in out, out
    dm.stop_daemon(ctx.root)
    s = Store(ctx.root)
    try:
        rows = s._read().execute(
            "SELECT p.name, d.code_hash FROM derive_stamps d "
            "JOIN partitions p ON p.id = d.partition_id WHERE d.pass_name = 'memory-compile'"
        ).fetchall()
    finally:
        s.close()
    store_mod._DERIVE_CODE_HASH_CACHE.clear()
    assert [(r[0], r[1]) for r in rows] == [
        (ctx.part, store_mod.derive_code_hash("memory-compile"))], rows
