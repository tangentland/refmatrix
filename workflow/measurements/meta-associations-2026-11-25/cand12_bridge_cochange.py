"""M4 candidates 1 (search-resolution bridge) and 2 (co-change), pre-registered at 82fb7997.

Why: the measured ceiling is recall (46% of cliquedb known-item queries never retrieve the gold),
so these two are scored on the logged product path: held-out query units whose new-touch gold the
retrieval missed, and whether the association's top-k would have reached it, against a popularity
and a placebo control. Prints counts and rates only.
"""
from __future__ import annotations

import bisect
import math
import os
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(os.environ.get("M4_SRC", "/Volumes/littlebig/refmatrix-m4/src")))
from refmatrix.terms import STOPWORDS  # same object as scan._PROMPT_STOPWORDS (checked)

from m4_common import REPO, load_queries, load_threads, ts_of, wilson

HOOK = {"scan_prompt", "prompt_recall", "session_start", "precompact"}
WIN, PRIOR = 10, 200
TOK = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]{2,}")
LAST14 = ts_of("2026-11-11T00:00:00Z")


def terms(text: str | None) -> set[str]:
    if not text:
        return set()
    return {t.lower() for t in TOK.findall(text) if t.lower() not in STOPWORDS}


def build_units():
    T = load_threads()
    threads, prompts = T["threads"], T["prompts"]
    Q = load_queries()
    by_sess = defaultdict(list)
    for (s, th), calls in threads.items():
        by_sess[s].append((th, calls))
    units = []
    unjoined = Counter()
    for qid, q in Q.items():
        s = q["session"]
        if s not in prompts and s not in by_sess:
            unjoined["no-transcript"] += 1
            continue
        if q["channel"] in HOOK and q["invocation"] == "hook":
            calls = threads.get((s, "main"))
            if not calls:
                unjoined["no-main"] += 1
                continue
            ps = prompts.get(s, [])
            pts = [p[0] for p in ps]
            j = bisect.bisect_right(pts, q["ts"] + 5) - 1
            text = ps[j][1] if j >= 0 and q["ts"] - ps[j][0] < 600 else None
            nxt = next((p for p in pts if p > q["ts"] + 2), float("inf"))
            cts = [c["ts"] for c in calls]
            start = bisect.bisect_right(cts, q["ts"])
            win = [c for c in calls[start:start + WIN] if c["ts"] < nxt]
            pos, thread = start, "main"
        else:
            best = None
            for th, calls in by_sess.get(s, []):
                for c in calls:
                    if q["ts"] - 120 <= c["ts"] <= q["ts"] + 2 and (
                            c["ctx"] or (c["cmd"] and "rmx" in c["cmd"] and (
                                "context" in c["cmd"] or "recall" in c["cmd"]))):
                        d = abs(q["ts"] - c["ts"])
                        if best is None or d < best[0]:
                            best = (d, th, calls, c)
            if best is None:
                unjoined["agent-call-not-found"] += 1
                continue
            _, thread, calls, c = best
            text = c["ctx"] or c["cmd"]
            pos = c["i"] + 1
            win = calls[pos:pos + WIN]
        prior = set(k for c in calls[max(0, pos - PRIOR):pos] for k in c["keys"])
        last3 = []
        for c in reversed(calls[max(0, pos - PRIOR):pos]):
            for k in c["keys"]:
                if k not in last3:
                    last3.append(k)
            if len(last3) >= 3:
                break
        wk = []
        for c in win:
            for k in c["keys"]:
                if k not in wk:
                    wk.append(k)
        new = [k for k in wk if k not in prior]
        re_ = [k for k in wk if k in prior]
        ranked = [k for _, k, _ in sorted(q["rows"])]
        top10 = []
        for k in ranked:
            if k not in top10:
                top10.append(k)
            if len(top10) == 10:
                break
        units.append({
            "qid": qid, "session": s, "thread": "main" if thread == "main" else "sub",
            "ts": q["ts"], "group": "push" if q["invocation"] == "hook" else "pull",
            "channel": q["channel"], "terms": terms(text), "retrieved": q["keys"],
            "cue_retrieved": top10[:10], "cue_last3": last3[:3], "win": set(wk),
            "new": new, "re": re_,
            "missed_new": [k for k in new if k not in q["keys"]],
            "missed_re": [k for k in re_ if k not in q["keys"]],
            "hit_new": [k for k in new if k in q["keys"]],
        })
    return units, unjoined


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def rank_top(scores: dict, k: int, exclude=frozenset()) -> list:
    return [x for x, _ in sorted(((x, v) for x, v in scores.items() if x not in exclude),
                                 key=lambda kv: (-kv[1], kv[0]))][:k]


def evaluate(name, units_eval, scorer, pop_list, gold_field, rng_seed, exclude_retrieved=False,
             filt=lambda k: True):
    rng = random.Random(rng_seed)
    res = []
    for u in units_eval:
        golds = [g for g in u[gold_field] if filt(g)]
        if not golds:
            continue
        ex = frozenset(u["retrieved"]) if exclude_retrieved else frozenset()
        others = [v for v in units_eval if v["session"] != u["session"]]
        plac = rng.choice(others) if others else None
        out = {"u": u}
        for lab, sc in (("cand", scorer(u)), ("plac", scorer(plac) if plac else {})):
            for k in (5, 10, 20):
                top = rank_top(sc, k, ex)
                out[f"{lab}@{k}"] = int(any(g in top for g in golds))
            top10 = rank_top(sc, 10, ex)
            out[f"{lab}_n"] = len(top10)
            out[f"{lab}_fr"] = (sum(1 for x in top10 if x not in u["win"]) / len(top10)) if top10 else None
        pl = [x for x in pop_list if x not in ex]
        for k in (5, 10, 20):
            out[f"pop@{k}"] = int(any(g in pl[:k] for g in golds))
        out["pop_fr"] = sum(1 for x in pl[:10] if x not in u["win"]) / max(1, len(pl[:10]))
        res.append(out)
    return res


def summarize(label, res, seed="m4"):
    n = len(res)
    if n == 0:
        print(f"{label}: n=0")
        return None
    def rate(key):
        k = sum(r[key] for r in res)
        lo, hi = wilson(k, n)
        return k, k / n, lo, hi
    line = [f"{label}: n={n}"]
    for key in ("cand@5", "cand@10", "cand@20", "pop@10", "plac@10"):
        k, p, lo, hi = rate(key)
        line.append(f"{key} {k}/{n}={p:.3f}[{lo:.3f},{hi:.3f}]")
    cfr = [r["cand_fr"] for r in res if r["cand_fr"] is not None]
    pfr = [r["plac_fr"] for r in res if r["plac_fr"] is not None]
    line.append(f"cand_nonempty {len(cfr)}/{n}")
    line.append(f"FR@10 cand {sum(cfr)/max(1,len(cfr)):.3f} pop {sum(r['pop_fr'] for r in res)/n:.3f}"
                f" plac {sum(pfr)/max(1,len(pfr)):.3f}")
    def lift(rs):
        c = sum(r["cand@10"] for r in rs) / len(rs)
        b = max(sum(r["pop@10"] for r in rs), sum(r["plac@10"] for r in rs)) / len(rs)
        return c - b
    L = lift(res)
    rng = random.Random(seed)
    bs = sorted(lift([res[rng.randrange(n)] for _ in range(n)]) for _ in range(2000))
    line.append(f"LIFT {L*100:+.1f}pp [{bs[50]*100:+.1f},{bs[1949]*100:+.1f}]")
    sess = defaultdict(list)
    for r in res:
        sess[r["u"]["session"]].append(r)
    if len(sess) >= 5:
        keys = list(sess)
        bsc = []
        for _ in range(2000):
            pick = [r for _k in range(len(keys)) for r in sess[keys[rng.randrange(len(keys))]]]
            bsc.append(lift(pick))
        bsc.sort()
        line.append(f"cluster[{bsc[50]*100:+.1f},{bsc[1949]*100:+.1f}] sessions={len(sess)}")
    else:
        line.append(f"sessions={len(sess)}")
    print(" | ".join(line))
    return L


def git_commits(max_files=30):
    out = subprocess.run(["git", "-C", str(REPO), "log", "master", "--format=@@%H %ct",
                          "--name-only", "--no-renames"], capture_output=True, text=True,
                         check=True).stdout
    commits = []
    cur = None
    for line in out.splitlines():
        if line.startswith("@@"):
            sha, ct = line[2:].split()
            cur = {"sha": sha, "ts": float(ct), "files": []}
            commits.append(cur)
        elif line.strip() and cur is not None:
            cur["files"].append(line.strip())
    return [c for c in commits if 0 < len(c["files"]) <= max_files], len(commits)


def main():
    units, unjoined = build_units()
    print("units", len(units), "unjoined", dict(unjoined))
    print("units by group/thread", Counter((u["group"], u["thread"]) for u in units))
    print("units with any new gold", sum(1 for u in units if u["new"]),
          "with missed new gold", sum(1 for u in units if u["missed_new"]),
          "with hit new gold", sum(1 for u in units if u["hit_new"]))
    ng = sum(len(u["new"]) for u in units)
    hn = sum(len(u["hit_new"]) for u in units)
    print(f"new-touch golds {ng}, retrieved by the query {hn} ({hn/max(1,ng):.3f})")

    # ---- candidate 1
    ev = [u for u in units if u["missed_new"]]
    T1 = pct([u["ts"] for u in ev], 0.6)
    train = [u for u in units if u["ts"] < T1]
    test = [u for u in ev if u["ts"] >= T1]
    print(f"\n== C1 T*={T1:.0f} train units {len(train)} (missed-pair units "
          f"{sum(1 for u in train if u['missed_new'])}), held-out eval units {len(test)}")
    df = Counter()
    for u in train:
        for t in u["terms"]:
            df[t] += 1
    N = len(train)
    ct, ctf = Counter(), defaultdict(Counter)
    for u in train:
        if not u["missed_new"]:
            continue
        for t in u["terms"]:
            ct[t] += 1
            for g in u["missed_new"]:
                ctf[t][g] += 1
    usable = {t for t, c in ct.items() if c >= 2}
    print("C1 usable terms", len(usable), "of", len(ct))

    def s1(u):
        sc = Counter()
        if u is None:
            return sc
        for t in u["terms"] & usable:
            idf = math.log(N / max(1, df[t]))
            for f, c in ctf[t].items():
                sc[f] += idf * c / (ct[t] + 2)
        return sc
    pop = Counter(g for u in train for g in u["missed_new"])
    pop_list = [k for k, _ in sorted(pop.items(), key=lambda kv: (-kv[1], kv[0]))]
    covered = sum(1 for u in test if u["terms"] & usable)
    print(f"C1 held-out units with >=1 usable term {covered}/{len(test)}")
    summarize("C1 all", evaluate("c1", test, s1, pop_list, "missed_new", "m4-1"))
    summarize("C1 push", evaluate("c1", [u for u in test if u["group"] == "push"], s1, pop_list,
                                  "missed_new", "m4-1"))
    summarize("C1 pull", evaluate("c1", [u for u in test if u["group"] == "pull"], s1, pop_list,
                                  "missed_new", "m4-1"))
    summarize("C1 main", evaluate("c1", [u for u in test if u["thread"] == "main"], s1, pop_list,
                                  "missed_new", "m4-1"))
    summarize("C1 sub", evaluate("c1", [u for u in test if u["thread"] == "sub"], s1, pop_list,
                                 "missed_new", "m4-1"))
    seen_u, dd = set(), []
    for u in test:
        key = (u["session"], frozenset(u["missed_new"]), frozenset(u["terms"]))
        if key not in seen_u:
            seen_u.add(key)
            dd.append(u)
    summarize("C1 one unit per prompt window (sens)", evaluate("c1", dd, s1, pop_list, "missed_new", "m4-1"))
    summarize("C1 excl-retrieved (sens)", evaluate("c1", test, s1, pop_list, "missed_new", "m4-1",
                                                   exclude_retrieved=True))
    test_re = [u for u in units if u["ts"] >= T1 and u["missed_re"]]
    summarize("C1 re-touch gold stratum", evaluate("c1", test_re, s1, pop_list, "missed_re", "m4-1"))
    vol = sum(1 for u in ev if u["ts"] >= LAST14) / 2
    print(f"C1 volume: {vol:.1f} missed-pair units/week (last 14 days)")

    # ---- candidate 2
    commits, ncomm = git_commits()
    def is_repo(k):
        return not k.startswith("memory/")
    ev2 = [u for u in units if any(is_repo(g) for g in u["missed_new"])]
    T2 = pct([u["ts"] for u in ev2], 0.6)
    test2 = [u for u in ev2 if u["ts"] >= T2]
    tr_commits = [c for c in commits if c["ts"] < T2]
    print(f"\n== C2 T*={T2:.0f} commits <=30 files before T* {len(tr_commits)} (of {ncomm} on master),"
          f" held-out eval units {len(test2)}")
    cc = defaultdict(Counter)
    nch = Counter()
    for c in tr_commits:
        fs = set(c["files"])
        for a in fs:
            nch[a] += 1
            for b in fs:
                if a != b:
                    cc[a][b] += 1

    def s2(cue_field):
        def f(u):
            sc = Counter()
            if u is None:
                return sc
            for a in u[cue_field]:
                for b, c in cc.get(a, {}).items():
                    sc[b] += c / (nch[a] + 1)
            return sc
        return f
    pop2 = Counter(g for u in units if u["ts"] < T2 for g in u["missed_new"] if is_repo(g))
    pop2_list = [k for k, _ in sorted(pop2.items(), key=lambda kv: (-kv[1], kv[0]))]
    cue_in_git = sum(1 for u in test2 if any(a in cc for a in u["cue_retrieved"]))
    print(f"C2 held-out units whose retrieved cue has co-change data {cue_in_git}/{len(test2)}")
    for lab, field in (("C2 cue=retrieved", "cue_retrieved"), ("C2 cue=last3 (secondary)", "cue_last3")):
        summarize(lab, evaluate("c2", test2, s2(field), pop2_list, "missed_new", "m4-2", filt=is_repo))
        summarize(lab + " push", evaluate("c2", [u for u in test2 if u["group"] == "push"], s2(field),
                                          pop2_list, "missed_new", "m4-2", filt=is_repo))
        summarize(lab + " excl-retrieved (sens)", evaluate("c2", test2, s2(field), pop2_list,
                                                           "missed_new", "m4-2", exclude_retrieved=True,
                                                           filt=is_repo))
    seen_u, dd2 = set(), []
    for u in test2:
        key = (u["session"], frozenset(u["missed_new"]), tuple(u["cue_retrieved"]))
        if key not in seen_u:
            seen_u.add(key)
            dd2.append(u)
    summarize("C2 cue=retrieved one unit per prompt window (sens)",
              evaluate("c2", dd2, s2("cue_retrieved"), pop2_list, "missed_new", "m4-2", filt=is_repo))
    vol2c = sum(1 for c in commits if c["ts"] >= LAST14) / 2
    vol2 = sum(1 for u in ev2 if u["ts"] >= LAST14) / 2
    print(f"C2 volume: {vol2c:.1f} commits/week (<=30 files), {vol2:.1f} eval units/week")
    # intrinsic: held-out commits, leave-one-out reach of the other files
    hc = [c for c in commits if c["ts"] >= T2 and len(set(c["files"])) >= 2]
    hits = n = 0
    for c in hc:
        fs = sorted(set(c["files"]))
        for a in fs:
            if a not in cc:
                continue
            sc = Counter({b: v / (nch[a] + 1) for b, v in cc[a].items()})
            top = rank_top(sc, 10)
            n += 1
            hits += int(any(b in top for b in fs if b != a))
    lo, hi = wilson(hits, n)
    print(f"C2 intrinsic (held-out commits, one file -> another in top-10): {hits}/{n}={hits/max(1,n):.3f}"
          f" [{lo:.3f},{hi:.3f}] over {len(hc)} commits")


if __name__ == "__main__":
    main()
