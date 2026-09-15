"""Phase 8: MCP server dispatch, scheduler, federated concept."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix import mcp, scheduler, search, discovery


@pytest.fixture
def home(monkeypatch):
    d = tempfile.mkdtemp(prefix="rh", dir="/tmp")
    monkeypatch.setenv("RMX_HOME", d)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ---- MCP protocol ----


def test_mcp_initialize():
    r = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION
    assert r["result"]["capabilities"]["tools"] == {}


def test_mcp_tools_list_covers_surface():
    r = mcp.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in r["result"]["tools"]}
    assert {"rmx_where", "rmx_context", "rmx_memory_recall", "rmx_query",
            "rmx_bus_pub", "rmx_queues", "rmx_focus"} <= names
    for t in r["result"]["tools"]:
        assert "inputSchema" in t and "description" in t


def test_mcp_notification_no_response():
    assert mcp.handle_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_mcp_unknown_tool_errors():
    r = mcp.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": "nope", "arguments": {}}})
    assert "error" in r


def test_mcp_tool_call_returns_content(monkeypatch):
    monkeypatch.setattr(search.discovery, "discover_roots", lambda: [])
    # rmx_where with no live stores → empty results, wrapped as text content
    r = mcp.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                            "params": {"name": "rmx_where",
                                       "arguments": {"query": "x"}}})
    assert r["result"]["content"][0]["type"] == "text"
    assert r["result"]["isError"] is False


def test_mcp_focus_tool(tmp_path, monkeypatch):
    from refmatrix.stm import Stm
    root = tmp_path / ".refmatrix"; root.mkdir()
    Stm(root, "default").record("tool", "x", refs=["alpha"])
    r = mcp.handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                            "params": {"name": "rmx_focus",
                                       "arguments": {"root": str(root)}}})
    import json
    payload = json.loads(r["result"]["content"][0]["text"])
    assert any(n["name"] == "alpha" for n in payload["graph"]["nodes"])


# ---- scheduler ----


def test_scheduler_add_list_remove(home):
    root = home / "proj" / ".refmatrix"; root.mkdir(parents=True)
    scheduler.add_job(root, "sync", 1800)
    data = scheduler.load_schedule()
    assert data[str(root.resolve())]["sync"] == 1800
    assert scheduler.remove_job(root, "sync") is True
    assert scheduler.load_schedule() == {}


def test_scheduler_rejects_bad_op(home):
    with pytest.raises(ValueError):
        scheduler.add_job(home / "p" / ".refmatrix", "rm-rf", 60)


def test_scheduler_due_respects_interval(home, monkeypatch):
    root = home / "proj" / ".refmatrix"; root.mkdir(parents=True)
    scheduler.add_job(root, "vacuum", 100)
    s = scheduler.Scheduler()
    # never run → due immediately
    assert any(op == "vacuum" for _, op, _ in s.due(now=0))
    s._last[f"{root.resolve()}|vacuum"] = 0
    assert not any(op == "vacuum" for _, op, _ in s.due(now=50))   # too soon
    assert any(op == "vacuum" for _, op, _ in s.due(now=150))      # elapsed


def test_scheduler_tick_runs_only_when_daemon_up(home, monkeypatch):
    root = home / "proj" / ".refmatrix"; root.mkdir(parents=True)
    scheduler.add_job(root, "vacuum", 10)
    s = scheduler.Scheduler()
    ran = []
    monkeypatch.setattr(scheduler, "Path", Path)
    import refmatrix.daemon as daemon_mod
    monkeypatch.setattr(daemon_mod, "ping", lambda r, timeout=0.5: False)
    out = s.tick_once(now=1000)
    assert out == []  # daemon down → nothing runs
    monkeypatch.setattr(daemon_mod, "ping", lambda r, timeout=0.5: True)
    monkeypatch.setattr(s, "_run", lambda root, op: ran.append((str(root), op)))
    out = s.tick_once(now=2000)
    assert any(op == "vacuum" for _, op in ran)


# ---- federated concept ----


def test_federated_concept_groups_by_project(monkeypatch):
    roots = [Path("/a/.refmatrix"), Path("/b/.refmatrix")]
    monkeypatch.setattr(search.discovery, "discover_roots", lambda: roots)
    monkeypatch.setattr(search.discovery, "store_name",
                        lambda r: "a" if "/a/" in str(r) else "b")
    # _live_roots classifies via discovery.daemon_status (busy != absent,
    # plan-3 r2 #b-2); a bare `ping` fake no longer reaches it.
    monkeypatch.setattr(search.discovery, "daemon_status",
                        lambda r, **kw: {"up": True, "busy": False, "pid": 1})
    # federated_concept resolves via the in-process replica bundle
    monkeypatch.setattr(search, "_replica_bundle", lambda root, name, degree=0: {
        "anchor": {"name": name, "kind": "concept"},
        "groups": {"mentions": [{"name": "x", "kind": "code"}]}})
    res = search.federated_concept("build_context")
    projs = {p["project"] for p in res["projects"]}
    assert projs == {"a", "b"}
    assert all(p["neighbors"] == 1 for p in res["projects"])
