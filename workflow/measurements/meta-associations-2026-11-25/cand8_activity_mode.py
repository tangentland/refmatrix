"""M4 candidate 8 (activity mode), pre-registered at 183c9e9c (Q87 = a, L253).

Why: if the agent's mode (reading, searching, editing, testing...) read from the STM ring changes
which KIND of item it uses, a mode-aware kind prior could re-rank deliveries. The test is not that
clusters exist but that use differs by mode beyond kind alone and beyond popularity. Counts,
rates and AUCs only; no command or prompt text leaves memory.
"""
from __future__ import annotations

import json
import random
import re
import statistics
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from m4_common import M4_ROOT, load_queries, load_threads, ts_of, wilson
from cand12_bridge_cochange import LAST14, build_units, pct

CATS = ["read", "search", "edit", "bash", "test", "other"]  # agent folded into other (#c8-features)
LA = ZoneInfo("America/Los_Angeles")
SEARCH_W = {"grep", "rg", "rmxgrep", "find", "ls", "tree"}
READ_W = {"cat", "sed", "head", "tail", "less", "wc", "awk", "jq", "diff"}
RMX_SEARCH = re.compile(r"^(rmx|rmx-master|\S*/rmx-master|\S*/rmx)\s+(context|grep|query|search|neighbors|"
                        r"where|locate|memory\s+recall|memory\s+search)\b")


def bash_cat(cmd: str) -> str:
    if re.search(r"\bpytest\b|lane-mini\.sh|lane-local\.sh", cmd):
        return "test"
    seg = re.split(r"&&|;|\|\||\|", cmd)
    first = ""
    for s in seg:
        s = s.strip()
        if not s or s.startswith("cd "):
            continue
        first = s
        break
    toks = first.split()
    while toks and (re.match(r"^\w+=", toks[0]) or toks[0] in ("timeout", "nice", "sudo", "-n", "-u")
                    or re.fullmatch(r"-?\d+[smh]?", toks[0])):
        if toks[0] == "sudo" and len(toks) > 2 and toks[1] == "-u":
            toks = toks[3:]
            continue
        toks = toks[1:]
    rest = " ".join(toks)
    if RMX_SEARCH.match(rest):
        return "search"
    w = toks[0].split("/")[-1] if toks else ""
    if w in SEARCH_W:
        return "search"
    if w in READ_W:
        return "read"
    return "bash"


def tool_cat(tool: str, cmd: str | None) -> str:
    if tool == "Read":
        return "read"
    if tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        return "edit"
    if tool == "Bash":
        return bash_cat(cmd or "")
    if tool in ("Grep", "Glob") or tool.startswith("mcp__refmatrix__rmx_"):
        return "search"
    return "other"


def local_to_utc(s: str) -> float:
    return datetime.fromisoformat(s).replace(tzinfo=LA).timestamp()


def load_rings():
    rings = defaultdict(list)
    for p in (M4_ROOT / "stm").glob("*.jsonl"):
        for line in open(p, errors="replace"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "ts" not in e or "session" not in e:
                continue
            if e.get("kind") == "tool":
                t = (e.get("terse") or "").split(" ")[0]
                c = tool_cat(t, e.get("detail") if t == "Bash" else None)
            else:
                c = "other"
            try:
                rings[e["session"]].append((local_to_utc(e["ts"]), CATS.index(c)))
            except ValueError:
                continue
    for s in rings:
        rings[s].sort()
    return rings


def feat(cats):
    v = np.zeros(len(CATS))
    for c in cats:
        v[c] += 1
    return v / max(1, len(cats))


def kmeans(X, k, rng, restarts=20, iters=100):
    best = None
    for _ in range(restarts):
        idx = [rng.randrange(len(X))]
        for _j in range(1, k):
            d = np.min(((X[:, None, :] - X[idx][None, :, :]) ** 2).sum(-1), axis=1)
            r = rng.random() * d.sum()
            idx.append(int(np.searchsorted(np.cumsum(d), r)))
        C = X[idx].copy()
        for _it in range(iters):
            lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
            newC = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
            if np.allclose(newC, C):
                break
            C = newC
        inertia = ((X - C[lab]) ** 2).sum()
        if best is None or inertia < best[0]:
            best = (inertia, C, lab)
    return best[1], best[2]


def silhouette(X, lab):
    D = np.sqrt(((X[:, None, :] - X[None]) ** 2).sum(-1))
    s = []
    for i in range(len(X)):
        same = lab == lab[i]
        if same.sum() <= 1:
            s.append(0.0)
            continue
        a = D[i, same].sum() / (same.sum() - 1)
        b = min(D[i, lab == j].mean() for j in set(lab.tolist()) if j != lab[i])
        s.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return float(np.mean(s))


def assign(C, v):
    return int(np.argmin(((C - v) ** 2).sum(-1)))


def auc(scores, y):
    pairs = sorted(zip(scores, y))
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        for t in range(i, j + 1):
            ranks[t] = (i + j) / 2 + 1
        i = j + 1
    npos = sum(y)
    nneg = len(y) - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    rs = sum(r for r, (_, yy) in zip(ranks, pairs) if yy)
    return (rs - npos * (npos + 1) / 2) / (npos * nneg)


def kind_of(k: str) -> str:
    if k.startswith("memory/"):
        return "memory"
    if k == "workflow/plan-of-plans.md":
        return "ruling"
    if k == "workflow/bug_registry.md":
        return "bug row"
    if k.endswith(".md"):
        return "doc"
    return "code"


def main():
    rings = load_rings()
    nev = sum(len(v) for v in rings.values())
    print(f"ring sessions {len(rings)}, ring events {nev}")

    def window(s, ts):
        r = rings.get(s)
        if not r:
            return None
        j = bisect_right([x[0] for x in r], ts)
        if j == 0:
            return None
        return feat([c for _, c in r[max(0, j - 20):j]])

    # ---- deliveries (C6 join)
    units, _ = build_units()
    Q = load_queries()
    dels = []
    for u in units:
        for k in Q[u["qid"]]["delivered"]:
            dels.append({"ts": u["ts"], "key": k, "kind": kind_of(k), "touched": int(k in u["win"]),
                         "qid": u["qid"], "session": u["session"]})
    T = pct([d["ts"] for d in dels], 0.6)
    print(f"deliveries {len(dels)}; T*={T:.0f}")

    # ---- clusters on train ring windows
    rng = random.Random("m4-8")
    tr_idx = [(s, i) for s, r in rings.items() for i, (t, _) in enumerate(r) if t < T]
    samp = rng.sample(tr_idx, min(20000, len(tr_idx)))
    X = np.array([feat([c for _, c in rings[s][max(0, i - 19):i + 1]]) for s, i in samp])
    sil_idx = rng.sample(range(len(X)), min(3000, len(X)))
    best = None
    for k in (3, 4, 5, 6):
        C, lab = kmeans(X, k, rng)
        sil = silhouette(X[sil_idx], lab[sil_idx])
        print(f"k={k} silhouette {sil:.3f} sizes {sorted(Counter(lab.tolist()).values(), reverse=True)}")
        if best is None or sil > best[0]:
            best = (sil, k, C, lab)
    _, K, C, lab = best
    print(f"chosen k={K}; centroids (shares of {CATS}):")
    for j in range(K):
        print(f"  mode {j}: " + " ".join(f"{c}={C[j][i]:.2f}" for i, c in enumerate(CATS))
              + f" (train windows {int((lab == j).sum())})")

    # ---- labels
    T2 = load_threads()
    tx = M4_ROOT / "tx"
    atype = {}
    for d in tx.iterdir():
        if d.is_dir():
            for m in (d / "subagents").glob("*.meta.json"):
                try:
                    atype[(d.name, m.name[:-len(".meta.json")])] = json.loads(m.read_text()).get("agentType")
                except (json.JSONDecodeError, OSError):
                    continue
    thread_modes = {}
    per_type = defaultdict(Counter)
    for (s, th), calls in T2["threads"].items():
        if th == "main" or (s, th) not in atype:
            continue
        cats = [CATS.index(tool_cat(c["tool"], c["cmd"])) for c in calls]
        ms = [assign(C, feat(cats[max(0, i - 19):i + 1])) for i in range(len(cats))]
        thread_modes[(s, th)] = (cats, ms)
        per_type[atype[(s, th)]].update(ms)
    print(f"labelled subagent threads {len(thread_modes)} over {len(per_type)} agentTypes")
    tot = sum(sum(v.values()) for v in per_type.values())
    for t, c in sorted(per_type.items(), key=lambda kv: -sum(kv[1].values()))[:12]:
        n = sum(c.values())
        m, v = c.most_common(1)[0]
        print(f"  {t}: windows {n}, modal mode {m} share {v/n:.2f}")
    # NMI
    joint = Counter()
    for t, c in per_type.items():
        for m, v in c.items():
            joint[(t, m)] += v
    pt = Counter()
    pm = Counter()
    for (t, m), v in joint.items():
        pt[t] += v
        pm[m] += v
    mi = sum(v / tot * np.log((v / tot) / (pt[t] / tot * pm[m] / tot)) for (t, m), v in joint.items())
    ht = -sum(v / tot * np.log(v / tot) for v in pt.values())
    hm = -sum(v / tot * np.log(v / tot) for v in pm.values())
    print(f"NMI(agentType, mode) {mi / np.sqrt(ht * hm):.3f}")

    # ---- lag
    lrng = random.Random("m4-8-lag")
    elig = [(k, v) for k, v in thread_modes.items() if len(v[0]) >= 40]
    modal = {k: Counter(v[1]).most_common(1)[0][0] for k, v in elig}
    pairs = [(a, b) for a in elig for b in elig if modal[a[0]] != modal[b[0]]]
    lrng.shuffle(pairs)
    lags = []
    for (ka, va), (kb, vb) in pairs[:500]:
        seq = va[0][-20:] + vb[0][:40]
        lag = 40
        for i in range(40):
            w = seq[i + 1:i + 21]
            if assign(C, feat(w)) == modal[kb]:
                lag = i + 1
                break
        lags.append(lag)
    if lags:
        q = statistics.quantiles(lags, n=4)
        print(f"lag: pairs {len(lags)} (of {len(pairs)} eligible), median {statistics.median(lags)}, "
              f"IQR [{q[0]}, {q[2]}], censored at 40: {sum(1 for x in lags if x == 40)}")

    # ---- use test
    for d in dels:
        w = window(d["session"], d["ts"])
        d["mode"] = assign(C, w) if w is not None else None
    dels = [d for d in dels if d["mode"] is not None]
    train = [d for d in dels if d["ts"] < T]
    test = [d for d in dels if d["ts"] >= T]
    prim_tr = [d for d in train if d["kind"] != "memory"]
    prim = [d for d in test if d["kind"] != "memory"]
    print(f"with a ring window: train {len(train)}, held-out {len(test)}; primary (non-memory) "
          f"held-out {len(prim)}, touched {sum(d['touched'] for d in prim)}")
    print("held-out deliveries per mode", dict(Counter(d["mode"] for d in test)))
    print("held-out mode by session (sessions per mode)",
          {m: len({d['session'] for d in test if d['mode'] == m}) for m in range(K)})
    tk, nk = Counter(), Counter()
    tkm, nkm = Counter(), Counter()
    for d in prim_tr:
        tk[d["kind"]] += d["touched"]
        nk[d["kind"]] += 1
        tkm[(d["kind"], d["mode"])] += d["touched"]
        nkm[(d["kind"], d["mode"])] += 1
    m0 = {k: (tk[k] + 0.5) / (nk[k] + 1) for k in nk}
    def M0(d):
        return m0.get(d["kind"], 0.0)
    def M1(d):
        p = M0(d)
        return (tkm[(d["kind"], d["mode"])] + 20 * p) / (nkm[(d["kind"], d["mode"])] + 20)
    pop = Counter()
    for u in units:
        if u["ts"] < T:
            for k in u["win"]:
                pop[k] += 1
    def P0(d):
        return pop.get(d["key"], 0)
    def P1(d):
        return (P0(d) + 1) * (M1(d) / M0(d) if M0(d) else 1.0)
    y = [d["touched"] for d in prim]
    A = {n: auc([f(d) for d in prim], y) for n, f in (("M0", M0), ("M1", M1), ("P0", P0), ("P1", P1))}
    print("held-out AUC " + " ".join(f"{k} {v:.3f}" for k, v in A.items()))
    byq = defaultdict(list)
    for i, d in enumerate(prim):
        byq[d["qid"]].append(i)
    qids = sorted(byq)
    brng = random.Random("m4")
    sc = {n: [f(d) for d in prim] for n, f in (("M0", M0), ("M1", M1), ("P0", P0), ("P1", P1))}
    d1s, d2s = [], []
    for _ in range(2000):
        idx = [i for _q in range(len(qids)) for i in byq[qids[brng.randrange(len(qids))]]]
        yy = [y[i] for i in idx]
        if 0 < sum(yy) < len(yy):
            a = {n: auc([sc[n][i] for i in idx], yy) for n in sc}
            d1s.append(a["M1"] - a["M0"])
            d2s.append(a["P1"] - a["P0"])
    d1s.sort()
    d2s.sort()
    ci = lambda xs: (xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1])
    D1, D2 = A["M1"] - A["M0"], A["P1"] - A["P0"]
    print(f"C8 Δ1 (mode vs no mode) {D1:+.3f} [{ci(d1s)[0]:+.3f},{ci(d1s)[1]:+.3f}]; "
          f"Δ2 (mode vs popularity) {D2:+.3f} [{ci(d2s)[0]:+.3f},{ci(d2s)[1]:+.3f}]")
    # heterogeneity
    def chi(ds, modes):
        s = 0.0
        by = defaultdict(list)
        for d, m in zip(ds, modes):
            by[d["kind"]].append((m, d["touched"]))
        for k, rows in by.items():
            n = len(rows)
            t = sum(r[1] for r in rows)
            if t == 0 or t == n:
                continue
            for m in set(r[0] for r in rows):
                g = [r[1] for r in rows if r[0] == m]
                for obs, exp in ((sum(g), len(g) * t / n), (len(g) - sum(g), len(g) * (n - t) / n)):
                    s += (obs - exp) ** 2 / exp
        return s
    obs = chi(prim, [d["mode"] for d in prim])
    prng = random.Random("m4-8-perm")
    bykind = defaultdict(list)
    for i, d in enumerate(prim):
        bykind[d["kind"]].append(i)
    ge = 0
    for _ in range(1000):
        modes = [d["mode"] for d in prim]
        for k, ix in bykind.items():
            vals = [modes[i] for i in ix]
            prng.shuffle(vals)
            for i, v in zip(ix, vals):
                modes[i] = v
        ge += chi(prim, modes) >= obs
    print(f"heterogeneity χ² {obs:.1f}, permutation p {(ge + 1) / 1001:.4f}")
    print("use rate by kind × mode (held-out, all kinds):")
    for k in ("code", "doc", "ruling", "bug row", "memory"):
        cells = []
        rates = []
        for m in range(K):
            g = [d for d in test if d["kind"] == k and d["mode"] == m]
            if not g:
                continue
            t = sum(d["touched"] for d in g)
            cells.append(f"m{m} {t}/{len(g)}")
            if len(g) >= 50:
                rates.append((t / len(g), t, len(g), m))
        line = f"  {k}: " + ", ".join(cells)
        if len(rates) >= 2:
            hi_, lo_ = max(rates), min(rates)
            wh, wl = wilson(hi_[1], hi_[2]), wilson(lo_[1], lo_[2])
            ratio = hi_[0] / lo_[0] if lo_[0] else float("inf")
            line += (f" | max/min (modes with >=50) m{hi_[3]}/m{lo_[3]} = {ratio:.2f}"
                     f" Wilson-bound [{wh[0] / wl[1]:.2f}, "
                     f"{(wh[1]/wl[0]) if wl[0] else float('inf'):.2f}]")
        print(line)
    # secondary: explicit used rows
    used = Counter()
    from m4_common import gmd_id_map, item_key
    gid = gmd_id_map()
    for line in open(M4_ROOT / "recall-events.jsonl"):
        e = json.loads(line)
        if e["stage"] != "used":
            continue
        k = item_key(e, gid)
        w = window(e["session"], ts_of(e["ts"]))
        used[(kind_of(k) if k else "no-key", assign(C, w) if w is not None else None)] += 1
    print("explicit used rows by (kind, mode):", dict(used))
    vol = sum(1 for d in dels if d["ts"] >= LAST14) / 2
    vr = sum(1 for r in rings.values() for t, _ in r if t >= LAST14) / 2
    print(f"C8 volume: {vol:.0f} deliveries/week with a mode, {vr:.0f} ring events/week")


if __name__ == "__main__":
    main()
