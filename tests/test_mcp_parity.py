"""CLI/MCP parity regressions (audit 2026-09-06): the MCP surface must call
the same ops with the same defaults as the CLI, or agents silently get a
degraded store."""
from __future__ import annotations

import json

import refmatrix.mcp as mcp
from refmatrix import daemon as daemon_mod


class _Calls:
    def __init__(self, results=None):
        self.log = []
        self.results = results or {}

    def __call__(self, root, op, args, timeout=0.0, **kw):
        self.log.append((op, args))
        return self.results.get(op, {"ok": True, "result": {}})


def _patch_daemon(monkeypatch, calls):
    monkeypatch.setattr(daemon_mod, "ping", lambda *a, **k: True)
    monkeypatch.setattr(daemon_mod, "call", calls)


def test_query_sends_expr_not_dsl(monkeypatch, tmp_path):
    calls = _Calls({"query": {"ok": True, "result": {"rows": []}}})
    _patch_daemon(monkeypatch, calls)
    monkeypatch.setattr(mcp, "_resolve_root", lambda a: tmp_path)
    out = mcp._t_query({"dsl": "mentions:x"})
    assert "error" not in out
    op, args = calls.log[0]
    assert op == "query" and args["expr"] == "mentions:x"
    assert "dsl" not in args


def test_ingest_semantic_defaults_on(monkeypatch, tmp_path):
    calls = _Calls({"ingest_path_start": {"ok": True, "result": {"job_id": "j"}}})
    _patch_daemon(monkeypatch, calls)
    monkeypatch.setattr(mcp, "_resolve_root", lambda a: tmp_path)
    mcp._t_ingest({})
    op, args = calls.log[0]
    assert op == "ingest_path_start" and args["semantic"] is True
    calls.log.clear()
    mcp._t_ingest({"semantic": False})
    assert calls.log[0][1]["semantic"] is False


def test_memory_add_routes_legacy_partition(monkeypatch, tmp_path):
    calls = _Calls({"memory_add": {"ok": True, "result": {"id": 1}}})
    _patch_daemon(monkeypatch, calls)
    monkeypatch.setattr(mcp, "_resolve_root", lambda a: tmp_path)
    from refmatrix import verbs
    monkeypatch.setattr(verbs, "memory_partition", lambda root: "memory-proj")
    mcp._t_memory_add({"name": "n", "content": "c"})
    op, args = calls.log[0]
    assert op == "memory_add" and args["partition"] == "memory-proj"


def test_recall_defaults_project_scope_and_excludes_session(monkeypatch, tmp_path):
    hits = {"ok": True, "result": {"hits": [
        {"id": 1, "distance": 0.1}, {"id": 2, "distance": 0.2}]}}
    gets = {1: {"name": "a", "mtype": "session/digest"},
            2: {"name": "b", "mtype": "project"}}

    class _C(_Calls):
        def __call__(self, root, op, args, timeout=0.0, **kw):
            self.log.append((op, args))
            if op == "memory_recall":
                return hits
            if op == "memory_get":
                return {"ok": True,
                        "result": {"memory": dict(gets[args["id"]])}}
            return {"ok": True, "result": {}}

    calls = _C()
    _patch_daemon(monkeypatch, calls)
    monkeypatch.setattr(mcp, "_resolve_root", lambda a: tmp_path)
    from refmatrix import verbs
    monkeypatch.setattr(verbs, "memory_partition", lambda root, **kw: "p")
    out = mcp._t_memory_recall({"query": "q"})
    names = [m["name"] for m in out["memories"]]
    assert names == ["b"]                       # session/* dropped
    assert all(op != "memory_search" or False for op, _ in calls.log)
    # scope=project by default: no global call happened (daemon ops only).
    out2 = mcp._t_memory_recall({"query": "q", "exclude_mtype": []})
    assert [m["name"] for m in out2["memories"]] == ["a", "b"]


def test_context_passes_knobs_and_decodes_body(monkeypatch, tmp_path):
    body = json.dumps({"ref": "x", "helix_note": "[helix] ...", "groups": {}})
    calls = _Calls({"context": {"ok": True, "result": {"body": body}}})
    _patch_daemon(monkeypatch, calls)
    monkeypatch.setattr(mcp, "_resolve_root", lambda a: tmp_path)
    out = mcp._t_context({"ref": "x", "expand": 5, "hit_lines": "text",
                          "max_tokens": 900, "linkage": "mentions"})
    op, args = calls.log[0]
    assert args["expand"] == 5 and args["hit_lines"] == "text"
    assert args["max_tokens"] == 900 and args["tokens_explicit"] is True
    assert args["linkages"] == ["mentions"]
    assert out["helix_note"] == "[helix] ..."   # decoded, single-encoded


def test_schema_aliases_not_over_required():
    tools = mcp.TOOLS
    fn = tools["rmx_focus_note"]["schema"]
    assert "text" not in (fn.get("required") or [])
    cs = tools["rmx_change_subject"]["schema"]
    assert "label" not in (cs.get("required") or [])
    fs = tools["rmx_focus"]["schema"]
    assert "top" in fs["properties"]
    ctx = tools["rmx_context"]["schema"]["properties"]
    for k in ("expand", "hit_lines", "max_entities", "max_tokens"):
        assert k in ctx
    rec = tools["rmx_memory_recall"]["schema"]["properties"]
    for k in ("kinds", "fuse", "exclude_mtype"):
        assert k in rec
