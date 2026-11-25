"""M5: a recency-windowed popularity prior measured against scan-prompt (Q89 = a, L254).

Pre-registered at f96cebc5 (docs/architecture/explorations/meta-associations.md #m5-prereg).
Why: in M4 a fixed "most often newly touched files" list beat every recall candidate; M5 asks
whether a windowed version reaches what scan-prompt missed, whether blending it into
scan-prompt's own budget helps, whether it only re-delivers what the session already holds, and
which modes and kinds it serves. Counts, rates and bytes only.
"""
from __future__ import annotations

import json
import math
import random
import statistics
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict

import numpy as np

from m4_common import M4_ROOT, gmd_id_map, item_key, load_queries, load_threads, ts_of, wilson
from cand12_bridge_cochange import LAST14, build_units, pct
import cand8_activity_mode as c8

DAY = 86400.0
TSTAR = 1794712398.0  # M4 C1 T*, 2026-11-15 03:13:18 UTC (fixed by the pre-registration)
WS = (3, 7, 14)


def new_touch_log(threads):
    ev = []
    for (s, th), calls in threads.items():
        for i, c in enumerate(calls):
            prior = {k for d in calls[max(0, i - 200):i] for k in d["keys"]}
            for k in dict.fromkeys(c["keys"]):
                if k not in prior:
                    ev.append((c["ts"], k, s))
    ev.sort()
    return ev


class Prior:
    def __init__(self, ev):
        self.ev = ev
        self.ts = [e[0] for e in ev]

    def keys_in(self, t, w):
        a = bisect_left(self.ts, t - w * DAY)
        b = bisect_left(self.ts, t)
        return self.ev[a:b]

    def top(self, t, w, k):
        c = Counter(e[1] for e in self.keys_in(t, w))
        return [x for x, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))][:k]


def boot(a, b, units, seed="m5", n=2000):
    """Paired bootstrap of mean(a) - mean(b) over units; returns (point, lo, hi)."""
    m = len(a)
    pt = (sum(a) - sum(b)) / m
    rng = random.Random(seed)
    xs = []
    for _ in range(n):
        idx = [rng.randrange(m) for _ in range(m)]
        xs.append((sum(a[i] for i in idx) - sum(b[i] for i in idx)) / m)
    xs.sort()
    return pt, xs[int(0.025 * n)], xs[int(0.975 * n) - 1]


def rate(xs):
    k, n = sum(xs), len(xs)
    lo, hi = wilson(k, n)
    return f"{k}/{n}={k/max(1,n):.3f}[{lo:.3f},{hi:.3f}]"


def fit_modes(units, Q):
    """cand8_activity_mode.py's clustering, reproduced step for step on these copies."""
    rings = c8.load_rings()
    dels = [{"ts": u["ts"]} for u in units for _k in Q[u["qid"]]["delivered"]]
    T = pct([d["ts"] for d in dels], 0.6)
    rng = random.Random("m4-8")
    tr_idx = [(s, i) for s, r in rings.items() for i, (t, _) in enumerate(r) if t < T]
    samp = rng.sample(tr_idx, min(20000, len(tr_idx)))
    X = np.array([c8.feat([c for _, c in rings[s][max(0, i - 19):i + 1]]) for s, i in samp])
    sil_idx = rng.sample(range(len(X)), min(3000, len(X)))
    best = None
    for k in (3, 4, 5, 6):
        C, lab = c8.kmeans(X, k, rng)
        sil = c8.silhouette(X[sil_idx], lab[sil_idx])
        if best is None or sil > best[0]:
            best = (sil, k, C)
    print(f"modes re-fitted: k={best[1]} silhouette {best[0]:.3f}")
    for j in range(best[1]):
        print(f"  mode {j}: " + " ".join(f"{c}={best[2][j][i]:.2f}" for i, c in enumerate(c8.CATS)))

    def mode_at(s, t):
        r = rings.get(s)
        if not r:
            return None
        j = bisect_right([x[0] for x in r], t)
        if j == 0:
            return None
        return c8.assign(best[2], c8.feat([c for _, c in r[max(0, j - 20):j]]))
    return mode_at


def main():
    T = load_threads()
    units, _ = build_units()
    Q = load_queries()
    gid = gmd_id_map()
    # scan_prompt delivered lists, ranked, keyless items kept (they hold budget)
    lists = defaultdict(list)
    for line in open(M4_ROOT / "recall-events.jsonl"):
        d = json.loads(line)
        if d["channel"] == "scan_prompt" and d["stage"] == "delivered":
            lists[d["query_id"]].append((d.get("rank") or 999, item_key(d, gid), d.get("bytes") or 0,
                                         d["kind"], ts_of(d["ts"])))
    for q in lists:
        lists[q].sort(key=lambda x: (x[0], str(x[1])))
    sp = [u for u in units if u["channel"] == "scan_prompt"]
    for u in sp:
        u["list"] = lists.get(u["qid"], [])
    ev = new_touch_log(T["threads"])
    P = Prior(ev)
    print(f"scan_prompt units {len(sp)}; new-touch events {len(ev)}; units with a delivered list "
          f"{sum(1 for u in sp if u['list'])}")
    item_bytes = statistics.median(b for q, l in lists.items() for r, k, b, kind, t in l
                                   if kind in ("code", "doc") and t < TSTAR and b)
    print(f"cost of one prior item (median bytes of train code/doc item lines) {item_bytes}")

    # ---------------- Q1
    train1 = [u for u in sp if u["ts"] < TSTAR and u["missed_new"]]
    test1 = [u for u in sp if u["ts"] >= TSTAR and u["missed_new"]]
    trreach = {w: sum(any(g in P.top(u["ts"], w, 10) for g in u["missed_new"]) for u in train1) / len(train1)
               for w in WS}
    W = min(WS, key=lambda w: (-trreach[w], w))
    print(f"\n== Q1 train units {len(train1)}, held-out {len(test1)}; train reach@10 by W "
          f"{ {w: round(v, 3) for w, v in trreach.items()} } -> W*={W}")
    rng = random.Random("m5")
    trng = random.Random("m5-time")
    fixed = Counter(g for u in sp if u["ts"] < TSTAR for g in u["missed_new"])
    fixed_list = [k for k, _ in sorted(fixed.items(), key=lambda kv: (-kv[1], kv[0]))]
    rows = []
    for u in test1:
        r = {"u": u}
        for w in WS:
            for k in (5, 10, 20):
                r[f"P{w}@{k}"] = int(any(g in P.top(u["ts"], w, k) for g in u["missed_new"]))
        pool = sorted({e[1] for e in P.keys_in(u["ts"], W)})
        r["chance@10"] = int(any(g in rng.sample(pool, min(10, len(pool))) for g in u["missed_new"]))
        other = trng.choice([v for v in test1 if v["session"] != u["session"]])
        r["time@10"] = int(any(g in P.top(other["ts"], W, 10) for g in u["missed_new"]))
        r["fixed@10"] = int(any(g in fixed_list[:10] for g in u["missed_new"]))
        top10 = P.top(u["ts"], W, 10)
        r["fr"] = sum(1 for x in top10 if x not in u["win"]) / max(1, len(top10))
        rows.append(r)
    for w in WS:
        print(f"Q1 P{w}: @5 {rate([r[f'P{w}@5'] for r in rows])} @10 {rate([r[f'P{w}@10'] for r in rows])}"
              f" @20 {rate([r[f'P{w}@20'] for r in rows])}")
    print(f"Q1 chance@10 {rate([r['chance@10'] for r in rows])}; time placebo@10 "
          f"{rate([r['time@10'] for r in rows])}; M4 fixed list@10 {rate([r['fixed@10'] for r in rows])};"
          f" FR@10 {statistics.mean(r['fr'] for r in rows):.3f}")
    a = [r[f"P{W}@10"] for r in rows]
    L = boot(a, [r["chance@10"] for r in rows], rows)
    R = boot(a, [r["time@10"] for r in rows], rows, seed="m5-r")
    Fx = boot(a, [r["fixed@10"] for r in rows], rows, seed="m5-f")
    print(f"Q1 LIFT vs chance {L[0]*100:+.1f}pp [{L[1]*100:+.1f},{L[2]*100:+.1f}]; recency value "
          f"(vs time placebo) {R[0]*100:+.1f}pp [{R[1]*100:+.1f},{R[2]*100:+.1f}]; vs M4 fixed list "
          f"{Fx[0]*100:+.1f}pp [{Fx[1]*100:+.1f},{Fx[2]*100:+.1f}]; sessions {len({r['u']['session'] for r in rows})}")

    # ---------------- Q2
    test2 = [u for u in sp if u["ts"] >= TSTAR and u["list"] and u["new"]]
    res2 = []
    for u in test2:
        lst = u["list"]
        n = len(lst)
        add = math.ceil(n / 4)
        out = {"u": u}
        for lab, keep_n, add_n, alone_n in (("own", n - add, add, n), ("8slot", 6, 2, 8)):
            alone = lst[:alone_n]
            kept = lst[:keep_n]
            have = {x[1] for x in kept if x[1]}
            pri = [k for k in P.top(u["ts"], W, add_n + len(have) + 5) if k not in have][:add_n]
            blend_keys = [x[1] for x in kept if x[1]] + pri
            alone_keys = [x[1] for x in alone if x[1]]
            out[f"{lab}_alone"] = int(any(g in alone_keys for g in u["new"]))
            out[f"{lab}_blend"] = int(any(g in blend_keys for g in u["new"]))
            out[f"{lab}_fr_alone"] = (sum(1 for k in alone_keys if k not in u["win"]) / len(alone_keys)) if alone_keys else None
            out[f"{lab}_fr_blend"] = (sum(1 for k in blend_keys if k not in u["win"]) / len(blend_keys)) if blend_keys else None
            ab = sum(x[2] for x in alone)
            bb = sum(x[2] for x in kept) + len(pri) * item_bytes
            out[f"{lab}_bytes"] = (bb - ab) / ab if ab else None
        res2.append(out)
    print(f"\n== Q2 held-out units with a list and a new-touch gold {len(test2)}")
    for lab in ("own", "8slot"):
        a = [r[f"{lab}_blend"] for r in res2]
        b = [r[f"{lab}_alone"] for r in res2]
        D = boot(a, b, res2, seed="m5-q2")
        fa = [r[f"{lab}_fr_alone"] for r in res2 if r[f"{lab}_fr_alone"] is not None]
        fb = [r[f"{lab}_fr_blend"] for r in res2 if r[f"{lab}_fr_blend"] is not None]
        by = [r[f"{lab}_bytes"] for r in res2 if r[f"{lab}_bytes"] is not None]
        print(f"Q2 {lab}: alone {rate(b)} blend {rate(a)} | Δ {D[0]*100:+.1f}pp [{D[1]*100:+.1f},"
              f"{D[2]*100:+.1f}] | FR alone {statistics.mean(fa):.3f} blend {statistics.mean(fb):.3f} |"
              f" payload change median {statistics.median(by)*100:+.1f}% mean {statistics.mean(by)*100:+.1f}%")
    # Not pre-registered (added after Q3 read >= 50% already held): the own-budget blend with the
    # prior's items deduped against what the session already touched or was delivered.
    touched_s = defaultdict(list)
    for (s, th), calls in T["threads"].items():
        for c in calls:
            for k in c["keys"]:
                touched_s[s].append((c["ts"], k))
    deliv_s = defaultdict(list)
    for q in Q.values():
        for k in q["delivered"]:
            deliv_s[q["session"]].append((q["ts"], k))
    dd_a, dd_b, extra_held = [], [], 0
    for r in res2:
        u = r["u"]
        held = ({k for t, k in touched_s[u["session"]] if t < u["ts"]}
                | {k for t, k in deliv_s[u["session"]] if t < u["ts"] - 1})
        lst = u["list"]
        n = len(lst)
        add = math.ceil(n / 4)
        kept = lst[:n - add]
        have = {x[1] for x in kept if x[1]}
        pri_all = [k for k in P.top(u["ts"], W, 400) if k not in have]
        pri = pri_all[:add]
        pri_dd = [k for k in pri_all if k not in held][:add]
        base = [x[1] for x in kept if x[1]]
        dd_a.append(int(any(g in base + pri_dd for g in u["new"])))
        dd_b.append(r["own_alone"])
        if r["own_blend"] and not r["own_alone"]:
            extra_held += int(all(g in held for g in u["new"] if g in pri))
    D = boot(dd_a, dd_b, res2, seed="m5-q2dd")
    print(f"Q2 own, prior deduped against the session (post hoc): blend {rate(dd_a)} | Δ "
          f"{D[0]*100:+.1f}pp [{D[1]*100:+.1f},{D[2]*100:+.1f}]; of the units the undeduped blend "
          f"newly reached, reached only by already-held items: {extra_held}/"
          f"{sum(1 for r in res2 if r['own_blend'] and not r['own_alone'])}")

    # ---------------- Q3
    days = sorted({int(u["ts"] // DAY) for u in sp if u["ts"] >= TSTAR})
    jac = []
    for d in days:
        a = set(P.top(d * DAY, W, 10))
        b = set(P.top((d - 1) * DAY, W, 10))
        if a or b:
            jac.append(len(a & b) / len(a | b))
    print(f"\n== Q3 day-to-day Jaccard of top-10 over {len(jac)} held-out days: mean "
          f"{statistics.mean(jac):.3f}, min {min(jac):.3f}, max {max(jac):.3f}")
    touched_by_sess = defaultdict(list)
    for (s, th), calls in T["threads"].items():
        for c in calls:
            for k in c["keys"]:
                touched_by_sess[s].append((c["ts"], k))
    deliv_by_sess = defaultdict(list)
    for q in Q.values():
        for k in q["delivered"]:
            deliv_by_sess[q["session"]].append((q["ts"], k))
    held_t, held_d, held_any = [], [], []
    for u in test2:
        add = math.ceil(len(u["list"]) / 4)
        top = P.top(u["ts"], W, add)
        if not top:
            continue
        tk = {k for t, k in touched_by_sess[u["session"]] if t < u["ts"]}
        dk = {k for t, k in deliv_by_sess[u["session"]] if t < u["ts"] - 1}
        held_t.append(sum(1 for k in top if k in tk) / len(top))
        held_d.append(sum(1 for k in top if k in dk) / len(top))
        held_any.append(sum(1 for k in top if k in tk or k in dk) / len(top))
    for lab, xs in (("touched", held_t), ("delivered earlier", held_d), ("either", held_any)):
        m = statistics.mean(xs)
        rr = random.Random("m5-q3")
        bs = sorted(statistics.mean([xs[rr.randrange(len(xs))] for _ in xs]) for _ in range(2000))
        print(f"Q3 already held ({lab}): mean {m:.3f} [{bs[50]:.3f},{bs[1949]:.3f}] over {len(xs)} units")

    # ---------------- Q4
    mode_at = fit_modes(units, Q)
    print("\n== Q4 strata")
    for r in rows:
        r["mode"] = mode_at(r["u"]["session"], r["u"]["ts"])
    for m in sorted({r["mode"] for r in rows}, key=lambda x: (x is None, x)):
        sub = [r for r in rows if r["mode"] == m]
        if len(sub) < 5:
            print(f"Q1 mode {m}: n={len(sub)}")
            continue
        D = boot([r[f"P{W}@10"] for r in sub], [r["chance@10"] for r in sub], sub, seed="m5-q4")
        print(f"Q1 mode {m}: n={len(sub)} reach {rate([r[f'P{W}@10'] for r in sub])} lift vs chance "
              f"{D[0]*100:+.1f}pp [{D[1]*100:+.1f},{D[2]*100:+.1f}]")
    for r in res2:
        r["mode"] = mode_at(r["u"]["session"], r["u"]["ts"])
    for m in sorted({r["mode"] for r in res2}, key=lambda x: (x is None, x)):
        sub = [r for r in res2 if r["mode"] == m]
        if len(sub) < 5:
            continue
        D = boot([r["own_blend"] for r in sub], [r["own_alone"] for r in sub], sub, seed="m5-q4b")
        print(f"Q2 mode {m}: n={len(sub)} Δ {D[0]*100:+.1f}pp [{D[1]*100:+.1f},{D[2]*100:+.1f}]")
    for kind in ("code", "doc", "ruling", "bug row", "memory"):
        sub = []
        for r in rows:
            gs = [g for g in r["u"]["missed_new"] if c8.kind_of(g) == kind]
            if gs:
                top = P.top(r["u"]["ts"], W, 10)
                pool = sorted({e[1] for e in P.keys_in(r["u"]["ts"], W)})
                ch = random.Random(f"m5-k-{r['u']['qid']}").sample(pool, min(10, len(pool)))
                sub.append((int(any(g in top for g in gs)), int(any(g in ch for g in gs))))
        if len(sub) < 5:
            print(f"Q1 kind {kind}: n={len(sub)}")
            continue
        D = boot([a for a, _ in sub], [b for _, b in sub], sub, seed="m5-q4k")
        print(f"Q1 kind {kind}: n={len(sub)} reach {rate([a for a, _ in sub])} lift vs chance "
              f"{D[0]*100:+.1f}pp [{D[1]*100:+.1f},{D[2]*100:+.1f}]")
    vol = sum(1 for u in sp if u["missed_new"] and u["ts"] >= LAST14) / 2
    print(f"\nvolume: {vol:.1f} scan_prompt units with a missed new-touch gold/week")


if __name__ == "__main__":
    main()
