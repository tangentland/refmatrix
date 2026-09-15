"""MCP `rmx_memory_recall` must do DENSE recall on the MEMORY partition.

Regression for the read-side twin of the embed wrong-partition bug: the handler
used to call the lexical `memory_search` op against `store_name(root)` (the code
partition), so natural-language recall returned `[]` while the CLI (dense, memory
partition) returned ranked hits. These tests capture the daemon ops the handler
issues; no store/model needed.
"""
from __future__ import annotations

import refmatrix.mcp as mcp
import refmatrix.daemon as daemon_mod


def _mock_daemon(monkeypatch, calls, *, legacy_present: bool):
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)

    def fake_call(root, op, args, timeout=None, **kw):
        calls.append((op, args))
        if op == "partition_list":
            rows = [{"name": "memory-proj"}] if legacy_present else [{"name": "proj"}]
            return {"ok": True, "result": {"rows": rows}}
        if op == "memory_recall":
            return {"ok": True, "result": {"hits": [{"id": 7, "distance": 0.1}]}}
        if op == "memory_get":
            return {"ok": True, "result": {"memory": {"id": 7, "name": "m7"}}}
        if op == "memory_recent":
            return {"ok": True, "result": {"rows": [{"id": 9, "name": "recent9"}]}}
        return {"ok": False}

    monkeypatch.setattr(daemon_mod, "call", fake_call)
    # store_name drives the project partition name; keep it deterministic.
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda root: "proj")


def test_recall_uses_dense_op_on_memory_partition(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []
    _mock_daemon(monkeypatch, calls, legacy_present=True)

    out = mcp._t_memory_recall(
        {"query": "some natural language phrase", "k": 3, "scope": "project",
         "root": str(tmp_path)})

    ops = [op for op, _ in calls]
    assert "memory_search" not in ops, "must NOT use lexical substring op"
    recall = next(a for op, a in calls if op == "memory_recall")
    # dense on the memory partition, memory kind only, dense-not-fused
    assert recall["partition"] == "memory-proj"
    assert recall["kinds"] == ["memory"]
    assert recall["fuse"] is False
    row = out["memories"][0]
    assert (row["id"], row["name"], row["scope"]) == (7, "m7", "project")
    # dense rows carry the ranking fields the CLI shows (plan-3 r1 #sk-4)
    assert row["distance"] == 0.1 and row["fused"] is False and "score" in row


def test_recall_falls_back_to_project_partition_post_merge(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []
    _mock_daemon(monkeypatch, calls, legacy_present=False)

    mcp._t_memory_recall(
        {"query": "q", "k": 2, "scope": "project", "root": str(tmp_path)})

    recall = next(a for op, a in calls if op == "memory_recall")
    # No legacy memory-<project> partition → route to the project partition.
    assert recall["partition"] == "proj"


def test_resolve_root_targets_project_by_name(tmp_path, monkeypatch):
    # Two stores discovered; cwd is NEITHER. `project` must resolve the right
    # root independent of the MCP server's cwd (the recall-drift fix).
    clq = tmp_path / "cliquedb" / ".refmatrix"
    via = tmp_path / "viascope" / ".refmatrix"
    clq.mkdir(parents=True); via.mkdir(parents=True)
    monkeypatch.setattr("refmatrix.discovery.discover_roots",
                        lambda: [clq, via])
    monkeypatch.setattr("refmatrix.discovery.store_name",
                        lambda root: root.parent.name)
    assert mcp._resolve_root({"project": "cliquedb"}) == clq
    assert mcp._resolve_root({"project": "viascope"}) == via


def test_resolve_root_explicit_root_beats_project(tmp_path, monkeypatch):
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [])
    # `root` wins over `project`; path normalized to the .refmatrix dir.
    got = mcp._resolve_root({"root": str(tmp_path), "project": "ignored"})
    assert got == tmp_path / ".refmatrix"


def test_resolve_root_unknown_project_falls_through(tmp_path, monkeypatch):
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [])
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    # Unknown project name → no match → next precedence (REFMATRIX_ROOT).
    assert mcp._resolve_root({"project": "nope"}) == tmp_path / ".refmatrix"


def test_empty_query_uses_recent_on_memory_partition(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []
    _mock_daemon(monkeypatch, calls, legacy_present=True)

    out = mcp._t_memory_recall({"scope": "project", "root": str(tmp_path)})

    ops = [op for op, _ in calls]
    assert "memory_recent" in ops and "memory_recall" not in ops
    recent = next(a for op, a in calls if op == "memory_recent")
    assert recent["partition"] == "memory-proj"
    assert out["memories"] == [{"id": 9, "name": "recent9", "scope": "project"}]


# --- _root slug-decode: cwd under ~/.claude/projects/<slug>/ ----------------

def test_root_decodes_projects_slug_to_project_store(tmp_path, monkeypatch):
    import refmatrix.cli as cli
    from pathlib import Path
    # A discovered project store whose parent encodes to <slug>.
    proj = tmp_path / "github" / "acme" / "widget"
    root = proj / ".refmatrix"
    root.mkdir(parents=True)
    slug = str(proj.resolve()).replace("/", "-").replace("_", "-")
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [root])
    # cwd standing inside ~/.claude/projects/<slug>/memory
    cwd = Path.home() / ".claude" / "projects" / slug / "memory"
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: cwd))
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    assert cli._root() == root  # NOT the global home store


def test_root_from_projects_slug_no_match_returns_none(tmp_path, monkeypatch):
    import refmatrix.cli as cli
    from pathlib import Path
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [])
    cwd = Path.home() / ".claude" / "projects" / "-nonexistent-proj" / "memory"
    assert cli._root_from_projects_slug(cwd) is None
    # a cwd outside ~/.claude/projects → None (not a projects-slug dir)
    assert cli._root_from_projects_slug(tmp_path) is None
