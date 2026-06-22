"""MCP write-path tools (rmx_focus_note / rmx_memory_add / rmx_change_subject).

Daemon-down here, so these exercise the in-proc / STM fallback paths the handlers
take when no per-project daemon is up. The daemon-routed path reuses the same ops
covered by test_subject.py + the memory suite.
"""
from __future__ import annotations

from refmatrix import mcp, stm as stm_mod
from refmatrix.store import Store, default_partition_name


def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    monkeypatch.setenv("RMX_SESSION", "mcpsess")
    root = tmp_path / ".refmatrix"
    Store(root).init()
    return root


def test_focus_note_records_reason_event(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    out = mcp._t_focus_note({"text": "chose namespaced mtype to avoid a column",
                             "root": str(tmp_path)})
    assert out["noted"] is True
    assert out["session"] == "mcpsess"
    evs = stm_mod.Stm(root, "mcpsess").all_events()
    assert any(e["kind"] == "reason" for e in evs)


def test_focus_note_accepts_note_alias(tmp_path, monkeypatch):
    # cliquedb bug report: callers guess `note` (matching the tool name) instead
    # of the schema's `text`; that used to KeyError. Both keys must work now.
    root = _root(tmp_path, monkeypatch)
    out = mcp._t_focus_note({"note": "alias path", "root": str(tmp_path)})
    assert out["noted"] is True
    evs = stm_mod.Stm(root, "mcpsess").all_events()
    assert any(e["kind"] == "reason" for e in evs)


def test_focus_note_missing_text_raises_clean(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    import pytest
    with pytest.raises(ValueError, match="focus_note requires 'text'"):
        mcp._t_focus_note({"root": str(tmp_path)})


def test_memory_add_inproc(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    out = mcp._t_memory_add({"name": "m1", "content": "body",
                             "mtype": "note", "root": str(tmp_path)})
    assert "id" in out and out["id"]
    s = Store(root)
    with s.with_partition(default_partition_name(root)):
        m = s.get_memory("m1")
    assert m and m["mtype"] == "note"


def test_change_subject_sets_pointer_and_node(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    out = mcp._t_change_subject({"label": "Explore Hypertree", "root": str(tmp_path)})
    assert out["subject"] == "explore_hypertree"
    assert out["id"]
    # STM pointer is set for the session
    assert stm_mod.Stm(root, "mcpsess").get_subject()["subject"] == "explore_hypertree"
    # durable node exists
    s = Store(root)
    with s.with_partition(default_partition_name(root)):
        assert s.get_memory("subject_explore_hypertree")["mtype"] == "subject"


def test_change_subject_accepts_subject_alias(tmp_path, monkeypatch):
    # cliquedb bug report: callers guess `subject` instead of the schema's
    # `label`; that used to KeyError on both the daemon and in-proc paths.
    root = _root(tmp_path, monkeypatch)
    out = mcp._t_change_subject({"subject": "json attr mgmt", "root": str(tmp_path)})
    assert out["subject"] == "json_attr_mgmt"
    assert out["label"] == "json attr mgmt"
    assert out["id"]
    assert stm_mod.Stm(root, "mcpsess").get_subject()["subject"] == "json_attr_mgmt"


def test_change_subject_missing_label_raises_clean(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    import pytest
    with pytest.raises(ValueError, match="change_subject requires 'label'"):
        mcp._t_change_subject({"root": str(tmp_path)})
