"""M4 candidate 6 (corrections: delivered -> contradicted, demote-only), pre-registered at 82fb7997.

Why: a demote-only signal is safe only if it is precise as a negative: items it flags must be
used less on later deliveries than items it does not. Measured on the product path (held-out
deliveries and their touch windows). Counts and rates only; no prompt text leaves memory.
"""
from __future__ import annotations

import bisect
import random
import re
import subprocess
from collections import Counter, defaultdict

from m4_common import M4_ROOT, REPO, load_queries, load_threads, ts_of, wilson
from cand12_bridge_cochange import LAST14, build_units, pct

CORR = re.compile(r"^\s*(no\b|wrong\b|that'?s not\b|not what\b|stop\b|don'?t\b|undo\b|revert\b|"
                  r"incorrect\b|you'?re wrong\b)", re.I)
EDGE = re.compile(r"^rel:\s*(supersedes|amends)\s*->\s*\[\[([^\]#|]+)", re.M)
DAY = 86400.0


def main():
    units, _ = build_units()
    Q = load_queries()
    prompts = load_threads()["prompts"]
    dels = []  # one row per (query unit, delivered key)
    for u in units:
        q = Q[u["qid"]]
        ps = prompts.get(u["session"], [])
        pts = [p[0] for p in ps]
        j = bisect.bisect_right(pts, u["ts"] + 2)
        nxt = ps[j][1] if j < len(ps) else None
        corr = bool(nxt and CORR.match(nxt))
        for k in q["delivered"]:
            dels.append({"ts": u["ts"], "key": k, "touched": int(k in u["win"]), "corr": corr,
                         "qid": u["qid"], "session": u["session"]})
    print(f"deliveries with a key and a joined window {len(dels)} over "
          f"{len({d['qid'] for d in dels})} query units; next prompt is a correction for "
          f"{len({d['qid'] for d in dels if d['corr']})} units")
    T = pct([d["ts"] for d in dels], 0.6)
    train = [d for d in dels if d["ts"] < T]
    test = [d for d in dels if d["ts"] >= T]
    # S1
    s1 = {d["key"] for d in train if d["corr"]}
    # S2
    created, inbound = {}, defaultdict(list)
    for p in (M4_ROOT / "memory").rglob("*.md"):
        t = p.read_text(errors="replace")
        m = re.search(r"^\s*created:\s*\"?(\d{4}-\d{2}-\d{2})", t, re.M)
        if not m:
            continue
        c = ts_of(m.group(1) + "T00:00:00Z")
        for _, tgt in EDGE.findall(t):
            inbound[f"memory/{tgt.strip()}"].append(c)
    s2 = {k for k, cs in inbound.items() if any(c < T for c in cs)}
    # S3
    out = subprocess.run(["git", "-C", str(REPO), "log", "master", "--format=@@%ct %s", "--name-only",
                          "--no-renames"], capture_output=True, text=True, check=True).stdout
    reverts = defaultdict(list)
    cur = None
    for line in out.splitlines():
        if line.startswith("@@"):
            ts, _, subj = line[2:].partition(" ")
            cur = float(ts) if subj.startswith("Revert") else None
        elif line.strip() and cur is not None:
            reverts[line.strip()].append(cur)
    s3 = set()
    for d in train:
        if any(d["ts"] < r <= d["ts"] + 7 * DAY and r < T for r in reverts.get(d["key"], [])):
            s3.add(d["key"])
    print(f"T*={T:.0f}: train deliveries {len(train)}, held-out {len(test)}; flagged keys "
          f"S1 {len(s1)}, S2 {len(s2)}, S3 {len(s3)}; revert commits touching files "
          f"{len({r for v in reverts.values() for r in v})}")

    def rr(flagset, label, pool=None):
        pool = test if pool is None else pool
        f = [d for d in pool if d["key"] in flagset]
        nf = [d for d in pool if d["key"] not in flagset]
        if not f or not nf:
            print(f"C6 {label}: flagged held-out deliveries {len(f)}")
            return
        tf, tn = sum(d["touched"] for d in f) / len(f), sum(d["touched"] for d in nf) / len(nf)
        R = tf / tn if tn else float("nan")
        rng = random.Random("m4")
        qids = sorted({d["qid"] for d in pool})
        byq = defaultdict(list)
        for d in pool:
            byq[d["qid"]].append(d)
        bs = []
        for _ in range(2000):
            pick = [d for _i in range(len(qids)) for d in byq[qids[rng.randrange(len(qids))]]]
            a = [d for d in pick if d["key"] in flagset]
            b = [d for d in pick if d["key"] not in flagset]
            if a and b and sum(x["touched"] for x in b):
                bs.append((sum(x["touched"] for x in a) / len(a)) / (sum(x["touched"] for x in b) / len(b)))
        bs.sort()
        lo, hi = bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs)) - 1]
        kf, kn = sum(d["touched"] for d in f), sum(d["touched"] for d in nf)
        # Wilson-bound ratio: the bootstrap degenerates to [0, 0] when the flagged arm has no touch
        wf, wn = wilson(kf, len(f)), wilson(kn, len(nf))
        wb = (wf[0] / wn[1], wf[1] / wn[0]) if wn[0] > 0 else (float("nan"),) * 2
        print(f"C6 {label}: flagged n={len(f)} touch {kf}/{len(f)}={tf:.3f} {fmt(wilson(kf, len(f)))}"
              f" | unflagged n={len(nf)} touch {kn}/{len(nf)}={tn:.3f} {fmt(wilson(kn, len(nf)))}"
              f" | RR {R:.2f} [{lo:.2f},{hi:.2f}] (query-cluster bootstrap)"
              f" Wilson-bound [{wb[0]:.2f},{wb[1]:.2f}]"
              f" | precision-as-negative {1-tf:.3f} vs {1-tn:.3f}")

    rr(s1, "S1 user-correction")
    rr(s2, "S2 superseded/amended memory")
    rr(s3, "S3 reverted file")
    rr(s1 | s2 | s3, "pooled")
    memtest = [d for d in test if d["key"].startswith("memory/")]
    rr(s2, "S2 stratified: memory deliveries only (review rule: stratify)", memtest)
    rr(s1, "S1 stratified: memory deliveries only", memtest)
    print("held-out touch rate by kind: memory "
          f"{sum(d['touched'] for d in memtest)}/{len(memtest)}, repo "
          f"{sum(d['touched'] for d in test if not d['key'].startswith('memory/'))}/"
          f"{sum(1 for d in test if not d['key'].startswith('memory/'))}")
    mem = [d for d in dels if d["key"].startswith("memory/")]
    stale = sum(1 for d in mem if any(c < d["ts"] for c in inbound.get(d["key"], [])))
    print(f"S2 prevalence: memory deliveries already superseded/amended at delivery {stale}/{len(mem)}"
          f" {fmt(wilson(stale, len(mem)))}")
    vol = sum(1 for d in dels if d["ts"] >= LAST14) / 2
    volc = len({d["qid"] for d in dels if d["ts"] >= LAST14 and d["corr"]}) / 2
    print(f"C6 volume: {vol:.0f} keyed deliveries/week; {volc:.1f} correction-followed units/week")


def fmt(t):
    return f"[{t[0]:.3f},{t[1]:.3f}]"


if __name__ == "__main__":
    main()
