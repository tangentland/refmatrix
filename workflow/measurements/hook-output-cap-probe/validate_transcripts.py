#!/usr/bin/env python3
"""Read-only cross-check of the probe's rule against INTERACTIVE session transcripts.

Rule under test: a hook's output is replaced by a <persisted-output> preview iff the UTF-16
length of its whitespace-trimmed stdout exceeds 10,000. Scans hook_success records in the
refmatrix project's transcripts (and subagent transcripts) modified in the last N days, reports
agreement, the largest-whole / smallest-previewed sizes, and per-event evidence that the cap is
per hook (whole hooks on one event summing past 10,000).

Usage: python3 validate_transcripts.py [days=14] [project-dir]
"""
import collections
import glob
import json
import os
import sys
import time

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 14
PROJ = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(
    "~/.claude/projects/-Users-tholley-claude-tools-refmatrix")


def u16(s):
    return len(s.encode("utf-16-le")) // 2


def main():
    cut = time.time() - DAYS * 86400
    files = [f for f in glob.glob(f"{PROJ}/*.jsonl") + glob.glob(f"{PROJ}/*/subagents/*.jsonl")
             if os.path.getmtime(f) > cut]
    stats = collections.Counter()
    versions = collections.Counter()
    mism = []
    near = []
    groups = collections.defaultdict(list)
    for f in files:
        gi = 0
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("type") in ("user", "assistant"):
                    gi += 1
                    continue
                a = r.get("attachment") or {}
                if r.get("type") != "attachment" or a.get("type") != "hook_success":
                    continue
                so = (a.get("stdout") or "").strip()
                if not so:
                    continue
                ev = a.get("hookEvent")
                prev = (a.get("content") or "").startswith("<persisted-output>")
                n = u16(so)
                versions[r.get("version")] += 1
                stats[(ev, "previewed" if prev else "whole", "rule>10000" if n > 10000 else
                       "rule<=10000")] += 1
                if prev != (n > 10000):
                    mism.append((os.path.basename(f), r.get("version"), ev, n, prev))
                if 9000 <= n <= 11000:
                    near.append((n, ev, prev, r.get("version")))
                if ev in ("UserPromptSubmit", "SessionStart"):
                    groups[(f, ev, gi)].append((n, prev))
    print(f"files={len(files)} days={DAYS} versions={dict(versions)}")
    for k, v in sorted(stats.items(), key=str):
        print(" ", k, v)
    print("mismatches:", len(mism), mism[:10])
    near.sort()
    whole = [x for x in near if not x[2]]
    prev = [x for x in near if x[2]]
    print("largest whole (9k-11k):", whole[-3:])
    print("smallest previewed (9k-11k):", prev[:3])
    c = collections.Counter()
    best = {}
    for (f, ev, g), hs in groups.items():
        w = [n for n, p in hs if not p]
        c[f"{ev} events"] += 1
        if len(w) >= 2 and sum(w) > 10000:
            c[f"{ev} events whose WHOLE hooks sum > 10000"] += 1
            best[ev] = max(best.get(ev, 0), sum(w))
        if any(p for n, p in hs) and any((not p) and n > 1000 for n, p in hs):
            c[f"{ev} events with one hook previewed beside another >1000 whole"] += 1
    for k, v in sorted(c.items()):
        print(" ", k, v)
    print("max whole-sum per event:", best)


if __name__ == "__main__":
    main()
