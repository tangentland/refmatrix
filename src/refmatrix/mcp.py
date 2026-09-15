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


def _resolve_project_root(project: str) -> "Path | None":
    """Map a project NAME (e.g. 'cliquedb') to its `.refmatrix` root among the
    discovered stores. Lets an MCP caller target a store explicitly instead of
    relying on the server process's cwd — the read-side twin of passing an
    explicit `root`. Matches on the store's default partition name (its parent
    dir basename), so 'cliquedb' resolves regardless of where `rmx mcp` runs."""
    from refmatrix import discovery
    for root in discovery.discover_roots():
        try:
            if discovery.store_name(root) == project:
                return root
        except Exception:
            continue
    return None


def _resolve_root(args: dict) -> Path:
    # Explicit target wins — `root` (path) or `project` (name). This is the
    # cwd-independent path: an MCP server serving one project can still be asked
    # to read another store's memory when a caller (e.g. a subagent) names it.
    if args.get("root"):
        r = Path(args["root"])
        return r if r.name == ".refmatrix" else r / ".refmatrix"
    if args.get("project"):
        pr = _resolve_project_root(str(args["project"]))
        if pr is not None:
            return pr
    env = os.environ.get("REFMATRIX_ROOT")
    if env:
        return Path(env)
    cur = Path.cwd()
    for d in (cur, *cur.parents):
        if (d / ".refmatrix").is_dir():
            return d / ".refmatrix"
    return cur / ".refmatrix"


# ---- tool handlers --------------------------------------------------------
#
# Every tool IS a verb (plan-3, 2026-09-14): TOOLS is generated from
# verbs.VERBS — name, description and schema come from the verb, and the
# handler is `_verb_tool(name)`, which resolves the store root from the
# transport args and runs the verb. A tool that called daemon/handoff/hub
# directly cannot exist here any more; tests/test_verb_parity.py asserts
# `set(TOOLS) == set(VERBS)` and that every handler dispatches to its verb.


def _verb_tool(name: str):
    def fn(args: dict) -> dict:
        from refmatrix.verbs import VERBS, VerbArgsError, VerbError
        try:
            return VERBS[name].run(_resolve_root(args), args)
        except VerbArgsError:
            raise          # caller bug: the dispatcher reports it as isError
        except VerbError as e:
            return {"error": str(e)}
    fn.__name__ = f"_t_{name[4:]}"
    fn.verb_name = name  # type: ignore[attr-defined]
    return fn


def _memory_partition(root: Path) -> str:
    """Delegates to verbs.memory_partition — ONE legacy-aware routing impl."""
    from refmatrix.verbs import memory_partition
    return memory_partition(root)


def _t_memory_add(args: dict) -> dict:
    """Daemon-routed write via the verb; in-proc fallback ONLY when the daemon
    is down (the documented bootstrap exception — a fresh store has no daemon
    yet and the first memory must still land)."""
    from refmatrix.verbs import VERBS, VerbError, memory_partition
    root = _resolve_root(args)
    try:
        return VERBS["rmx_memory_add"].run(root, args)
    except VerbError as e:
        if "daemon not running" not in str(e):
            return {"error": str(e)}
    from refmatrix.store import Store
    part = memory_partition(root)
    s = Store(root)
    with s.with_partition(part):
        eid = s.add_memory(name=args["name"], content=args["content"],
                           mtype=args.get("mtype", "observation"),
                           tags=args.get("tags"),
                           protected=bool(args.get("protect", False)))
    return {"id": eid}


_t_memory_add.verb_name = "rmx_memory_add"  # type: ignore[attr-defined]
_SPECIAL = {"rmx_memory_add": _t_memory_add}


def _build_tools() -> dict:
    from refmatrix.verbs import VERBS
    return {name: {"description": v.description, "schema": v.schema,
                   "fn": _SPECIAL.get(name) or _verb_tool(name)}
            for name, v in VERBS.items()}


TOOLS: dict[str, dict] = _build_tools()

# Module-level handler names kept for callers/tests that reach a tool by
# function (`mcp._t_query(...)`); each is the generated dispatcher.
_t_where = TOOLS["rmx_where"]["fn"]
_t_search = TOOLS["rmx_search"]["fn"]
_t_context = TOOLS["rmx_context"]["fn"]
_t_query = TOOLS["rmx_query"]["fn"]
_t_memory_recall = TOOLS["rmx_memory_recall"]["fn"]
_t_bus_pub = TOOLS["rmx_bus_pub"]["fn"]
_t_bus_history = TOOLS["rmx_bus_history"]["fn"]
_t_bus_channels = TOOLS["rmx_bus_channels"]["fn"]
_t_bus_read = TOOLS["rmx_bus_read"]["fn"]
_t_bus_mark_read = TOOLS["rmx_bus_mark_read"]["fn"]
_t_bus_delete = TOOLS["rmx_bus_delete"]["fn"]
_t_bus_archive = TOOLS["rmx_bus_archive"]["fn"]
_t_bus_unarchive = TOOLS["rmx_bus_unarchive"]["fn"]
_t_bus_purge = TOOLS["rmx_bus_purge"]["fn"]
_t_bus_stats = TOOLS["rmx_bus_stats"]["fn"]
_t_queues = TOOLS["rmx_queues"]["fn"]
_t_focus = TOOLS["rmx_focus"]["fn"]
_t_projects = TOOLS["rmx_projects"]["fn"]
_t_focus_note = TOOLS["rmx_focus_note"]["fn"]
_t_change_subject = TOOLS["rmx_change_subject"]["fn"]
_t_memory = TOOLS["rmx_memory"]["fn"]
_t_locate = TOOLS["rmx_locate"]["fn"]
_t_task = TOOLS["rmx_task"]["fn"]
_t_ingest = TOOLS["rmx_ingest"]["fn"]
_t_ingest_status = TOOLS["rmx_ingest_status"]["fn"]
_t_save_state = TOOLS["rmx_save_state"]["fn"]
_t_recall_state = TOOLS["rmx_recall_state"]["fn"]

from refmatrix.verbs import _MEMORY_OPS, _memory_payload  # noqa: E402,F401  (re-exported for callers/tests)


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
        tool = TOOLS.get(name) if isinstance(name, str) else None
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
