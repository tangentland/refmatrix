"""M4 candidate 4 (decision provenance: file -> ruling), pre-registered at 82fb7997.

Why: a change to a file often re-opens the ruling that last shaped it; if the commit history
already links files to the L / Q / bug ids their commits cite, that link is a precise cue.
Counts and rates only; ids are reported as counts, never listed.
"""
from __future__ import annotations

import random
import re
import subprocess
from collections import Counter, defaultdict

from m4_common import REPO, wilson
from cand12_bridge_cochange import LAST14, pct, rank_top, summarize

IDRE = re.compile(r"\b(L\d{2,3}|Q\d{1,3}|bug-\d{3})\b")


def commits():
    out = subprocess.run(["git", "-C", str(REPO), "log", "master", "--no-renames",
                          "--format=@@@%H %ct%n%B@@@END", "--name-only"],
                         capture_output=True, text=True, check=True).stdout
    res = []
    for block in out.split("@@@")[1:]:
        if block.startswith("END"):
            files = [l.strip() for l in block[3:].splitlines() if l.strip()]
            if res:
                res[-1]["files"] = files
            continue
        head, _, body = block.partition("\n")
        sha, ct = head.split()
        res.append({"sha": sha, "ts": float(ct), "ids": set(IDRE.findall(body)), "files": []})
    return res


def main():
    cs = commits()
    citing = [c for c in cs if c["ids"] and c["files"]]
    print(f"commits {len(cs)}, citing an id {len(citing)} ({len(citing)/len(cs):.3f})")
    # evaluation units are held-out commits that re-cite a pre-T* id; T* from the citing commits
    # first (the units are only defined once T* is), so T* = 60th pct of citing commits' times.
    T = pct([c["ts"] for c in citing], 0.6)
    train = [c for c in citing if c["ts"] < T]
    seen = set().union(*[c["ids"] for c in train])
    held = [c for c in citing if c["ts"] >= T]
    test = []
    for c in held:
        g = c["ids"] & seen
        if g:
            test.append({**c, "gold": g})
    nh = sum(len(c["ids"]) for c in held)
    nre = sum(len(c["ids"] & seen) for c in held)
    lo, hi = wilson(nre, nh)
    print(f"T*={T:.0f}: train citing commits {len(train)}, held-out citing {len(held)}, held-out "
          f"citations re-citing a pre-T* id {nre}/{nh}={nre/max(1,nh):.3f} [{lo:.3f},{hi:.3f}];"
          f" eval units {len(test)}")
    fid = defaultdict(Counter)
    nf = Counter()
    for c in train:
        for f in set(c["files"]):
            nf[f] += 1
            for i in c["ids"]:
                fid[f][i] += 1
    pop = Counter(i for c in train for i in c["ids"])
    pop_list = [k for k, _ in sorted(pop.items(), key=lambda kv: (-kv[1], kv[0]))]

    def s4(c):
        sc = Counter()
        for f in set(c["files"]):
            for i, v in fid.get(f, {}).items():
                sc[i] += v / (nf[f] + 1)
        return sc
    rng = random.Random("m4-4")
    res = []
    for c in test:
        p = rng.choice([x for x in test if x is not c])
        out = {"u": {"session": c["sha"]}}
        for lab, sc in (("cand", s4(c)), ("plac", s4(p))):
            for k in (5, 10, 20):
                out[f"{lab}@{k}"] = int(bool(set(rank_top(sc, k)) & c["gold"]))
            top10 = rank_top(sc, 10)
            out[f"{lab}_fr"] = (sum(1 for x in top10 if x not in c["ids"]) / len(top10)) if top10 else None
        for k in (5, 10, 20):
            out[f"pop@{k}"] = int(bool(set(pop_list[:k]) & c["gold"]))
        out["pop_fr"] = sum(1 for x in pop_list[:10] if x not in c["ids"]) / 10
        res.append(out)
    summarize("C4 file->ruling", res)
    for kind, pre in (("L-rows", "L"), ("Q ids", "Q"), ("bug ids", "bug-")):
        sub = [r for r, c in zip(res, test) if any(g.startswith(pre) for g in c["gold"])]
        summarize(f"C4 units re-citing {kind}", sub)
    vol = sum(1 for c in citing if c["ts"] >= LAST14) / 2
    volre = sum(1 for c in test if c["ts"] >= LAST14) / 2
    print(f"C4 volume: {vol:.1f} citing commits/week, {volre:.1f} re-citing eval units/week")


if __name__ == "__main__":
    main()
