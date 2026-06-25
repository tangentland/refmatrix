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
    if frag is not None:
        for packed in frag:
            cid = packed >> _CONCEPT_SHIFT
            eid = packed & _ENTITY_MASK
            add(int(cid), int(eid), 1.0)

    # 2. typed linkage edges, restricted to the active partition on both ends
    #    so cross-partition `same_as` / canon edges don't leak foreign nodes
    #    into a partition-local centrality.
    try:
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
