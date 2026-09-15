"""Federated retrieval across every live store — the engine behind the web
omnibox, `rmx where`, and the MCP `where` tool. One code path, many front doors.

Daemon-routed: each store is queried through its own daemon (`daemon.call`),
never a direct Store open.
"""
from __future__ import annotations

import os

import threading
from pathlib import Path

from refmatrix import daemon as daemon_mod
from refmatrix import discovery

# Shared per-root read-only replica Store cache (used by federated search AND
# the UI server). Opening a large snapshot cold costs seconds; reuse keeps
# reads sub-second. DuckDB cursors aren't concurrency-safe, so each cached
# store carries its own lock.
_REPLICA_CACHE: "dict[str, tuple]" = {}
_REPLICA_CACHE_LOCK = threading.Lock()


def _snapshot_sig(s) -> "tuple | None":
    """Identity of the file a read-only Store is bound to. The daemon
    regenerates `catalog.read.duckdb` by tmp+rename, so an open connection
    keeps reading the OLD inode forever — a long-lived process (the MCP
    server, the hub) went permanently stale on where/locate until restart
    (found by tests/test_verbs_migrated.py, plan-3 r1)."""
    try:
        st = os.stat(s.db_path)
        return (st.st_ino, st.st_mtime_ns, st.st_size)
    except Exception:
        return None


def cached_replica(root: Path):
    """Return (store, lock) for a root, opening on first use and REOPENING
    when the snapshot file underneath has been replaced since."""
    from refmatrix.store import Store
    key = str(Path(root).resolve())
    with _REPLICA_CACHE_LOCK:
        hit = _REPLICA_CACHE.get(key)
        if hit is not None:
            s, lock, sig = hit
            if sig == _snapshot_sig(s):
                return s, lock
            _REPLICA_CACHE.pop(key, None)
            try:
                s.close()
            except Exception:
                pass
    part = discovery.store_name(root)
    s = Store(root, partition=part, read_only=True)
    entry = (s, threading.Lock(), _snapshot_sig(s))
    with _REPLICA_CACHE_LOCK:
        existing = _REPLICA_CACHE.setdefault(key, entry)
    if existing is not entry:
        try:
            s.close()
        except Exception:
            pass
    return existing[0], existing[1]


def _replica_bundle(root: Path, ref: str, *, degree: int = 0,
                    grep_backstop: bool = False) -> dict:
    """In-process cached read-only-replica context bundle (the working read
    path; the daemon context op mis-resolves on multi-partition daemons).
    `grep_backstop=False` by default — the filesystem-grep floor is slow on a
    big tree and pointless for federated search (we want index hits only).
    Returns the render_json dict or {} on failure."""
    from refmatrix.context import build_context, render_json
    import json as _json
    part = discovery.store_name(root)
    try:
        s, lock = cached_replica(root)
    except Exception:
        return {}
    try:
        with lock, s.with_partition(part):
            b = build_context(s, ref, degree=degree, grep_backstop=grep_backstop,
                              _entities_explicit=False, _tokens_explicit=False)
        return _json.loads(render_json(b))
    except Exception:
        return {}


def _where_one_project(root, q: str) -> list[dict]:
    """code/doc/concept anchor hits (via cached replica) + memory_search hits
    for one project. Best-effort; returns [] on any failure."""
    out: list[dict] = []
    proj = discovery.store_name(root)
    try:
        b = _replica_bundle(root, q, degree=0)
        if b:
            anchor = b.get("anchor")
            if anchor:
                out.append({"source": anchor.get("kind", "concept"),
                            "project": proj, "root": str(root),
                            "name": anchor["name"],
                            "kind": anchor.get("kind", "concept"),
                            "path": anchor.get("path"), "line": None})
            for entries in (b.get("groups") or {}).values():
                for e in entries[:6]:
                    out.append({"source": e.get("kind", "concept"),
                                "project": proj, "root": str(root),
                                "name": e["name"], "kind": e.get("kind", "concept"),
                                "path": e.get("path"), "line": e.get("line"),
                                "snippet": e.get("snippet")})
    except Exception:
        pass
    try:
        mem = daemon_mod.call(root, "memory_search",
                              {"query": q, "limit": 4, "partition": proj},
                              timeout=3.0, retries=0)
        if mem.get("ok"):
            for m in mem["result"].get("rows", []):
                out.append({"source": "memory", "project": proj,
                            "root": str(root), "name": m["name"], "kind": "memory",
                            "path": None, "snippet": (m.get("content") or "")[:120]})
    except Exception:
        pass
    return out


def _live_roots() -> "tuple[list, list[dict]]":
    """Stores whose daemon answers, plus the ones that were SKIPPED and why
    (busy: alive, not answering; absent: no daemon). A busy store used to be
    silently dropped from the fan-out (ch-bsd plan-3 r2 #b-2)."""
    roots, skipped = [], []
    for r in discovery.discover_roots():
        rp = Path(r)
        st = discovery.daemon_status(rp)
        if st.get("up"):
            roots.append(r)
        elif st.get("busy"):
            skipped.append({"project": discovery.store_name(rp), "root": str(r),
                            "reason": f"daemon busy pid={st.get('pid')} (alive, not answering)"})
        else:
            skipped.append({"project": discovery.store_name(rp), "root": str(r),
                            "reason": "daemon not running"})
    return roots, skipped


def federated_where(q: str, *, limit: int = 40) -> dict:
    """Fan a query across all live stores: code/doc/concept hits from the cached
    replica + memory hits, grouped by source, deduped, capped. Per-project work
    runs concurrently with short timeouts so one slow/stuck daemon can't stall
    the whole omnibox. Returns
    {"results": [{source, project, root, name, kind, path, line, snippet}],
     "skipped": [{project, root, reason}]}."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    roots, skipped = _live_roots()
    results: list[dict] = []
    if roots:
        ex = ThreadPoolExecutor(max_workers=min(8, len(roots)))
        futs = {ex.submit(_where_one_project, r, q): r for r in roots}
        try:
            for fut in as_completed(futs, timeout=6):
                try:
                    results.extend(fut.result(timeout=0.1) or [])
                except Exception:
                    pass
        except Exception:
            pass  # overall fan-out timeout — return whatever finished
        # don't block on stragglers (a `with` block would shutdown(wait=True))
        ex.shutdown(wait=False, cancel_futures=True)
    # global behavior memories (hub-local; fast)
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
                        "snippet": (m.get("content") or "")[:120]})
    except Exception:
        pass

    seen, deduped = set(), []
    for r in results:
        key = (r["kind"], r["name"], r["project"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return {"results": deduped[:limit], "skipped": skipped}


def federated_concept(name: str) -> dict:
    """Which projects host a concept (exact anchor match) — the cross-project
    canon view. Returns {concept, projects:[{project, root, kind, neighbors}]}."""
    out = []
    roots, skipped = _live_roots()
    for root in roots:
        proj = discovery.store_name(root)
        try:
            b = _replica_bundle(root, name, degree=0)
            if b:
                anchor = b.get("anchor")
                if anchor and anchor.get("name") == name:
                    neighbors = sum(len(v) for v in (b.get("groups") or {}).values())
                    out.append({"project": proj, "root": str(root),
                                "kind": anchor.get("kind"), "neighbors": neighbors})
        except Exception:
            pass
    return {"concept": name, "projects": out, "skipped": skipped}


def federated_query(dsl: str, *, limit: int = 50) -> dict:
    """Run a DSL query against every live store, returning per-project hit
    counts + entity ids."""
    out = []
    roots, skipped = _live_roots()
    for root in roots:
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
    return {"projects": out, "skipped": skipped}


def _locate_one_project(root, filename: str | None,
                        keywords: list[str]) -> dict:
    """Per-project locate. Returns {path: {path, project, root, score, why}} for
    the live store at `root`. Best-effort; returns {} on any failure.

    - `filename` (basename, no path) -> exact-basename match on code/doc entity
      paths (the `name` hit; score 0 from keywords, but always surfaced).
    - `keywords` -> reuse the proven content-ranking bundle per keyword and
      accumulate a relevance score per file path (rank-decayed, summed).
    """
    proj = discovery.store_name(root)
    hits: dict[str, dict] = {}

    def _bump(path: str | None, score: float, why: str,
              name_hit: bool = False) -> None:
        if not path:
            return
        h = hits.get(path)
        if h is None:
            h = {"path": path, "project": proj, "root": str(root),
                 "score": 0.0, "name_hit": False, "why": set()}
            hits[path] = h
        h["score"] += score
        if name_hit:
            h["name_hit"] = True
        if why:
            h["why"].add(why)

    # 1) Exact-basename file match via the cached read-only replica.
    if filename:
        try:
            s, lock = cached_replica(root)
            with lock, s.with_partition(proj):
                con = s._connect()
                rows = con.execute(
                    "SELECT DISTINCT path FROM entities "
                    "WHERE kind IN ('code', 'doc') AND path IS NOT NULL "
                    "AND noise = 0 AND partition_id = ? "
                    "AND (path = ? OR path LIKE '%/' || ?)",
                    [s.partition_id, filename, filename],
                ).fetchall()
            for (path,) in rows:
                _bump(path, 0.0, f"filename={filename}", name_hit=True)
        except Exception:
            pass

    # 2) Keyword/concept relevance -> file paths, reusing the content bundle.
    for kw in keywords:
        try:
            b = _replica_bundle(root, kw, degree=0)
        except Exception:
            continue
        if not b:
            continue
        anchor = b.get("anchor")
        if anchor and anchor.get("path"):
            _bump(anchor["path"], 3.0, kw)
        for entries in (b.get("groups") or {}).values():
            for rank, e in enumerate(entries):
                if e.get("path"):
                    _bump(e["path"], max(2.0 - 0.1 * rank, 0.2), kw)
    return hits


def federated_locate(filename: str | None = None,
                     keywords: list[str] | None = None, *,
                     limit: int = 10) -> dict:
    """Locate full filesystem paths by filename (basename, no path) and/or
    keywords/concepts, across every live store. Returns
    {"results": [{path, project, root, score, why}]} ranked best-first.

    Combine semantics:
    - filename only      -> every exact-basename file match (score by keywords
                            is 0, so ties broken by path).
    - keywords only      -> files ranked by summed keyword relevance.
    - filename + keywords -> intersection: basename matches RANKED by their
                            keyword relevance (the "find file X about Y" case).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    keywords = [k for k in (keywords or []) if k.strip()]
    roots, skipped = _live_roots()
    merged: dict[str, dict] = {}
    if roots:
        ex = ThreadPoolExecutor(max_workers=min(8, len(roots)))
        futs = {ex.submit(_locate_one_project, r, filename, keywords): r
                for r in roots}
        try:
            for fut in as_completed(futs, timeout=8):
                try:
                    part = fut.result(timeout=0.1) or {}
                except Exception:
                    part = {}
                for path, h in part.items():
                    cur = merged.get(path)
                    if cur is None:
                        merged[path] = h
                    else:
                        cur["score"] += h["score"]
                        cur["name_hit"] = cur["name_hit"] or h["name_hit"]
                        cur["why"] |= h["why"]
        except Exception:
            pass
        ex.shutdown(wait=False, cancel_futures=True)

    rows = list(merged.values())
    # When a filename is given, it's a hard filter: only basename matches.
    if filename:
        rows = [r for r in rows if r["name_hit"]]
    # Rank: higher score first, then shorter path (closer to root), then path.
    rows.sort(key=lambda r: (-r["score"], len(r["path"]), r["path"]))
    out = [{"path": r["path"], "project": r["project"], "root": r["root"],
            "score": round(r["score"], 3), "why": sorted(r["why"])}
           for r in rows[:limit]]
    return {"results": out, "skipped": skipped}
