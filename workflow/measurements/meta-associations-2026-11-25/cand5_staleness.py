"""M4 candidate 5 (staleness: memory <-> the code it names), pre-registered at 82fb7997.

Why: if churn of the files a memory names predicts that the memory is later superseded or
amended, a staleness flag on delivery could demote a memory before it misleads. Counts, rates and
AUCs only; memory ids are never printed.
"""
from __future__ import annotations

import random
import re
import subprocess
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone

from m4_common import M4_ROOT, REPO, key_of_path, repo_files, ts_of, wilson
from cand12_bridge_cochange import pct

DAY = 86400.0
END = ts_of("2026-11-25T23:59:59Z")
EDGE = re.compile(r"^rel:\s*(supersedes|amends)\s*->\s*\[\[([^\]#|]+)", re.M)
PATHTOK = re.compile(r"(?:[\w.\-]+/)+[\w.\-]+\.(?:py|md|sh|json|toml|yaml|yml|js|css|html)")


def fm_date(text: str, field: str):
    m = re.search(rf"^\s*{field}:\s*\"?(\d{{4}}-\d{{2}}-\d{{2}})", text, re.M)
    return ts_of(m.group(1) + "T00:00:00Z") if m else None


def auc(pos, neg):
    if not pos or not neg:
        return float("nan")
    s = 0.0
    for p in pos:
        for n in neg:
            s += 1.0 if p > n else 0.5 if p == n else 0.0
    return s / (len(pos) * len(neg))


def main():
    mems = {}
    for p in (M4_ROOT / "memory").rglob("*.md"):
        if p.name == "MEMORY.md":
            continue
        t = p.read_text(errors="replace")
        idm = re.search(r"^id:\s*\"?([^\"\n]+)", t, re.M)
        mid = idm.group(1).strip() if idm else p.stem
        created = fm_date(t, "created")
        updated = fm_date(t, "updated")
        body = t.split("\n---", 2)[-1] if t.startswith("---") else t
        named = set()
        for tok in PATHTOK.findall(body):
            k = key_of_path(tok)
            if k and not k.startswith("memory/"):
                named.add(k)
        mems[mid] = {"created": created, "date": updated or created, "named": named,
                     "edges": EDGE.findall(t), "savestate": p.stem.startswith("savestate_"),
                     "impression": "impressions" in p.parts}
    inbound = defaultdict(list)  # target -> [(created ts of source, verb)]
    for mid, m in mems.items():
        for verb, tgt in m["edges"]:
            if m["created"] is not None:
                inbound[tgt.strip()].append((m["created"], verb))
    print(f"memories {len(mems)}, dated {sum(1 for m in mems.values() if m['date'])}, naming repo "
          f"files {sum(1 for m in mems.values() if m['named'])}, supersedes/amends edges "
          f"{sum(len(v) for v in inbound.values())} onto {len(inbound)} targets "
          f"({sum(1 for t in inbound if t in mems)} resolve to a present memory)")

    out = subprocess.run(["git", "-C", str(REPO), "log", "master", "--format=@@%ct", "--name-only",
                          "--no-renames"], capture_output=True, text=True, check=True).stdout
    touches = defaultdict(list)
    ts = None
    for line in out.splitlines():
        if line.startswith("@@"):
            ts = float(line[2:])
        elif line.strip():
            touches[line.strip()].append(ts)
    for v in touches.values():
        v.sort()

    def churn(files, d):
        return sum(bisect_right(touches.get(f, []), d + 7 * DAY) - bisect_right(touches.get(f, []), d)
                   for f in files)

    def outcome(mid, d):
        return int(any(d + 7 * DAY < c <= d + 35 * DAY for c, _ in inbound.get(mid, [])))

    def early(mid, d):
        return int(any(d < c <= d + 7 * DAY for c, _ in inbound.get(mid, [])))

    elig = [(mid, m) for mid, m in mems.items() if m["date"] and m["date"] + 35 * DAY <= END]
    named = [(mid, m) for mid, m in elig if m["named"]]
    unnamed = [(mid, m) for mid, m in elig if not m["named"]]
    print(f"eligible (35 d follow-up) {len(elig)}: naming files {len(named)}, naming none {len(unnamed)}")
    rows = [{"mid": mid, "d": m["date"], "churn": churn(m["named"], m["date"]),
             "y": outcome(mid, m["date"]), "early": early(mid, m["date"]), "k": len(m["named"]),
             "ss": m["savestate"], "imp": m["impression"]} for mid, m in named]
    T = pct([r["d"] for r in rows], 0.6)
    train = [r for r in rows if r["d"] < T]
    test = [r for r in rows if r["d"] >= T]
    print(f"T*={datetime.fromtimestamp(T, timezone.utc).date()} train {len(train)} "
          f"(positives {sum(r['y'] for r in train)}), held-out {len(test)} "
          f"(positives {sum(r['y'] for r in test)}); superseded within 7 d (counted negative) "
          f"{sum(r['early'] for r in rows)}")
    tp = sorted(r["churn"] for r in train if r["y"])
    thr = tp[len(tp) // 2] if tp else None
    print(f"train threshold (median churn of train positives) {thr}")
    pos = [r["churn"] for r in test if r["y"]]
    neg = [r["churn"] for r in test if not r["y"]]
    A = auc(pos, neg)
    rng = random.Random("m4-5")
    bs = []
    for _ in range(2000):
        smp = [test[rng.randrange(len(test))] for _ in test]
        a = auc([r["churn"] for r in smp if r["y"]], [r["churn"] for r in smp if not r["y"]])
        if a == a:
            bs.append(a)
    bs.sort()
    ci = (bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs)) - 1]) if bs else (float("nan"),) * 2
    print(f"C5 held-out AUC(churn) {A:.3f} [{ci[0]:.3f},{ci[1]:.3f}] (pos {len(pos)}, neg {len(neg)})")
    if thr is not None:
        hi_ = [r for r in test if r["churn"] >= thr]
        lo_ = [r for r in test if r["churn"] < thr]
        for lab, g in (("churn>=thr", hi_), ("churn<thr", lo_)):
            k = sum(r["y"] for r in g)
            print(f"  outcome rate {lab}: {k}/{len(g)} {wilson(k, len(g))}")
    # controls
    yn = [outcome(mid, m["date"]) for mid, m in unnamed if m["date"] >= T]
    print(f"control: outcome rate, held-out memories naming no file {sum(yn)}/{len(yn)} "
          f"{wilson(sum(yn), len(yn))}; naming files {sum(r['y'] for r in test)}/{len(test)} "
          f"{wilson(sum(r['y'] for r in test), len(test))}")
    allf = sorted(f for f in repo_files() if f in touches)
    pc = {r["mid"]: churn(rng.sample(allf, r["k"]), r["d"]) for r in test}
    Ap = auc([pc[r["mid"]] for r in test if r["y"]], [pc[r["mid"]] for r in test if not r["y"]])
    print(f"placebo churn (same count of random repo files) held-out AUC {Ap:.3f}")
    # stratum without save-states and impressions
    core = [r for r in test if not r["ss"] and not r["imp"]]
    Ac = auc([r["churn"] for r in core if r["y"]], [r["churn"] for r in core if not r["y"]])
    print(f"stratum feedback/project/reference only: n {len(core)}, positives "
          f"{sum(r['y'] for r in core)}, AUC {Ac:.3f}")
    wk = sum(1 for mid, m in mems.items() if m["created"] and m["created"] >= ts_of("2026-11-11T00:00:00Z")) / 2
    we = sum(1 for v in inbound.values() for c, _ in v if c >= ts_of("2026-11-11T00:00:00Z")) / 2
    print(f"C5 volume: {wk:.1f} new memories/week, {we:.1f} supersedes/amends edges/week")


if __name__ == "__main__":
    main()
