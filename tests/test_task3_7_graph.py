"""Task 3.7 batch B — the graph-read family as `rmx_graph` actions (RED).

Spec #fam-graph-read, #decisions-r2, #budgets, C1-C9 (incl. C4a):
  neighbors / co_occur / top / stats(stale=False) → `snapshot_read`;
  describe → its lock-free daemon op `describe`, 10 s, single attempt;
  stats(stale=True) → daemon `stats` op with `include_stale`, 10 s; absent ⇒ C4a;
  recall → the NEW daemon op `graph_recall` (180 s), the base CLI's algorithm run
           server-side: no Embedder in the caller, `-s` validated as ints;
  dense  → daemon `ann_search` WITH `partition` (180 s), names from the same partition;
  timeline → graph leg from the snapshot, session leg through `memory_search` on the
           sessions partition (budgeted), git via subprocess; a failed or skipped leg is a
           `warnings` entry — never `except: pass`, never a direct `Store(...)` open.
Defects (each fails at the base 591a2fb, which HEAD still carries for these paths):
  neighbors reads through the WRITE accessor; search-dense omits `partition`; concept
  timeline's silent passes + `_iter_session_memories`' direct Store open; recall loads
  `Embedder()` in-process.

Result shapes pinned (the CLI renders them; test_verb_parity.py canaries use them):
  neighbors {concept, entities:[{id,kind,name,path}], cardinality}; co_occur {rows:
  [{concept, overlap}]}; top {rows:[{id,name,kind,weight}]}; describe {found,
  candidates}; recall {hits:[{rank,id,score,kind,name,path}]}; dense {hits:[{rank,id,
  distance|score,kind,name}], warnings}; stats = Store.stats() (+ stale_files);
  timeline {concept, resolved_files, resolved_concepts, hops, events, session_count,
  truncated, warnings}. Every snapshot/in-process read also carries `source`.

Interpretation (named in the report): `recall` / `dense` with NO daemon are left
unpinned here — C4a's in-process branch would need an in-process embedder, which
#fam-graph-read-recall forbids.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery, verbs
from refmatrix.store import Store
from tests.task3_7_helpers import (FakeDaemon, HashEmbedder, graph_store, make_snapshot, rm,
                                   short_root)
from tests.test_plan2_remedy import _SilentDaemon

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src" / "refmatrix"


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37g-")
    monkeypatch.setattr(cli_mod, "_root", lambda: r)
    yield r
    rm(base)


@pytest.fixture
def gstore(root):
    """No daemon (absent), a real graph, no snapshot."""
    ids = graph_store(root)
    return root, ids


@pytest.fixture
def silent_with_snapshot(monkeypatch):
    """A REAL busy daemon (live pid, socket that never answers) over a real graph
    WITH a snapshot."""
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon()
    graph_store(d.root)
    make_snapshot(d.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
    yield d
    d.close()


# ---- neighbors ------------------------------------------------------------------


def test_neighbors_with_no_daemon_reads_in_process(gstore):
    root, ids = gstore
    out = verbs.graph(root, action="neighbors", concept="alpha")
    assert sorted(e["id"] for e in out["entities"]) == ids["docs"][:4], out
    assert out["cardinality"] == 4 and out["source"] == "in-process", out
    assert {"id", "kind", "name", "path"} <= set(out["entities"][0])


def test_neighbors_limit_truncates_rows_not_the_cardinality(gstore):
    root, _ids = gstore
    out = verbs.graph(root, action="neighbors", concept="alpha", limit=2)
    assert len(out["entities"]) == 2 and out["cardinality"] == 4, out


def test_neighbors_on_a_busy_daemon_reads_the_snapshot(silent_with_snapshot):
    out = verbs.graph(silent_with_snapshot.root, action="neighbors", concept="alpha")
    assert out["source"] == "snapshot" and out["cardinality"] == 4, out


def test_cli_neighbors_on_a_busy_daemon_is_worded_as_a_read_not_a_write(monkeypatch):
    """The defect: with no snapshot the CLI read through `_store()` — the WRITE
    accessor — so a busy daemon said "writes go through the daemon"."""
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon()       # unseeded: a seeded in-process writer turns this into a
    try:                      # same-process DuckDB attach conflict, not the defect
        monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
        r = CliRunner().invoke(cli_mod.main, ["neighbors", "alpha"])
        out = r.output + (r.stderr or "")
        assert r.exit_code != 0, out
        assert "writes go through the daemon" not in out, out
        assert "no read snapshot yet" in out, out
    finally:
        d.close()


# ---- co_occur / top -------------------------------------------------------------


def test_co_occur_reads_with_no_daemon_and_no_snapshot(gstore):
    root, _ids = gstore
    out = verbs.graph(root, action="co_occur", concept="alpha")
    assert out["rows"] == [{"concept": "beta", "overlap": 2}], out
    assert out["source"] == "in-process"


def test_cli_co_occur_works_on_a_daemonless_store(gstore):
    """C4a guard: `co-occur` on a daemonless, snapshotless store answers (it holds at
    2bc1405 and must keep holding once the CLI calls the verb)."""
    r = CliRunner().invoke(cli_mod.main, ["co-occur", "alpha"])
    assert r.exit_code == 0, r.output
    assert "beta" in r.output


def test_top_ranks_by_weight(gstore):
    root, ids = gstore
    out = verbs.graph(root, action="top", concept="alpha", k=3)
    d = ids["docs"]
    assert [r["id"] for r in out["rows"]] == [d[3], d[2], d[1]], out
    assert [r["weight"] for r in out["rows"]] == [4.0, 3.0, 2.0]
    assert out["rows"][0]["name"] == "d3.md"


def test_top_of_an_unknown_concept_is_a_verb_error(gstore):
    root, _ids = gstore
    with pytest.raises(verbs.VerbError):
        verbs.graph(root, action="top", concept="nope")


# ---- describe ---------------------------------------------------------------------


def test_describe_goes_through_its_daemon_op_with_one_budgeted_attempt(root, monkeypatch):
    fd = FakeDaemon({"describe": {"ok": True, "result": {
        "found": {"id": 6, "name": "d3.md"}, "candidates": [{"id": 6}]}}}).install(monkeypatch)
    out = verbs.graph(root, action="describe", ref="d3.md", first=True, edge_limit=7,
                      no_vectors=True, partition="px")
    _op, args, timeout, retries = fd.last("describe")
    assert args["ref"] == "d3.md" and args["first"] is True and args["edge_limit"] == 7
    assert args["include_vectors"] is False and args["partition"] == "px", args
    assert timeout == 10.0 and retries == 0, (timeout, retries)
    assert out["found"]["name"] == "d3.md"


def test_describe_refusal_is_a_verb_error(root, monkeypatch):
    FakeDaemon({"describe": {"ok": False, "error": "CANARY-desc-refused"}}).install(monkeypatch)
    with pytest.raises(verbs.VerbError) as ei:
        verbs.graph(root, action="describe", ref="x")
    assert "CANARY-desc-refused" in str(ei.value)


def test_describe_with_no_daemon_reads_in_process(gstore):
    root, ids = gstore
    out = verbs.graph(root, action="describe", ref="d3.md", no_vectors=True)
    assert out["found"] is not None and out["source"] == "in-process", out


def test_describe_on_a_busy_daemon_is_busy(silent_with_snapshot):
    with pytest.raises(verbs.VerbBusyError):
        verbs.graph(silent_with_snapshot.root, action="describe", ref="d3.md")


# ---- recall: the graph_recall op ----------------------------------------------------


def test_recall_sends_graph_recall_with_the_180s_budget(root, monkeypatch):
    fd = FakeDaemon({"graph_recall": {"ok": True, "result": {"hits": [
        {"rank": 1, "id": 6, "score": 0.0, "kind": "doc", "name": "d3.md", "path": "/p"}]}}}
    ).install(monkeypatch)
    out = verbs.graph(root, action="recall", query="document number 3", k=3, kinds=["doc"],
                      concept=["beta"], symbolic=["8", "3"], partition="px")
    _op, args, timeout, retries = fd.last("graph_recall")
    assert args["query"] == "document number 3" and args["k"] == 3
    assert args["kinds"] == ["doc"] and args["concept"] == ["beta"], args
    assert args["symbolic"] == [8, 3], "-s values travel as validated ints"
    assert args["partition"] == "px"
    assert timeout == 180.0 and retries == 0, (timeout, retries)
    assert out["hits"][0]["id"] == 6


def test_recall_symbolic_values_must_be_ints(root, monkeypatch):
    fd = FakeDaemon({}).install(monkeypatch)
    with pytest.raises(verbs.VerbArgsError):
        verbs.graph(root, action="recall", query="q", symbolic=["8", "not-an-id"])
    assert fd.calls == []


def test_recall_transport_timeout_is_busy(root, monkeypatch):
    FakeDaemon({"graph_recall": TimeoutError("timed out")}).install(monkeypatch)
    with pytest.raises(verbs.VerbBusyError):
        verbs.graph(root, action="recall", query="q")


def test_cli_recall_never_loads_an_embedder_in_process(gstore, monkeypatch):
    """The defect: `rmx recall` built `Embedder()` (sentence-transformers) in the
    CLI process. Through the verb the daemon embeds."""
    root, _ids = gstore
    make_snapshot(root)

    class _NoLocalModel:
        def __init__(self, *a, **k):
            raise AssertionError("Embedder() constructed in the caller's process")
    monkeypatch.setattr("refmatrix.embedder.Embedder", _NoLocalModel)
    fd = FakeDaemon({"graph_recall": {"ok": True, "result": {"hits": [
        {"rank": 1, "id": 6, "score": 0.0, "kind": "doc", "name": "CANARY-d3",
         "path": "/p"}]}}}).install(monkeypatch)
    r = CliRunner().invoke(cli_mod.main, ["recall", "document number 3", "--json"])
    assert not isinstance(r.exception, AssertionError), r.exception
    assert r.exit_code == 0, r.output
    assert "graph_recall" in fd.ops() and "CANARY-d3" in r.output


# The base CLI's rank order (591a2fb `recall_cmd`, unchanged at 2bc1405) on the
# `graph_store` fixture with `HashEmbedder` patched in as `refmatrix.embedder.Embedder`
# — recorded in workflow/review-output/task-3.7/probe-b.log. ids: d0..d5 = 3..8.
_BASE_ORDER = {
    "dense": ({"query": "document number 3"},
              [(6, 0.0), (7, 0.1563), (4, 0.2483), (5, 0.2927), (3, 0.4916), (8, 0.7308)]),
    "prefilter": ({"query": "document number 3", "concept": ["beta"]},
                  [(6, 0.0), (7, 0.1563), (5, 0.2927), (8, 0.7308)]),
    "hybrid": ({"query": "document number 3", "symbolic": [8, 3]},
               [(8, 0.0321), (3, 0.032), (6, 0.0167), (7, 0.0164), (4, 0.0161), (5, 0.0159)]),
    "symbolic_only": ({"query": "x", "symbolic": [4, 7], "no_dense": True},
                      [(4, 1.0), (7, 0.5)]),
}


@pytest.mark.parametrize("case", sorted(_BASE_ORDER))
def test_graph_recall_op_reproduces_the_base_cli_rank_order(gstore, case):
    """#fam-graph-read-recall (r1 B2, r2 M3): `graph_recall` runs the CLI's own
    algorithm server-side — bitmap_prefilter → dense_recall, hybrid_recall when -s,
    the symbolic-only fallback — no rerank, no BM25 fusion. ONE deterministic
    embedder is injected through the daemon's `_embedder()` cache."""
    root, _ids = gstore
    make_snapshot(root)
    assert "graph_recall" in dm.OPS, "no graph_recall daemon op"
    args, expected = _BASE_ORDER[case]
    s = Store(root)
    s.init()
    d = dm.Daemon(root)
    d.store = s
    d._log = lambda msg: None
    d._embedder_inst = HashEmbedder()
    try:
        out = dm.OPS["graph_recall"](d, {"k": 10, "kinds": None,
                                          "partition": discovery.store_name(root), **args})
    finally:
        s.close()
    got = [(h["id"], round(float(h["score"]), 4)) for h in out["hits"]]
    assert got == expected, (case, got)
    assert [h["rank"] for h in out["hits"]] == list(range(1, len(expected) + 1))
    assert out["hits"][0]["name"] == f"d{expected[0][0] - 3}.md"


# ---- dense (search-dense) ------------------------------------------------------------


def _ann_answer(args):
    return {"ok": True, "result": {"hits": [{"id": 6, "distance": 0.1},
                                            {"id": 3, "distance": 0.5}]}}


def test_dense_sends_partition_and_resolves_names_from_it(root, monkeypatch):
    graph_store(root, partition="px")
    make_snapshot(root)
    fd = FakeDaemon({"ann_search": _ann_answer}).install(monkeypatch)
    out = verbs.graph(root, action="dense", query="q", k=4, kinds=["doc"], partition="px")
    _op, args, timeout, retries = fd.last("ann_search")
    assert args.get("partition") == "px", ("ids resolve against the wrong partition", args)
    assert args["k"] == 4 and args["kinds"] == ["doc"]
    assert timeout == 180.0 and retries == 0
    assert [h["name"] for h in out["hits"]] == ["d3.md", "d0.md"], out


def test_cli_search_dense_forwards_the_cli_partition(root, monkeypatch):
    """The defect: `rmx -p X search-dense` never sent `partition` to ann_search."""
    graph_store(root, partition="px")
    make_snapshot(root)
    fd = FakeDaemon({"ann_search": _ann_answer}).install(monkeypatch)
    r = CliRunner().invoke(cli_mod.main, ["-p", "px", "search-dense", "q"])
    assert "ann_search" in fd.ops(), r.output
    assert fd.last("ann_search")[1].get("partition") == "px"


# ---- stats ----------------------------------------------------------------------------


def test_stats_reads_counts_from_the_snapshot_route(gstore):
    root, _ids = gstore
    out = verbs.graph(root, action="stats")
    assert out["entities"] == {"doc": 6, "concept": 2}, out
    assert out["source"] == "in-process"


def test_stats_stale_goes_through_the_daemon_stats_op(root, monkeypatch):
    """r3 S1: the replica's tracked_files is not refreshed, so --stale is the writer's."""
    fd = FakeDaemon({"stats": {"ok": True, "result": {
        "entities": {}, "linkages": {}, "stale_files": []}}}).install(monkeypatch)
    out = verbs.graph(root, action="stats", stale=True)
    _op, args, timeout, retries = fd.last("stats")
    assert args.get("include_stale") is True, args
    assert timeout == 10.0 and retries == 0
    assert out["stale_files"] == []


def test_stats_stale_with_no_daemon_is_in_process(gstore):
    root, _ids = gstore
    out = verbs.graph(root, action="stats", stale=True)
    assert "stale_files" in out and out["source"] == "in-process", out


def test_stats_stale_on_a_busy_daemon_is_busy(silent_with_snapshot):
    with pytest.raises(verbs.VerbBusyError):
        verbs.graph(silent_with_snapshot.root, action="stats", stale=True)


# ---- concept timeline -----------------------------------------------------------------

_SESSION_ROW = {"id": 90, "name": "sess-1", "mtype": "session",
                "content": "# Session about alpha {#root}\nworked on alpha",
                "metadata": {"session_id": "sess-1", "ended": "2026-10-01T10:00:00",
                             "files_touched": []}}


def test_timeline_session_leg_goes_through_memory_search_on_the_sessions_partition(
        root, monkeypatch):
    graph_store(root)
    make_snapshot(root)
    fd = FakeDaemon({
        "memory_search": {"ok": True, "result": {"rows": [_SESSION_ROW]}},
        "memory_iter": {"ok": True, "result": {"rows": [_SESSION_ROW]}},
    }).install(monkeypatch)
    out = verbs.graph(root, action="timeline", concept="alpha", git=False)
    _op, args, timeout, retries = fd.last("memory_search")
    assert args["partition"] == "sessions-proj", args
    assert timeout <= 60.0 and retries == 0, (timeout, retries)
    assert any(e["type"] == "session" for e in out["events"]), out
    assert out["resolved_files"] == 4 and out["warnings"] == [], out


def _rw_store_opens(monkeypatch) -> list:
    opened: list = []
    real = Store.__init__

    def rec(self, root, *a, **kw):
        if not kw.get("read_only") and not (len(a) >= 3 and a[2]):
            opened.append(str(root))
        return real(self, root, *a, **kw)
    monkeypatch.setattr(Store, "__init__", rec)
    return opened


def test_timeline_on_a_busy_daemon_warns_and_never_opens_the_writer(silent_with_snapshot,
                                                                  monkeypatch):
    """The defect: a busy daemon failed ping, the helper opened `Store(root,
    partition=…)` read-WRITE on the active slot, and `except Exception: pass` hid it."""
    opened = _rw_store_opens(monkeypatch)
    out = verbs.graph(silent_with_snapshot.root, action="timeline", concept="alpha", git=False)
    assert opened == [], f"read-write Store opened under a busy daemon: {opened}"
    assert out["warnings"] and any("session" in w for w in out["warnings"]), out
    assert out["resolved_files"] == 4, "the graph leg still answers"


def test_cli_timeline_json_carries_the_failed_leg(silent_with_snapshot):
    r = CliRunner().invoke(cli_mod.main, ["concept", "timeline", "alpha", "--no-git", "--json"])
    assert r.exit_code == 0, r.output
    doc = json.loads(r.output)
    assert doc.get("warnings"), ("a failed session leg must be reported", doc)


def test_timeline_git_leg_outside_a_repo_is_a_warning(gstore):
    """C8: a leg skipped by design (no git repo) reports it."""
    root, _ids = gstore
    out = verbs.graph(root, action="timeline", concept="alpha", git=True)
    assert any("git" in w.lower() for w in out["warnings"]), out


def _funcs_named(path: Path, pred):
    tree = ast.parse(path.read_text())
    return [f for f in ast.walk(tree)
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and pred(f.name)]


def test_no_timeline_code_swallows_an_exception_or_opens_the_writer():
    """C8 + #fam-graph-read: the two `except Exception: pass` blocks and the direct
    `Store(...)` open in `_iter_session_memories` are gone."""
    bad = []
    for path in (_SRC / "cli.py", _SRC / "verbs.py"):
        for fn in _funcs_named(path, lambda n: "timeline" in n or n == "_iter_session_memories"):
            for h in ast.walk(fn):
                if isinstance(h, ast.ExceptHandler) and all(isinstance(b, ast.Pass)
                                                            for b in h.body):
                    bad.append(f"{path.name}:{fn.name}:{h.lineno} except: pass")
            if fn.name == "_iter_session_memories":
                for c in ast.walk(fn):
                    if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "Store":
                        bad.append(f"{path.name}:{fn.name}:{c.lineno} direct Store(...) open")
    assert not bad, "\n".join(bad)


# ---- the gmd-curator `top mentions` lines → `rmx primer` (r1 M3) ------------------------


@pytest.mark.parametrize("rel", ["src/refmatrix/templates/agents/gmd-curator.md",
                                 ".claude/agents/gmd-curator.md"])
def test_gmd_curator_no_longer_teaches_top_mentions(rel):
    text = (_REPO / rel).read_text()
    assert "rmx top mentions" not in text, f"{rel} still teaches `rmx top mentions -k N`"
    assert "rmx primer" in text, f"{rel}: the most-referenced entities are `rmx primer`"


# ---- C1 / C6: the batch-B verbs are generated MCP tools; per-action defaults ------------

_BATCH_B_ACTIONS = {
    "rmx_graph": {"neighbors", "co_occur", "top", "describe", "recall", "dense", "stats",
                  "timeline"},
    "rmx_canon": {"find", "siblings", "link"},
}


@pytest.mark.parametrize("vname", sorted(_BATCH_B_ACTIONS))
def test_batch_b_verb_is_a_generated_mcp_tool_with_its_actions(vname):
    import refmatrix.mcp as mcp
    assert vname in verbs.VERBS and vname in mcp.TOOLS, vname
    schema = mcp.TOOLS[vname]["schema"]
    assert schema == verbs.VERBS[vname].schema
    assert set(schema["properties"]["action"]["enum"]) == _BATCH_B_ACTIONS[vname]


def test_graph_action_defaults_resolve_the_shared_param_conflicts():
    """r1 S1: `limit` 50 vs 20, `k` 10 vs 40, `linkage` multi/None vs "mentions";
    recall / dense carry the 180 s cold-model budget (#budgets)."""
    ad = verbs.ACTION_DEFAULTS
    assert ad[("rmx_graph", "neighbors")]["limit"] == 50
    assert ad[("rmx_graph", "co_occur")]["limit"] == 20
    assert ad[("rmx_graph", "co_occur")]["linkage"] == "mentions"
    assert ad[("rmx_graph", "top")]["linkage"] == "mentions"
    assert ad[("rmx_graph", "top")]["k"] == 10
    assert ad[("rmx_graph", "timeline")]["k"] == 40
    assert ad[("rmx_graph", "recall")]["timeout"] == 180.0
    assert ad[("rmx_graph", "dense")]["timeout"] == 180.0
    import inspect
    sig = inspect.signature(verbs.graph)
    for p in ("limit", "k", "linkage"):
        assert sig.parameters[p].default is None, f"{p}: a per-action default is X | None = None"


# ---- recall / dense with NO daemon (spec b12c0ed #fam-graph-read-recall "No daemon") -----
#
# C4a: on VerbAbsentError ONLY, recall / dense run the SAME library function the
# `graph_recall` / `ann_search` op runs, in-process over a read-only store, with the
# embedder from the ONE module-level accessor `recall.shared_embedder(root)` — which
# `Daemon._embedder` delegates to, so no in-process `Daemon(...)` is ever needed (C3) —
# patched here to the ONE HashEmbedder for both paths; `source: "in-process"`. Busy
# never runs in-process.
# RMX_RERANK=0 keeps the cross-encoder (on by default) out of both paths.


def _op_result(root, op, args):
    s = Store(root)
    s.init()
    d = dm.Daemon(root)
    d.store = s
    d._log = lambda msg: None
    try:
        return dm.OPS[op](d, {"partition": discovery.store_name(root), **args})
    finally:
        s.close()


@pytest.mark.parametrize("case", sorted(_BASE_ORDER))
def test_recall_with_no_daemon_ranks_exactly_as_the_daemon_op(gstore, monkeypatch, case):
    root, _ids = gstore
    monkeypatch.setenv("RMX_RERANK", "0")
    monkeypatch.setattr("refmatrix.recall.shared_embedder", lambda root, *a, **k: HashEmbedder())
    assert not dm.ping(root)
    args, expected = _BASE_ORDER[case]
    out = verbs.graph(root, action="recall", k=10, **args)
    got = [(h["id"], round(float(h["score"]), 4)) for h in out["hits"]]
    assert got == expected, (case, got)
    assert out["source"] == "in-process", out
    assert "graph_recall" in dm.OPS
    op = _op_result(root, "graph_recall", {"k": 10, "kinds": None, **args})
    assert [(h["id"], round(float(h["score"]), 4)) for h in op["hits"]] == got, (
        "the no-daemon path and the daemon op disagree")


def test_dense_with_no_daemon_ranks_exactly_as_the_ann_search_op(gstore, monkeypatch):
    root, _ids = gstore
    monkeypatch.setenv("RMX_RERANK", "0")
    monkeypatch.setattr("refmatrix.recall.shared_embedder", lambda root, *a, **k: HashEmbedder())
    assert not dm.ping(root)
    out = verbs.graph(root, action="dense", query="document number 3", k=10)
    assert out["source"] == "in-process", out
    op = _op_result(root, "ann_search", {"query": "document number 3", "k": 10,
                                         "rerank": False})
    want = [(h["id"], round(float(h["distance"]), 4)) for h in op["hits"]]
    got = [(h["id"], round(float(h["distance"]), 4)) for h in out["hits"]]
    assert got == want and got[0][0] == 6, (got, want)
    assert out["hits"][0]["name"] == "d3.md"


@pytest.mark.parametrize("action,kw", [("recall", {"query": "document number 3"}),
                                       ("dense", {"query": "document number 3"})])
def test_recall_and_dense_on_a_busy_daemon_never_run_in_process(silent_with_snapshot,
                                                                monkeypatch, action, kw):
    loaded: list = []
    monkeypatch.setattr("refmatrix.recall.shared_embedder",
                        lambda root, *a, **k: loaded.append("shared_embedder") or HashEmbedder())

    class _NoModel:
        def __init__(self, *a, **k):
            loaded.append("Embedder()")
            raise AssertionError("embedder constructed under a busy daemon")
    monkeypatch.setattr("refmatrix.embedder.Embedder", _NoModel)
    opened: list = []
    real = Store.__init__

    def rec(self, root, *a, **k):
        opened.append((str(root), k.get("read_only")))
        return real(self, root, *a, **k)
    monkeypatch.setattr(Store, "__init__", rec)
    with pytest.raises(verbs.VerbBusyError):
        verbs.graph(silent_with_snapshot.root, action=action, **kw)
    assert opened == [], f"an in-process store was opened under a busy daemon: {opened}"
    assert loaded == [], f"an embedder was loaded under a busy daemon: {loaded}"


def test_the_daemon_embedder_accessor_delegates_to_the_one_shared_seam(gstore, monkeypatch):
    """The daemon path and the in-process path provably share ONE embedder seam."""
    root, _ids = gstore
    sentinel = HashEmbedder()
    seen: list = []
    monkeypatch.setattr("refmatrix.recall.shared_embedder",
                        lambda r, *a, **k: seen.append(r) or sentinel)
    d = dm.Daemon(root)
    d._log = lambda msg: None
    assert d._embedder() is sentinel, "Daemon._embedder does not delegate to recall.shared_embedder"
    assert seen, "recall.shared_embedder was never asked"


@pytest.mark.parametrize("action,kw", [("recall", {"query": "document number 3"}),
                                       ("dense", {"query": "document number 3"})])
def test_the_no_daemon_path_never_constructs_a_daemon(gstore, monkeypatch, action, kw):
    """C3: never an in-process `Daemon(...)` — the old search-dense fallback built one."""
    root, _ids = gstore
    monkeypatch.setenv("RMX_RERANK", "0")
    monkeypatch.setattr("refmatrix.recall.shared_embedder", lambda r, *a, **k: HashEmbedder())
    built: list = []
    real = dm.Daemon.__init__

    def rec(self, *a, **k):
        built.append(a[:1])
        return real(self, *a, **k)
    monkeypatch.setattr(dm.Daemon, "__init__", rec)
    out = verbs.graph(root, action=action, k=10, **kw)
    assert out["source"] == "in-process", out
    assert built == [], f"Daemon(...) constructed on the in-process {action} path: {built}"
