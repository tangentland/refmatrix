"""
Local-push approximate Personalized PageRank (PPR) — stage 3 of scan-prompt
ranking.

Where the stage-2 global prior (`pagerank.py`) is query-agnostic, this is the
query-personalized half: seed a random-walk-with-restart on the prompt's
matched concepts and let it propagate over the bipartite concept⇄entity graph.
The payoff over plain salience reranking is *discovery* — the walk surfaces
concepts/entities strongly related to the seeds that the prompt never named.

Algorithm: Andersen–Chung–Lang local push (the standard approximate PPR). It
touches only the local cluster around the seeds — push work is bounded by
O(1/(eps·alpha)), independent of total graph size — so it stays cheap enough
to run per-query when explicitly requested (`--rank ppr`).

    alpha  restart (teleport) probability; 1-alpha is the walk-continuation
           probability. alpha=0.15 ↔ damping 0.85.
    eps    residual threshold per unit weighted-degree; smaller = larger
           explored cluster, more work, more reach.

The graph + edge weights come from `pagerank.build_adjacency`, so typed
linkage edges (defines/calls/...) already carry heavier transition weight than
bare co-mention edges via its `link_weight`.
"""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from refmatrix.pagerank import build_adjacency

if TYPE_CHECKING:
    from refmatrix.store import Store


def local_push_ppr(
    adj: dict[int, dict[int, float]],
    seeds: "dict[int, float] | list[int]",
    *,
    alpha: float = 0.15,
    eps: float = 1e-4,
    max_push: int = 200_000,
) -> dict[int, float]:
    """Approximate personalized PageRank vector via ACL local push.

    `seeds` is either a {node: restart-mass} map (need not be normalized — it
    is) or a list of nodes given uniform mass. Returns {node: ppr-mass} over
    the explored local cluster (unexplored nodes are implicitly 0)."""
    r: dict[int, float] = {}
    if isinstance(seeds, dict):
        total = sum(seeds.values()) or 1.0
        for n, m in seeds.items():
            r[n] = r.get(n, 0.0) + m / total
    else:
        if not seeds:
            return {}
        w = 1.0 / len(seeds)
        for n in seeds:
            r[n] = r.get(n, 0.0) + w

    p: dict[int, float] = {}
    wdeg: dict[int, float] = {}

    def deg(u: int) -> float:
        d = wdeg.get(u)
        if d is None:
            d = sum(adj.get(u, {}).values())
            wdeg[u] = d
        return d

    q: deque[int] = deque()
    inq: set[int] = set()
    for u in list(r):
        if deg(u) > 0 and r[u] > eps * deg(u):
            q.append(u)
            inq.add(u)

    pushes = 0
    while q and pushes < max_push:
        u = q.popleft()
        inq.discard(u)
        du = deg(u)
        ru = r.get(u, 0.0)
        if du <= 0 or ru <= eps * du:
            continue
        pushes += 1
        # Lazy-walk push: settle alpha·r[u] into p, keep half the rest on u,
        # spread the other half across neighbors weighted by edge weight.
        p[u] = p.get(u, 0.0) + alpha * ru
        retain = (1.0 - alpha) * ru / 2.0
        spread = (1.0 - alpha) * ru / 2.0
        r[u] = retain
        for v, w in adj[u].items():
            r[v] = r.get(v, 0.0) + spread * w / du
            if v not in inq and deg(v) > 0 and r[v] > eps * deg(v):
                q.append(v)
                inq.add(v)
        if u not in inq and r[u] > eps * du:
            q.append(u)
            inq.add(u)

    return p


# Raw session/digest CARD anchors are operational content that must not be
# surfaced as graph concepts (see the "operational content stays out of graph"
# rule). They're high-degree hubs, so an unfiltered PPR walk can land on them.
# Curated MEMORY docs whose names merely CONTAIN "session" (e.g.
# `project_session_0328_to_0331`) are knowledge, not cards — only the bare
# `session-<id>` / `digest-<id>` prefixes are excluded.
_OPERATIONAL_PREFIXES = ("session-", "digest-")


def _is_operational(name: str) -> bool:
    return name.startswith(_OPERATIONAL_PREFIXES)


def rank_related(
    store: "Store",
    seed_ids: list[int],
    *,
    k: int = 10,
    alpha: float = 0.15,
    eps: float = 1e-4,
    link_weight: float = 2.0,
    kinds: "tuple[str, ...] | None" = ("concept",),
    include_seeds: bool = True,
) -> list[dict]:
    """Run seeded PPR over the active partition's graph and return the top-`k`
    nodes (by PPR mass) as `{id, name, kind, score, seed}` dicts, optionally
    filtered to `kinds`. `include_seeds=False` drops the seed concepts from the
    output so only *discovered* neighbors remain."""
    adj = build_adjacency(store, link_weight=link_weight)
    seedset = set(seed_ids)
    seeds = {sid: 1.0 for sid in seed_ids if sid in adj}
    if not seeds:
        return []
    p = local_push_ppr(adj, seeds, alpha=alpha, eps=eps)
    con = store._connect()
    out: list[dict] = []
    for nid, score in sorted(p.items(), key=lambda kv: -kv[1]):
        if not include_seeds and nid in seedset:
            continue
        r = con.execute(
            "SELECT name, kind FROM entities WHERE id = ?", (int(nid),),
        ).fetchone()
        if r is None:
            continue
        if kinds and r[1] not in kinds:
            continue
        if _is_operational(r[0]):
            continue
        out.append({
            "id": int(nid), "name": r[0], "kind": r[1],
            "score": score, "seed": nid in seedset,
        })
        if len(out) >= k:
            break
    return out
