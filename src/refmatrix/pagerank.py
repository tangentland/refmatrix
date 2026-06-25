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

import time
from typing import TYPE_CHECKING

from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK

if TYPE_CHECKING:
    from refmatrix.store import Store


def build_adjacency(
    store: "Store", *, link_weight: float = 2.0,
) -> dict[int, dict[int, float]]:
    """Bipartite concept⇄entity adjacency for the store's ACTIVE partition.

    Returns an undirected weighted adjacency map `{node: {neighbor: weight}}`.
    Parallel edges (a mention AND a typed link between the same pair) sum their
    weights. Self-loops are dropped."""
    adj: dict[int, dict[int, float]] = {}

    def add(a: int, b: int, w: float) -> None:
        if a == b or w <= 0:
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
    con = store._connect()
    pid = store._partition_id
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
    """Weighted PageRank via power iteration. Pure Python (no numpy dep).

    `adj` is the undirected weighted adjacency from `build_adjacency`. Returns
    the stationary distribution (sums to 1 over all nodes). Dangling nodes
    (none, for a connected undirected graph, but guarded anyway) redistribute
    their mass uniformly."""
    nodes = list(adj.keys())
    n = len(nodes)
    if n == 0:
        return {}
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
    for nid, score in scores.items():
        con.execute(
            "INSERT INTO pagerank (partition_id, entity_id, score, computed_at) "
            "VALUES (?, ?, ?, ?)",
            (pid, int(nid), float(score), ts),
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
