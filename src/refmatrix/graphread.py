"""Graph-read algorithms shared by the `rmx_graph` verb, its CLI twins and the daemon ops.

Why this module exists (task 3.7 #fam-graph-read, 2026-10-20): each graph-read command
carried its algorithm inside its click body — `describe` twice (the CLI and `_op_describe`),
`concept timeline`'s graph and session joins only in the CLI — so the MCP verb could not
reuse them without importing the CLI. These are pure functions over an open `Store`; the
ROUTING (snapshot, daemon op, in-process) is the verb's job (`verbs.graph`), never theirs.
"""
from __future__ import annotations

import json
from pathlib import Path


# ---- describe ---------------------------------------------------------------------------


def describe_payload(s, ref: str, *, first: bool = False, evidence_limit: int = 20,
                     edge_limit: int = 200, sibling_limit: int = 200,
                     include_vectors: bool = True) -> dict:
    """`{found, candidates}` for one entity ref — the daemon `describe` op and the verb's
    no-daemon branch run this one body. An ambiguous ref without `first` lists the
    candidates and describes nothing."""
    targets = s.find_describe_targets(str(ref))
    if not targets:
        return {"found": None, "candidates": []}
    if len(targets) > 1 and not first:
        return {"found": None, "candidates": targets}
    return {"found": s.describe_entity(targets[0]["id"], evidence_limit=evidence_limit,
                                       edge_limit=edge_limit, sibling_limit=sibling_limit,
                                       include_vectors=include_vectors),
            "candidates": targets}


# ---- neighbors / co-occur / top -----------------------------------------------------------


def neighbors_payload(s, concept: str, *, depth: int = 1, linkages=None, limit: int = 50,
                      include_noise: bool = False, strict: bool = False) -> dict:
    """The depth-N linkage closure of `concept`: `{concept, entities: [{id, kind, name,
    path}] (first `limit`), cardinality, hint}`. An empty walk is ambiguous — unknown seed,
    no edges, or edges on the doc's `#root` node — so `hint` says which."""
    from refmatrix.query import QueryEngine
    from refmatrix.telemetry import log_query
    qe = QueryEngine(s, include_noise=include_noise, strict=strict)
    with log_query(s, kind="neighbors", body=concept, source="neighbors") as t:
        bm = qe.neighbors(concept, depth=depth, linkages=list(linkages) if linkages else None)
        t.cardinality = len(bm)
    entities = []
    for eid in list(bm)[:limit]:
        e = s.get_entity_by_id(eid)
        if e:
            entities.append({"id": e.id, "kind": e.kind, "name": e.name, "path": e.path})
    hint = None
    if len(bm) == 0:
        if not s.resolve_concept_ids(concept, strict=strict):
            hint = (f"no concept resolves to '{concept}'"
                    f"{' (try without --strict)' if strict else ''}")
        else:
            hint = f"'{concept}' has no edges at depth={depth}"
            if "#" not in concept and s.resolve_entity(f"{concept}#root"):
                hint += f"; GMD rel: edges for this doc are on '{concept}#root'"
    return {"concept": concept, "entities": entities, "cardinality": len(bm), "hint": hint}


def co_occur_payload(s, concept: str, *, linkage: str = "mentions", limit: int = 20,
                     include_noise: bool = False) -> dict:
    """Concepts sharing entities with `concept` under `linkage`: `{rows: [{concept,
    overlap}]}`, most overlap first."""
    from refmatrix.query import QueryEngine
    from refmatrix.telemetry import log_query
    qe = QueryEngine(s, include_noise=include_noise)
    with log_query(s, kind="co-occur", body=concept, source="co-occur") as t:
        rows = qe.co_occurrence(concept, linkage=linkage)[:limit]
        t.cardinality = len(rows)
    return {"rows": [{"concept": name, "overlap": int(n)} for name, n in rows]}


def top_payload(s, concept: str, *, linkage: str = "mentions", k: int = 10) -> dict:
    """Top-`k` entities by weight under (`linkage`, `concept`): `{rows: [{id, name, kind,
    weight}]}`. An unknown concept raises `LookupError` (the verb words it)."""
    from refmatrix.telemetry import log_query
    e = s.resolve_entity(concept)
    if e is None or e.kind != "concept":
        raise LookupError(f"no concept: {concept}")
    with log_query(s, kind="top", body=concept, source="top") as tlog:
        rows = s.top_weighted(linkage, e.id, k=k)
        tlog.cardinality = len(rows)
    out = []
    for eid, w in rows:
        ent = s.get_entity_by_id(eid)
        out.append({"id": int(eid), "name": ent.name if ent else None,
                    "kind": ent.kind if ent else None, "weight": float(w)})
    return {"rows": out}


# ---- concept timeline -----------------------------------------------------------------------

# Structural linkages whose neighbors carry the concept's file footprint.
TIMELINE_LINKAGES = ["defines", "implements", "calls", "called_by", "imports", "mentions"]


def concept_files(s, cids, *, hops, cap=200):
    """Resolve concept ids -> {abspath: relpath} for the code/doc files in the
    concept's structural footprint, expanding `hops` concept-hops out. Also
    returns the concept names visited (for the header)."""
    from refmatrix.context import _concept_rows
    # Only walk linkages that actually exist — top_weighted/load_bitmap raise
    # on an unregistered linkage type (a fresh store has only what's linked).
    existing = {lk["name"] for lk in s.list_linkages()}
    linkages = [ln for ln in TIMELINE_LINKAGES if ln in existing]
    files: dict[str, str] = {}
    seen: set[int] = set(cids)
    names: dict[int, str] = {}
    for cid in cids:
        ent = s.get_entity_by_id(cid)
        if ent is not None:
            names[cid] = ent.name
    frontier = list(cids)
    depth = 0
    while frontier and depth <= hops and len(files) < cap:
        nxt: list[int] = []
        for cid in frontier:
            for _ln, eid, _w in _concept_rows(s, cid, linkages, cap):
                e = s.get_entity_by_id(eid)
                if e is None:
                    continue
                if e.kind in ("code", "doc") and e.path:
                    files.setdefault(e.path, e.name or e.path)
                elif e.kind == "concept" and depth < hops and e.id not in seen:
                    seen.add(e.id)
                    names[e.id] = e.name
                    nxt.append(e.id)
        frontier = nxt
        depth += 1
    return files, names


def timeline_graph_leg(s, concept: str, *, hops: int) -> dict:
    """The timeline's graph leg: `{files: {abspath: relpath}, concepts: {id: name},
    project: <project dir>}`. An unresolvable concept raises `LookupError`."""
    cids = s.resolve_concept_ids(concept, strict=False)
    if not cids:
        e = s.resolve_entity(concept)
        if e is not None and e.kind == "concept":
            cids = [e.id]
    if not cids:
        raise LookupError(f"unknown concept: {concept!r}")
    files, names = concept_files(s, cids, hops=hops)
    return {"files": files, "concepts": names, "project": str(Path(s.root).parent)}


def since_to_iso(since: "str | None") -> "str | None":
    """Convert `7d`/`1h`/ISO-prefix to an ISO timestamp string for comparison. An
    unparseable value is returned as given (compared as an ISO prefix)."""
    if not since:
        return None
    if since[0:4].isdigit() and "-" in since:
        return since
    from refmatrix.verbs import VerbError, parse_duration
    try:
        secs = parse_duration(since)
    except VerbError:
        return since
    import datetime
    import time
    return (datetime.datetime.fromtimestamp(time.time() - secs, tz=datetime.timezone.utc)
            .isoformat().replace("+00:00", "Z"))


def build_timeline(concept: str, *, hops: int, k: int, graph: dict, git_events: list,
                   direct_rows: list, indirect_rows: list, since: "str | None",
                   until: "str | None", warnings: list) -> dict:
    """Join the legs into the `concept timeline` answer: direct sessions (they name the
    concept) outrank indirect ones (they touched one of its files); events sort by date;
    the earliest `k` session rows are kept (introduction is the point)."""
    since_iso, until_iso = since_to_iso(since), since_to_iso(until)
    rel_keys = list(graph["files"].values())
    sessions: dict[str, dict] = {}

    def _record(m, how, via=None):
        sid = session_meta_get(m, "session_id") or m.get("name", "")
        ended = session_meta_get(m, "ended") or ""
        if since_iso and ended and ended < since_iso:
            return
        if until_iso and ended and ended > until_iso:
            return
        title = (m.get("content") or "").split("\n", 2)[0].lstrip("# ").strip()
        title = title.split(" {#")[0]
        cur = sessions.get(sid)
        if cur is None:
            sessions[sid] = {"date": ended, "title": title[:56], "how": how, "via": via}
        elif how == "direct" and cur["how"] != "direct":
            cur["how"] = "direct"  # naming the concept outranks a file touch
            cur["via"] = None

    for m in direct_rows:
        _record(m, "direct")
    if rel_keys:
        for m in indirect_rows:
            touched = session_meta_list(m, "files_touched")
            hit = next((rel for rel in rel_keys if any(rel in f for f in touched)), None)
            if hit:
                _record(m, "indirect", via=hit)
    events = list(git_events)
    for sid, d in sessions.items():
        via = f" via {d['via']}" if d.get("via") else ""
        events.append({"date": d["date"], "type": "session", "ref": sid[:8],
                       "detail": f"[{d['how']}{via}] {d['title']}"})
    events = [e for e in events if e["date"]]
    events.sort(key=lambda e: e["date"])
    session_events = [e for e in events if e["type"] == "session"]
    truncated = len(session_events) > k
    if truncated:
        keep = set(id(e) for e in session_events[:k])
        events = [e for e in events if e["type"] != "session" or id(e) in keep]
    return {"concept": concept, "resolved_files": len(graph["files"]),
            "resolved_concepts": len(graph["concepts"]), "hops": hops, "events": events,
            "session_count": len(session_events), "truncated": truncated,
            "warnings": list(warnings)}


# ---- the session index (the `sessions-<project>` partition) ------------------------------


def sessions_partition(root) -> str:
    """`sessions-<project>` for the store at `root` — where session cards live."""
    from refmatrix.store import SESSIONS_PARTITION_PREFIX
    try:
        project = Path(root).resolve().parent.name or "default"
    except OSError:
        project = "default"
    return f"{SESSIONS_PARTITION_PREFIX}{project}"


def session_meta_get(mem: dict, key: str, default=None):
    """Reach into memory_content.metadata; handle daemon (already-parsed)
    vs. direct-store (may be a JSON str) shapes."""
    meta = mem.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    return meta.get(key, default) if isinstance(meta, dict) else default


def session_meta_list(mem: dict, key: str) -> list[str]:
    """List-valued metadata accessor. Frontmatter list values like
    `files_touched: ["a", "b"]` survive ingest as JSON-encoded strings
    (the YAML parser used by ingest-gmd's --as-memory path doesn't unwrap
    nested metadata). Parse on read; a non-JSON bracket list is split on commas."""
    v = session_meta_get(mem, key)
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
            inner = s[1:-1].strip()
            if not inner:
                return []
            return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
        return [s] if s else []
    return []
