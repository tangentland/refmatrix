"""
Global PageRank prior over the concept⇄entity graph.

Stage 2 of the scan-prompt ranking work. Precomputes one centrality score
per node (concept or entity) for a partition, offline, and stashes it in the
`pagerank` sidecar table. At query time the scan-prompt salience ranker looks
up a matched concept's score as a *prior* — a query-agnostic measure of how
central the concept is in the graph — instead of (or alongside) raw linkage
degree. Stage 3 (`rmx ... --rank ppr`) layers a query-personalized walk on
top; this module is the static base.

Graph model: bipartite, undirected. Nodes are `entities.id` values. Edges:
  - mention edges from the partition's `mentions` roaring fragment, decoded in
    one pass (`concept_id` high 32 bits, `entity_id` low 32 bits);
  - typed-linkage edges from `entity_links`, restricted to (concept, entity)
    pairs both resident in the active partition. Typed edges carry a heavier
    transition weight than bare mentions (`link_weight`) since `defines` /
    `implements` / `calls` are stronger signal than co-mention.

Stored score is the *centrality ratio* `pr * N` (an average node scores 1.0,
hubs score > 1, leaves < 1) so the salience formula can use it directly
without re-deriving N.
"""
from __future__ import annotations

from pathlib import Path

import re
import time
from typing import TYPE_CHECKING

from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK

if TYPE_CHECKING:
    from refmatrix.store import Store

# Raw session/digest CARD anchors are operational content (the "operational
# content stays out of graph" rule). Anchored at start with either separator so
# curated memory docs that merely contain "session" mid-name aren't caught.
_OPERATIONAL_RE = re.compile(r"(?i)^(session|digest)[-_]")


def _adj_mentions_mode() -> str:
    """How `build_adjacency` should count a `mentions` edge.

    `flat` (default) counts a mention ONCE, unweighted, from the bitmap
    fragment — which is what `--link-weight`'s own help text describes: a
    multiplier "for typed linkage edges (defines/calls/...) relative to bare
    co-mention edges".

    `both` was the previous default and it double-counts: pass 1 adds every
    mention flat at 1.0, then pass 2 adds the SAME edge again at
    `link_weight * tf` from `entity_links`, which mirrors those bitmaps.
    Verified `1 + 2*tf` on live data (stored 171 -> adjacency 343). With 99.3%
    of the edges in this graph being mentions, that made PageRank substantially
    a measure of term frequency — and PageRank is the centrality prior under
    `scan._salience`, so `central` and `df` became nearly the same variable.

    `weighted` keeps pass 2 only: one count, at tf. Measured indistinguishable
    from `both` (the +1 is noise beside 2*tf), so it does not settle whether
    repetition means association strength; it just removes the duplication a
    different way.

    Flipping to `flat` measured NEUTRAL-to-positive on MemAware — scan MRR
    0.241 -> 0.242, hit@20 0.411 -> 0.422, with `context` byte-identical as a
    control (it never reads PageRank). It ships because it is a BUG FIX that
    costs nothing, not because 0.011 hit@20 is a result."""
    import os as _os
    v = (_os.environ.get("RMX_ADJ_MENTIONS") or "flat").strip().lower()
    return v if v in ("both", "flat", "weighted") else "flat"


class _NeighborView:
    """Read-only mapping view over one node's CSR slice. Duck-types the
    dict-of-dicts surface local_push_ppr consumes: .items(), .values()."""

    __slots__ = ("_nbrs", "_wts")

    def __init__(self, nbrs, wts):
        self._nbrs = nbrs
        self._wts = wts

    def items(self):
        return zip(self._nbrs.tolist(), self._wts.tolist())

    def values(self):
        return self._wts

    def __len__(self):
        return len(self._nbrs)


class CSRAdjacency:
    """Compact adjacency for caching in a long-lived daemon.

    The dict-of-dicts build_adjacency returns costs ~100+ bytes per directed
    edge in Python object overhead — ~180MB on a 1M-edge store, which is
    daemon-jetsam territory. CSR arrays cost 16 bytes/edge (~15MB for the
    same store). Duck-types the subset of the mapping API the PPR walker
    uses: `u in adj`, `adj.get(u, default)`, `adj[u].items()/.values()`."""

    __slots__ = ("_index", "_offsets", "_nbrs", "_wts")

    def __init__(self, index, offsets, nbrs, wts):
        self._index = index      # {node_id: dense_row}
        self._offsets = offsets  # int64[rows+1]
        self._nbrs = nbrs        # int64[edges]
        self._wts = wts          # float64[edges]

    @classmethod
    def from_dict(cls, adj: dict) -> "CSRAdjacency":
        import numpy as np
        index = {u: i for i, u in enumerate(adj)}
        offsets = np.zeros(len(adj) + 1, dtype=np.int64)
        total = sum(len(v) for v in adj.values())
        nbrs = np.empty(total, dtype=np.int64)
        wts = np.empty(total, dtype=np.float64)
        pos = 0
        for u, row in adj.items():
            offsets[index[u]] = pos
            for v, w in row.items():
                nbrs[pos] = v
                wts[pos] = w
                pos += 1
        offsets[len(adj)] = pos
        # offsets[i] currently holds row-start; verify monotonic by
        # construction (dict iteration order == index order).
        return cls(index, offsets, nbrs, wts)

    def __contains__(self, u) -> bool:
        return u in self._index

    def __getitem__(self, u) -> _NeighborView:
        i = self._index[u]
        lo, hi = int(self._offsets[i]), int(self._offsets[i + 1])
        return _NeighborView(self._nbrs[lo:hi], self._wts[lo:hi])

    def get(self, u, default=None):
        if u in self._index:
            return self[u]
        return default if default is not None else _EMPTY_VIEW

    def __len__(self):
        return len(self._index)


import numpy as _np
_EMPTY_VIEW = _NeighborView(_np.empty(0, dtype=_np.int64),
                            _np.empty(0, dtype=_np.float64))


def _adj_disk_paths(store: "Store"):
    root = Path(store.root)
    return root / "adjacency.cache.npz", root / "adjacency.cache.json"


def _adj_log_size(store: "Store") -> "int | None":
    """facts.log size as the graph-version proxy: every logged write grows
    it, and the restructuring ops force a snapshot (0.61.2), so equal size
    == same graph for cache purposes. None (log disabled/missing) opts out
    of the disk tier."""
    try:
        lp = getattr(store, "log_path", None)
        if lp is None:
            return None
        return int(Path(lp).stat().st_size)
    except OSError:
        return None


def cached_adjacency(store: "Store", *, link_weight: float = 2.0,
                     exclude_operational: bool = True) -> CSRAdjacency:
    """CSR adjacency with two cache tiers sharing one freshness key.

    In-process: stored on the Store instance, dropped by
    _invalidate_content_rank_caches (the BM25 caches' write-batch boundary).
    Serves the long-lived daemon.

    On-disk (.refmatrix/adjacency.cache.npz): keyed by (partition, params,
    facts.log size). Serves the ONE-SHOT processes — the CLI's replica-first
    context path and the scan-prompt hook — where an instance cache dies
    with the process (measured: warm CLI calls paid the full ~0.6s rebuild).
    Written atomically by whoever builds; a stale or unreadable file falls
    back to a fresh build. Best-effort throughout."""
    import json as _json
    key = (store._partition_id, link_weight, exclude_operational,
           _adj_mentions_mode())
    cached = getattr(store, "_adjacency_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]

    log_size = _adj_log_size(store)
    npz_path, meta_path = _adj_disk_paths(store)
    disk_key = list(key) + [log_size]
    if log_size is not None:
        try:
            meta = _json.loads(meta_path.read_text())
            if meta.get("key") == disk_key:
                import numpy as np
                z = np.load(npz_path)
                index = {int(k): int(v) for k, v in
                         zip(z["idx_keys"], z["idx_vals"])}
                csr = CSRAdjacency(index, z["offsets"], z["nbrs"], z["wts"])
                store._adjacency_cache = (key, csr)
                return csr
        except Exception:
            pass

    adj = build_adjacency(store, link_weight=link_weight,
                          exclude_operational=exclude_operational)
    csr = CSRAdjacency.from_dict(adj)
    store._adjacency_cache = (key, csr)
    if log_size is not None:
        try:
            import numpy as np
            tmp = npz_path.with_suffix(".tmp.npz")
            np.savez(
                tmp,
                idx_keys=np.fromiter(csr._index.keys(), dtype=np.int64,
                                     count=len(csr._index)),
                idx_vals=np.fromiter(csr._index.values(), dtype=np.int64,
                                     count=len(csr._index)),
                offsets=csr._offsets, nbrs=csr._nbrs, wts=csr._wts,
            )
            tmp.replace(npz_path)
            mtmp = meta_path.with_suffix(".tmp.json")
            mtmp.write_text(_json.dumps({"key": disk_key}))
            mtmp.replace(meta_path)
        except Exception:
            pass
    return csr


def build_adjacency(
    store: "Store", *, link_weight: float = 2.0,
    exclude_operational: bool = True,
) -> dict[int, dict[int, float]]:
    """Bipartite concept⇄entity adjacency for the store's ACTIVE partition.

    Returns an undirected weighted adjacency map `{node: {neighbor: weight}}`.
    Parallel edges (a mention AND a typed link between the same pair) sum their
    weights. Self-loops are dropped.

    `exclude_operational` drops raw `session-<id>` / `digest-<id>` card concept
    nodes (and any edge touching them) before building the graph — they are
    operational content (the "operational content stays out of graph" rule),
    and being high-degree hubs they would otherwise top the centrality prior
    and act as PPR conduits between unrelated concepts. Curated memory docs
    that merely contain "session" in their name are NOT excluded."""
    con = store._connect()
    pid = store._partition_id

    # Operational card concept ids to drop from the graph entirely. Match
    # both separators (`session-<id>` raw cards keep the dash; `add_concept`
    # canonicalizes to `session_<id>`) via a broad LIKE prefilter + a precise
    # `^(session|digest)[-_]` regex — so a curated memory like
    # `project_session_0328` (separator not at the start) is never caught.
    # NOT partition-scoped: a code partition's `mentions` fragment can carry
    # cross-partition edges to session-card concepts that live in the
    # sessions-<project> partition, so a partition-local filter misses them.
    # Match operational concepts globally.
    # Any kind, any partition: a session card can enter the graph as a concept
    # node OR as a doc/memory entity the code partition mentions. The anchored
    # regex keeps curated memories (e.g. `project_session_0328`) safe.
    op_ids: set[int] = set()
    if exclude_operational:
        try:
            for r in con.execute(
                "SELECT id, name FROM entities "
                "WHERE lower(name) LIKE 'session%' OR lower(name) LIKE 'digest%'",
            ).fetchall():
                if _OPERATIONAL_RE.match(str(r[1])):
                    op_ids.add(int(r[0]))
        except Exception:
            op_ids = set()

    adj: dict[int, dict[int, float]] = {}

    def add(a: int, b: int, w: float) -> None:
        if a == b or w <= 0 or a in op_ids or b in op_ids:
            return
        adj.setdefault(a, {})
        adj.setdefault(b, {})
        adj[a][b] = adj[a].get(b, 0.0) + w
        adj[b][a] = adj[b].get(a, 0.0) + w

    # 1. mention fragment — single-pass decode of the whole partition's
    #    packed (concept, entity) forward index.
    try:
        frag = store._load_fragment("mentions")
    except Exception:
        frag = None
    _mmode = _adj_mentions_mode()
    if frag is not None and _mmode != "weighted":
        for packed in frag:
            cid = packed >> _CONCEPT_SHIFT
            eid = packed & _ENTITY_MASK
            add(int(cid), int(eid), 1.0)

    # 2. typed linkage edges, restricted to the active partition on both ends
    #    so cross-partition `same_as` / canon edges don't leak foreign nodes
    #    into a partition-local centrality.
    # `mentions` rows are EXCLUDED here when the dedupe is on, because pass 1
    # already added every one of them from the bitmap fragment. `entity_links`
    # mirrors those bitmaps, so without the filter each mention edge is scored
    # twice -- once flat at 1.0, once at `link_weight * tf` -- giving
    # `1 + 2*tf`, verified on live data (stored 171 -> adjacency 343). Since
    # 99.3% of the edges in this graph ARE mentions, that made PageRank
    # substantially a measure of term frequency, and PageRank feeds
    # `scan._salience`'s centrality prior. The docstring's "a mention AND a
    # typed link between the same pair" assumes the two sources are disjoint;
    # they are not.
    skip_lid = None
    if _mmode == "flat":
        try:
            skip_lid = store.get_linkage_id("mentions")
        except Exception:
            skip_lid = None
    try:
        if skip_lid is not None:
            rows = con.execute(
                "SELECT el.concept_id, el.entity_id, el.weight "
                "FROM entity_links el "
                "JOIN entities ce ON ce.id = el.concept_id AND ce.partition_id = ? "
                "JOIN entities ee ON ee.id = el.entity_id  AND ee.partition_id = ? "
                "WHERE el.linkage_id <> ?",
                (pid, pid, skip_lid),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT el.concept_id, el.entity_id, el.weight "
                "FROM entity_links el "
                "JOIN entities ce ON ce.id = el.concept_id AND ce.partition_id = ? "
                "JOIN entities ee ON ee.id = el.entity_id  AND ee.partition_id = ? ",
                (pid, pid),
            ).fetchall()
    except Exception:
        rows = []
    for r in rows:
        cid, eid = int(r[0]), int(r[1])
        w = r[2] if r[2] is not None else 1.0
        # Negative weights (contradicts) still contribute connectivity; use
        # magnitude for the undirected centrality graph.
        add(cid, eid, link_weight * abs(float(w)))

    return adj


def pagerank(
    adj: dict[int, dict[int, float]], *,
    damping: float = 0.85, max_iter: int = 100, tol: float = 1e-7,
) -> dict[int, float]:
    """Weighted PageRank via power iteration over the undirected weighted
    adjacency from `build_adjacency`. Returns the stationary distribution
    (sums to 1 over all nodes).

    Prefers a scipy.sparse matvec: it runs in C and RELEASES THE GIL during the
    multiply, so a daemon computing this stays responsive to pings (the hub
    watchdog would otherwise see a multi-second pure-python GIL hold as a dead
    daemon and SIGKILL-restart it). Falls back to a pure-python loop when
    numpy/scipy aren't installed (base install without the [dense] extra)."""
    nodes = list(adj.keys())
    n = len(nodes)
    if n == 0:
        return {}
    try:
        return _pagerank_scipy(adj, nodes, damping, max_iter, tol)
    except Exception:
        return _pagerank_pure(adj, nodes, damping, max_iter, tol)


def _pagerank_scipy(
    adj: dict[int, dict[int, float]], nodes: list[int],
    damping: float, max_iter: int, tol: float,
) -> dict[int, float]:
    import numpy as np
    from scipy import sparse

    n = len(nodes)
    idx = {nd: i for i, nd in enumerate(nodes)}
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for u, nbrs in adj.items():
        ui = idx[u]
        for v, w in nbrs.items():
            rows.append(ui)
            cols.append(idx[v])
            data.append(w)
    # M[u, v] = w(u, v). The adjacency is symmetric (undirected), so M == M.T;
    # contribution into v is sum_u M[u,v] * pr[u]/wdeg[u].
    m = sparse.csr_matrix((data, (rows, cols)), shape=(n, n), dtype="float64")
    wdeg = np.asarray(m.sum(axis=1)).ravel()
    nz = wdeg > 0
    inv = np.zeros(n, dtype="float64")
    inv[nz] = 1.0 / wdeg[nz]
    dangling_mask = ~nz
    pr = np.full(n, 1.0 / n, dtype="float64")
    base = (1.0 - damping) / n
    for _ in range(max_iter):
        contrib = m.T.dot(pr * inv)            # C-level matvec, GIL released
        dangling = float(pr[dangling_mask].sum())
        nxt = base + damping * contrib + damping * dangling / n
        if float(np.abs(nxt - pr).sum()) < tol:
            pr = nxt
            break
        pr = nxt
    return {nodes[i]: float(pr[i]) for i in range(n)}


def _pagerank_pure(
    adj: dict[int, dict[int, float]], nodes: list[int],
    damping: float, max_iter: int, tol: float,
) -> dict[int, float]:
    """Dependency-free power iteration. Dangling nodes (none for a connected
    undirected graph, but guarded) redistribute their mass uniformly."""
    n = len(nodes)
    wdeg = {u: sum(adj[u].values()) for u in nodes}
    pr = {u: 1.0 / n for u in nodes}
    base = (1.0 - damping) / n
    for _ in range(max_iter):
        dangling = damping * sum(pr[u] for u in nodes if wdeg[u] <= 0) / n
        nxt = {u: base + dangling for u in nodes}
        for u in nodes:
            wd = wdeg[u]
            if wd <= 0:
                continue
            share = damping * pr[u] / wd
            for v, w in adj[u].items():
                nxt[v] += share * w
        delta = sum(abs(nxt[u] - pr[u]) for u in nodes)
        pr = nxt
        if delta < tol:
            break
    return pr


def compute(
    store: "Store", *, damping: float = 0.85, link_weight: float = 2.0,
    max_iter: int = 100,
) -> dict[int, float]:
    """Compute the centrality-ratio score (`pr * N`) per node for the store's
    active partition. Average node == 1.0. Empty graph → empty dict."""
    adj = build_adjacency(store, link_weight=link_weight)
    pr = pagerank(adj, damping=damping, max_iter=max_iter)
    n = len(pr)
    if n == 0:
        return {}
    return {nid: score * n for nid, score in pr.items()}


def store_scores(
    store: "Store", scores: dict[int, float], *, now: float | None = None,
) -> int:
    """Replace the active partition's `pagerank` rows with `scores`. Returns
    the row count written. Caller owns transaction/locking semantics (the
    daemon op holds `_store_lock`)."""
    con = store._connect()
    pid = store._partition_id
    ts = now if now is not None else time.time()
    con.execute("DELETE FROM pagerank WHERE partition_id = ?", (pid,))
    # Bulk insert — DuckDB (columnar) is pathologically slow at single-row
    # INSERTs, so a per-row loop took minutes on a 110k-node store. executemany
    # batches it into one bind.
    rows = [(pid, int(nid), float(score), ts) for nid, score in scores.items()]
    if rows:
        con.executemany(
            "INSERT INTO pagerank (partition_id, entity_id, score, computed_at) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
    try:
        con.commit()
    except Exception:
        pass
    return len(scores)


def load_scores(store: "Store") -> dict[int, float]:
    """Load the full {entity_id: centrality-ratio} map for the active
    partition. Empty dict if PageRank was never computed."""
    con = store._connect()
    pid = store._partition_id
    try:
        rows = con.execute(
            "SELECT entity_id, score FROM pagerank WHERE partition_id = ?",
            (pid,),
        ).fetchall()
    except Exception:
        return {}
    return {int(r[0]): float(r[1]) for r in rows}


def has_scores(store: "Store") -> bool:
    """True when PageRank has been computed for the active partition (the
    `pagerank` table holds at least one row). Lets callers distinguish a
    concept that is genuinely peripheral (scored low / absent from a
    populated table) from a fresh store where PageRank never ran — the two
    warrant different centrality fallbacks in the salience ranker."""
    con = store._connect()
    pid = store._partition_id
    try:
        row = con.execute(
            "SELECT 1 FROM pagerank WHERE partition_id = ? LIMIT 1", (pid,),
        ).fetchone()
    except Exception:
        return False
    return row is not None


def get_score(store: "Store", entity_id: int) -> float | None:
    """Single centrality-ratio lookup for one node in the active partition,
    or None if absent. Cheap PK-indexed read — used by the scan-prompt
    salience ranker per matched concept."""
    con = store._connect()
    pid = store._partition_id
    try:
        row = con.execute(
            "SELECT score FROM pagerank WHERE partition_id = ? AND entity_id = ?",
            (pid, int(entity_id)),
        ).fetchone()
    except Exception:
        return None
    return float(row[0]) if row else None
