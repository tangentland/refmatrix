"""M4 candidate 7 (read depth: cue -> anchor), pre-registered at 82fb7997.

Why: agents read large docs a window at a time; if those windows concentrate on a few GMD
sections, anchor-level delivery could replace whole-file reads at a fraction of the bytes. Counts,
rates and byte ratios only; file paths are reported hashed.
"""
from __future__ import annotations

import re
import statistics
import subprocess
from bisect import bisect_right
from collections import Counter, defaultdict

from m4_common import M4_ROOT, REPO, h, load_threads, wilson
from cand12_bridge_cochange import LAST14, pct

SED = re.compile(r"sed\s+-n\s+['\"]?(\d+),(\d+)p['\"]?\s+([^\s;|&]+)")
MIN_LINES, MIN_TRAIN = 300, 5
_hist: dict = {}
_show: dict = {}


def content_at(key: str, ts: float):
    if key.startswith("memory/"):
        p = next((M4_ROOT / "memory").rglob(key.split("/", 1)[1] + ".md"), None)
        return p.read_text(errors="replace") if p else None
    if key not in _hist:
        out = subprocess.run(["git", "-C", str(REPO), "log", "master", "--format=%ct %H", "--", key],
                             capture_output=True, text=True).stdout
        _hist[key] = sorted((float(a), b) for a, b in (l.split() for l in out.splitlines()))
    hs = _hist[key]
    i = bisect_right([t for t, _ in hs], ts) - 1
    if i < 0:
        return None
    sha = hs[i][1]
    if (sha, key) not in _show:
        r = subprocess.run(["git", "-C", str(REPO), "show", f"{sha}:{key}"], capture_output=True)
        _show[(sha, key)] = r.stdout.decode(errors="replace") if r.returncode == 0 else None
    return _show[(sha, key)]


def sections(text: str):
    """[(start_line, end_line, anchor, bytes)] 1-based inclusive; preamble is its own section."""
    lines = text.splitlines(keepends=True)
    heads = []
    fence = False
    for i, l in enumerate(lines, 1):
        if l.lstrip().startswith("```"):
            fence = not fence
        if not fence and re.match(r"#{1,6}\s", l):
            m = re.search(r"\{#([\w\-.]+)\}", l)
            heads.append((i, m.group(1) if m else "h:" + h(l.strip())))
    out = []
    starts = [1] + [s for s, _ in heads] if (not heads or heads[0][0] != 1) else [s for s, _ in heads]
    names = (["<pre>"] if (not heads or heads[0][0] != 1) else []) + [a for _, a in heads]
    for j, s in enumerate(starts):
        e = (starts[j + 1] - 1) if j + 1 < len(starts) else len(lines)
        out.append((s, e, names[j], sum(len(x.encode()) for x in lines[s - 1:e])))
    return out, len(lines), sum(len(x.encode()) for x in lines)


def main():
    T = load_threads()
    reads = []
    for (s, th), calls in T["threads"].items():
        for c in calls:
            if c["tool"] == "Read" and c["keys"] and (c["offset"] or c["limit"]):
                a = int(c["offset"] or 1)
                b = a + int(c["limit"] or 2000) - 1
                reads.append({"ts": c["ts"], "key": c["keys"][0], "a": a, "b": b, "form": "Read",
                              "main": th == "main", "session": s})
            elif c["tool"] == "Bash" and c["cmd"]:
                for m in SED.finditer(c["cmd"]):
                    from m4_common import key_of_path
                    k = key_of_path(m.group(3))
                    if k:
                        reads.append({"ts": c["ts"], "key": k, "a": int(m.group(1)), "b": int(m.group(2)),
                                      "form": "sed", "main": th == "main", "session": s})
    print(f"partial reads with a file key {len(reads)} (Read {sum(r['form']=='Read' for r in reads)},"
          f" sed {sum(r['form']=='sed' for r in reads)}; main loop {sum(r['main'] for r in reads)})")
    # GMD heading sections exist only in markdown; a .py file's "# comment" lines are not anchors,
    # so the brief's "large docs" are the .md files and memories (first run mixed in code files).
    print(f"  of which markdown/memory {sum(1 for r in reads if r['key'].endswith('.md') or r['key'].startswith('memory/'))}")
    reads = [r for r in reads if r["key"].endswith(".md") or r["key"].startswith("memory/")]
    big = []
    for r in reads:
        t = content_at(r["key"], r["ts"])
        if t is None:
            continue
        secs, n, nb = sections(t)
        if n < MIN_LINES:
            continue
        r.update(secs=secs, n=n, nb=nb)
        r["b"] = min(r["b"], n)
        if r["a"] > n:
            continue
        big.append(r)
    print(f"partial reads on files >= {MIN_LINES} lines (content resolved at read time) {len(big)} over"
          f" {len({r['key'] for r in big})} files")
    T7 = pct([r["ts"] for r in big], 0.6)
    train = [r for r in big if r["ts"] < T7]
    test = [r for r in big if r["ts"] >= T7]
    cnt = defaultdict(Counter)
    ntr = Counter()
    for r in train:
        ntr[r["key"]] += 1
        for s, e, a, _ in r["secs"]:
            if s <= r["b"] and e >= r["a"]:
                cnt[r["key"]][a] += 1
    ev = [r for r in test if ntr[r["key"]] >= MIN_TRAIN]
    print(f"T*={T7:.0f}: train reads {len(train)}, held-out {len(test)}, held-out on files with >= "
          f"{MIN_TRAIN} train reads {len(ev)} over {len({r['key'] for r in ev})} files")
    inside = cov90 = 0
    ctrl, cuts, cov, oracle_cuts, sec_per_read = [], [], [], [], []
    for r in ev:
        top = {a for a, _ in sorted(cnt[r["key"]].items(), key=lambda kv: (-kv[1], kv[0]))[:3]}
        tl = set()
        tb = 0
        for s, e, a, b in r["secs"]:
            if a in top:
                tl.update(range(s, e + 1))
                tb += b
        rl = set(range(r["a"], r["b"] + 1))
        c = len(rl & tl) / len(rl)
        cov.append(c)
        inside += int(c == 1.0)
        cov90 += int(c >= 0.9)
        ctrl.append(len(tl) / r["n"])
        cuts.append(1 - tb / r["nb"])
        ob = sum(b for s, e, a, b in r["secs"] if s <= r["b"] and e >= r["a"])
        oracle_cuts.append(1 - ob / r["nb"])
        sec_per_read.append(sum(1 for s, e, a, b in r["secs"] if s <= r["b"] and e >= r["a"]))
    n = len(ev)
    if n:
        lo, hi = wilson(inside, n)
        print(f"C7 held-out reads inside the train top-3 anchors {inside}/{n}={inside/n:.3f} "
              f"[{lo:.3f},{hi:.3f}]; control (top-3 size share) mean {statistics.mean(ctrl):.3f};"
              f" ratio {inside/n/statistics.mean(ctrl):.2f}x")
        lo, hi = wilson(cov90, n)
        print(f"C7 coverage>=0.9 by top-3 {cov90}/{n}={cov90/n:.3f} [{lo:.3f},{hi:.3f}]; mean coverage "
              f"{statistics.mean(cov):.3f}; median payload cut by top-3 delivery "
              f"{statistics.median(cuts):.3f}; oracle (sections the read overlaps) median cut "
              f"{statistics.median(oracle_cuts):.3f}; sections per read median "
              f"{statistics.median(sec_per_read)}")
        for lab, sub in (("main", [i for i, r in enumerate(ev) if r["main"]]),
                         ("sub", [i for i, r in enumerate(ev) if not r["main"]])):
            if sub:
                k = sum(1 for i in sub if cov[i] == 1.0)
                print(f"  stratum {lab}: {k}/{len(sub)} inside, control {statistics.mean(ctrl[i] for i in sub):.3f}")
        files = Counter(r["key"] for r in ev)
        print("  held-out reads per file (hashed):", [(h(k), v) for k, v in files.most_common(8)])
    # concentration on train: share of a file's train reads on its top-3 sections
    shares = []
    for k, c in cnt.items():
        if ntr[k] >= MIN_TRAIN:
            tot = sum(c.values())
            shares.append(sum(v for _, v in c.most_common(3)) / tot)
    if shares:
        print(f"train concentration: files {len(shares)}, median share of section-hits on top-3 "
              f"{statistics.median(shares):.3f}")
    vol = sum(1 for r in big if r["ts"] >= LAST14) / 2
    print(f"C7 volume: {vol:.1f} partial reads of large files/week")


if __name__ == "__main__":
    main()
