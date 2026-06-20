"""Federated retrieval across every live store — the engine behind the web
omnibox, `rmx where`, and the MCP `where` tool. One code path, many front doors.

Daemon-routed: each store is queried through its own daemon (`daemon.call`),
never a direct Store open.
"""
from __future__ import annotations

from pathlib import Path

from refmatrix import daemon as daemon_mod
from refmatrix import discovery


def federated_where(q: str, *, limit: int = 40) -> dict:
    """Fan a query across all live stores: code/doc/concept hits from context +
    memory hits, grouped by source, deduped, capped. Returns
    {"results": [{source, project, root, name, kind, path, line, snippet}]}."""
    results: list[dict] = []
    for root in discovery.discover_roots():
        if not daemon_mod.ping(root):
            continue
        proj = discovery.store_name(root)
        try:
            ctx = daemon_mod.call(root, "context", {
                "ref": q, "format": "json", "degree": 0,
                "entities_explicit": False, "tokens_explicit": False,
                "partition": proj,
            }, timeout=20.0)
            if ctx.get("ok"):
                b = ctx["result"]
                anchor = b.get("anchor")
                if anchor:
                    results.append({
                        "source": anchor.get("kind", "concept"),
                        "project": proj, "root": str(root),
                        "name": anchor["name"], "kind": anchor.get("kind", "concept"),
                        "path": anchor.get("path"), "line": None,
                    })
                for entries in (b.get("groups") or {}).values():
                    for e in entries[:6]:
                        results.append({
                            "source": e.get("kind", "concept"),
                            "project": proj, "root": str(root),
                            "name": e["name"], "kind": e.get("kind", "concept"),
                            "path": e.get("path"), "line": e.get("line"),
                            "snippet": e.get("snippet"),
                        })
        except Exception:
            pass
        try:
            mem = daemon_mod.call(root, "memory_search", {
                "query": q, "limit": 4, "partition": proj,
            }, timeout=10.0)
            if mem.get("ok"):
                for m in mem["result"].get("rows", []):
                    results.append({
                        "source": "memory", "project": proj, "root": str(root),
                        "name": m["name"], "kind": "memory", "path": None,
                        "snippet": (m.get("content") or "")[:120],
                    })
        except Exception:
            pass
    # include global behavior memories
    try:
        from refmatrix import hub as hub_mod
        if hub_mod.global_store_root().exists():
            g = hub_mod.global_call("memory_search", {"query": q, "limit": 6})
            if g.get("ok"):
                for m in g["result"].get("rows", []):
                    results.append({
                        "source": "global", "project": "global",
                        "root": str(hub_mod.global_store_root()),
                        "name": m["name"], "kind": "memory", "path": None,
                        "snippet": (m.get("content") or "")[:120],
                    })
    except Exception:
        pass

    seen, deduped = set(), []
    for r in results:
        key = (r["kind"], r["name"], r["project"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return {"results": deduped[:limit]}


def federated_concept(name: str) -> dict:
    """Which projects host a concept (exact anchor match) — the cross-project
    canon view. Returns {concept, projects:[{project, root, kind, neighbors}]}."""
    out = []
    for root in discovery.discover_roots():
        if not daemon_mod.ping(root):
            continue
        proj = discovery.store_name(root)
        try:
            ctx = daemon_mod.call(root, "context", {
                "ref": name, "format": "json", "degree": 0,
                "entities_explicit": False, "tokens_explicit": False,
                "partition": proj}, timeout=15.0)
            if ctx.get("ok"):
                b = ctx["result"]
                anchor = b.get("anchor")
                if anchor and anchor.get("name") == name:
                    neighbors = sum(len(v) for v in (b.get("groups") or {}).values())
                    out.append({"project": proj, "root": str(root),
                                "kind": anchor.get("kind"), "neighbors": neighbors})
        except Exception:
            pass
    return {"concept": name, "projects": out}


def federated_query(dsl: str, *, limit: int = 50) -> dict:
    """Run a DSL query against every live store, returning per-project hit
    counts + entity ids."""
    out = []
    for root in discovery.discover_roots():
        if not daemon_mod.ping(root):
            continue
        proj = discovery.store_name(root)
        try:
            r = daemon_mod.call(root, "query",
                                {"expr": dsl, "partition": proj, "limit": limit},
                                timeout=20.0)
            if r.get("ok"):
                res = r["result"]
                rows = res.get("rows") or []
                out.append({"project": proj, "root": str(root),
                            "count": res.get("cardinality", len(rows)),
                            "rows": rows[:limit]})
        except Exception:
            pass
    return {"projects": out}
