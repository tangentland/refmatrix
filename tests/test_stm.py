"""Phase 5b: short-term memory focus graph + task pushdown stack + isolation."""
from __future__ import annotations

from refmatrix.stm import Stm, _extract_refs


def test_record_and_tail(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("input", "look at build_context in context.py")
    s.record("rmx", "context build_context", refs=["build_context"])
    rows = s.tail(10)
    assert len(rows) == 2
    assert rows[0]["kind"] == "input" and rows[1]["kind"] == "rmx"
    assert "build_context" in rows[1]["refs"]


def test_ring_trims_to_size(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess", size=10)
    for i in range(200):
        s.record("tool", f"edit file_{i}.py", refs=[f"file_{i}.py"])
    rows = s.all_events()
    assert len(rows) <= 10 + 64  # trims with a margin
    # most recent retained
    assert rows[-1]["refs"] == ["file_199.py"]


def test_focus_graph_ranks_by_recency_weight(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    for _ in range(3):
        s.record("tool", "x", refs=["old_thing"])
    for _ in range(3):
        s.record("tool", "x", refs=["hot_thing"])
    g = s.focus_graph(top=10)
    names = [n["name"] for n in g["nodes"]]
    # hot_thing is more recent → ranks above old_thing
    assert names.index("hot_thing") < names.index("old_thing")
    assert g["focus"][0] == "hot_thing"


def test_focus_graph_edges_cooccur(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("tool", "x", refs=["a.py", "b.py"])
    s.record("tool", "x", refs=["a.py", "b.py"])
    g = s.focus_graph(top=10)
    pairs = {(e["source"], e["target"]) for e in g["edges"]}
    assert ("a.py", "b.py") in pairs


def test_task_push_pop_restores_focus(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("tool", "x", refs=["refactor_target"])
    s.task_push("refactor X")
    assert s.task_current()["desc"] == "refactor X"
    # tangent
    s.record("tool", "x", refs=["test_failure"])
    s.task_push("chase test")
    assert s.current_task_desc() == "chase test"
    assert len(s.task_list()) == 2
    r = s.task_pop()
    assert r["popped"] == "chase test"
    assert r["restored"] == "refactor X"
    assert "refactor_target" in r["restored_focus"]


def test_task_swap(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.task_push("a")
    s.task_push("b")
    assert s.task_current()["desc"] == "b"
    r = s.task_swap()
    assert r["swapped"] and r["current"] == "a"


def test_events_tagged_with_current_task(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.task_push("big task")
    ev = s.record("tool", "work", refs=["z"])
    assert ev["task"] == "big task"


def test_clear(tmp_path):
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("tool", "x", refs=["y"])
    s.task_push("t")
    s.clear()
    assert s.tail() == []
    assert s.task_list() == []


def test_isolation_between_projects(tmp_path):
    a = Stm(tmp_path / "A" / ".refmatrix", "s")
    b = Stm(tmp_path / "B" / ".refmatrix", "s")
    a.record("tool", "x", refs=["only_in_a"])
    assert any("only_in_a" in e["refs"] for e in a.tail())
    assert b.tail() == []  # B never sees A's focus


def test_extract_refs():
    refs = _extract_refs("edited context.py and called build_context for the parser")
    assert "context.py" in refs
    assert "build_context" in refs
    assert "the" not in refs  # stopword
