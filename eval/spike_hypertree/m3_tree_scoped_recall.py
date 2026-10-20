#!/usr/bin/env python3
"""M3 (hypertree spike 2026-10-20): recall parity of a TREE-SCOPED retrieval vs the production
`content_rank` order. Option C's precondition in exploration-hypertree#measurements.

Measurement only, never imported by `src/`. Reads COPIES of read snapshots:
  cliquedb : <SPIKE_ROOT>/m3/cliquedb/.refmatrix/catalog.duckdb   (copy of the 2026-10-19 snapshot)
  memaware : <SPIKE_ROOT>/m3/memaware/.refmatrix/catalog.duckdb   (copy of /Volumes/littlebig/memaware
             read snapshot; that store has its own eval daemon, so only the snapshot was copied)

Harness = eval/spikes/2026-10-06-loc-coloc/{cliq_grid3,mem_grid2}.py, reused verbatim for query
construction, gold, pool (50) and the MRR cutoff (rank within top 20). Its query sampling seed
(20260903) is KEPT so the base arm reproduces loc-coloc's base numbers; the tree arms are
parameter-free, so no seed of this spike enters the ranking.

BASE = production `Store.content_rank(terms, limit=50)` (MemAware: limit 200, collapsed to the
first 50 distinct sessions), exactly the loc-coloc base arm. No reranker, no co-location.

TREE-SCOPED arms (C's retrieval shape: answer from the top subtree, the graph/base order as the
fallback). For each query, over the base top-50 candidates:
  1. choose ONE subtree S of the fs containment tree (directories, relative to the corpus root);
  2. rerank = [candidates whose file lies under S, in base order] + [the rest, in base order].
Subtree choice:
  d2_top1     S = the top-1 hit's directory truncated to depth 2 (or its own directory when
              shallower). A root-level top-1 makes S the whole tree (no-op for that query).
  d2_plur10   S = the plurality depth-2 subtree among the top-10 (ties -> the higher-ranked).
  dir_top1    S = the top-1 hit's own (deepest) directory. (cliquedb only; for MemAware it
              equals d2_top1 because the tree is corpus/<date>/<session>.md.)
Candidates with no path are never inside S (they fall to the fallback).
MemAware's tree is its real on-disk layout corpus/<YYYY-MM-DD>/<session>.md, i.e. the subtree
is a DAY of sessions — the closest honest containment for a session corpus.

Held-out: MemAware test-720 (questions not in stratified-30/holdout-90; "untouched" in loc-coloc)
is the held-out set; tune-180 is reported for completeness. cliquedb lines/merge have no split;
since the tree arms have no fitted parameters every query is out-of-sample.

Bands (pre-registered): any held-out MRR loss > 0.005 -> C stays eliminated; within +-0.005 ->
no worse, still eliminated on migration cost; gain >= 0.02 held-out -> reopen C.

Outputs aggregates + ids only (no query text): eval/spike_hypertree/results/m3_<set>.json.
Usage: m3_tree_scoped_recall.py cliquedb|memaware
"""
from __future__ import annotations

import collections
import json
import math
import os
import random
import sys
import time
from pathlib import Path

REPO = Path("/Users/tholley/claude_tools/refmatrix")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "eval" / "cliquedb"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, SPIKE_ROOT, rel_parts  # noqa: E402

WHICH = sys.argv[1]
ROOT = str(SPIKE_ROOT / "m3" / WHICH / ".refmatrix")
assert ROOT.startswith("/Volumes/littlebig/refmatrix-spike-hypertree/") or "spike" in ROOT, ROOT
os.environ["REFMATRIX_ROOT"] = ROOT
os.environ["RMX_PARTITION"] = "cliquedb" if WHICH == "cliquedb" else "memaware"
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from refmatrix.store import Store  # noqa: E402
from refmatrix.terms import content_terms  # noqa: E402

POOL, CUT = 50, 20


def first_rank(order, gold, cut=CUT):
    return next((i + 1 for i, c in enumerate(order[:cut]) if c in gold), 0)


def subtree_key(dirs, mode):
    if dirs is None:
        return None
    return tuple(dirs[:2]) if mode.startswith("d2") else tuple(dirs)


def inside(dirs, key):
    return dirs is not None and key is not None and tuple(dirs[:len(key)]) == key


def tree_rerank(order, dirs_of, mode):
    if not order:
        return order, None
    if mode == "d2_plur10":
        votes = collections.Counter()
        first = {}
        for i, c in enumerate(order[:10]):
            k = subtree_key(dirs_of(c), "d2")
            if k is None:
                continue
            votes[k] += 1
            first.setdefault(k, i)
        if not votes:
            return order, None
        key = max(votes, key=lambda k: (votes[k], -first[k]))
    else:
        key = subtree_key(dirs_of(order[0]), mode)
        if key is None:
            return order, None
    ins = [c for c in order if inside(dirs_of(c), key)]
    out = [c for c in order if not inside(dirs_of(c), key)]
    return ins + out, key


def sign_p(w, l):
    n = w + l
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)


def summarize(recs, modes):
    """recs: list of dict(order=[cand ids], gold=set, dirs={cand: dirs}, gold_dirs=[dirs...])."""
    n = len(recs)
    out = {"n": n}
    base = [first_rank(r["order"], r["gold"]) for r in recs]

    def stats(ranks):
        return {"mrr": sum(1 / x for x in ranks if x) / n if n else 0.0,
                "hit1": sum(1 for x in ranks if x == 1) / n if n else 0.0,
                "hit10": sum(1 for x in ranks if x and x <= 10) / n if n else 0.0,
                "hit20": sum(1 for x in ranks if x) / n if n else 0.0}

    out["base"] = stats(base)
    for m in modes:
        ranks, gold_out, gold_out_frac, noop, rel_in_pool_out = [], 0, [], 0, 0
        for r in recs:
            new, key = tree_rerank(r["order"], lambda c: r["dirs"].get(c), m)
            ranks.append(first_rank(new, r["gold"]))
            if key is None or key == ():
                noop += 1
            # relevant items (whole gold set, pool or not) outside the chosen subtree
            gd = r["gold_dirs"]
            if gd and key is not None:
                o = sum(1 for d in gd if not inside(d, key))
                gold_out_frac.append(o / len(gd))
                if o == len(gd):
                    gold_out += 1
            # relevant items IN the base pool but outside S: the cross-tree hits C demotes
            rel_in_pool_out += sum(1 for c in r["order"] if c in r["gold"]
                                   and not inside(r["dirs"].get(c), key))
        w = sum(1 for x, y in zip(base, ranks) if y and (not x or y < x))
        l = sum(1 for x, y in zip(base, ranks) if x and (not y or y > x))
        st = stats(ranks)
        st.update({"delta_mrr": st["mrr"] - out["base"]["mrr"], "won": w, "lost": l,
                   "sign_p": sign_p(w, l), "noop_queries": noop,
                   "queries_all_gold_outside_S": gold_out,
                   "mean_share_gold_outside_S": (sum(gold_out_frac) / len(gold_out_frac)
                                                 if gold_out_frac else None),
                   "relevant_in_pool_outside_S": rel_in_pool_out})
        out[m] = st
    return out


def run_cliquedb():
    import baseline_rederive as H
    croot = "/Users/tholley/github/atollogy/bdep/cliquedb"
    s = Store(ROOT, read_only=True)
    con = s._connect()
    pid = s._partition_id
    by_path = collections.defaultdict(set)
    ent_dirs = {}
    for eid, path in con.execute("SELECT id, path FROM entities WHERE partition_id=? "
                                 "AND path IS NOT NULL", (pid,)).fetchall():
        by_path[str(path)].add(int(eid))
        rp = rel_parts(str(path), croot)
        ent_dirs[int(eid)] = rp[:-1] if rp else None
    md = [p for p in by_path if p.endswith(".md") and Path(p).exists()]
    recs = {"lines": [], "merge": []}
    rnd = random.Random(20260903)   # loc-coloc's sampling seed, kept for comparability
    paths = md[:]
    rnd.shuffle(paths)
    asked = 0
    for p in paths:
        if asked >= 300:
            break
        pool = H._body_lines(Path(p))
        if not pool:
            continue
        draw = random.Random(rnd.random())
        qs = {"lines": H._q_lines(pool, random.Random(draw.random()), None),
              "merge": H._q_merge(pool)}
        if all(v is None for v in qs.values()):
            continue
        asked += 1
        gold = by_path[p]
        rp = rel_parts(p, croot)
        gdirs = [rp[:-1]] if rp else []
        for cons, q in qs.items():
            if q is None:
                continue
            base = s.content_rank(q.split(), limit=POOL)
            order = [int(e) for e, _ in base]
            recs[cons].append({"order": order, "gold": {int(g) for g in gold},
                               "dirs": {c: ent_dirs.get(c) for c in order},
                               "gold_dirs": gdirs})
    res = {"asked_docs": asked}
    for cons in ("lines", "merge"):
        res[cons] = summarize(recs[cons], ["d2_top1", "d2_plur10", "dir_top1"])
    # how deep is the cliquedb tree the arms cut? (distribution of gold dir depth)
    depth = collections.Counter(len(rel_parts(p, croot)) - 1 for p in md)
    res["gold_dir_depth_hist_all_md"] = dict(sorted(depth.items()))
    return res


def run_memaware():
    DATA = Path("/Volumes/littlebig/memaware")
    s = Store(ROOT, read_only=True)
    con = s._connect()
    pid = s._partition_id
    ent_sid = {}
    for eid, name, path in con.execute(
            "SELECT id, name, path FROM entities WHERE partition_id=?", (pid,)).fetchall():
        v = str(path) if path else str(name)
        sid = Path(v).stem if ("/" in v or v.endswith(".md")) else v
        ent_sid[int(eid)] = sid.split("#", 1)[0]
    files = {p.stem: p for p in (DATA / "corpus").rglob("*.md")}
    sid_dirs = {sid: rel_parts(str(p), str(DATA))[:-1] for sid, p in files.items()}
    qrels = json.loads((DATA / "qrels.json").read_text())
    used = set()
    for f in ("stratified-30.json", "holdout-90.json"):
        used |= {q["question_id"] for q in json.loads((DATA / "subsets" / f).read_text())}
    allq = json.loads((DATA / "upstream" / "data" / "questions.json").read_text())
    qs = [q for q in allq if qrels.get(q["question_id"])]
    recs = {"tune180": [], "test720": []}
    rel_days = []
    for q in qs:
        rel = {Path(p).stem for p in qrels[q["question_id"]]}
        terms = content_terms(q["question"])
        hits = s.content_rank(terms, limit=POOL * 4)
        order, seen = [], set()
        for eid, _sc in hits:
            sid = ent_sid.get(int(eid))
            if sid and sid not in seen:
                seen.add(sid)
                order.append(sid)
            if len(order) >= POOL:
                break
        gd = [sid_dirs[r] for r in rel if r in sid_dirs]
        rel_days.append(len({tuple(d) for d in gd}))
        recs["tune180" if q["question_id"] in used else "test720"].append(
            {"order": order, "gold": rel, "dirs": {c: sid_dirs.get(c) for c in order},
             "gold_dirs": gd})
    res = {}
    for k in ("test720", "tune180"):
        res[k] = summarize(recs[k], ["d2_top1", "d2_plur10"])
    c = collections.Counter(rel_days)
    res["relevant_sessions_distinct_days_hist"] = {str(k): v for k, v in sorted(c.items())}
    res["corpus_sessions"] = len(files)
    res["corpus_days"] = len({tuple(d) for d in sid_dirs.values()})
    return res


if __name__ == "__main__":
    t0 = time.time()
    out = run_cliquedb() if WHICH == "cliquedb" else run_memaware()
    out["store_copy"] = ROOT
    out["elapsed_s"] = round(time.time() - t0, 1)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"m3_{WHICH}.json").write_text(json.dumps(out, indent=2, default=list))
    print(json.dumps(out, indent=2, default=list))
