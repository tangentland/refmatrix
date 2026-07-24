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
    assert "rel: co-occurs ->" in out


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


# ---- co-occurs edge selection: outliers (lift) not bulk (weight) ----

def test_cooccur_ranks_by_lift_not_weight():
    # `hub` co-occurs heavily with everything (bulk); `a`/`b` are a rare tight
    # pair (outlier). Raw weight favors hub; lift favors the a-b binding.
    topic = {
        "members": ["hub", "aardvark", "boron", "xigma", "yotta"],
        "nodes": [
            {"name": "hub", "freq": 10}, {"name": "aardvark", "freq": 1},
            {"name": "boron", "freq": 1}, {"name": "xigma", "freq": 5},
            {"name": "yotta", "freq": 5}],
        "edges": [
            {"source": "hub", "target": "xigma", "weight": 4},
            {"source": "hub", "target": "yotta", "weight": 4},
            {"source": "aardvark", "target": "boron", "weight": 2}],
    }
    out = _render_gmd(
        None, [topic], expand=False, per_node_entities=4,
        expand_nodes_per_topic=3, max_expansions=6, max_tokens=5000, turn=1,
        cooccur_edges=1)
    assert "[[boron]]" in out          # outlier pair rendered
    assert "[[xigma]]" not in out and "[[yotta]]" not in out  # hub bulk dropped


def test_cooccur_edges_zero_drops_block():
    topic = {
        "members": ["aardvark", "boron"],
        "nodes": [{"name": "aardvark", "freq": 1}, {"name": "boron", "freq": 1}],
        "edges": [{"source": "aardvark", "target": "boron", "weight": 2}],
    }
    out = _render_gmd(
        None, [topic], expand=False, per_node_entities=4,
        expand_nodes_per_topic=3, max_expansions=6, max_tokens=5000, turn=1,
        cooccur_edges=0)
    assert "co-occurs" not in out
    assert "aardvark" in out  # header/Members still present


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
