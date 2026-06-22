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
    root = _resolve_root(args)
    s = stm_mod.Stm(root, _session(args, stm_mod, root))
    return {"graph": s.focus_graph(top=int(args.get("top", 20))),
            "tasks": s.task_list()}


def _t_projects(args: dict) -> dict:
    from refmatrix import discovery
    return {"projects": discovery.all_projects(with_footprint=False)}


# ---- write path (per-project; daemon-routed, in-proc fallback) -------------


def _session(args: dict, stm_mod, root: Path) -> str:
    """Resolve the STM session for read OR write: explicit arg → most-recently-
    written ring (the active Claude session a spawned MCP process can't name) →
    bare "default". Reads and writes MUST resolve identically, else a note
    written to the active session is invisible to a `focus` read that fell back
    to "default"."""
    return (args.get("session") or stm_mod.latest_session(root)
            or stm_mod.session_id())


def _t_focus_note(args: dict) -> dict:
    """Record a deliberate reasoning note into the project's short-term memory —
    the WHY behind a decision/tradeoff. File-based + per-project; works with or
    without the daemon. MCP-native so note text bypasses shell quoting."""
    from refmatrix import stm as stm_mod
    root = _resolve_root(args)
    text = args.get("text") or args.get("note")
    if not text:
        raise ValueError("focus_note requires 'text' (alias: 'note')")
    s = stm_mod.Stm(root, _session(args, stm_mod, root))
    ev = s.record("reason", str(text)[:800])
    return {"noted": True, "session": s.session, "refs": ev.get("refs", [])[:6]}


def _t_memory_add(args: dict) -> dict:
    """Add/update a durable memory in the project store. Daemon-routed (the
    single write control point); in-proc fallback only when the daemon is down."""
    from refmatrix import daemon as daemon_mod, discovery
    root = _resolve_root(args)
    part = discovery.store_name(root)
    payload = {"name": args["name"], "content": args["content"],
               "mtype": args.get("mtype", "observation"),
               "tags": args.get("tags"),
               "protected": bool(args.get("protect", False)), "partition": part}
    if daemon_mod.ping(root):
        r = daemon_mod.call(root, "memory_add", payload, timeout=30.0)
        return r.get("result", {}) if r.get("ok") else {"error": r.get("error")}
    from refmatrix.store import Store
    s = Store(root)
    with s.with_partition(part):
        eid = s.add_memory(name=payload["name"], content=payload["content"],
                           mtype=payload["mtype"], tags=payload["tags"],
                           protected=payload["protected"])
    return {"id": eid}


def _t_change_subject(args: dict) -> dict:
    """Set the active subject (a named STM partition) for this session + upsert
    its durable LTM node. STM pointer is file-based; the node write is daemon-
    routed (in-proc fallback when down)."""
    from refmatrix import daemon as daemon_mod, discovery, stm as stm_mod
    root = _resolve_root(args)
    label = args.get("label") or args.get("subject")
    if not label:
        raise ValueError("change_subject requires 'label' (alias: 'subject')")
    s = stm_mod.Stm(root, _session(args, stm_mod, root))
    rec = s.set_subject(label)
    part = discovery.store_name(root)
    eid = None
    if daemon_mod.ping(root):
        r = daemon_mod.call(root, "subject_upsert",
                            {"label": label, "partition": part}, timeout=30.0)
        eid = r.get("result", {}).get("id") if r.get("ok") else None
    else:
        from refmatrix.store import Store
        s2 = Store(root)
        with s2.with_partition(part):
            eid = s2.upsert_subject(label)["id"]
    return {"subject": rec["subject"], "label": rec["label"], "id": eid,
            "session": s.session}


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
    "rmx_focus_note": {
        "description": "Record a deliberate reasoning note into the project's "
                       "short-term memory — the WHY behind a decision, a "
                       "hypothesis, a tradeoff. The reliable reasoning-capture "
                       "channel (extended thinking is redacted from transcripts).",
        "schema": {"type": "object", "properties": {
            "text": {"type": "string"}, "note": {"type": "string"},
            "session": {"type": "string"},
            "root": {"type": "string"}}, "required": ["text"]},
        "fn": _t_focus_note},
    "rmx_memory_add": {
        "description": "Add or update a durable memory in the current project's "
                       "memory store (daemon-routed write).",
        "schema": {"type": "object", "properties": {
            "name": {"type": "string"}, "content": {"type": "string"},
            "mtype": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "protect": {"type": "boolean"}, "root": {"type": "string"}},
            "required": ["name", "content"]},
        "fn": _t_memory_add},
    "rmx_change_subject": {
        "description": "Set the active subject (a named STM partition + durable "
                       "LTM container) for this session's thread of work; "
                       "promoted digests/handoffs file under it.",
        "schema": {"type": "object", "properties": {
            "label": {"type": "string"}, "subject": {"type": "string"},
            "session": {"type": "string"},
            "root": {"type": "string"}}, "required": ["label"]},
        "fn": _t_change_subject},
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
