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
    if not Path(s.db_path).exists():
        # A read never creates and never caches what it cannot open: the
        # driver refuses a read-only open of a missing file (nothing is
        # written), but caching the unopened Store would hand every later
        # caller in this process the same dead entry, and the miss would
        # surface as the driver's IOException at their first query instead
        # of the plain fact — no replica yet (2026-09-15, the replica-first
        # partition probe on a bootstrap-window root).
        raise FileNotFoundError(f"no replica catalog to read at {s.db_path}")
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


# Fan-out deadlines. A store that has not answered by then is NAMED in
# `skipped` with the deadline (bsd-plan3-r5 #s-3: the pools abandoned their
# stragglers silently and `federated_query` waited 60 s × retries on a held
# writer, then dropped it from both `projects` and `skipped`).
WHERE_FANOUT_S = float(os.environ.get("RMX_WHERE_FANOUT_S", "6") or "6")
LOCATE_FANOUT_S = float(os.environ.get("RMX_LOCATE_FANOUT_S", "8") or "8")
QUERY_OP_TIMEOUT_S = float(os.environ.get("RMX_QUERY_OP_TIMEOUT_S", "20") or "20")
WHERE_MEMORY_OP_S = 3.0


def _skip(skipped: list, root, reason: str) -> None:
    skipped.append({"project": discovery.store_name(root), "root": str(root),
                    "reason": reason})


def _name_stragglers(futs: dict, done: set, skipped: list, deadline_s: float) -> None:
    """Every future still running past the fan-out deadline is a store the
    caller did not hear from: say so, per store."""
    for fut, r in futs.items():
        if fut not in done:
            _skip(skipped, r, f"did not answer within {deadline_s:g}s")


def _where_one_project(root, q: str) -> "tuple[list[dict], list[str]]":
    """code/doc/concept anchor hits (via cached replica) + memory_search hits
    for one project. Returns (rows, reasons): a leg that failed is SAID in
    `reasons` (the memory leg's 3 s bound on a held writer used to be a
    silent `pass` — bsd-plan3-r5 #s-3)."""
    out: list[dict] = []
    reasons: list[str] = []
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
    except Exception as e:  # noqa: BLE001 — said, never mute
        reasons.append(f"replica bundle failed ({type(e).__name__}: {e})")
    try:
        mem = daemon_mod.call(root, "memory_search",
                              {"query": q, "limit": 4, "partition": proj},
                              timeout=WHERE_MEMORY_OP_S, retries=0)
        if mem.get("ok"):
            for m in mem["result"].get("rows", []):
                out.append({"source": "memory", "project": proj,
                            "root": str(root), "name": m["name"], "kind": "memory",
                            "path": None, "snippet": (m.get("content") or "")[:120]})
        else:
            reasons.append(f"memory_search answered an error: {mem.get('error')}")
    except Exception as e:  # noqa: BLE001 — a held writer: the op did not answer
        reasons.append(f"memory_search did not answer within {WHERE_MEMORY_OP_S:g}s "
                       f"({type(e).__name__})")
    return out, reasons


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
    from concurrent.futures import TimeoutError as _FutTimeout
    roots, skipped = _live_roots()
    results: list[dict] = []
    if roots:
        ex = ThreadPoolExecutor(max_workers=min(8, len(roots)))
        futs = {ex.submit(_where_one_project, r, q): r for r in roots}
        done: set = set()
        try:
            for fut in as_completed(futs, timeout=WHERE_FANOUT_S):
                done.add(fut)
                try:
                    rows, reasons = fut.result(timeout=0.1)
                except Exception as e:  # noqa: BLE001 — said per store
                    rows, reasons = [], [f"where failed ({type(e).__name__}: {e})"]
                results.extend(rows or [])
                for why in reasons:
                    _skip(skipped, futs[fut], why)
        except _FutTimeout:
            pass  # the fan-out deadline: the stragglers are named below
        _name_stragglers(futs, done, skipped, WHERE_FANOUT_S)
        # don't block on stragglers (a `with` block would shutdown(wait=True))
        ex.shutdown(wait=False, cancel_futures=True)
    # global behavior memories (hub-local; fast) — bounded, one attempt, said
    try:
        from refmatrix import hub as hub_mod
        if hub_mod.global_store_root().exists():
            g = hub_mod.global_call("memory_search", {"query": q, "limit": 6},
                                    timeout=WHERE_MEMORY_OP_S, retries=0)
            if g.get("ok"):
                for m in g["result"].get("rows", []):
                    results.append({
                        "source": "global", "project": "global",
                        "root": str(hub_mod.global_store_root()),
                        "name": m["name"], "kind": "memory", "path": None,
                        "snippet": (m.get("content") or "")[:120]})
            else:
                skipped.append({"project": "global", "root": str(hub_mod.global_store_root()),
                                "reason": f"memory_search answered an error: {g.get('error')}"})
    except Exception as e:  # noqa: BLE001 — the global leg, said
        from refmatrix import hub as hub_mod
        skipped.append({"project": "global", "root": str(hub_mod.global_store_root()),
                        "reason": f"global memory_search did not answer within "
                                  f"{WHERE_MEMORY_OP_S:g}s ({type(e).__name__})"})

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
            # one attempt: a held writer does not free in 20 s, and the
            # library's retries made this 60 s per store, sequentially
            r = daemon_mod.call(root, "query",
                                {"expr": dsl, "partition": proj, "limit": limit},
                                timeout=QUERY_OP_TIMEOUT_S, retries=0)
        except Exception as e:  # noqa: BLE001 — the op did not answer: said
            _skip(skipped, root, f"daemon busy: query did not answer within "
                                 f"{QUERY_OP_TIMEOUT_S:g}s ({type(e).__name__})")
            continue
        if r.get("ok"):
            res = r["result"]
            rows = res.get("rows") or []
            out.append({"project": proj, "root": str(root),
                        "count": res.get("cardinality", len(rows)),
                        "rows": rows[:limit]})
        else:
            _skip(skipped, root, f"query answered an error: {r.get('error')}")
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
    from concurrent.futures import TimeoutError as _FutTimeout
    keywords = [k for k in (keywords or []) if k.strip()]
    roots, skipped = _live_roots()
    merged: dict[str, dict] = {}
    if roots:
        ex = ThreadPoolExecutor(max_workers=min(8, len(roots)))
        futs = {ex.submit(_locate_one_project, r, filename, keywords): r
                for r in roots}
        done: set = set()
        try:
            for fut in as_completed(futs, timeout=LOCATE_FANOUT_S):
                done.add(fut)
                try:
                    part = fut.result(timeout=0.1) or {}
                except Exception as e:  # noqa: BLE001 — said per store
                    part = {}
                    _skip(skipped, futs[fut], f"locate failed ({type(e).__name__}: {e})")
                for path, h in part.items():
                    cur = merged.get(path)
                    if cur is None:
                        merged[path] = h
                    else:
                        cur["score"] += h["score"]
                        cur["name_hit"] = cur["name_hit"] or h["name_hit"]
                        cur["why"] |= h["why"]
        except _FutTimeout:
            pass  # the fan-out deadline: the stragglers are named below
        _name_stragglers(futs, done, skipped, LOCATE_FANOUT_S)
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
