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


def _t_where(args: dict) -> dict:
    from refmatrix.search import federated_where
    return federated_where(args["query"], limit=int(args.get("limit", 40)))


def _t_search(args: dict) -> dict:
    from refmatrix.search import federated_query
    return federated_query(args["dsl"], limit=int(args.get("limit", 50)))


def _t_context(args: dict) -> dict:
    from refmatrix.verbs import VERBS, VerbError
    try:
        return VERBS["rmx_context"].run(_resolve_root(args), args)
    except VerbError as e:
        return {"error": str(e)}


def _t_query(args: dict) -> dict:
    from refmatrix.verbs import VERBS, VerbError
    try:
        return VERBS["rmx_query"].run(_resolve_root(args), args)
    except VerbError as e:
        return {"error": str(e)}


def _memory_partition(root: Path) -> str:
    """Delegates to verbs.memory_partition — ONE legacy-aware routing impl."""
    from refmatrix.verbs import memory_partition
    return memory_partition(root)


def _t_memory_recall(args: dict) -> dict:
    from refmatrix.verbs import VERBS, VerbError
    try:
        return VERBS["rmx_memory_recall"].run(_resolve_root(args), args)
    except VerbError as e:
        return {"error": str(e)}


def _t_bus_pub(args: dict) -> dict:
    from refmatrix import hub as hub_mod, discovery
    import os
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    channel = args["channel"]
    # Identity passthrough (mirrors `rmx bus pub`): explicit `from` wins, then
    # $RMX_AGENT, then the MCP server's own project name. NOT a hardcoded
    # "claude-mcp" — co-located agents share a hostname, so the project is the
    # only default that tells receivers WHO published.
    sender = (args.get("from") or os.environ.get("RMX_AGENT")
              or discovery.store_name(_resolve_root(args)))
    # Derive the project tag from a proj:<name>:<topic> channel unless the
    # caller set it explicitly (global:* channels stay project-less).
    project = args.get("project")
    if project is None and channel.startswith("proj:"):
        parts = channel.split(":")
        project = parts[1] if len(parts) > 1 else None
    return hub_mod.rpc("bus_pub", {
        "channel": channel, "body": args["body"],
        "type": args.get("type", "announce"),
        "from": sender, "project": project,
        "reply_to": args.get("reply_to"),
    }).get("result", {})


def _t_bus_history(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_history", {
        "channel": args["channel"], "n": int(args.get("n", 20))}).get("result", {})


def _t_bus_channels(args: dict) -> dict:
    """Discover live bus channels, optionally filtered by a glob (`proj:*`,
    `global:*`, `proj:cliquedb:*`)."""
    from refmatrix import hub as hub_mod
    import fnmatch
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    chans = hub_mod.rpc("bus_channels").get("result", {}).get("channels", [])
    glob = args.get("glob")
    if glob:
        chans = [c for c in chans
                 if fnmatch.fnmatch(str(c.get("channel", "")), glob)]
    return {"channels": chans}


def _bus_agent(args: dict) -> str:
    """Agent identity for read-cursor / stats — mirrors `_t_bus_pub`'s sender
    resolution: explicit `agent`/`from`, then $RMX_AGENT, then the MCP server's
    own project (co-located agents share a hostname; the project is the only
    default that distinguishes them)."""
    import os
    from refmatrix import discovery
    return (args.get("agent") or args.get("from") or os.environ.get("RMX_AGENT")
            or discovery.store_name(_resolve_root(args)))


def _t_bus_read(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    chans = args.get("channels")
    if chans is None:
        chans = [args["channel"]] if args.get("channel") else ["*"]
    if isinstance(chans, str):
        chans = [chans]
    return hub_mod.rpc("bus_read", {
        "agent": _bus_agent(args), "channels": chans,
        "peek": bool(args.get("peek")), "n": args.get("n")}).get("result", {})


def _t_bus_mark_read(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_mark_read", {
        "agent": _bus_agent(args), "channel": args["channel"],
        "upto_seq": args.get("upto_seq")}).get("result", {})


def _t_bus_delete(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_delete", {"id": args["id"]}).get("result", {})


def _t_bus_archive(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_archive", {
        "id": args.get("id"), "channel": args.get("channel"),
        "before_ts": args.get("before_ts")}).get("result", {})


def _t_bus_unarchive(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_unarchive", {"id": args["id"]}).get("result", {})


def _t_bus_purge(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_purge", {
        "status": args.get("status", "deleted"), "channel": args.get("channel"),
        "before_ts": args.get("before_ts")}).get("result", {})


def _t_bus_stats(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running"}
    return hub_mod.rpc("bus_stats", {"agent": _bus_agent(args)}).get("result", {})


def _t_queues(args: dict) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        return {"error": "hub not running — change-queue visibility needs it"}
    return hub_mod.rpc("queues").get("result", {})


def _t_focus(args: dict) -> dict:
    from refmatrix.verbs import VERBS
    a = {**args, "session": _session_arg(args)}
    return VERBS["rmx_focus"].run(_resolve_root(args), a)


def _t_projects(args: dict) -> dict:
    from refmatrix.verbs import VERBS
    return VERBS["rmx_projects"].run(_resolve_root(args), args)


# ---- write path (per-project; daemon-routed, in-proc fallback) -------------


def _session_arg(args: dict) -> "str | None":
    """Explicit session arg or None — verbs resolve latest-ring/default
    themselves with the same precedence as _session()."""
    return args.get("session")


def _session(args: dict, stm_mod, root: Path) -> str:
    """Resolve the STM session for read OR write: explicit arg → most-recently-
    written ring (the active Claude session a spawned MCP process can't name) →
    bare "default". Reads and writes MUST resolve identically, else a note
    written to the active session is invisible to a `focus` read that fell back
    to "default"."""
    return (args.get("session") or stm_mod.latest_session(root)
            or stm_mod.session_id())


def _t_focus_note(args: dict) -> dict:
    from refmatrix.verbs import VERBS
    text = args.get("text") or args.get("note")
    if not text:
        raise ValueError("focus_note requires 'text' (alias: 'note')")
    a = {**args, "text": text, "session": _session_arg(args)}
    return VERBS["rmx_focus_note"].run(_resolve_root(args), a)


def _t_memory_add(args: dict) -> dict:
    """Daemon-routed write via the verb; in-proc fallback only when the
    daemon is down (the documented bootstrap exception)."""
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


def _t_change_subject(args: dict) -> dict:
    from refmatrix.verbs import VERBS, VerbError
    label = args.get("label") or args.get("subject")
    if not label:
        raise ValueError("change_subject requires 'label' (alias: 'subject')")
    a = {**args, "label": label,
         "session": _session_arg(args)}
    try:
        return VERBS["rmx_change_subject"].run(_resolve_root(args), a)
    except VerbError as e:
        return {"error": str(e)}


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
    from refmatrix import daemon as daemon_mod, hub as hub_mod
    root = _resolve_root(args)
    part = args.get("partition") or _memory_partition(root)
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
    if not isinstance(action, str) or (op := _MEMORY_OPS.get(action)) is None:
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
    from refmatrix.verbs import VERBS, VerbError
    try:
        return VERBS["rmx_ingest"].run(_resolve_root(args), args)
    except VerbError as e:
        return {"error": str(e)}


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


def _t_save_state(args: dict) -> dict:
    from refmatrix.verbs import VERBS
    a = {**args, "session": _session_arg(args)}
    return VERBS["rmx_save_state"].run(_resolve_root(args), a)


def _t_recall_state(args: dict) -> dict:
    """Pull the prior session's handoff + live STM + git + daemon health to
    resume (mirror of the CLI `recall-state`). Read-only; returns the structured
    resume payload: latest save-state handoff, STM focus digest, recent
    memories, git facts, daemon status, and anomalies."""
    from refmatrix import handoff, stm as stm_mod
    root = _resolve_root(args)
    repo = root.parent
    s = stm_mod.Stm(root, _session(args, stm_mod, root))
    memdir = handoff.default_memory_dir(repo)
    return handoff.compose_recall_state(s, root, repo=repo, memdir=memdir)


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
                       "the current project (anchor + typed neighbors + helix "
                       "staleness notes). expand=N adds source lines per code "
                       "hit; hit_lines=nums|text lists every hit line per file.",
        "schema": {"type": "object", "properties": {
            "ref": {"type": "string"}, "root": {"type": "string"},
            "degree": {"type": "integer"}, "expand": {"type": "integer"},
            "hit_lines": {"type": "string",
                          "enum": ["first", "nums", "text"]},
            "max_entities": {"type": "integer"},
            "max_tokens": {"type": "integer"},
            "linkage": {"type": "string"}, "fuse": {"type": "boolean"},
            "strict": {"type": "boolean"},
            "include_sessions": {"type": "boolean"},
            "grep_backstop": {"type": "boolean"}}, "required": ["ref"]},
        "fn": _t_context},
    "rmx_query": {
        "description": "Run a refmatrix DSL query in the current project.",
        "schema": {"type": "object", "properties": {
            "dsl": {"type": "string"}, "root": {"type": "string"}},
            "required": ["dsl"]},
        "fn": _t_query},
    "rmx_memory_recall": {
        "description": "Recall memories — project store by default "
                       "(scope=project, matching the CLI); scope=both adds the "
                       "global behavior store. Pass `project` (name, "
                       "e.g. 'cliquedb') or `root` to target a specific store "
                       "when this server's cwd is a different project.",
        "schema": {"type": "object", "properties": {
            "query": {"type": "string"}, "scope": {
                "type": "string", "enum": ["project", "global", "both"]},
            "k": {"type": "integer"}, "root": {"type": "string"},
            "project": {"type": "string"},
            "kinds": {"type": "array", "items": {"type": "string"}},
            "fuse": {"type": "boolean"}, "rerank": {"type": "boolean"},
            "since_seconds": {"type": "number"},
            "exclude_mtype": {"type": "array", "items": {"type": "string"},
                              "description": "mtype globs to drop; default "
                                             "['session/*'] (pass [] for none)"}},
            "required": []},
        "fn": _t_memory_recall},
    "rmx_bus_pub": {
        "description": "Publish a message to the agent bus "
                       "(proj:<name>:<topic> or global:<topic>). `from` "
                       "defaults to this server's project; pass `reply_to` "
                       "(a prior message id) to thread a reply.",
        "schema": {"type": "object", "properties": {
            "channel": {"type": "string"}, "body": {"type": "string"},
            "type": {"type": "string"},
            "from": {"type": "string"},
            "project": {"type": "string"},
            "reply_to": {"type": "string"}}, "required": ["channel", "body"]},
        "fn": _t_bus_pub},
    "rmx_bus_history": {
        "description": "Read recent messages on a bus channel.",
        "schema": {"type": "object", "properties": {
            "channel": {"type": "string"}, "n": {"type": "integer"}},
            "required": ["channel"]},
        "fn": _t_bus_history},
    "rmx_bus_channels": {
        "description": "List live bus channels (with message counts), "
                       "optionally filtered by a glob like `proj:*` or "
                       "`proj:cliquedb:*`. Channel discovery for the bus.",
        "schema": {"type": "object", "properties": {
            "glob": {"type": "string"}}, "required": []},
        "fn": _t_bus_channels},
    "rmx_bus_read": {
        "description": "Read bus messages you have NOT seen yet across matching "
                       "channels, advancing your read-cursor (unless peek=true). "
                       "`channels` is a list of patterns (`proj:*`, `global:`, "
                       "exact); default `*`. Use this instead of bus_history to "
                       "poll for new messages without re-reading old ones.",
        "schema": {"type": "object", "properties": {
            "channels": {"type": "array", "items": {"type": "string"}},
            "agent": {"type": "string"}, "peek": {"type": "boolean"},
            "n": {"type": "integer"}}, "required": []},
        "fn": _t_bus_read},
    "rmx_bus_mark_read": {
        "description": "Mark a channel read up to a point (default: everything) "
                       "without returning the messages.",
        "schema": {"type": "object", "properties": {
            "channel": {"type": "string"}, "agent": {"type": "string"},
            "upto_seq": {"type": "integer"}}, "required": ["channel"]},
        "fn": _t_bus_mark_read},
    "rmx_bus_delete": {
        "description": "Soft-delete a bus message by id — hidden from "
                       "history/read, recoverable until purge.",
        "schema": {"type": "object", "properties": {
            "id": {"type": "string"}}, "required": ["id"]},
        "fn": _t_bus_delete},
    "rmx_bus_archive": {
        "description": "Archive bus messages (still readable via bus_history "
                       "status=archived): by `id`, or a whole `channel` "
                       "(optionally only those with ts < `before_ts`).",
        "schema": {"type": "object", "properties": {
            "id": {"type": "string"}, "channel": {"type": "string"},
            "before_ts": {"type": "string"}}, "required": []},
        "fn": _t_bus_archive},
    "rmx_bus_unarchive": {
        "description": "Restore an archived bus message to active.",
        "schema": {"type": "object", "properties": {
            "id": {"type": "string"}}, "required": ["id"]},
        "fn": _t_bus_unarchive},
    "rmx_bus_purge": {
        "description": "Hard-remove bus messages — the only destructive path. "
                       "Default reaps soft-deleted rows; status=archived reaps "
                       "the archive; status=all + before_ts prunes old history.",
        "schema": {"type": "object", "properties": {
            "status": {"type": "string"}, "channel": {"type": "string"},
            "before_ts": {"type": "string"}}, "required": []},
        "fn": _t_bus_purge},
    "rmx_bus_stats": {
        "description": "Bus overview: per-status totals + per-channel breakdown "
                       "(active/archived/deleted) + your unread counts.",
        "schema": {"type": "object", "properties": {
            "agent": {"type": "string"}}, "required": []},
        "fn": _t_bus_stats},
    "rmx_queues": {
        "description": "Change-queue visibility: pending sync/stale work per "
                       "project + refinement-queue depth.",
        "schema": {"type": "object", "properties": {}},
        "fn": _t_queues},
    "rmx_focus": {
        "description": "Current short-term focus graph + task stack for the "
                       "project (what's being worked on right now).",
        "schema": {"type": "object", "properties": {
            "root": {"type": "string"}, "session": {"type": "string"},
            "top": {"type": "integer"}}},
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
            "text": {"type": "string"},
            "note": {"type": "string",
                     "description": "alias for text; one of the two required"},
            "session": {"type": "string"},
            "root": {"type": "string"}}, "required": []},
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
            "label": {"type": "string"},
            "subject": {"type": "string",
                        "description": "alias for label; one of the two required"},
            "session": {"type": "string"},
            "root": {"type": "string"}}, "required": []},
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
            "dry_run": {"type": "boolean"}, "root": {"type": "string"},
            "project": {"type": "string"}},
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
    "rmx_save_state": {
        "description": "Save session state — the handoff for the next instance. "
                       "Writes ONE durable handoff memory capturing: git state "
                       "(branch, HEAD, commits-ahead, dirty/uncommitted files, "
                       "this-session commits), the STM focus graph (top weighted "
                       "symbols/files), the task stack, and recent-memory links. "
                       "Unless promote=false, ALSO promotes the condensed STM "
                       "digest (topics, milestones, intent arc, touched files) "
                       "to durable memory so working memory graduates to LTM. "
                       "Mirror of rmx_recall_state.",
        "schema": {"type": "object", "properties": {
            "message": {"type": "string"},
            "promote": {"type": "boolean"}, "dry_run": {"type": "boolean"},
            "session": {"type": "string"}, "root": {"type": "string"}}},
        "fn": _t_save_state},
    "rmx_recall_state": {
        "description": "Recall session state — pull the prior handoff and orient "
                       "(read-only). Returns: the latest save-state handoff "
                       "(prior git/focus/tasks/recent-memory links), the live "
                       "session's STM focus digest (top symbols, topics, "
                       "milestones, intent arc), recent memories, current git "
                       "state, daemon health, and anomalies (dirty tree, "
                       "unmerged/undeployed commits, stale daemon). Mirror of "
                       "rmx_save_state.",
        "schema": {"type": "object", "properties": {
            "session": {"type": "string"}, "root": {"type": "string"}}},
        "fn": _t_recall_state},
}


# ---- verb-generated schemas ------------------------------------------------
# For every tool backed by a verb, the schema and description come FROM the
# verb signature — hand-written schemas for these are forbidden (they are what
# drifted). Aliases are transport-level conveniences declared here only.

def _apply_verb_schemas() -> None:
    import copy
    from refmatrix.verbs import VERBS
    aliased = {
        "rmx_focus_note": (
            {"note": {"type": "string",
                      "description": "alias for text; one of the two required"}},
            ("text",)),
        "rmx_change_subject": (
            {"subject": {"type": "string",
                         "description": "alias for label; one of the two required"}},
            ("label",)),
    }
    for name, v in VERBS.items():
        if name not in TOOLS:
            continue
        schema = copy.deepcopy(v.schema)
        extra, drop = aliased.get(name, ({}, ()))
        schema["properties"].update(extra)
        schema["required"] = [r for r in schema.get("required", [])
                              if r not in drop]
        TOOLS[name]["schema"] = schema
        TOOLS[name]["description"] = v.description


_apply_verb_schemas()


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
