"""Spike 2026-10-07: what SHAPE do refmatrix's adjacencies have, and can it be leveraged?

Read-only. Runs on a COPY of a store's catalog (never the live file):

    cp .refmatrix/catalog.read.duckdb /tmp/x/catalog.duckdb
    python eval/spikes/2026-10-07-adjacency-shape/measure.py /tmp/x/catalog.duckdb \
        --partition-id 4 --out eval/spikes/2026-10-07-adjacency-shape/results-refmatrix.json

The graph measured is the term-location incidence layer (`mentions`: concept -> entity),
which every term-term relation in ADR-0004 is a projection of. Four questions:

1. Degree: is it heavy-tailed (hubs + a hapax tail)? Discrete power-law tail fit
   (Clauset-style xmin by KS) plus the hub share of edges and of roaring bytes.
2. Small world through hubs: entity-to-entity reach within 1 and 2 hops (entity ->
   concept -> entity is one hop), with and without the top hub concepts. The claim
   under test: global walks failed (degree-2 walk 5x worse, PPR flat) because hubs
   put everything within two hops.
3. Communities: Louvain modularity on the entity projection over non-hub,
   non-hapax concepts.
4. Compression: total serialized roaring bytes of every concept bitmap when entity
   ids are renumbered by (a) today's ids, (b) path/locality order, (c) community
   order, (d) a random order (control).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import Counter, defaultdict

import duckdb
import numpy as np
from pyroaring import BitMap


def load(db: str, pid: int):
    c = duckdb.connect(db, read_only=True)
    rows = c.execute(
        """
        SELECT el.concept_id, el.entity_id
        FROM entity_links el
        JOIN linkage_types lt ON lt.id = el.linkage_id
        JOIN entities e ON e.id = el.entity_id
        WHERE lt.name = 'mentions' AND e.partition_id = ?
        """, [pid]).fetchall()
    ents = c.execute(
        "SELECT id, kind, coalesce(path, ''), name FROM entities "
        "WHERE partition_id = ? AND kind != 'concept'", [pid]).fetchall()
    names = dict(c.execute(
        "SELECT id, name FROM entities WHERE partition_id = ? AND kind = 'concept'",
        [pid]).fetchall())
    return rows, ents, names


def powerlaw_fit(x: np.ndarray, max_xmin: int = 200) -> dict:
    """Discrete power-law MLE (Clauset, Shalizi & Newman 2009 approximation):
    alpha = 1 + n / sum(ln(x / (xmin - 0.5))), xmin chosen to minimise KS distance."""
    x = np.sort(x[x >= 1])
    best = None
    for xmin in sorted(set(int(v) for v in x if v <= max_xmin)):
        tail = x[x >= xmin]
        n = len(tail)
        if n < 50:
            break
        alpha = 1.0 + n / np.sum(np.log(tail / (xmin - 0.5)))
        # KS between empirical and fitted CCDF on the tail
        uniq = np.unique(tail)
        emp = np.array([np.mean(tail >= u) for u in uniq])
        fit = (uniq / xmin) ** (1.0 - alpha)
        d = float(np.max(np.abs(emp - fit)))
        if best is None or d < best["ks"]:
            best = {"xmin": xmin, "alpha": float(alpha), "ks": d, "n_tail": int(n)}
    return best or {}


def percentiles(x: np.ndarray) -> dict:
    return {f"p{p}": float(np.percentile(x, p)) for p in (25, 50, 75, 90, 95, 99)} | {
        "max": int(x.max()), "mean": float(x.mean())}


def bitmap_bytes(groups: dict[int, list[int]], relabel: "dict[int, int] | None") -> int:
    total = 0
    for ents in groups.values():
        ids = [relabel[e] for e in ents] if relabel is not None else ents
        bm = BitMap(ids)
        bm.run_optimize()
        total += len(bm.serialize())
    return total


def reach(ent_to_con, con_to_ent, sources, banned: set[int]) -> dict:
    """Fraction of all entities reachable from each source within 1 and 2 entity hops."""
    n_ent = len(ent_to_con)
    r1, r2 = [], []
    for s in sources:
        hop1 = set()
        for c in ent_to_con[s]:
            if c not in banned:
                hop1.update(con_to_ent[c])
        hop1.discard(s)
        hop2 = set(hop1)
        for e in hop1:
            for c in ent_to_con[e]:
                if c not in banned:
                    hop2.update(con_to_ent[c])
        hop2.discard(s)
        r1.append(len(hop1) / n_ent)
        r2.append(len(hop2) / n_ent)
    return {"reach1_mean": float(np.mean(r1)), "reach2_mean": float(np.mean(r2)),
            "reach2_p50": float(np.median(r2))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--partition-id", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sources", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261007)
    a = ap.parse_args()
    t0 = time.time()
    rows, ents, names = load(a.db, a.partition_id)

    con_to_ent: dict[int, list[int]] = defaultdict(list)
    ent_to_con: dict[int, list[int]] = defaultdict(list)
    for cid, eid in set(rows):
        con_to_ent[cid].append(eid)
        ent_to_con[eid].append(cid)
    df = np.array([len(v) for v in con_to_ent.values()])
    edeg = np.array([len(v) for v in ent_to_con.values()])
    edges = int(df.sum())

    # hubs = top 1% / top 0.1% concepts by df
    order = sorted(con_to_ent, key=lambda c: -len(con_to_ent[c]))
    top1 = set(order[: max(1, len(order) // 100)])
    top01 = set(order[: max(1, len(order) // 1000)])
    hapax = {c for c, v in con_to_ent.items() if len(v) <= 1}

    def share(cs):
        return sum(len(con_to_ent[c]) for c in cs) / edges

    out: dict = {"partition_id": a.partition_id, "concepts": len(con_to_ent),
                 "entities": len(ent_to_con), "edges": edges}
    out["concept_df"] = percentiles(df) | {"share_df_le_1": float(np.mean(df <= 1))}
    out["entity_degree"] = percentiles(edeg)
    out["powerlaw_concept_df"] = powerlaw_fit(df.astype(float))
    out["top_hubs"] = [{"name": names.get(c, str(c)), "df": len(con_to_ent[c])}
                       for c in order[:12]]
    out["edge_share"] = {"top_0.1pct": share(top01), "top_1pct": share(top1),
                         "df_le_1": share(hapax)}

    # bytes by class, today's ids
    groups = {c: con_to_ent[c] for c in con_to_ent}
    total_b = bitmap_bytes(groups, None)
    out["roaring_bytes"] = {
        "total": total_b,
        "share_top_1pct": bitmap_bytes({c: con_to_ent[c] for c in top1}, None) / total_b,
        "share_df_le_1": bitmap_bytes({c: con_to_ent[c] for c in hapax}, None) / total_b,
    }

    # small world through hubs
    rnd = random.Random(a.seed)
    sources = rnd.sample(sorted(ent_to_con), min(a.sources, len(ent_to_con)))
    out["reach"] = {
        "all_concepts": reach(ent_to_con, con_to_ent, sources, set()),
        "minus_top_0.1pct": reach(ent_to_con, con_to_ent, sources, top01),
        "minus_top_1pct": reach(ent_to_con, con_to_ent, sources, top1),
    }

    # communities on the entity projection over 2 <= df <= p99 concepts, hubs excluded
    import networkx as nx
    cap = int(np.percentile(df, 99))
    w: Counter = Counter()
    used = 0
    for c, es in con_to_ent.items():
        if c in top1 or not (2 <= len(es) <= cap):
            continue
        used += 1
        es = sorted(es)
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                w[(es[i], es[j])] += 1
    g = nx.Graph()
    g.add_nodes_from(ent_to_con)
    g.add_weighted_edges_from((u, v, x) for (u, v), x in w.items())
    comms = nx.community.louvain_communities(g, weight="weight", seed=a.seed)
    q = nx.community.modularity(g, comms, weight="weight")
    sizes = sorted((len(cm) for cm in comms), reverse=True)
    out["communities"] = {
        "concepts_used": used, "df_cap": cap, "projection_edges": len(w),
        "louvain_modularity": float(q), "n_communities": len(comms),
        "largest": sizes[:8], "singletons": int(sum(1 for s in sizes if s == 1)),
    }
    comm_of = {e: i for i, cm in enumerate(comms) for e in cm}

    # compression under id orderings
    meta = {eid: (path, name) for eid, kind, path, name in ents}
    ids = sorted(ent_to_con)

    def relabel(seq):
        return {e: i for i, e in enumerate(seq)}

    by_path = sorted(ids, key=lambda e: (meta.get(e, ("", ""))[0], meta.get(e, ("", ""))[1], e))
    by_comm = sorted(ids, key=lambda e: (comm_of.get(e, -1), meta.get(e, ("", ""))[0], e))
    shuffled = ids[:]
    rnd.shuffle(shuffled)
    out["compression_bytes"] = {
        "today_ids": total_b,
        "dense_rank_today_order": bitmap_bytes(groups, relabel(ids)),
        "path_locality_order": bitmap_bytes(groups, relabel(by_path)),
        "community_order": bitmap_bytes(groups, relabel(by_comm)),
        "random_order_control": bitmap_bytes(groups, relabel(shuffled)),
    }
    out["elapsed_s"] = round(time.time() - t0, 1)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
