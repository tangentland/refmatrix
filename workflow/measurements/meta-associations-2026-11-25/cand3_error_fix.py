"""M4 candidate 3 (error -> fix), pre-registered at 82fb7997.

Why: an error signature is a precise cue; if the same failure recurs, the files that fixed it
last time are a recall bridge vocabulary cannot give. Leg A: transcript tool errors (the STM
ring holds no tool output) -> the next repo-file edit in the thread. Leg B: bug_registry rows,
dated by the commit that added them. Counts and rates only.
"""
from __future__ import annotations

import random
import re
import subprocess
from collections import Counter, defaultdict

from m4_common import REPO, key_of_path, load_queries, load_threads, ts_of, wilson
from cand12_bridge_cochange import LAST14, pct, rank_top, summarize

WIN = 20


def signature(err: str) -> str:
    # "Exit code N" heads every failed Bash result; picking it collapsed 288 of 642 errors into
    # one signature (seen at the first run, 2026-11-25) -- a normaliser bug, fixed and reported.
    lines = [l.strip() for l in err.splitlines()
             if l.strip() and not re.fullmatch(r"Exit code \d+", l.strip())]
    pick = None
    for l in reversed(lines):  # the exception line of a traceback is last
        if re.match(r"^[A-Za-z_.]*(Error|Exception|Exit|Interrupt)\b", l):
            pick = l
            break
    if pick is None:
        pick = next((l for l in lines if re.search(r"error|fail|denied|not found|no such", l, re.I)),
                    lines[0] if lines else "")
    s = re.sub(r"(/[\w.\-~]+)+", "<p>", pick)
    s = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", "<q>", s)
    s = re.sub(r"0x[0-9a-f]+|[0-9a-f]{7,40}", "<h>", s, flags=re.I)
    s = re.sub(r"\d+", "<n>", s)
    return re.sub(r"\s+", " ", s).strip()[:120]


def leg_a():
    T = load_threads()
    Q = load_queries()
    qs = defaultdict(list)
    for q in Q.values():
        qs[q["session"]].append(q)
    units = []
    for (s, th), calls in T["threads"].items():
        for c in calls:
            if not c["err"]:
                continue
            fix = None
            for d in calls[c["i"] + 1:c["i"] + 1 + WIN]:
                if d["edit"] and d["keys"] and not d["keys"][0].startswith("memory/"):
                    fix = d
                    break
            sig = signature(c["err"])
            u = {"session": s, "thread": "main" if th == "main" else "sub", "ts": c["ts"],
                 "sig": sig, "gold": [fix["keys"][0]] if fix else [], "win": set()}
            if fix:
                u["win"] = {k for d in calls[c["i"] + 1:fix["i"] + 1] for k in d["keys"]}
                ret = set()
                for q in qs.get(s, []):
                    if c["ts"] <= q["ts"] <= fix["ts"]:
                        ret |= q["keys"]
                u["retrieved"] = ret
                u["missed"] = [g for g in u["gold"] if g not in ret]
            u["harness"] = bool(re.search(r"tool_use_error|Permission for th|hook error|classifier|"
                                          r"Teammates cannot|Blocked:", c["err"][:300]))
            units.append(u)
    print(f"A: errors {len(units)}, with a repo-file edit within {WIN} calls "
          f"{sum(1 for u in units if u['gold'])}, distinct signatures {len({u['sig'] for u in units})}")
    print("A: by thread", Counter(u["thread"] for u in units),
          "fix-followed by thread", Counter(u["thread"] for u in units if u["gold"]))
    ev = [u for u in units if u.get("missed")]
    print(f"A: fix gold missed by every query in the error->fix window {len(ev)}/"
          f"{sum(1 for u in units if u['gold'])}")
    T3 = pct([u["ts"] for u in ev], 0.6)
    train = [u for u in units if u["ts"] < T3]
    test = [u for u in ev if u["ts"] >= T3]
    sigfix = defaultdict(Counter)
    for u in train:
        for g in u.get("missed", []):
            sigfix[u["sig"]][g] += 1
    sigs_train = {u["sig"] for u in train}
    rec = sum(1 for u in test if u["sig"] in sigs_train)
    rec_fix = sum(1 for u in test if u["sig"] in sigfix)
    lo, hi = wilson(rec, len(test))
    print(f"A: T*={T3:.0f} train errors {len(train)}, held-out eval units {len(test)}; held-out "
          f"signature seen in train {rec}/{len(test)}={rec/max(1,len(test)):.3f} [{lo:.3f},{hi:.3f}],"
          f" seen with a train fix {rec_fix}")
    pop = Counter(g for u in train for g in u.get("missed", []))
    pop_list = [k for k, _ in sorted(pop.items(), key=lambda kv: (-kv[1], kv[0]))]

    def s3(u):
        return Counter(sigfix.get(u["sig"], {})) if u else Counter()
    rng = random.Random("m4-3")
    res = []
    for u in test:
        others = [v for v in test if v["session"] != u["session"]]
        plac = rng.choice(others) if others else None
        out = {"u": u}
        for lab, sc in (("cand", s3(u)), ("plac", s3(plac))):
            for k in (5, 10, 20):
                out[f"{lab}@{k}"] = int(any(g in rank_top(sc, k) for g in u["missed"]))
            top10 = rank_top(sc, 10)
            out[f"{lab}_fr"] = (sum(1 for x in top10 if x not in u["win"]) / len(top10)) if top10 else None
        for k in (5, 10, 20):
            out[f"pop@{k}"] = int(any(g in pop_list[:k] for g in u["missed"]))
        out["pop_fr"] = sum(1 for x in pop_list[:10] if x not in u["win"]) / 10
        res.append(out)
    summarize("C3-A error->fix", res)
    summarize("C3-A code errors only (harness errors excluded)", [r for r in res if not r["u"]["harness"]])
    summarize("C3-A main", [r for r in res if r["u"]["thread"] == "main"])
    summarize("C3-A sub", [r for r in res if r["u"]["thread"] == "sub"])
    vol = sum(1 for u in units if u["gold"] and u["ts"] >= LAST14) / 2
    print(f"A volume: {vol:.1f} error->fix episodes/week; transcripts cover "
          f"{len({u['session'] for u in units})} sessions")


def bug_rows():
    out = subprocess.run(["git", "-C", str(REPO), "log", "master", "--reverse", "-p",
                          "--format=@@%ct", "--", "workflow/bug_registry.md"],
                         capture_output=True, text=True, check=True).stdout
    first = {}
    ts = None
    for line in out.splitlines():
        if line.startswith("@@") and not line.startswith("@@ "):
            ts = float(line[2:])
        elif line.startswith("+| bug-"):
            bid = line[3:].split("|")[0].strip()
            first.setdefault(bid, ts)
    rows = []
    text = (REPO / "workflow/bug_registry.md").read_text()
    for line in text.splitlines():
        if not line.startswith("| bug-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        bid, sym, files = cells[0], cells[1], cells[2] if len(cells) > 2 else ""
        fk = set()
        for tok in re.findall(r"`([^`]+)`", files) + re.findall(r"[\w./\-]+\.(?:py|md|sh|json|toml)", files):
            k = key_of_path(tok.split()[0]) if tok.strip() else None
            if k:
                fk.add(k)
        toks = {t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", sym)}
        rows.append({"id": bid, "ts": first.get(bid), "files": fk, "toks": toks})
    return rows


def leg_b():
    rows = [r for r in bug_rows() if r["ts"] is not None]
    ev = [r for r in rows if r["files"]]
    T = pct([r["ts"] for r in ev], 0.6)
    train = [r for r in ev if r["ts"] < T]
    test = [r for r in ev if r["ts"] >= T]
    print(f"\nB: bug rows dated {len(rows)}, with repo files {len(ev)}; T*={T:.0f} train {len(train)},"
          f" held-out {len(test)}")

    def jac(a, b):
        return len(a & b) / max(1, len(a | b))

    def matched(r):
        m = sorted(((jac(r["toks"], t["toks"]), t["id"], t) for t in train), key=lambda x: (-x[0], x[1]))
        return [t for j, _, t in m if j >= 0.5][:10]

    pop = Counter(f for r in train for f in r["files"])
    pop_list = [k for k, _ in sorted(pop.items(), key=lambda kv: (-kv[1], kv[0]))][:10]
    rng = random.Random("m4-3b")
    nm = hit = ph = pl = 0
    res = []
    for r in test:
        m = matched(r)
        nm += bool(m)
        cand = set().union(*[t["files"] for t in m]) if m else set()
        p = rng.choice([x for x in test if x is not r])
        pc = set().union(*[t["files"] for t in matched(p)]) if matched(p) else set()
        res.append({"u": {"session": r["id"]}, "cand@5": int(bool(cand & r["files"])),
                    "cand@10": int(bool(cand & r["files"])), "cand@20": int(bool(cand & r["files"])),
                    "pop@10": int(bool(set(pop_list) & r["files"])),
                    "plac@10": int(bool(pc & r["files"])), "cand_fr": None, "plac_fr": None,
                    "pop_fr": 0.0})
    lo, hi = wilson(nm, len(test))
    print(f"B: held-out rows with a train row at Jaccard>=0.5: {nm}/{len(test)}={nm/max(1,len(test)):.3f}"
          f" [{lo:.3f},{hi:.3f}]")
    summarize("C3-B bug-row recurrence -> files (cand@k = matched rows' files, k n/a)", res)
    last14 = sum(1 for r in rows if r["ts"] >= LAST14) / 2
    print(f"B volume: {last14:.1f} new bug rows/week")


if __name__ == "__main__":
    leg_a()
    leg_b()
