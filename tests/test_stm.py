"""Phase 5b: short-term focus graph — scored eviction, in-place update, decay,
admission, frontier stubs, task stack, isolation."""
from __future__ import annotations

from refmatrix.stm import Stm, _extract_refs


def _turn(s, *refs):
    """Open a new turn (input, no extracted refs) + touch refs via a tool event."""
    s.record("input", "go", refs=[])  # refs=[] so the turn marker admits nothing
    if refs:
        s.record("tool", "work", refs=list(refs))


# ---- event ring ----


def test_record_and_tail(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("input", "look at build_context in context.py")
    s.record("rmx", "context build_context", refs=["build_context"])
    rows = s.tail(10)
    assert len(rows) == 2
    assert rows[1]["refs"] == ["build_context"]


def test_ring_trims_to_size(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess", size=10)
    for i in range(200):
        s.record("tool", f"edit f_{i}.py", refs=[f"f_{i}.py"])
    rows = s.all_events()
    assert len(rows) <= 10 + 64
    assert rows[-1]["refs"] == ["f_199.py"]


# ---- focus graph ----


def test_in_place_update_no_duplicates(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("tool", "x", refs=["thing"])
    s.record("tool", "x", refs=["thing"])
    g = s._load_graph()
    assert list(g["nodes"]).count("thing") == 1
    assert g["nodes"]["thing"]["freq"] == 2  # in-place bump, not append


def test_decay_lowers_recency(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("tool", "x", refs=["old"])
    r0 = s._load_graph()["nodes"]["old"]["recency"]
    for _ in range(4):
        _turn(s, "other")  # turns decay 'old' without touching it
    r1 = s._load_graph()["nodes"]["old"]["recency"]
    assert r1 < r0


def test_focus_ranks_recent_over_decayed(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("tool", "x", refs=["old_thing"])
    for _ in range(5):
        _turn(s)  # decay old_thing
    _turn(s, "hot_thing")
    names = [n["name"] for n in s.focus_graph(top=10)["nodes"]]
    assert names.index("hot_thing") < names.index("old_thing")


def test_focus_edges_cooccur(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("tool", "x", refs=["a.py", "b.py"])
    pairs = {(e["source"], e["target"]) for e in s.focus_graph()["edges"]}
    assert ("a.py", "b.py") in pairs


def test_admission_cap_per_turn(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    # one event with 50 refs — capped at MAX_ADMIT_PER_TURN (12)
    s.record("tool", "x", refs=[f"r{i}" for i in range(50)])
    real = [n for n, nd in s._load_graph()["nodes"].items() if not nd.get("frontier")]
    assert len(real) <= 12


def test_eviction_respects_budget_and_pin(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess", node_budget=10)
    s.record("tool", "x", refs=["KEEPME"])
    assert s.pin("KEEPME") is True
    for i in range(60):
        _turn(s, f"n{i}")  # churn well past budget
    g = s._load_graph()
    real = [n for n, nd in g["nodes"].items() if not nd.get("frontier")]
    assert len(real) <= 10
    assert "KEEPME" in g["nodes"]  # pinned survived eviction
    assert g["nodes"]["KEEPME"]["pin"] == 1


def test_frontier_stub_on_eviction_with_live_neighbor(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess", node_budget=3)
    # hub co-occurs with many; spokes get evicted but hub stays → stubs
    for i in range(20):
        s.record("tool", "x", refs=["hub", f"spoke{i}"])
        _turn(s)
    g = s._load_graph()
    has_frontier = any(nd.get("frontier") for nd in g["nodes"].values())
    real = [n for n, nd in g["nodes"].items() if not nd.get("frontier")]
    assert len(real) <= 3
    assert has_frontier  # some evicted spokes left breadcrumbs


def test_rehydrate_frontier_on_retouch(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess", node_budget=3)
    for i in range(20):
        s.record("tool", "x", refs=["hub", f"spoke{i}"])
        _turn(s)
    g = s._load_graph()
    front = [n for n, nd in g["nodes"].items() if nd.get("frontier")]
    if front:
        target = front[0]
        # re-touch across several turns so it out-scores and reclaims a seat
        for _ in range(4):
            _turn(s, target)
        assert s._load_graph()["nodes"][target]["frontier"] is False


# ---- task stack ----


def test_task_push_pop_restores_focus(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("tool", "x", refs=["refactor_target"])
    s.task_push("refactor X")
    _turn(s, "test_failure")
    s.task_push("chase test")
    assert s.current_task_desc() == "chase test"
    r = s.task_pop()
    assert r["popped"] == "chase test" and r["restored"] == "refactor X"
    assert "refactor_target" in r["restored_focus"]


def test_task_swap_clear(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.task_push("a"); s.task_push("b")
    assert s.task_swap()["current"] == "a"
    s.clear()
    assert s.task_list() == [] and s.tail() == []


def test_isolation_between_projects(tmp_path):
    a = Stm(tmp_path / "A" / ".refmatrix", "s")
    b = Stm(tmp_path / "B" / ".refmatrix", "s")
    a.record("tool", "x", refs=["only_in_a"])
    assert "only_in_a" in a._load_graph()["nodes"]
    assert b._load_graph()["nodes"] == {}


def test_extract_refs():
    refs = _extract_refs("edited context.py and called build_context for the parser")
    assert "context.py" in refs and "build_context" in refs and "the" not in refs


# ---- latest_session resolution (read surfaces default to the active session) ----


def test_latest_session_none_when_empty(tmp_path):
    from refmatrix.stm import latest_session
    assert latest_session(tmp_path / ".refmatrix") is None


def test_latest_session_picks_most_recent_ring(tmp_path):
    import os
    from refmatrix.stm import latest_session
    root = tmp_path / ".refmatrix"
    a = Stm(root, "sess-a")
    a.record("tool", "old work", refs=["a.py"])
    b = Stm(root, "sess-b")
    b.record("tool", "new work", refs=["b.py"])
    # Force b's ring to be newer regardless of filesystem mtime granularity.
    os.utime(root / "stm" / "sess-a.jsonl", (1, 1))
    os.utime(root / "stm" / "sess-b.jsonl", (2, 2))
    assert latest_session(root) == "sess-b"


def test_latest_session_ignores_tmp(tmp_path):
    from refmatrix.stm import latest_session
    root = tmp_path / ".refmatrix"
    s = Stm(root, "real")
    s.record("tool", "work", refs=["x.py"])
    (root / "stm" / "scratch.jsonl.tmp").write_text("{}\n")
    assert latest_session(root) == "real"


# ---- ref extraction noise filtering (clean focus graph) ----


def test_extract_refs_drops_shell_words():
    refs = _extract_refs("Bash echo hi && grep -n foo src/refmatrix/stm.py")
    assert "src/refmatrix/stm.py" in refs        # real path kept
    for noise in ("Bash", "echo", "grep"):       # stoplisted shell words
        assert noise not in refs


def test_extract_refs_drops_home_path_segments():
    refs = _extract_refs("cat /Users/tholley/claude_tools/refmatrix/notes.md")
    assert any(r.endswith("notes.md") for r in refs)
    for seg in ("Users", "tholley", "claude_tools"):
        assert seg not in refs
