"""MCP bus tools must pass sender identity + reply_to through, and expose
channel discovery.

Regressions for the MCP-bus drift cliquedb flagged: `rmx_bus_pub` hardcoded
`from="claude-mcp"` and `project=null` and dropped `reply_to`; there was no
channel-discovery tool. The hub op already supported all three — only the MCP
tool layer was thin.
"""
from __future__ import annotations

import refmatrix.mcp as mcp
import refmatrix.hub as hub_mod


def _mock_hub(monkeypatch, calls, *, channels=None):
    monkeypatch.setattr(hub_mod, "is_running", lambda: True)
    monkeypatch.delenv("RMX_AGENT", raising=False)

    def fake_rpc(op, args=None):
        calls.append((op, args or {}))
        if op == "bus_channels":
            return {"ok": True, "result": {"channels": channels or []}}
        return {"ok": True, "result": {"message": {"id": "m1"}}}

    monkeypatch.setattr(hub_mod, "rpc", fake_rpc)
    # Identity defaults to the server's project name.
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda root: "refmatrix")


def test_pub_defaults_sender_to_project_not_claude_mcp(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []
    _mock_hub(monkeypatch, calls)

    mcp._t_bus_pub({"channel": "proj:cliquedb:hello", "body": "hi",
                    "root": str(tmp_path)})

    op, args = next(c for c in calls if c[0] == "bus_pub")
    assert args["from"] == "refmatrix"        # NOT "claude-mcp"
    assert args["project"] == "cliquedb"      # derived from proj:<name>: channel
    assert args["reply_to"] is None


def test_pub_explicit_from_and_reply_to_pass_through(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []
    _mock_hub(monkeypatch, calls)

    mcp._t_bus_pub({"channel": "global:bugs", "body": "b", "from": "agent-x",
                    "reply_to": "abc123", "root": str(tmp_path)})

    _, args = next(c for c in calls if c[0] == "bus_pub")
    assert args["from"] == "agent-x"
    assert args["reply_to"] == "abc123"
    assert args["project"] is None            # global:* channel → no project tag


def test_pub_rmx_agent_env_overrides_project_default(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []
    _mock_hub(monkeypatch, calls)
    monkeypatch.setenv("RMX_AGENT", "env-agent")

    mcp._t_bus_pub({"channel": "global:x", "body": "b", "root": str(tmp_path)})

    _, args = next(c for c in calls if c[0] == "bus_pub")
    assert args["from"] == "env-agent"


def test_bus_channels_glob_filters(tmp_path, monkeypatch):
    chans = [
        {"channel": "proj:cliquedb:hello", "messages": 3},
        {"channel": "proj:refmatrix:bugs", "messages": 5},
        {"channel": "global:announce", "messages": 1},
    ]
    calls: list[tuple[str, dict]] = []
    _mock_hub(monkeypatch, calls, channels=chans)

    out = mcp._t_bus_channels({"glob": "proj:cliquedb:*"})
    names = [c["channel"] for c in out["channels"]]
    assert names == ["proj:cliquedb:hello"]

    out_all = mcp._t_bus_channels({})
    assert len(out_all["channels"]) == 3


def test_bus_pub_and_channels_registered_with_schema():
    for name in ("rmx_bus_pub", "rmx_bus_channels"):
        assert name in mcp.TOOLS
        assert "schema" in mcp.TOOLS[name] and "fn" in mcp.TOOLS[name]
    props = mcp.TOOLS["rmx_bus_pub"]["schema"]["properties"]
    assert {"from", "project", "reply_to"} <= set(props)
