"""Full-enrichment expansion: seeds -> degree-2 walk -> coalesce -> rank.

An alternative to `ppr` for turning a prompt's concepts into the concept set
that earns context bundles. Where PPR diffuses mass and reads the result off
one vector, this walks explicitly and keeps the two things PPR conflates:

    reach  — how MANY distinct seeds arrive at a node
    weight — how STRONGLY any single seed arrives

PPR sums those into one number, so a node hammered by one hub seed is
indistinguishable from a node reached weakly by five. On a prompt, the second
is the interesting one: it is the node the whole request agrees on. That is the
same argument `content_rank`'s `coverage^3` makes for entities, and it was the
largest single win in the CSN scoring stack.

The walk is degree-2 over the bipartite concept<->entity graph, which is the
smallest walk that reaches sibling CONCEPTS:

    seed concept --(mentions/typed)--> entity --(mentions/typed)--> concept

One hop lands on documents; two hops land on the other concepts those
documents talk about. Beyond that the frontier is the whole store — measured
below, not assumed.

STM seeds are merged at the front when the caller supplies them: the session's
current focus is evidence about what a short prompt means, and it is the one
input here that adds information rather than rearranging what the prompt
already said. Note that no independent-question benchmark can measure it —
MemAware's items have no session continuity, so an STM prior conditions on
nothing there.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from refmatrix.pagerank import _OPERATIONAL_RE, build_adjacency

if TYPE_CHECKING:
    from refmatrix.store import Store

# Per-hop decay. A degree-2 sibling is real evidence but weaker than a direct
# neighbor; without decay the second hop's fan-out swamps the first.
DEFAULT_DECAY = 0.35

# How much a seed carried in from STM focus counts against one the prompt
# actually named. Below 1.0 on purpose: the prompt is what the user asked,
# the session is only what they were doing.
DEFAULT_STM_WEIGHT = 0.5

# Exponent on reach (distinct seeds arriving). Mirrors content_rank's
# coverage_alpha, for the same reason.
DEFAULT_REACH_ALPHA = 2.0


def walk(
    adj: dict[int, dict[int, float]],
    seeds: dict[int, float],
    *,
    hops: int = 2,
    decay: float = DEFAULT_DECAY,
    max_frontier: int = 4000,
) -> dict[int, tuple[float, set[int]]]:
    """Weighted breadth-first expansion to `hops`, tracking provenance.

    Returns `{node: (accumulated_weight, {seed ids that reached it})}`.

    `max_frontier` bounds each level. The second hop of a hub concept can
    touch a large slice of the store, and an always-on hook cannot pay for
    that; the cap keeps the walk proportional to the prompt rather than to
    the corpus. Levels are truncated by descending weight, so what is dropped
    is the weakest evidence.
    """
    acc: dict[int, tuple[float, set[int]]] = {}
    for sid, w in seeds.items():
        if sid in adj:
            acc[sid] = (w, {sid})

    frontier = dict(acc)

    for hop in range(hops):
        level: dict[int, tuple[float, set[int]]] = {}
        step = decay ** (hop + 1)
        for node, (w, prov) in frontier.items():
            nbrs = adj.get(node)
            if not nbrs:
                continue
            for nb, edge_w in nbrs.items():
                add = w * edge_w * step
                cur_w, cur_prov = level.get(nb, (0.0, set()))
                level[nb] = (cur_w + add, cur_prov | prov)
        if not level:
            break
        if len(level) > max_frontier:
            keep = sorted(level.items(), key=lambda kv: -kv[1][0])[:max_frontier]
            level = dict(keep)
        for nb, (w, prov) in level.items():
            cur_w, cur_prov = acc.get(nb, (0.0, set()))
            acc[nb] = (cur_w + w, cur_prov | prov)
        frontier = level
    return acc


def enrich_concepts(
    store: "Store",
    seed_ids: list[int],
    *,
    k: int = 10,
    hops: int = 2,
    decay: float = DEFAULT_DECAY,
    reach_alpha: float = DEFAULT_REACH_ALPHA,
    stm_seed_ids: "list[int] | None" = None,
    stm_weight: float = DEFAULT_STM_WEIGHT,
    link_weight: float = 2.0,
    clique_weight: float = 0.0,
    kinds: "tuple[str, ...] | None" = ("concept",),
    include_seeds: bool = True,
) -> list[dict]:
    """Run the full enrichment and return ranked `{id, name, kind, score,
    seed, reach}` dicts.

    Score is `weight * (reach / n_seeds) ** reach_alpha` — accumulated walk
    weight, scaled by the fraction of the prompt's seeds that independently
    arrived at the node. A node every seed reaches outranks one that a single
    hub seed reaches hard.
    """
    adj = build_adjacency(store, link_weight=link_weight)
    seeds: dict[int, float] = {sid: 1.0 for sid in seed_ids if sid in adj}
    prompt_seeds = set(seeds)
    for sid in (stm_seed_ids or []):
        if sid in adj and sid not in seeds:
            seeds[sid] = stm_weight
    if not seeds:
        return []

    if clique_weight > 0:
        from refmatrix.ppr import overlay_prompt_clique
        adj = overlay_prompt_clique(adj, list(seeds), weight=clique_weight)

    acc = walk(adj, seeds, hops=hops, decay=decay)
    n_seeds = max(len(seeds), 1)

    con = store._connect()
    scored: list[dict] = []
    for nid, (w, prov) in acc.items():
        if not include_seeds and nid in prompt_seeds:
            continue
        reach = len(prov)
        score = w * ((reach / n_seeds) ** reach_alpha)
        scored.append({"id": nid, "score": score, "reach": reach,
                       "seed": nid in prompt_seeds})

    scored.sort(key=lambda r: -r["score"])
    out: list[dict] = []
    for rec in scored:
        row = con.execute(
            "SELECT name, kind FROM entities WHERE id = ?", (rec["id"],),
        ).fetchone()
        if row is None:
            continue
        name, kind = row[0], row[1]
        if kinds is not None and kind not in kinds:
            continue
        if _OPERATIONAL_RE.match(name or ""):
            continue
        rec["name"] = name
        rec["kind"] = kind
        out.append(rec)
        if len(out) >= k:
            break
    return out
