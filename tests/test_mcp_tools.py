"""MCP parity tools: payload mapping, registration, and cross-surface
consistency (MCP write visible to CLI read).
"""
from __future__ import annotations

from click.testing import CliRunner

import refmatrix.mcp as mcp
from refmatrix import stm as stm_mod
from refmatrix.cli import main


def test_all_new_tools_registered_with_valid_schema():
    for name in ("rmx_memory", "rmx_locate", "rmx_task",
                 "rmx_ingest", "rmx_ingest_status"):
        assert name in mcp.TOOLS, f"{name} not registered"
        t = mcp.TOOLS[name]
        assert callable(t["fn"])
        assert t["schema"]["type"] == "object"
        assert isinstance(t["description"], str) and t["description"]


def test_memory_payload_mirrors_daemon_op_contracts():
    # get / forget: id wins over name, coerced to int
    assert mcp._memory_payload("get", {"id": "7"}) == {"id": 7}
    assert mcp._memory_payload("forget", {"name": "m"}) == {"name": "m"}
    # list: only present optional keys
    assert mcp._memory_payload("list", {"mtype": "project", "limit": 5}) == {
        "mtype": "project", "limit": 5}
    # search: query required + optionals
    assert mcp._memory_payload("search", {"query": "q", "limit": 3}) == {
        "query": "q", "limit": 3}
    # reclassify: to_mtype + optionals
    assert mcp._memory_payload("reclassify", {"to_mtype": "feedback",
                                              "dry_run": True}) == {
        "to_mtype": "feedback", "dry_run": True}
    # link: src_name + concept + default linkage
    assert mcp._memory_payload("link", {"name": "m", "concept": "c"}) == {
        "src_name": "m", "linkage": "related-to", "concept": "c"}
    # score: concept + optionals
    assert mcp._memory_payload("score", {"concept": "c", "cap": 2.0}) == {
        "concept": "c", "cap": 2.0}
    # bulk_forget: dry_run default false + lists
    assert mcp._memory_payload("bulk_forget", {"mtypes": ["a"]}) == {
        "dry_run": False, "mtypes": ["a"]}
    # dedup
    assert mcp._memory_payload("dedup", {}) == {"dry_run": False}


def test_memory_action_op_map_covers_enum():
    # every non-special action in the tool enum maps to a daemon op
    enum = mcp.TOOLS["rmx_memory"]["schema"]["properties"]["action"]["enum"]
    special = {"recall", "add", "promote"}
    for action in enum:
        if action in special:
            continue
        assert action in mcp._MEMORY_OPS, f"{action} unmapped"


def test_mcp_task_push_visible_to_cli_list(tmp_path, monkeypatch):
    # MCP write (rmx_task push) must be visible to the CLI read (task list) —
    # both resolve the active session via the symmetric _session/_resolve.
    root = tmp_path
    (root / ".refmatrix").mkdir(parents=True)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root / ".refmatrix"))
    monkeypatch.delenv("RMX_SESSION", raising=False)
    # Seed an active session ring (what the hook does live).
    stm_mod.Stm(root / ".refmatrix", "claude-sess").record("input", "hi")

    r = mcp._t_task({"action": "push", "desc": "ship feature"})
    assert r["depth"] == 1 and r["current"] == "ship feature"

    out = CliRunner().invoke(main, ["task", "list"])
    assert out.exit_code == 0, out.output
    assert "ship feature" in out.output


def test_mcp_task_unknown_action_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    (tmp_path / ".refmatrix").mkdir(parents=True)
    r = mcp._t_task({"action": "bogus"})
    assert "error" in r


def test_locate_tool_delegates_to_federated(monkeypatch):
    seen = {}

    def fake(file, keywords, *, limit):
        seen.update(file=file, keywords=keywords, limit=limit)
        return {"results": []}

    monkeypatch.setattr("refmatrix.search.federated_locate", fake)
    mcp._t_locate({"file": "cli.py", "keywords": ["ingest"], "n": 3})
    assert seen == {"file": "cli.py", "keywords": ["ingest"], "limit": 3}
