"""M6: per-session retrieval pressure (Q91 = a, L257), pre-registered at 2049188d.

Why: 10.2's names-only dedupe keeps rank and k, and nothing accumulates when retrieval returns
the same item turn after turn; the STM focus graph is fed only by what the agent does. Before a
running per-session "pressure" score shapes the held line or a tier upgrade, measure whether it
predicts the agent's next touch beyond STM's own node score (recomputed with stm.py's scorer,
imported, not re-implemented), M5's popularity prior and the current rank. Counts, rates, AUCs.
"""
from __future__ import annotations

import json
import os
import re
import random
import statistics
import sys
import tempfile
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

os.environ.pop("RMX_STM_DECAY", None)  # the scorer's default (0.85), as deployed
import cand12_bridge_cochange as c12  # noqa: E402  (inserts the clone's src on sys.path)
from refmatrix import stm as stm_mod  # noqa: E402
from refmatrix.terms import STOPWORDS  # noqa: E402

from m4_common import M4_ROOT, gmd_id_map, item_key, key_of_path, ts_of, wilson, memory_stems  # noqa: E402
from m5_popularity_prior import Prior, new_touch_log  # noqa: E402

TSTAR = 1794712398.0
HOOK = ("scan_prompt", "prompt_recall", "session_start", "precompact")
DECAYS = (0.70, 0.85, 0.95)
LA = ZoneInfo("America/Los_Angeles")
MEMGET = re.compile(r"(?:rmx|rmx-master)\s+memory\s+get\s+['\"]?([\w\-.]+)")

# ---- touch extension (pre-registration #m6-prereg-defs): `rmx memory get <name>` touches
# memory/<name>. Applied to M6's copy of the thread timelines only; m4_common is unchanged.
_orig_load = c12.load_threads
_STEMS = None


def _augmented_threads():
    global _STEMS
    t = _orig_load()
    if _STEMS is None:
        _STEMS = memory_stems()
    for calls in t["threads"].values():
        for c in calls:
            names = []
            if c["cmd"]:
                names += MEMGET.findall(c["cmd"])
            if c["tool"].startswith("mcp__refmatrix__rmx_memory") and c["ctx"]:
                names.append(c["ctx"])
            for n in names:
                if n in _STEMS and f"memory/{n}" not in c["keys"]:
                    c["keys"].append(f"memory/{n}")
    return t


c12.load_threads = _augmented_threads


def load_queries_full():
    gid = gmd_id_map()
    q = {}
    for line in open(M4_ROOT / "recall-events.jsonl"):
        d = json.loads(line)
        if d["stage"] not in ("retrieved", "delivered"):
            continue
        e = q.setdefault(d["query_id"], {"session": d["session"], "ts": ts_of(d["ts"]),
                                         "turn": d["turn"], "channel": d["channel"],
                                         "inv": d["invocation"], "rank": {}, "deliv": {}})
        k = item_key(d, gid)
        if not k:
            continue
        r = d.get("rank") or 99
        e["rank"][k] = min(e["rank"].get(k, 99), r)
        if d["stage"] == "delivered":
            e["deliv"][k] = max(e["deliv"].get(k, 0), d.get("bytes") or 0)
    return q


def pressure_tables(Q):
    """{qid: {key: {variant: value}}} for every hook query and every key it retrieved."""
    by_sess = defaultdict(list)
    for qid, q in Q.items():
        if q["channel"] in HOOK and q["inv"] == "hook" and isinstance(q["turn"], int):
            by_sess[q["session"]].append((q["turn"], q["ts"], qid))
    out = {}
    for s, qs in by_sess.items():
        qs.sort()
        hist = defaultdict(list)  # key -> [(turn, rank, channel)]
        for turn, ts, qid in qs:
            q = Q[qid]
            cur = {}
            for k in q["rank"]:
                v = {}
                h = [x for x in hist.get(k, []) if x[0] < turn]
                for d in DECAYS:
                    v[("count", d)] = sum(d ** (turn - t) for t, r, ch in h)
                    v[("rank", d)] = sum(d ** (turn - t) / r for t, r, ch in h)
                    v[("scan", d)] = sum(d ** (turn - t) for t, r, ch in h if ch == "scan_prompt")
                    v[("recall", d)] = sum(d ** (turn - t) for t, r, ch in h if ch == "prompt_recall")
                cur[k] = v
            out[qid] = cur
            for k, r in q["rank"].items():
                hist[k].append((turn, r, q["channel"]))
    return out


def ring_times(e):
    return datetime.fromisoformat(e["ts"]).replace(tzinfo=LA).timestamp()


def stm_scores(Q, needs):
    """needs: {session: [(ts, qid, [keys])]} -> {(qid, key): score} by replaying the ring through
    stm.Stm._apply_turn and scoring with stm._node_score / stm._graph_degree."""
    tmp = Path(tempfile.mkdtemp(prefix="m6stm", dir=str(M4_ROOT)))
    out = {}
    kcache = {}
    for s, reqs in needs.items():
        p = M4_ROOT / "stm" / f"{s}.jsonl"
        if not p.exists():
            continue
        evs = []
        for line in open(p, errors="replace"):
            try:
                e = json.loads(line)
                evs.append((ring_times(e), e))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        evs.sort(key=lambda x: x[0])
        st = stm_mod.Stm(tmp, session=s)
        g = {"turn": 0, "nodes": {}, "edges": {}}
        i = 0
        for ts, qid, keys in sorted(reqs):
            while i < len(evs) and evs[i][0] <= ts:
                e = evs[i][1]
                st._apply_turn(g, list(e.get("refs") or []), new_turn=(e.get("kind") == "input"))
                i += 1
            nodes = g["nodes"]
            deg = stm_mod._graph_degree(g)
            maxdeg = max(deg.values()) if deg else 1
            real = [nd for nd in nodes.values() if not nd.get("frontier")]
            maxfreq = max((nd.get("freq", 0) for nd in real), default=1) or 1
            best = {}
            for nd in real:
                nm = nd["name"]
                if nm not in kcache:
                    kcache[nm] = key_of_path(nm)
                k = kcache[nm]
                if k:
                    sc = stm_mod._node_score(nd, maxfreq, deg, maxdeg)
                    best[k] = max(best.get(k, 0.0), sc)
            for k in keys:
                out[(qid, k)] = best.get(k, 0.0)
    return out


def boot_auc(groups, y, cols, seed="m6", n=2000):
    """Paired bootstrap over query units of AUC differences; cols = {name: scores}."""
    rng = random.Random(seed)
    keys = sorted(groups)
    res = defaultdict(list)
    for _ in range(n):
        idx = [i for _k in range(len(keys)) for i in groups[keys[rng.randrange(len(keys))]]]
        yy = y[idx]
        if yy.sum() == 0 or yy.sum() == len(yy):
            continue
        for nm, sc in cols.items():
            res[nm].append(roc_auc_score(yy, sc[idx]))
    return {nm: np.array(v) for nm, v in res.items()}


def ci(a):
    a = np.sort(a)
    return a[int(0.025 * len(a))], a[int(0.975 * len(a)) - 1]


def main():
    units, _ = c12.build_units()
    T = c12.load_threads()
    Q = load_queries_full()
    P = pressure_tables(Q)
    prior = Prior(new_touch_log(T["threads"]))
    hook = [u for u in units if u["group"] == "push" and u["qid"] in P]
    print(f"hook units with pressure {len(hook)} (of {len(units)} joined)")
    # ---- candidates
    cands = []
    for u in hook:
        q = Q[u["qid"]]
        pop = Counter(e[1] for e in prior.keys_in(u["ts"], 7))
        for k, r in q["rank"].items():
            cands.append({"u": u, "qid": u["qid"], "key": k, "y": int(k in u["new"]), "rank": r,
                          "pop": pop.get(k, 0), "p": P[u["qid"]][k], "test": u["ts"] >= TSTAR})
    needs = defaultdict(list)
    per_q = defaultdict(list)
    for c in cands:
        per_q[c["qid"]].append(c["key"])
    for u in hook:
        needs[u["session"]].append((u["ts"], u["qid"], per_q[u["qid"]]))
    S = stm_scores(Q, needs)
    for c in cands:
        c["stm"] = S.get((c["qid"], c["key"]), 0.0)
    tr = [c for c in cands if not c["test"]]
    te = [c for c in cands if c["test"]]
    print(f"candidates train {len(tr)} (pos {sum(c['y'] for c in tr)}), held-out {len(te)} "
          f"(pos {sum(c['y'] for c in te)}) over {len({c['qid'] for c in te})} units, "
          f"{len({c['u']['session'] for c in te})} sessions; STM score > 0 for "
          f"{sum(1 for c in te if c['stm'] > 0)} held-out candidates")

    def feats(cs, names, variant):
        cols = []
        for nm in names:
            if nm == "stm":
                cols.append([c["stm"] for c in cs])
            elif nm == "pop":
                cols.append([c["pop"] for c in cs])
            elif nm == "rank":
                cols.append([-c["rank"] for c in cs])
            elif nm == "p":
                cols.append([c["p"][variant] for c in cs])
        return np.array(cols).T

    def lr_scores(names, variant):
        Xtr, Xte = feats(tr, names, variant), feats(te, names, variant)
        sc = StandardScaler().fit(Xtr)
        m = LogisticRegression(max_iter=2000).fit(sc.transform(Xtr), [c["y"] for c in tr])
        return m.decision_function(sc.transform(Xte))

    y = np.array([c["y"] for c in te])
    groups = defaultdict(list)
    for i, c in enumerate(te):
        groups[c["qid"]].append(i)
    prim = ("count", 0.85)
    print("\n== Q1 held-out AUC, single scores: " + ", ".join(
        f"{nm} {roc_auc_score(y, feats(te, [nm], prim)[:, 0]):.3f}" for nm in ("stm", "pop", "rank", "p")))
    for variant in [prim] + [(v, d) for v in ("count", "rank", "scan", "recall") for d in DECAYS
                             if (v, d) != prim]:
        cols = {"p": feats(te, ["p"], variant)[:, 0]}
        for b in ("stm", "pop", "rank"):
            cols[b] = feats(te, [b], variant)[:, 0]
            cols[b + "+p"] = lr_scores([b, "p"], variant)
        cols["all3"] = lr_scores(["stm", "pop", "rank"], variant)
        cols["all3+p"] = lr_scores(["stm", "pop", "rank", "p"], variant)
        A = {nm: roc_auc_score(y, sc) for nm, sc in cols.items()}
        if variant == prim:
            B = boot_auc(groups, y, cols)
            parts = []
            for b in ("stm", "pop", "rank", "all3"):
                d = B[b + "+p"] - B[b]
                lo, hi = ci(d)
                parts.append(f"Δ_{b} {A[b+'+p']-A[b]:+.3f} [{lo:+.3f},{hi:+.3f}] "
                             f"({A[b]:.3f}->{A[b+'+p']:.3f})")
            print(f"Q1 PRIMARY {variant}: AUC(p) {A['p']:.3f}; " + "; ".join(parts))
        else:
            print(f"Q1 variant {variant}: AUC(p) {A['p']:.3f}; " + "; ".join(
                f"Δ_{b} {A[b+'+p']-A[b]:+.3f}" for b in ("stm", "pop", "rank", "all3")))
    for ch in ("scan_prompt", "prompt_recall"):
        sub = [i for i, c in enumerate(te) if c["u"]["channel"] == ch]
        if sub and 0 < y[sub].sum() < len(sub):
            print(f"Q1 stratum {ch}: n {len(sub)} pos {int(y[sub].sum())} AUC(p) "
                  f"{roc_auc_score(y[sub], feats([te[i] for i in sub], ['p'], prim)[:, 0]):.3f} "
                  f"AUC(stm) {roc_auc_score(y[sub], feats([te[i] for i in sub], ['stm'], prim)[:, 0]):.3f}")

    # ---- Q2 held-line ordering
    print("\n== Q2")
    threads = T["threads"]
    prompts = T["prompts"]
    hook_by_s = defaultdict(list)
    for qid, q in Q.items():
        if q["channel"] in HOOK and q["inv"] == "hook" and isinstance(q["turn"], int):
            hook_by_s[q["session"]].append((q["turn"], qid))
    rr = {"def": [], "p": [], "stm": []}
    rr_new = {"def": [], "p": []}
    for u in hook:
        if u["ts"] < TSTAR:
            continue
        q = Q[u["qid"]]
        s = u["session"]
        mk = max((t for t, qq in hook_by_s[s] if Q[qq]["channel"] == "precompact" and t < q["turn"]),
                 default=-1)
        earlier = set()
        for t, qq in hook_by_s[s]:
            if mk <= t < q["turn"]:
                earlier |= set(Q[qq]["deliv"])
        held = [k for k in q["deliv"] if k in earlier]
        if not held:
            continue
        calls = threads.get((s, "main"), [])
        cts = [c["ts"] for c in calls]
        start = bisect_right(cts, u["ts"])
        pts = [p[0] for p in prompts.get(s, [])]
        nxt = next((p for p in pts if p > u["ts"] + 2), float("inf"))
        order = []
        for c in calls[start:start + 10]:
            if c["ts"] >= nxt:
                break
            for k in c["keys"]:
                if k in held and k not in order:
                    order.append(k)
        if not order:
            continue
        first = order[0]
        dflt = sorted(held, key=lambda k: (q["rank"].get(k, 99), k))
        byp = sorted(held, key=lambda k: (-P[u["qid"]][k][prim], q["rank"].get(k, 99), k))
        bys = sorted(held, key=lambda k: (-S.get((u["qid"], k), 0.0), q["rank"].get(k, 99), k))
        rr["def"].append(1 / (dflt.index(first) + 1))
        rr["p"].append(1 / (byp.index(first) + 1))
        rr["stm"].append(1 / (bys.index(first) + 1))
        if first in u["new"]:
            rr_new["def"].append(rr["def"][-1])
            rr_new["p"].append(rr["p"][-1])
    n = len(rr["def"])
    print(f"Q2 held-out units with a held item touched in the window: {n}; mean held items "
          f"per unit n/a")
    if n:
        d = np.array(rr["p"]) - np.array(rr["def"])
        rng = random.Random("m6-q2")
        bs = sorted(np.mean([d[rng.randrange(n)] for _ in range(n)]) for _ in range(2000))
        print(f"Q2 MRR default {np.mean(rr['def']):.3f}, pressure {np.mean(rr['p']):.3f}, STM "
              f"{np.mean(rr['stm']):.3f}; Δ MRR (pressure - default) {d.mean():+.3f} "
              f"[{bs[50]:+.3f},{bs[1949]:+.3f}]; new-touch stratum n {len(rr_new['def'])} "
              f"Δ {np.mean(np.array(rr_new['p'])-np.array(rr_new['def'])) if rr_new['def'] else float('nan'):+.3f}")

    # ---- Q3 tier upgrade
    print("\n== Q3")
    touch_by_s = defaultdict(list)
    for (s, th), calls in threads.items():
        for c in calls:
            for k in c["keys"]:
                touch_by_s[s].append((c["ts"], k))
    for s in touch_by_s:
        touch_by_s[s].sort()
    pr_bytes = [b for q in Q.values() if q["channel"] == "prompt_recall" for b in q["deliv"].values()]
    full_b = statistics.median([b for b in pr_bytes if b >= 500]) if any(b >= 500 for b in pr_bytes) else 0
    ptr_b = statistics.median([b for b in pr_bytes if 0 < b < 125])
    print(f"tier bytes (prompt_recall delivered): pointer median {ptr_b}, full median {full_b}; "
          f"cost per upgrade {full_b - ptr_b} B")

    def later_touch(s, k, t0):
        ps = [p[0] for p in prompts.get(s, []) if p[0] > t0]
        t1 = ps[4] if len(ps) >= 5 else float("inf")
        return int(any(t0 < ts < t1 and kk == k for ts, kk in touch_by_s.get(s, [])
                       [bisect_left([x[0] for x in touch_by_s.get(s, [])], t0):]))

    items = []
    for s, lst in hook_by_s.items():
        lst = sorted(lst)
        first = {}
        for t, qid in lst:
            q = Q[qid]
            for k, b in q["deliv"].items():
                if k in first:
                    continue
                if q["channel"] in ("prompt_recall", "session_start"):
                    first[k] = (t, q["ts"], "pointer" if b < 125 else "excerpt" if b < 500 else "full")
                else:
                    first[k] = (t, q["ts"], None)
        for k, (t0, ts0, tier) in first.items():
            if tier not in ("pointer", "excerpt") or ts0 < TSTAR:
                continue
            cross = {}
            for t, qid in lst:
                if t < t0 or k not in P.get(qid, {}):
                    continue
                pv = P[qid][k][prim]
                for b in (1.5, 2.5, 4.0):
                    if b not in cross and pv >= b:
                        cross[b] = Q[qid]["ts"]
            items.append({"s": s, "k": k, "tier": tier, "base": later_touch(s, k, ts0),
                          "cross": {b: later_touch(s, k, tt) for b, tt in cross.items()}})
    base = [it["base"] for it in items]
    lo, hi = wilson(sum(base), len(base))
    print(f"Q3 held-out items first delivered as pointer/excerpt: {len(items)} "
          f"(pointer {sum(1 for i in items if i['tier']=='pointer')}); base later-touch rate "
          f"{sum(base)}/{len(base)} [{lo:.3f},{hi:.3f}]")
    nsess = len({i["s"] for i in items}) or 1
    for b in (1.5, 2.5, 4.0):
        xs = [it["cross"][b] for it in items if b in it["cross"]]
        if not xs:
            print(f"Q3 band {b}: 0 crossers")
            continue
        lo, hi = wilson(sum(xs), len(xs))
        print(f"Q3 band {b}: crossers {len(xs)}, precision {sum(xs)}/{len(xs)}={sum(xs)/len(xs):.3f} "
              f"[{lo:.3f},{hi:.3f}] vs base {sum(base)/max(1,len(base)):.3f}; upgrades/session "
              f"{len(xs)/nsess:.1f}, bytes/session {len(xs)/nsess*(full_b-ptr_b):.0f}")

    # ---- Q4 self-reinforcement
    print("\n== Q4")
    pv = np.array([c["p"][prim] for c in te])
    sv = np.array([c["stm"] for c in te])
    ov = []
    for c in te:
        toks = {t for t in re.split(r"[^a-z0-9]+", c["key"].lower()) if t and t not in STOPWORDS}
        ov.append(len(toks & c["u"]["terms"]) / len(toks) if toks else 0.0)
    ov = np.array(ov)
    r1 = spearmanr(pv, sv).statistic
    r2 = spearmanr(pv, ov).statistic
    rng = random.Random("m6-q4")
    keys = sorted(groups)
    b1, b2 = [], []
    for _ in range(1000):
        idx = [i for _k in range(len(keys)) for i in groups[keys[rng.randrange(len(keys))]]]
        b1.append(spearmanr(pv[idx], sv[idx]).statistic)
        b2.append(spearmanr(pv[idx], ov[idx]).statistic)
    print(f"Q4 Spearman(pressure, STM) {r1:.3f} [{ci(np.array(b1))[0]:.3f},{ci(np.array(b1))[1]:.3f}]; "
          f"Spearman(pressure, prompt-term overlap) {r2:.3f} [{ci(np.array(b2))[0]:.3f},"
          f"{ci(np.array(b2))[1]:.3f}]; share of held-out candidates with pressure > 0 "
          f"{(pv > 0).mean():.3f}")
    last = c12.LAST14
    print(f"\nvolume: candidates {sum(1 for c in cands if c['u']['ts'] >= last)/2:.0f}/week; "
          f"held-out items for Q3 {len(items)}")


if __name__ == "__main__":
    main()
