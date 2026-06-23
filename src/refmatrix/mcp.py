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
import threading
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "refmatrix", "version": "1"}

# Channels are on unless explicitly disabled. When on, the server advertises the
# `claude/channel` capability and bridges hub bus messages → native push
# notifications (see the channel-bridge section below).
CHANNELS_ENABLED = os.environ.get("REFMATRIX_CHANNELS", "1") not in ("0", "false", "")


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


# ---- full memory parity (one dispatcher over the CLI `memory` group) --------

_MEMORY_OPS = {
    "get": "memory_get", "list": "memory_iter", "search": "memory_search",
    "forget": "memory_forget", "reclassify": "memory_reclassify",
    "retag": "memory_retag", "link": "memory_link", "score": "memory_score",
    "bulk_forget": "memory_bulk_forget", "dedup": "memory_dedup",
}


def _memory_payload(action: str, a: dict) -> dict:
    """Build the daemon-op payload for a memory action. Keys mirror what the
    CLI memory subcommands send (the proven callers) so the daemon op contract
    stays single-sourced."""
    def keyed():
        return {"id": int(a["id"])} if a.get("id") is not None else {"name": a["name"]}
    if action == "get" or action == "forget":
        return keyed()
    if action == "list":
        return {k: a[k] for k in ("mtype", "limit", "tags", "tags_match")
                if a.get(k) is not None}
    if action == "search":
        p = {"query": a["query"]}
        for k in ("limit", "tags", "tags_match"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "reclassify":
        p = {"to_mtype": a["to_mtype"]}
        for k in ("from_mtype", "like", "names", "dry_run"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "retag":
        p = keyed()
        for k in ("add", "remove", "replace"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "link":
        p = {"src_id": int(a["id"])} if a.get("id") is not None \
            else {"src_name": a["name"]}
        p["linkage"] = a.get("linkage", "related-to")
        p["concept"] = a["concept"]
        if a.get("weight") is not None:
            p["weight"] = a["weight"]
        return p
    if action == "score":
        p = {"concept": a["concept"]}
        for k in ("halflife_days", "cap", "explain"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "bulk_forget":
        p = {"dry_run": bool(a.get("dry_run", False))}
        for k in ("ids", "names", "mtypes"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "dedup":
        return {"dry_run": bool(a.get("dry_run", False))}
    return {}


def _t_memory(args: dict) -> dict:
    """Full parity with the CLI `rmx memory` group via one dispatcher. `action`
    selects the operation; the remaining args are the operation's parameters
    (see the action enum). recall/add reuse the dedicated tools; promote is the
    project→global behavior-store copy; everything else routes to the daemon's
    `memory_*` op with the project partition injected."""
    action = args.get("action")
    if action == "recall":
        return _t_memory_recall(args)
    if action == "add":
        return _t_memory_add(args)
    from refmatrix import daemon as daemon_mod, discovery, hub as hub_mod
    root = _resolve_root(args)
    part = args.get("partition") or discovery.store_name(root)
    if not daemon_mod.ping(root):
        return {"error": f"daemon not running for {root}"}
    if action == "promote":
        key = {"id": int(args["id"])} if args.get("id") is not None \
            else {"name": args["name"]}
        g0 = daemon_mod.call(root, "memory_get", {**key, "partition": part},
                             timeout=30.0)
        m = g0.get("result", {}).get("memory") if g0.get("ok") else None
        if not m:
            return {"error": "no memory matching the id/name"}
        tags = list(dict.fromkeys((m.get("tags") or []) + ["behavior"]))
        g = hub_mod.global_call("memory_add", {
            "name": m["name"], "content": m["content"],
            "mtype": m.get("mtype") or "feedback", "tags": tags,
            "metadata": m.get("metadata")})
        return g.get("result", {}) if g.get("ok") else {"error": g.get("error")}
    op = _MEMORY_OPS.get(action)
    if op is None:
        return {"error": f"unknown memory action {action!r}"}
    try:
        payload = {**_memory_payload(action, args), "partition": part}
    except KeyError as exc:
        return {"error": f"missing required arg for {action}: {exc}"}
    r = daemon_mod.call(root, op, payload, timeout=120.0)
    return r.get("result", {}) if r.get("ok") else {"error": r.get("error")}


def _t_locate(args: dict) -> dict:
    """Locate full filesystem paths by filename and/or keywords/concepts,
    across every live store (federated)."""
    from refmatrix.search import federated_locate
    return federated_locate(args.get("file"), args.get("keywords") or [],
                            limit=int(args.get("n", 10)))


def _t_task(args: dict) -> dict:
    """Task pushdown stack for the active session (push/pop/list/current/swap).
    Uses the symmetric session resolution so MCP writes are visible to CLI
    reads and vice versa."""
    from refmatrix import stm as stm_mod
    root = _resolve_root(args)
    s = stm_mod.Stm(root, _session(args, stm_mod, root))
    action = args.get("action", "list")
    if action == "push":
        if not args.get("desc"):
            return {"error": "task push requires 'desc'"}
        return s.task_push(args["desc"])
    if action == "pop":
        return s.task_pop(args.get("selector"))
    if action == "list":
        return {"tasks": s.task_list()}
    if action == "current":
        return {"current": s.task_current()}
    if action == "swap":
        return s.task_swap()
    return {"error": f"unknown task action {action!r}"}


def _t_ingest(args: dict) -> dict:
    """Fire-and-poll ingest/embed: enqueues the job on the daemon and returns a
    `job_id` immediately (time-bound). Poll `rmx_ingest_status`. `mode`:
    'ingest' (default, the project tree) or 'embed' (dense vectors)."""
    from refmatrix import daemon as daemon_mod, discovery
    root = _resolve_root(args)
    if not daemon_mod.ping(root):
        return {"error": f"daemon not running for {root}"}
    part = args.get("partition") or discovery.store_name(root)
    if args.get("mode") == "embed":
        payload = {"partition": part}
        for k in ("kinds", "limit", "rebuild"):
            if args.get(k) is not None:
                payload[k] = args[k]
        r = daemon_mod.call(root, "embed_start", payload, timeout=30.0)
    else:
        payload = {
            "path": args.get("path") or str(Path(root).parent),
            "source": args.get("source", "auto"),
            "semantic": bool(args.get("semantic", False)),
            "partition": part,
        }
        r = daemon_mod.call(root, "ingest_path_start", payload, timeout=30.0)
    return r.get("result", {}) if r.get("ok") else {"error": r.get("error")}


def _t_ingest_status(args: dict) -> dict:
    """Poll an ingest/embed job started by `rmx_ingest`. Omit `job_id` to list
    all jobs; pass `since_seq` to stream new per-file events."""
    from refmatrix import daemon as daemon_mod
    root = _resolve_root(args)
    if not daemon_mod.ping(root):
        return {"error": f"daemon not running for {root}"}
    payload = {k: args[k] for k in ("job_id", "since_seq", "limit")
               if args.get(k) is not None}
    r = daemon_mod.call(root, "ingest_gmd_status", payload, timeout=15.0)
    return r.get("result", {}) if r.get("ok") else {"error": r.get("error")}


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
    "rmx_memory": {
        "description": "Full access to the project memory store — parity with "
                       "the CLI `rmx memory` group. `action` selects the op; "
                       "pass that op's params alongside.",
        "schema": {"type": "object", "properties": {
            "action": {"type": "string", "enum": [
                "recall", "add", "get", "list", "search", "forget",
                "reclassify", "retag", "link", "score", "bulk_forget",
                "dedup", "promote"]},
            "name": {"type": "string"}, "id": {"type": "integer"},
            "content": {"type": "string"}, "mtype": {"type": "string"},
            "to_mtype": {"type": "string"}, "from_mtype": {"type": "string"},
            "query": {"type": "string"}, "scope": {"type": "string"},
            "k": {"type": "integer"}, "limit": {"type": "integer"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "tags_match": {"type": "string"},
            "add": {"type": "array", "items": {"type": "string"}},
            "remove": {"type": "array", "items": {"type": "string"}},
            "replace": {"type": "array", "items": {"type": "string"}},
            "names": {"type": "array", "items": {"type": "string"}},
            "ids": {"type": "array", "items": {"type": "integer"}},
            "mtypes": {"type": "array", "items": {"type": "string"}},
            "like": {"type": "string"}, "concept": {"type": "string"},
            "linkage": {"type": "string"}, "weight": {"type": "number"},
            "halflife_days": {"type": "number"}, "cap": {"type": "number"},
            "explain": {"type": "boolean"}, "protect": {"type": "boolean"},
            "dry_run": {"type": "boolean"}, "root": {"type": "string"}},
            "required": ["action"]},
        "fn": _t_memory},
    "rmx_locate": {
        "description": "Locate full filesystem paths by filename (basename, no "
                       "path) and/or keywords/concepts, across all live stores.",
        "schema": {"type": "object", "properties": {
            "file": {"type": "string"},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "n": {"type": "integer"}}},
        "fn": _t_locate},
    "rmx_task": {
        "description": "Task pushdown stack for the active session: push, pop, "
                       "list, current, swap. Snapshots focus on push; restores "
                       "it on pop (git-stash semantics).",
        "schema": {"type": "object", "properties": {
            "action": {"type": "string",
                       "enum": ["push", "pop", "list", "current", "swap"]},
            "desc": {"type": "string"}, "selector": {"type": "string"},
            "session": {"type": "string"}, "root": {"type": "string"}}},
        "fn": _t_task},
    "rmx_ingest": {
        "description": "Fire-and-poll ingest/embed: enqueues the job and returns "
                       "a job_id immediately (time-bound). `mode`: 'ingest' "
                       "(project tree) or 'embed'. Poll with rmx_ingest_status.",
        "schema": {"type": "object", "properties": {
            "mode": {"type": "string", "enum": ["ingest", "embed"]},
            "path": {"type": "string"}, "source": {"type": "string"},
            "semantic": {"type": "boolean"},
            "kinds": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer"}, "rebuild": {"type": "boolean"},
            "root": {"type": "string"}}},
        "fn": _t_ingest},
    "rmx_ingest_status": {
        "description": "Poll an ingest/embed job started by rmx_ingest. Omit "
                       "job_id to list all jobs; since_seq streams new events.",
        "schema": {"type": "object", "properties": {
            "job_id": {"type": "string"}, "since_seq": {"type": "integer"},
            "limit": {"type": "integer"}, "root": {"type": "string"}}},
        "fn": _t_ingest_status},
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
        caps: dict = {"tools": {}}
        if CHANNELS_ENABLED:
            caps["experimental"] = {"claude/channel": {}}
        return _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": caps,
            "serverInfo": SERVER_INFO,
        })
    if method in ("notifications/initialized", "initialized"):
        if CHANNELS_ENABLED:
            _ensure_channel_bridge()
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


# ---- channel bridge (hub bus → native push notifications) -----------------
#
# The hub already streams matching bus messages over its control socket
# (`subscribe_stream`). We tap that stream on a daemon thread and re-emit each
# message as a `notifications/claude/channel` notification, so bus traffic to
# `proj:<project>:*` / `global:*` arrives in-context with zero polling. The
# client only acts on these if it negotiated the `claude/channel` capability;
# otherwise they're harmless no-ops.

_OUT_LOCK = threading.Lock()
_CHANNEL_STOP = threading.Event()
_CHANNEL_THREAD: "threading.Thread | None" = None


def _emit(obj: dict) -> None:
    """Serialize a JSON-RPC object to stdout. Shared by the request loop and
    the channel bridge, so writes from both never interleave."""
    line = json.dumps(obj, default=str)
    with _OUT_LOCK:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _channel_patterns() -> list[str]:
    """Which bus channels to forward. Default: this project + global. Override
    with REFMATRIX_CHANNEL_PATTERNS (comma-separated)."""
    env = os.environ.get("REFMATRIX_CHANNEL_PATTERNS")
    if env:
        return [p.strip() for p in env.split(",") if p.strip()]
    pats = ["global:*"]
    try:
        from refmatrix import discovery
        name = discovery.store_name(_resolve_root({}))
        if name:
            pats.insert(0, f"proj:{name}:*")
    except Exception:
        pass
    return pats


def _channel_notification(msg: dict) -> dict:
    """Map a bus message to a claude/channel notification. The body becomes the
    content; routing fields become meta (→ tag attributes). meta keys must be
    bare identifiers, so we only pass known-safe ones."""
    body = msg.get("body")
    content = body if isinstance(body, str) else json.dumps(body, default=str)
    meta = {}
    for k in ("channel", "from", "type", "id", "ts", "project"):
        v = msg.get(k)
        if v is not None:
            meta[k] = str(v)
    return {"jsonrpc": "2.0", "method": "notifications/claude/channel",
            "params": {"content": content, "meta": meta}}


def _channel_loop() -> None:
    from refmatrix import hub as hub_mod
    patterns = _channel_patterns()
    while not _CHANNEL_STOP.is_set():
        if not hub_mod.is_running():
            _CHANNEL_STOP.wait(5.0)
            continue
        try:
            for msg in hub_mod.subscribe_stream(patterns, history=0):
                if _CHANNEL_STOP.is_set():
                    break
                try:
                    _emit(_channel_notification(msg))
                except Exception:
                    pass
        except Exception:
            # hub restarted / socket dropped — back off, then reconnect.
            _CHANNEL_STOP.wait(3.0)


def _ensure_channel_bridge() -> None:
    """Start the bus→channel bridge once, on `initialized`."""
    global _CHANNEL_THREAD
    if _CHANNEL_THREAD is not None and _CHANNEL_THREAD.is_alive():
        return
    _CHANNEL_THREAD = threading.Thread(
        target=_channel_loop, name="rmx-mcp-channel", daemon=True)
    _CHANNEL_THREAD.start()


def serve_stdio() -> None:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout."""
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
            _emit(resp)
    _CHANNEL_STOP.set()
