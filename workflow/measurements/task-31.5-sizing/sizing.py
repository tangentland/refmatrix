#!/usr/bin/env python3
"""Sizing for task 31.5 (plan-31): what the session transcripts already hold.

Why (2026-11-15): the 31.5 spec had to say how many prompts a measurement window needs, how
noisy "discovery calls per prompt" is, and how often past hook output was cut or previewed,
before any capture existed. This reads Claude Code session transcripts READ-ONLY and prints
COUNTS AND BYTE TOTALS ONLY: no prompt, command, payload or path text ever reaches stdout
(feedback_no_raw_prompts_in_public_repo). It is a sizing aid, not the task's scorer.

Usage:  python3 -I sizing.py <transcript dir> [--b-start ISO] [--c-start ISO] [--since ISO]

`--since` prints one more line: the hook-fired prompts and sessions at or after that UTC
instant (the "how many prompts is a week" figure; ch-bsd spec r1 M2 could not reproduce it from
the per-regime lines alone).

`--b-start` / `--c-start` are the UTC instants the 0.83.0 and 0.84.0 builds started serving
hooks. The defaults are approximations read off the transcripts (the first
`--max-bytes 4499` trailer; the 0.84.0 deploy commit), not log-verified instants.
"""
import collections
import glob
import json
import os
import re
import statistics as st
import sys

# A main-loop tool call that goes looking for something. Rough on purpose (a regex over the
# Bash command); the spec's extractor (S0b) is the real definition.
DISC_BASH = re.compile(
    r"(^|[\s;&|(])(grep|rg|find|sed\s+-n|cat|head|tail|rmx\s+grep|rmx\s+context|rmx-master)\b")
OMIT = re.compile(r"# \[\+(\d+) block\(s\) omitted by --max-bytes (\d+)\]")


def block_bytes(stdout: str) -> "collections.Counter":
    """UTF-8 bytes per block kind of one scan-prompt hook stdout, split by header line."""
    out: "collections.Counter" = collections.Counter()
    kind = "other"
    for line in stdout.split("\n"):
        n = len(line.encode("utf-8")) + 1
        if line.startswith("# refmatrix content matches for prompt"):
            kind = "content"
        elif line.startswith("# refmatrix context for prompt-mentioned symbols"):
            kind = "symbol"
        elif line.startswith("=== context for") and kind != "content":
            kind = "symbol"
        elif line.startswith("# STM topic composite"):
            kind = "composite"
        elif line.startswith("# [+") or line.startswith("# [truncated"):
            out["trailer"] += n
            continue
        out[kind] += n
        if kind == "composite" and line.strip() == "```" and out["composite"] > 60:
            kind = "after_composite"          # the curator-status line(s) of the same command
    return out


def main(argv: "list[str]") -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    b_start, c_start = "2026-11-14T01:00", "2026-11-15T04:30"
    since = None
    for i, a in enumerate(argv):
        if a == "--b-start":
            b_start = argv[i + 1]
        if a == "--c-start":
            c_start = argv[i + 1]
        if a == "--since":
            since = argv[i + 1]

    def regime(ts: str) -> str:
        return "A" if ts < b_start else ("B" if ts < c_start else "C")

    seen: set = set()
    prompts: "list[dict]" = []
    unreadable = 0
    files = sorted(glob.glob(os.path.join(argv[1], "*.jsonl")), key=os.path.getmtime)
    for p in files:
        sid = os.path.basename(p)[:8]
        cur = None
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    unreadable += 1
                    continue
                u = r.get("uuid")
                if u:
                    if u in seen:            # a resumed session's file repeats earlier records
                        continue
                    seen.add(u)
                t = r.get("type")
                if t == "attachment":
                    a = r.get("attachment") or {}
                    if a.get("type") != "hook_success" or a.get("hookEvent") != "UserPromptSubmit":
                        continue
                    cmd = a.get("command") or ""
                    so, co = a.get("stdout") or "", a.get("content") or ""
                    tid = a.get("toolUseID")
                    if cur is None or cur["tid"] != tid:
                        cur = {"tid": tid, "sid": sid, "ts": r.get("timestamp") or "",
                               "disc": 0, "agent": 0, "scan": None, "recall": None}
                        prompts.append(cur)
                    rec = {"bytes": len(so.encode("utf-8")), "previewed": len(co) < len(so) - 10}
                    if "scan-prompt" in cmd:
                        rec["omit"] = bool(OMIT.search(so))
                        rec["kinds"] = block_bytes(so)
                        cur["scan"] = rec
                    elif "memory recall" in cmd:
                        cur["recall"] = rec
                elif t == "assistant" and not r.get("isSidechain") and cur is not None:
                    for x in (r.get("message") or {}).get("content") or []:
                        if not (isinstance(x, dict) and x.get("type") == "tool_use"):
                            continue
                        nm = x.get("name") or ""
                        if nm in ("Grep", "Glob", "Read") or nm.startswith("mcp__refmatrix__"):
                            cur["disc"] += 1
                        elif nm == "Bash" and DISC_BASH.search(
                                (x.get("input") or {}).get("command") or ""):
                            cur["disc"] += 1
                        elif nm in ("Agent", "Task"):
                            cur["agent"] += 1

    print(f"transcripts={len(files)} unreadable_lines={unreadable} "
          f"hook_fired_prompts={len(prompts)} sessions={len({p['sid'] for p in prompts})}")
    if since is not None:
        recent = collections.Counter(p["sid"] for p in prompts if p["ts"] >= since)
        print(f"since {since}: prompts={sum(recent.values())} sessions={len(recent)} "
              f"per_session={sorted(recent.values())}")
    by = collections.defaultdict(list)
    for p in prompts:
        by[regime(p["ts"])].append(p)
    for k in sorted(by):
        v = by[k]
        d = sorted(p["disc"] for p in v)
        per_sess = collections.Counter(p["sid"] for p in v)
        scan = [p["scan"] for p in v if p["scan"]]
        rec = [p["recall"] for p in v if p["recall"]]
        kinds: "collections.Counter" = collections.Counter()
        for s in scan:
            kinds.update(s["kinds"])
        tot = sum(kinds.values()) or 1
        print(f"regime {k}: prompts={len(v)} sessions={len(per_sess)} "
              f"per_session={sorted(per_sess.values())}")
        print(f"  discovery/prompt: mean={st.mean(d):.2f} sd={st.pstdev(d):.2f} "
              f"median={st.median(d)} zero={sum(1 for x in d if x == 0)} "
              f"p90={d[int(0.9 * len(d))]} max={d[-1]} | agent_dispatch/prompt="
              f"{st.mean([p['agent'] for p in v]):.2f}")
        means = [round(st.mean([p['disc'] for p in v if p['sid'] == s]), 2)
                 for s in per_sess if per_sess[s] >= 10]
        print(f"  per-session mean discovery/prompt (sessions with >=10 prompts): {means}")
        print(f"  scan outputs={len(scan)} omit_trailer={sum(1 for s in scan if s['omit'])} "
              f"previewed={sum(1 for s in scan if s['previewed'])} "
              f"with_composite={sum(1 for s in scan if s['kinds'].get('composite'))}")
        print("  scan stdout bytes by header split: "
              + " ".join(f"{n}={kinds[n]} ({100 * kinds[n] / tot:.1f}%)"
                         for n in ("content", "symbol", "composite", "after_composite",
                                   "trailer", "other")))
        print(f"  recall outputs={len(rec)} previewed={sum(1 for s in rec if s['previewed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
