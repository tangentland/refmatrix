"""Hub-as-MCP — expose refmatrix retrieval as native tools for Claude.

A dependency-free MCP server speaking JSON-RPC 2.0 over stdio (newline-delimited
messages), so Claude Code can call `where` / `context` / `memory_recall(scope=
both)` / `query` / `bus` / `queues` / `focus` directly instead of shelling out
and parsing text. This is the integration-refinement payoff: rmx becomes a
first-class tool surface.

All data access is daemon-routed (federated search hits per-project daemons; bus
/queues go through the hub; focus is file-based). Configure in Claude Code as an
MCP server: command `rmx mcp`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "refmatrix", "version": "1"}


# ---- root resolution ------------------------------------------------------


def _resolve_root(args: dict) -> Path:
    if args.get("root"):
        r = Path(args["root"])
        return r if r.name == ".refmatrix" else r / ".refmatrix"
    env = os.environ.get("REFMATRIX_ROOT")
    if env:
        return Path(env)
    cur = Path.cwd()
    for d in (cur, *cur.parents):
        if (d / ".refmatrix").is_dir():
            return d / ".refmatrix"
    return cur / ".refmatrix"


# ---- tool handlers --------------------------------------------------------


def _t_where(args: dict) -> dict:
    from refmatrix.search import federated_where
    return federated_where(args["query"], limit=int(args.get("limit", 40)))


def _t_search(args: dict) -> dict:
    from refmatrix.search import federated_query
    return federated_query(args["dsl"], limit=int(args.get("limit", 50)))


def _t_context(args: dict) -> dict:
    from refmatrix import daemon as daemon_mod, discovery
    root = _resolve_root(args)
    if not daemon_mod.ping(root):
        return {"error": "daemon not running for this project"}
    resp = daemon_mod.call(root, "context", {
        "ref": args["ref"], "format": "json", "degree": int(args.get("degree", 0)),
        "entities_explicit": False, "tokens_explicit": False,
        "partition": discovery.store_name(root),
    }, timeout=60.0)
    return resp.get("result", {}) if resp.get("ok") else {"error": resp.get("error")}


def _t_query(args: dict) -> dict:
    from refmatrix import daemon as daemon_mod, discovery
    root = _resolve_root(args)
    if not daemon_mod.ping(root):
        return {"error": "daemon not running for this project"}
    resp = daemon_mod.call(root, "query", {
        "dsl": args["dsl"], "partition": discovery.store_name(root)}, timeout=30.0)
    return resp.get("result", {}) if resp.get("ok") else {"error": resp.get("error")}


def _t_memory_recall(args: dict) -> dict:
    """Lexical recall across project + global behavior store (scope=both)."""
    from refmatrix import daemon as daemon_mod, discovery, hub as hub_mod
    q = args["query"]
    k = int(args.get("k", 8))
    scope = args.get("scope", "both")
    rows = []
    root = _resolve_root(args)
    if scope in ("project", "both") and daemon_mod.ping(root):
        r = daemon_mod.call(root, "memory_search", {
            "query": q, "limit": k, "partition": discovery.store_name(root)})
        if r.get("ok"):
            for m in r["result"].get("rows", []):
                m["scope"] = "project"; rows.append(m)
    if scope in ("global", "both") and hub_mod.global_store_root().exists():
        g = hub_mod.global_call("memory_search", {"query": q, "limit": k})
        if g.get("ok"):
            for m in g["result"].get("rows", []):
                m["scope"] = "global"; rows.append(m)
    return {"memories": rows[: k * 2]}


def _t_bus_pub(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_pub", {
        "channel": args["channel"], "body": args["body"],
        "type": args.get("type", "announce"),
        "from": args.get("from", "claude-mcp")}).get("result", {})


def _t_bus_history(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_history", {
        "channel": args["channel"], "n": int(args.get("n", 20))}).get("result", {})


def _t_queues(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running — change-queue visibility needs it"}
    return hub_mod.rpc("queues").get("result", {})


def _t_focus(args: dict) -> dict:
    from refmatrix import stm as stm_mod
    s = stm_mod.Stm(_resolve_root(args), args.get("session") or stm_mod.session_id())
    return {"graph": s.focus_graph(top=int(args.get("top", 20))),
            "tasks": s.task_list()}


def _t_projects(args: dict) -> dict:
    from refmatrix import discovery
    return {"projects": discovery.all_projects(with_footprint=False)}


TOOLS: dict[str, dict] = {
    "rmx_where": {
        "description": "Find where something is across ALL your refmatrix "
                       "projects + global memory — code, docs, concepts, "
                       "memories. The 'where are my keys?' tool.",
        "schema": {"type": "object", "properties": {
            "query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"]},
        "fn": _t_where},
    "rmx_search": {
        "description": "Run a refmatrix DSL query across all projects "
                       "(e.g. 'mentions:parser AND defines:parser').",
        "schema": {"type": "object", "properties": {
            "dsl": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["dsl"]},
        "fn": _t_search},
    "rmx_context": {
        "description": "Token-budgeted context bundle for a symbol/concept in "
                       "the current project (anchor + typed neighbors).",
        "schema": {"type": "object", "properties": {
            "ref": {"type": "string"}, "root": {"type": "string"},
            "degree": {"type": "integer"}}, "required": ["ref"]},
        "fn": _t_context},
    "rmx_query": {
        "description": "Run a refmatrix DSL query in the current project.",
        "schema": {"type": "object", "properties": {
            "dsl": {"type": "string"}, "root": {"type": "string"}},
            "required": ["dsl"]},
        "fn": _t_query},
    "rmx_memory_recall": {
        "description": "Recall memories — project + global 'Claude behavior' "
                       "store (scope=both by default).",
        "schema": {"type": "object", "properties": {
            "query": {"type": "string"}, "scope": {
                "type": "string", "enum": ["project", "global", "both"]},
            "k": {"type": "integer"}, "root": {"type": "string"}},
            "required": ["query"]},
        "fn": _t_memory_recall},
    "rmx_bus_pub": {
        "description": "Publish a message to the agent bus "
                       "(proj:<name>:<topic> or global:<topic>).",
        "schema": {"type": "object", "properties": {
            "channel": {"type": "string"}, "body": {"type": "string"},
            "type": {"type": "string"}}, "required": ["channel", "body"]},
        "fn": _t_bus_pub},
    "rmx_bus_history": {
        "description": "Read recent messages on a bus channel.",
        "schema": {"type": "object", "properties": {
            "channel": {"type": "string"}, "n": {"type": "integer"}},
            "required": ["channel"]},
        "fn": _t_bus_history},
    "rmx_queues": {
        "description": "Change-queue visibility: pending sync/stale work per "
                       "project + refinement-queue depth.",
        "schema": {"type": "object", "properties": {}},
        "fn": _t_queues},
    "rmx_focus": {
        "description": "Current short-term focus graph + task stack for the "
                       "project (what's being worked on right now).",
        "schema": {"type": "object", "properties": {
            "root": {"type": "string"}, "session": {"type": "string"}}},
        "fn": _t_focus},
    "rmx_projects": {
        "description": "List all refmatrix projects + daemon status.",
        "schema": {"type": "object", "properties": {}},
        "fn": _t_projects},
}


# ---- JSON-RPC dispatch ----------------------------------------------------


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_message(msg: dict):
    """Dispatch one JSON-RPC message. Returns a response dict, or None for
    notifications (no id)."""
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": [
            {"name": n, "description": t["description"], "inputSchema": t["schema"]}
            for n, t in TOOLS.items()
        ]})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        tool = TOOLS.get(name)
        if tool is None:
            return _error(req_id, -32602, f"unknown tool: {name}")
        try:
            out = tool["fn"](params.get("arguments") or {})
            return _result(req_id, {
                "content": [{"type": "text", "text": json.dumps(out, default=str)}],
                "isError": bool(isinstance(out, dict) and out.get("error")),
            })
        except Exception as e:
            return _result(req_id, {
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                "isError": True,
            })
    if req_id is not None:
        return _error(req_id, -32601, f"method not found: {method}")
    return None


def serve_stdio() -> None:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout."""
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_message(msg)
        if resp is not None:
            out.write(json.dumps(resp) + "\n")
            out.flush()
