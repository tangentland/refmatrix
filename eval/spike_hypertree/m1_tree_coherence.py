"""M1 — tree-coherence of concepts (hypertree exploration, spike 2026-10-20).

Read-only, on a COPY of a store's snapshot. Measures whether refmatrix's concept hyperedges
(`mentions`: concept -> entity) are local to the `fs` containment tree, i.e. whether the store
is a hypertree in the graph-theory sense ([[exploration-hypertree#def-graph-theory]]).

Definitions (pre-registered metric, operationalised here):
- members = every `mentions` member with a path: doc, code, and the path-bearing concept-kind
  GMD section nodes (most members are sections; the 2026-10-07 spike counted them too).
- tree node of an entity = its root-relative path components (dir ... file). Code symbols and
  sections sit at their file. Files in the project's ~/.claude memory dir map to a virtual
  top-level `@memory` subtree; other paths outside the root (`@ext`, e.g. /private/tmp scratch)
  and path-less rows (memory rows) are excluded and counted.
- concept population: `mentions` concepts with df >= 2 over the included entities.
- LCA of a concept = longest common component prefix of its members' nodes; depth = its length
  (a file node counts as a level, so "all members in src/foo.py" is depth 2).
- tree-local@k: LCA depth >= k. The band metric is the EDGE-WEIGHTED share local@2
  (sum df of local concepts / sum df), as the doc specifies. Unweighted share also reported.
- components: distinct depth-2 subtrees (node truncated to 2 components) a concept touches.
- null: the same concepts with entity->node assignment permuted (seeded, 3 draws), so
  "local by chance" is visible.

Associative-power add-on (the user's framing, 2026-10-20): for 300 seeded source entities,
rank every other entity by idf-weighted shared non-hub concepts (2 <= df <= p99) and report
the share of each source's top-10 associates that lie OUTSIDE its depth-2 subtree, against
the share expected at random. That is the share of "what else bears on this?" that a
subtree-scoped retrieval would drop. Also: mean association (idf-weighted Jaccard) by tree
distance bucket, as lift over random pairs — whether LCA proximity carries signal (B's
proximity band).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, SEED, STORES, copy_db, rel_parts  # noqa: E402


def lcp_len(a: tuple, b: tuple) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def coherence(con_to_ent, node_of, weight_df=True):
    tot_w = 0
    loc = {1: 0, 2: 0, 3: 0}
    loc_n = {1: 0, 2: 0, 3: 0}
    single_file_w = 0
    comps = []
    comps_w = 0.0
    n = 0
    for c, es in con_to_ent.items():
        nodes = [node_of[e] for e in es]
        df = len(es)
        lca = nodes[0]
        L = len(lca)
        for nd in nodes[1:]:
            L = min(L, lcp_len(lca, nd))
            if L == 0:
                break
        n += 1
        tot_w += df
        for k in loc:
            if L >= k:
                loc[k] += df
                loc_n[k] += 1
        if len(set(nodes)) == 1:
            single_file_w += df
        k2 = len({nd[:2] for nd in nodes})
        comps.append(k2)
        comps_w += k2 * df
    return {
        "concepts": n, "edges": tot_w,
        "edge_weighted_local": {f"depth>={k}": loc[k] / tot_w for k in loc},
        "unweighted_local": {f"depth>={k}": loc_n[k] / n for k in loc_n},
        "edge_weighted_single_file": single_file_w / tot_w,
        "components_depth2_mean": float(np.mean(comps)),
        "components_depth2_p50": float(np.median(comps)),
        "components_depth2_edge_weighted_mean": comps_w / tot_w,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("store")
    ap.add_argument("--sources", type=int, default=300)
    a = ap.parse_args()
    root, pid = STORES[a.store]
    t0 = time.time()
    c = duckdb.connect(copy_db(a.store), read_only=True)
    ents = c.execute(
        "SELECT id, kind, path FROM entities WHERE partition_id = ? AND path IS NOT NULL",
        [pid]).fetchall()
    rows = c.execute(
        """SELECT DISTINCT el.concept_id, el.entity_id, ce.name
           FROM entity_links el JOIN linkage_types lt ON lt.id = el.linkage_id
           JOIN entities e ON e.id = el.entity_id
           JOIN entities ce ON ce.id = el.concept_id
           WHERE lt.name = 'mentions' AND e.partition_id = ? AND e.path IS NOT NULL""",
        [pid]).fetchall()

    node_of: dict[int, tuple] = {}
    excl = {"no_path": 0, "external": 0}
    for eid, kind, path in ents:
        p = rel_parts(path, root)
        if p is None:
            excl["no_path"] += 1
        elif p[0] == "@ext" and "/.claude/projects/" in path and "/memory/" in path:
            # the project's curated memory dir is a real containment subtree the store
            # ingests; give it a virtual top-level node instead of dropping it
            node_of[eid] = ("@memory",) + tuple(
                x for x in path.split("/memory/", 1)[1].split("/") if x)
            excl["memory_dir_mapped"] = excl.get("memory_dir_mapped", 0) + 1
        elif p[0] == "@ext":
            excl["external"] += 1
        else:
            node_of[eid] = p
    cname: dict[int, str] = {}
    c2e: dict[int, set] = defaultdict(set)
    for cid, eid, nm in rows:
        if eid in node_of:
            c2e[cid].add(eid)
            cname[cid] = nm
    c2e2 = {k: v for k, v in c2e.items() if len(v) >= 2}
    df = np.array([len(v) for v in c2e2.values()])
    p99 = float(np.percentile(df, 99))
    order = sorted(c2e2, key=lambda k: -len(c2e2[k]))
    top1 = set(order[: max(1, len(order) // 100)])

    out: dict = {"store": a.store, "partition_id": pid, "entities_in_tree": len(node_of),
                 "excluded_entities": excl, "files": len(set(node_of.values())),
                 "max_tree_depth": max(len(v) for v in node_of.values()),
                 "df_p99": p99}
    out["all_df_ge_2"] = coherence(c2e2, node_of)
    out["non_keyword"] = coherence(
        {k: v for k, v in c2e2.items() if not cname[k].startswith("keyword/")}, node_of)
    out["minus_top1pct_hubs"] = coherence(
        {k: v for k, v in c2e2.items() if k not in top1}, node_of)

    # null: permute entity -> node
    rnd = random.Random(SEED)
    eids = sorted(node_of)
    nulls = []
    for _ in range(3):
        perm = [node_of[e] for e in eids]
        rnd.shuffle(perm)
        nulls.append(coherence(c2e2, dict(zip(eids, perm))))
    out["null_permuted"] = {
        "edge_weighted_local_depth>=2": float(np.mean(
            [x["edge_weighted_local"]["depth>=2"] for x in nulls])),
        "unweighted_local_depth>=2": float(np.mean(
            [x["unweighted_local"]["depth>=2"] for x in nulls])),
        "components_depth2_mean": float(np.mean([x["components_depth2_mean"] for x in nulls])),
    }

    # ---- associative power: where do an entity's strongest associates sit? ----
    N = len(eids)
    assoc = {k: v for k, v in c2e2.items() if len(v) <= p99 and k not in top1}
    idf = {k: math.log(N / len(v)) for k, v in assoc.items()}
    e2c: dict[int, list] = defaultdict(list)
    for k, v in assoc.items():
        for e in v:
            e2c[e].append(k)
    wsum = {e: sum(idf[k] for k in cs) for e, cs in e2c.items()}
    sub2 = {e: node_of[e][:2] for e in eids}
    sub_size: dict[tuple, int] = defaultdict(int)
    for e in eids:
        sub_size[sub2[e]] += 1
    srcs = rnd.sample(sorted(e2c), min(a.sources, len(e2c)))
    outside, expect, same_file, top_lca = [], [], [], []
    for s in srcs:
        sc: dict[int, float] = defaultdict(float)
        for k in e2c[s]:
            w = idf[k]
            for t in assoc[k]:
                if t != s:
                    sc[t] += w
        if not sc:
            continue
        top = sorted(sc, key=lambda t: (-sc[t], t))[:10]
        outside.append(np.mean([sub2[t] != sub2[s] for t in top]))
        same_file.append(np.mean([node_of[t] == node_of[s] for t in top]))
        expect.append(1 - (sub_size[sub2[s]] - 1) / (N - 1))
        top_lca.append(np.mean([lcp_len(node_of[t], node_of[s]) for t in top]))
    out["top10_associates"] = {
        "sources": len(outside),
        "share_outside_depth2_subtree": float(np.mean(outside)),
        "share_outside_expected_random": float(np.mean(expect)),
        "share_same_file": float(np.mean(same_file)),
        "mean_lca_depth": float(np.mean(top_lca)),
    }

    # association (idf-weighted Jaccard) by tree-distance bucket, stratified pair samples
    def wj(x, y):
        cx, cy = set(e2c.get(x, ())), set(e2c.get(y, ()))
        inter = sum(idf[k] for k in cx & cy)
        uni = wsum.get(x, 0) + wsum.get(y, 0) - inter
        return inter / uni if uni > 0 else 0.0

    by_file: dict[tuple, list] = defaultdict(list)
    by_dir: dict[tuple, list] = defaultdict(list)
    by_sub2: dict[tuple, list] = defaultdict(list)
    for e in eids:
        by_file[node_of[e]].append(e)
        by_dir[node_of[e][:-1]].append(e)
        by_sub2[sub2[e]].append(e)

    def sample_within(groups, exclude_same=None, n=20000):
        gs = [g for g in groups.values() if len(g) >= 2]
        if not gs:
            return []
        wts = [len(g) * (len(g) - 1) for g in gs]
        pairs = []
        tries = 0
        while len(pairs) < n and tries < n * 20:
            tries += 1
            g = rnd.choices(gs, weights=wts)[0]
            x, y = rnd.sample(g, 2)
            if exclude_same and exclude_same(x, y):
                continue
            pairs.append((x, y))
        return pairs

    rand_pairs = [tuple(rnd.sample(eids, 2)) for _ in range(20000)]
    buckets = {
        "same_file": sample_within(by_file),
        "same_dir_diff_file": sample_within(by_dir, lambda x, y: node_of[x] == node_of[y]),
        "same_depth2_diff_dir": sample_within(
            by_sub2, lambda x, y: node_of[x][:-1] == node_of[y][:-1]),
        "diff_depth2": [p for p in rand_pairs if sub2[p[0]] != sub2[p[1]]],
        "random": rand_pairs,
    }
    base = float(np.mean([wj(x, y) for x, y in rand_pairs]))
    out["association_by_tree_distance"] = {
        k: {"pairs": len(v), "mean_wjaccard": (m := float(np.mean([wj(x, y) for x, y in v]))
                                               if v else None),
            "lift_vs_random": (m / base if v and base else None)}
        for k, v in buckets.items()}
    out["elapsed_s"] = round(time.time() - t0, 1)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"m1_{a.store}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
