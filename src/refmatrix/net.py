"""Prompt-as-net expansion: core clique -> tldr expansion -> corroboration cull.

A fourth concept-selection strategy, distinct from `ppr` (diffuse mass and read
the vector) and `enrich` (degree-2 walk with soft reach weighting). The shape:

    1. CORE      the prompt's concepts, plus the session's STM focus,
                 linked to each other as a clique — the prompt asserts they
                 belong together, and ingest already writes co-occurrence
                 inside a document as an edge for exactly that reason.
    2. EXPAND    reach out from the core two ways: graph adjacency, and the
                 core nodes' own `tldr` bodies (which anchored concepts only
                 started carrying once `_extract_concept` stopped returning
                 bare labels).
    3. CULL      keep only nodes reached by MORE THAN ONE core member — the
                 net. This is the whole point.
    4. DECORATE  attach each net node's degree-1 adjacencies as the result.

Step 3 is why this is not `enrich`. That one soft-weighted by reach
(`(reach/n) ** alpha`) and kept everything under a frontier cap; measured on
MemAware it collapsed to 0.013 MRR against PPR's 0.065, because a degree-2
frontier on a bipartite concept<->entity graph outruns any decay. A hard
corroboration threshold does not weight the fan-out down, it deletes it: a node
one hub seed happens to touch never enters the net at all.

Step 1's STM half is load-bearing for step 3, not decoration. A single-term
prompt has a core of one, and nothing can have more than one edge into a core
of one — the cull would empty the net exactly when the prompt carries the least
signal. Merging the session's focus raises the core above one in precisely that
case. Short prompt, long session is the normal case for an always-on hook.

Caveat worth stating plainly: no independent-question benchmark can measure the
STM half. MemAware's items have no session continuity, so its focus graph is
empty and the STM merge contributes nothing to any number produced there.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from refmatrix.pagerank import _OPERATIONAL_RE, build_adjacency

if TYPE_CHECKING:
    from refmatrix.store import Store

# A node must be reached by at least this many distinct core members to enter
# the net. 2 is the definition of corroboration; higher tightens it further.
DEFAULT_MIN_SUPPORT = 2

# How many body terms to mine per core node when expanding via `tldr`, and how
# many hits each expansion may contribute. Both bounded: the body of a hub
# concept can otherwise recruit a large slice of the store on its own, which
# is the failure the cull exists to prevent — better not to create it.
DEFAULT_BODY_TERMS = 8
DEFAULT_BODY_HITS = 20


def _core_ids(
    store: "Store",
    seed_ids: list[int],
    stm_seed_ids: "list[int] | None",
    adj: dict[int, dict[int, float]],
) -> tuple[list[int], set[int]]:
    """Core = prompt concepts + STM focus concepts, restricted to nodes the
    graph actually knows. Returns `(core, prompt_subset)`."""
    core: list[int] = []
    seen: set[int] = set()
    for sid in seed_ids:
        if sid in adj and sid not in seen:
            seen.add(sid)
            core.append(sid)
    prompt = set(core)
    for sid in (stm_seed_ids or []):
        if sid in adj and sid not in seen:
            seen.add(sid)
            core.append(sid)
    return core, prompt


def _body_expansion(
    store: "Store",
    core: list[int],
    *,
    body_terms: int,
    body_hits: int,
) -> dict[int, set[int]]:
    """`{reached_node: {core members whose BODY reached it}}`.

    Expands through what a core node says, not only what it links to. Two
    concepts can describe the same thing and share no edge — that is the case
    graph adjacency structurally cannot reach, and the case a prompt most often
    means.
    """
    from refmatrix.terms import STOPWORDS, content_terms

    out: dict[int, set[int]] = defaultdict(set)
    con = store._connect()
    for cid in core:
        row = con.execute(
            "SELECT tldr FROM entities WHERE id = ?", (cid,)).fetchone()
        body = (row[0] if row else None) or ""
        if not body.strip():
            continue
        terms: list[str] = []
        for t in content_terms(body, drop_stopwords=False):
            low = t.lower()
            if low in STOPWORDS or len(low) < 3:
                continue
            terms.append(t)
            if len(terms) >= body_terms:
                break
        if not terms:
            continue
        try:
            hits = store.content_rank(terms, limit=body_hits)
        except Exception:
            continue
        for eid, _score in hits:
            if eid != cid:
                out[eid].add(cid)
    return out


def build_net(
    store: "Store",
    seed_ids: list[int],
    *,
    stm_seed_ids: "list[int] | None" = None,
    min_support: int = DEFAULT_MIN_SUPPORT,
    body_terms: int = DEFAULT_BODY_TERMS,
    body_hits: int = DEFAULT_BODY_HITS,
    link_weight: float = 2.0,
    use_bodies: bool = True,
) -> tuple[dict[int, set[int]], list[int], set[int]]:
    """Core -> expand -> cull. Returns `(net, core, prompt_core)`.

    `net` maps each surviving node to the set of core members that reached it,
    so a caller can rank by support and explain why a node is present.
    """
    adj = build_adjacency(store, link_weight=link_weight)
    core, prompt_core = _core_ids(store, seed_ids, stm_seed_ids, adj)
    if not core:
        return {}, [], set()

    support: dict[int, set[int]] = defaultdict(set)
    core_set = set(core)
    for cid in core:
        for nb in adj.get(cid, {}):
            if nb not in core_set:
                support[nb].add(cid)
    if use_bodies:
        for node, sources in _body_expansion(
                store, core, body_terms=body_terms, body_hits=body_hits).items():
            if node not in core_set:
                support[node] |= sources

    net = {n: srcs for n, srcs in support.items() if len(srcs) >= min_support}
    return net, core, prompt_core


def net_concepts(
    store: "Store",
    seed_ids: list[int],
    *,
    k: int = 10,
    stm_seed_ids: "list[int] | None" = None,
    min_support: int = DEFAULT_MIN_SUPPORT,
    use_bodies: bool = True,
    kinds: "tuple[str, ...] | None" = ("concept",),
    include_seeds: bool = True,
) -> list[dict]:
    """Ranked concepts from the net, best-corroborated first.

    Ranked by support (how many core members reached the node), then by the
    node's own degree as a tie-break. Prompt concepts are appended after the
    net so a caller that needs them always has them — the net answers "what
    else", not "instead of".
    """
    net, core, prompt_core = build_net(
        store, seed_ids, stm_seed_ids=stm_seed_ids,
        min_support=min_support, use_bodies=use_bodies,
    )
    if not net and not core:
        return []

    con = store._connect()
    rows: list[dict] = []
    for nid, srcs in sorted(net.items(), key=lambda kv: -len(kv[1])):
        row = con.execute(
            "SELECT name, kind FROM entities WHERE id = ?", (nid,)).fetchone()
        if row is None:
            continue
        name, kind = row[0], row[1]
        if kinds is not None and kind not in kinds:
            continue
        if _OPERATIONAL_RE.match(name or ""):
            continue
        rows.append({"id": nid, "name": name, "kind": kind,
                     "support": len(srcs), "score": float(len(srcs)),
                     "seed": False})
        if len(rows) >= k:
            break

    if include_seeds:
        have = {r["id"] for r in rows}
        for cid in core:
            if cid in have:
                continue
            row = con.execute(
                "SELECT name, kind FROM entities WHERE id = ?", (cid,)).fetchone()
            if row is None:
                continue
            if kinds is not None and row[1] not in kinds:
                continue
            rows.append({"id": cid, "name": row[0], "kind": row[1],
                         "support": 0, "score": 0.0,
                         "seed": cid in prompt_core})
    return rows[:k] if k else rows
