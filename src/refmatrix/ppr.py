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

from refmatrix.pagerank import _OPERATIONAL_RE, build_adjacency

if TYPE_CHECKING:
    from refmatrix.store import Store


def local_push_ppr(
    adj,  # dict[int, dict[int, float]] | pagerank.CSRAdjacency (duck-typed)
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
def _is_operational(name: str) -> bool:
    return bool(_OPERATIONAL_RE.match(name))


def overlay_prompt_clique(
    adj: dict[int, dict[int, float]],
    seeds: list[int],
    *,
    weight: float = 1.0,
) -> dict[int, dict[int, float]]:
    """Return `adj` with a weighted clique added among `seeds`.

    Seeding PPR on several concepts is NOT the same as linking them. Joint
    seeding gives each seed its own restart mass and sums the diffusions, so a
    node near many seeds scores well — but mass never flows THROUGH one prompt
    concept to reach another's neighborhood. A clique changes the topology: a
    walk that lands on A can step directly to B, so B's region is reinforced by
    A's mass and the walk can reach clusters no single seed reaches alone.

    The justification is the one ingest already uses. Co-occurrence inside a
    document is written as a co-mention edge because it is evidence of
    association. A prompt is a document. Leaving its concepts mutually
    unlinked is the inconsistency.

    The risk is symmetric and real: a junk seed that survives the salience gate
    now leaks its mass into every other seed's neighborhood. Hence `weight`
    defaults well below `build_adjacency`'s `link_weight` (2.0) and the caller
    scales per-edge by endpoint salience.

    Mutates a shallow copy — the caller's `adj` is left alone, but the
    per-node dicts are copied only for the seeds we touch.
    """
    if weight <= 0 or len(seeds) < 2:
        return adj
    present = [n for n in seeds if n in adj]
    if len(present) < 2:
        return adj
    out = dict(adj)
    for a in present:
        row = dict(out[a])
        for b in present:
            if a == b:
                continue
            row[b] = row.get(b, 0.0) + weight
        out[a] = row
    return out


def seed_coverage(
    adj: dict[int, dict[int, float]],
    seeds: list[int],
) -> dict[int, float]:
    """For each seed, the fraction of its neighbors shared with the OTHER
    seeds — "how much of this concept's world is also the rest of the
    prompt's world".

    This is the bitmap-coverage idea applied to concept SELECTION rather than
    entity ranking. `content_rank` already multiplies entity scores by
    `(covered_terms / n_terms) ** 3`, and on CodeSearchNet that coverage term
    was the single largest jump in the whole scoring stack (+0.050 MRR@10).
    Concept selection never used it: bundles went to the highest-salience
    concepts, where salience is a property of the concept alone and knows
    nothing about the rest of the prompt.

    Uses the adjacency rather than reading roaring fragments directly, because
    the PPR path has already built it — so this costs set intersections, not
    another pass over the store.
    """
    if len(seeds) < 2:
        return {n: 0.0 for n in seeds}
    nbrs = {n: set(adj.get(n, {})) for n in seeds}
    out: dict[int, float] = {}
    for n in seeds:
        mine = nbrs[n]
        if not mine:
            out[n] = 0.0
            continue
        others: set[int] = set()
        for m in seeds:
            if m != n:
                others |= nbrs[m]
        out[n] = len(mine & others) / len(mine)
    return out


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


def rank_related_for_prompt(
    store: "Store",
    seed_ids: list[int],
    *,
    k: int = 10,
    alpha: float = 0.15,
    eps: float = 1e-4,
    link_weight: float = 2.0,
    clique_weight: float = 0.0,
    coverage_alpha: float = 0.0,
    kinds: "tuple[str, ...] | None" = ("concept",),
    include_seeds: bool = True,
) -> list[dict]:
    """PPR over the prompt's concepts, with the two prompt-aware terms.

    Differs from `rank_related` in that the seeds are treated as a SET that
    the prompt itself asserts belongs together:

    * `clique_weight > 0` links the seeds to each other before the walk, so
      mass can travel between them (see `overlay_prompt_clique`).
    * `coverage_alpha > 0` boosts a seed by how much its neighborhood overlaps
      the rest of the prompt's, so bundles go to the concepts that are
      coherent with the request rather than the ones that are merely central
      on their own (see `seed_coverage`).

    Both default to off; `rank_related`'s behavior is the zero case. Returns
    the same `{id, name, kind, score, seed}` dicts, with `coverage` added for
    seed rows.
    """
    adj = build_adjacency(store, link_weight=link_weight)
    present = [sid for sid in seed_ids if sid in adj]
    if not present:
        return []

    cov = seed_coverage(adj, present) if coverage_alpha > 0 else {}
    walk_adj = overlay_prompt_clique(adj, present, weight=clique_weight)
    p = local_push_ppr(walk_adj, {sid: 1.0 for sid in present},
                       alpha=alpha, eps=eps)

    if coverage_alpha > 0:
        # (1 + cov) rather than cov: a seed sharing nothing with the rest of
        # the prompt is demoted, never zeroed. A single-concept prompt has no
        # "rest" and must not have all its mass erased.
        for sid, c in cov.items():
            if sid in p:
                p[sid] *= (1.0 + c) ** coverage_alpha

    seedset = set(present)
    con = store._connect()
    out: list[dict] = []
    for nid, score in sorted(p.items(), key=lambda kv: -kv[1]):
        if not include_seeds and nid in seedset:
            continue
        row = con.execute(
            "SELECT name, kind FROM entities WHERE id = ?", (nid,),
        ).fetchone()
        if row is None:
            continue
        name, kind = row[0], row[1]
        if kinds is not None and kind not in kinds:
            continue
        if _OPERATIONAL_RE.match(name or ""):
            continue
        rec = {"id": nid, "name": name, "kind": kind, "score": score,
               "seed": nid in seedset}
        if nid in cov:
            rec["coverage"] = cov[nid]
        out.append(rec)
        if len(out) >= k:
            break
    return out
