"""STM topic-composite: build a GMD subgraph of the session's current focus
(a running aggregate of every prompt+result), injected by scan-prompt with its
own autoscaling token budget, and keep hub/notification noise out of STM.
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from refmatrix import stm as stm_mod
from refmatrix.cli import main, _is_ambient_prompt
from refmatrix.composite import (
    _is_junk, _render_gmd, _scaled_budget, build_topic_composite,
)
from refmatrix.scan import scan_prompt
from refmatrix.store import Store
from refmatrix.stm import topic_composites


def _seed(root):
    """Two clean topic threads (parser/lexer, daemon/socket) in a session."""
    s = stm_mod.Stm(root, "sess")
    s.record("input", "parser and lexer", refs=["parser.py", "lexer"])
    s.record("tool", "edit parser lexer", refs=["parser.py", "lexer", "tokens"])
    s.record("input", "daemon socket", refs=["daemon", "socket"])
    s.record("tool", "daemon socket bind", refs=["daemon", "socket", "bind"])
    s.record("input", "parser lexer again", refs=["parser.py", "lexer"])
    return s


# ---- junk gate ----

def test_is_junk_gates_ids_hex_paths_keeps_words():
    for bad in ("toolu_01ABC", "wf_deadbeef", "a02b61d4963696b49", "a22a",
                "e8fb2e", "/private/tmp/claude/x/y/z", "d290f1ee-6c54-4b01"):
        assert _is_junk(bad), bad
    for good in ("parser.py", "lexer", "daemon", "face", "cafe",
                 "build_context", "stm.py"):
        assert not _is_junk(good), good


# ---- budget autoscale ----

def test_scaled_budget_floor_ramp_ceiling():
    assert _scaled_budget(1200, 0, autoscale=True, ceiling=3000, per_turn=15) == 1200
    assert _scaled_budget(1200, 60, autoscale=True, ceiling=3000, per_turn=15) == 2100
    assert _scaled_budget(1200, 10_000, autoscale=True, ceiling=3000, per_turn=15) == 3000
    # disabled → always the floor
    assert _scaled_budget(1200, 10_000, autoscale=False, ceiling=3000, per_turn=15) == 1200


# ---- topic_composites (induced subgraphs, top-k) ----

def test_topic_composites_splits_threads(tmp_path):
    root = tmp_path / ".refmatrix"
    _seed(root)
    g = stm_mod.Stm(root, "sess").focus_graph(top=30)
    tcs = topic_composites(g, k=3)
    members = {frozenset(t["members"]) for t in tcs}
    assert frozenset({"parser.py", "lexer", "tokens"}) in members
    assert frozenset({"daemon", "socket", "bind"}) in members
    # every edge stays inside its cluster (induced subgraph invariant)
    for t in tcs:
        keep = set(t["members"])
        for e in t["edges"]:
            assert e["source"] in keep and e["target"] in keep


def test_topic_composites_respects_k(tmp_path):
    root = tmp_path / ".refmatrix"
    _seed(root)
    g = stm_mod.Stm(root, "sess").focus_graph(top=30)
    assert len(topic_composites(g, k=1)) == 1


# ---- build_topic_composite (STM-only; store unused when expand=False) ----

def test_build_composite_stm_only(tmp_path):
    root = tmp_path / ".refmatrix"
    _seed(root)
    out = build_topic_composite(None, root, expand=False, session="sess")
    assert "STM topic composite" in out
    assert "```gmd" in out
    assert "parser.py" in out and "daemon" in out
    # expand=False → no LTM lookups, so no grounded/external edges; the header +
    # Members line (the signal) still render. co-occurs is gone entirely.
    assert "Members:" in out and "co-occurs" not in out


def test_build_composite_empty_when_no_stm(tmp_path):
    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True)
    assert build_topic_composite(None, root, expand=False) == ""


def test_build_composite_drops_junk_and_noise_topics(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "sess")
    # one clean thread + one all-junk thread
    s.record("input", "parser lexer", refs=["parser.py", "lexer"])
    s.record("tool", "p", refs=["parser.py", "lexer"])
    s.record("input", "ids", refs=["toolu_01A", "a02b61d4963696b49"])
    s.record("tool", "ids2", refs=["toolu_01A", "a02b61d4963696b49"])
    out = build_topic_composite(None, root, expand=False, session="sess")
    assert "toolu_01A" not in out
    assert "a02b61d4963696b49" not in out
    assert "parser.py" in out  # clean thread survives


# ---- intra-cluster edges: grounded real verbs, not weak co-occurs ----

def _intra_topic():
    # A cluster of three members; the durable graph links A→B (calls) but A's
    # other neighbor `xtern` is NOT a member (external bridge).
    return {
        "members": ["parser", "lexer", "tokens"],
        "nodes": [{"name": "parser", "freq": 3}, {"name": "lexer", "freq": 2},
                  {"name": "tokens", "freq": 1}],
        "edges": [],  # STM co-occurs is no longer consulted
    }


def _patch_bc(monkeypatch, groups_for):
    import types
    import refmatrix.composite as C

    def fake_build_context(s, name, **kw):
        ents = groups_for(name)
        if not ents:
            return types.SimpleNamespace(anchor=None, groups={})
        return types.SimpleNamespace(
            anchor=types.SimpleNamespace(id=0, name=name), groups=ents)

    monkeypatch.setattr(C, "build_context", fake_build_context)
    import refmatrix.pagerank as PR
    monkeypatch.setattr(PR, "load_scores", lambda s: {})


def test_intra_cluster_emits_real_verb_not_cooccurs(monkeypatch):
    import types
    import refmatrix.composite as C

    def groups_for(name):
        if name == "parser":  # parser calls lexer (member) + mentions xtern (ext)
            return {"calls": [types.SimpleNamespace(
                        entity=types.SimpleNamespace(id=1, name="lexer"))],
                    "mentions": [types.SimpleNamespace(
                        entity=types.SimpleNamespace(id=9, name="xtern"))]}
        return {}

    _patch_bc(monkeypatch, groups_for)
    out = C._render_gmd(
        object(), [_intra_topic()], expand=True, per_node_entities=4,
        expand_nodes_per_topic=3, max_expansions=6, max_tokens=5000, turn=1,
        intra_edges=3)
    assert "co-occurs" not in out                       # weak relation gone
    assert "rel: calls -> [[lexer]] {from: parser, graph: 1}" in out  # grounded
    assert "rel: mentions -> [[xtern]] {anchor: parser, ltm: 1}" in out  # ext kept


def test_intra_edges_zero_drops_grounded_block(monkeypatch):
    import types
    import refmatrix.composite as C

    def groups_for(name):
        if name == "parser":
            return {"calls": [types.SimpleNamespace(
                entity=types.SimpleNamespace(id=1, name="lexer"))]}
        return {}

    _patch_bc(monkeypatch, groups_for)
    out = C._render_gmd(
        object(), [_intra_topic()], expand=True, per_node_entities=4,
        expand_nodes_per_topic=3, max_expansions=6, max_tokens=5000, turn=1,
        intra_edges=0)
    assert "graph: 1" not in out       # no grounded intra edges
    assert "parser" in out             # header/Members still present


# ---- LTM expansion: sparse-first (low PageRank) + dedup across composite ----

def test_ltm_expansion_ranks_sparse_first_and_dedups(monkeypatch):
    import types
    import refmatrix.composite as C

    def _ent(eid, name):
        return types.SimpleNamespace(id=eid, name=name)

    def _entry(eid, name):
        return types.SimpleNamespace(entity=_ent(eid, name))

    # Every anchor resolves to the same neighborhood: a hub target (high PR) and
    # a sparse target (low PR), plus one target shared across anchors.
    def fake_build_context(s, name, **kw):
        return types.SimpleNamespace(
            anchor=_ent(999, name),
            groups={"mentions": [
                _entry(1, "hub_memory"),      # high centrality → demote
                _entry(2, "sparse_bridge"),   # low centrality → aha, surface
                _entry(3, "shared_target"),   # appears for every anchor → dedup
            ]})

    import refmatrix.pagerank as PR
    monkeypatch.setattr(C, "build_context", fake_build_context)
    monkeypatch.setattr(PR, "load_scores", lambda s: {1: 0.90, 2: 0.01, 3: 0.50})

    topic = {
        "members": ["alpha", "bravo"],
        "nodes": [{"name": "alpha", "freq": 1}, {"name": "bravo", "freq": 1}],
        "edges": [],
    }
    out = C._render_gmd(
        object(), [topic], expand=True, per_node_entities=2,
        expand_nodes_per_topic=2, max_expansions=6, max_tokens=5000, turn=1,
        intra_edges=0)
    ltm = [ln for ln in out.splitlines() if "ltm: 1" in ln]
    # sparse_bridge (lowest PR) ranks above hub_memory within an anchor
    joined = "\n".join(ltm)
    assert "sparse_bridge" in joined and "hub_memory" in joined
    assert joined.index("sparse_bridge") < joined.index("hub_memory")
    # shared_target emitted once across the whole composite (dedup), not per-anchor
    assert joined.count("[[shared_target]]") == 1


# ---- cadence gate (inject every Nth turn) ----

def test_composite_every_gates_on_turn(tmp_path):
    root = tmp_path / ".refmatrix"
    _seed(root)
    turn = stm_mod.Stm(root, "sess").focus_graph(top=30)["turn"]
    assert turn > 0
    # every=1 always renders
    assert build_topic_composite(None, root, expand=False, session="sess", every=1)
    # a divisor of turn renders (turn % turn == 0); turn+1 never divides → skip
    assert build_topic_composite(
        None, root, expand=False, session="sess", every=turn)
    assert build_topic_composite(
        None, root, expand=False, session="sess", every=turn + 1) == ""


def test_scan_prompt_composite_every_suppresses(tmp_path):
    root = tmp_path / ".refmatrix"
    _seed(root)
    turn = stm_mod.Stm(root, "sess").focus_graph(top=30)["turn"]
    s = Store(root)
    out = scan_prompt(
        s, "nothing matches here", composite=True, composite_root=root,
        composite_expand=False, composite_every=turn + 1)
    assert "STM topic composite" not in out


# ---- scan-prompt append / omit ----

def test_scan_prompt_appends_composite(tmp_path):
    root = tmp_path / ".refmatrix"
    _seed(root)
    s = Store(root)  # empty long-term store; composite still appends
    out = scan_prompt(
        s, "nothing matches here",
        composite=True, composite_root=root, composite_expand=False)
    assert "STM topic composite" in out


def test_scan_prompt_no_composite_when_disabled(tmp_path):
    root = tmp_path / ".refmatrix"
    _seed(root)
    s = Store(root)
    out = scan_prompt(s, "nothing matches here", composite=False)
    assert "STM topic composite" not in out


def test_scan_prompt_json_never_carries_composite(tmp_path):
    root = tmp_path / ".refmatrix"
    _seed(root)
    s = Store(root)
    out = scan_prompt(
        s, "parser", fmt="json",
        composite=True, composite_root=root, composite_expand=False)
    # valid JSON, no GMD block spliced in
    json.loads(out) if out.strip() else None
    assert "STM topic composite" not in out


# ---- ambient-prompt gate (hub/notification never enters STM) ----

def test_ambient_prompt_detection():
    assert _is_ambient_prompt('<channel source="refmatrix" channel="global:queues">{}</channel>')
    assert _is_ambient_prompt("  <task-notification>x</task-notification>")
    assert _is_ambient_prompt("[SYSTEM NOTIFICATION - NOT USER INPUT]\nfoo")
    assert not _is_ambient_prompt("add a daemon restart command")
    assert not _is_ambient_prompt("")


def test_focus_hook_skips_ambient_channel_message(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"
    monkeypatch.setenv("RMX_SESSION", "hooksess")
    # patch _root() so the hook writes under tmp
    import refmatrix.cli as cli
    monkeypatch.setattr(cli, "_root", lambda: root)
    envelope = json.dumps({
        "session_id": "hooksess",
        "prompt": '<channel source="refmatrix" channel="global:queues">{"q":1}</channel>',
    })
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"],
                           input=envelope, catch_exceptions=False)
    assert r.exit_code == 0
    # nothing recorded → no ring for this session
    st = stm_mod.Stm(root, "hooksess")
    assert st.event_count() == 0


def test_rebuild_focus_drops_ambient_keeps_ring(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "sess")
    s.record("input", "work on parser.py", refs=["parser.py", "lexer"])
    # ambient turns older ingests admitted (channel + notification)
    s.record("input", '<channel source="hub">{"q":1}</channel>', refs=["channel"])
    s.record("input", "<task-notification>x</task-notification>", refs=["notification"])
    before = s.event_count()
    st = s.rebuild_focus(dry_run=True)
    assert st["dropped_events"] == 2 and st["dry_run"] is True
    # dry-run leaves ring intact and does not rewrite the graph
    assert s.event_count() == before
    st2 = s.rebuild_focus()
    assert st2["dropped_events"] == 2 and st2["dry_run"] is False
    g = stm_mod.Stm(root, "sess").focus_graph(top=30)
    names = {n["name"] for n in g["nodes"]}
    assert "channel" not in names and "notification" not in names
    assert "parser.py" in names  # real ref survives
    assert s.event_count() == before  # ring preserved


def test_focus_hook_records_real_prompt(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"
    monkeypatch.setenv("RMX_SESSION", "hooksess2")
    import refmatrix.cli as cli
    monkeypatch.setattr(cli, "_root", lambda: root)
    envelope = json.dumps({"session_id": "hooksess2",
                           "prompt": "work on parser.py"})
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"],
                           input=envelope, catch_exceptions=False)
    assert r.exit_code == 0
    st = stm_mod.Stm(root, "hooksess2")
    assert st.event_count() == 1
