#!/usr/bin/env python3
"""Census of dated ledger bullets for task 31.3 (plan-31): how many end with exactly one {#id}.

Why (2026-11-15): the 31.3 spec's rule ("every dated bullet in a ch-bsd ledger ends with exactly
one anchor", the bug-242 guard) had to be counted against the real ledgers before it was written,
and the count found 15 whole bullets that never had an id. This script is that count. It is also
the PRECONDITION CHECK of the task's GREEN: after the lead's plan-31 D7 edit it must print
`none=0` for the memory dir's ledgers. It is not the checker the task builds (that one selects
ledger docs by frontmatter and reuses the linter's anchor regex); it selects nothing and judges
every file it is given.

Usage:  python3 -I ledger_census.py <file-or-dir> [...]
Prints per file: dated bullets, ok, none, multi, not_at_end, other (undated) bullets, and the
line numbers of the bad ones. Read-only.
"""
import re, sys, glob, os
BUL = re.compile(r"^- (20\d\d-\d\d-\d\d)\b")
ANY_BUL = re.compile(r"^- ")
ANCH = re.compile(r"\{#([A-Za-z0-9_.\-]+)\}")
END = re.compile(r"\{#([A-Za-z0-9_.\-]+)\}\s*$")
def census(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    blocks = []; cur = None; fence = False
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"): fence = not fence
        if fence: 
            if cur: cur[2].append(ln)
            continue
        if BUL.match(ln):
            cur = [i, ln, [ln]]; blocks.append(cur)
        elif cur is not None and (ln.startswith("  ") or ln.startswith("\t")) and ln.strip():
            cur[2].append(ln)
        else:
            cur = None
    ok = none = multi = notend = 0; bad = []
    for start, first, body in blocks:
        text = "\n".join(body)
        n = len(ANCH.findall(text))
        endok = bool(END.search(text))
        if n == 1 and endok: ok += 1
        elif n == 0: none += 1; bad.append((start, "none"))
        elif n > 1: multi += 1; bad.append((start, f"multi{n}"))
        else: notend += 1; bad.append((start, "not-at-end"))
    other_bul = sum(1 for ln in lines if ANY_BUL.match(ln) and not BUL.match(ln))
    return len(blocks), ok, none, multi, notend, other_bul, bad
tot = [0]*6
for p in sys.argv[1:]:
    for f in (sorted(glob.glob(os.path.join(p, "*.md"))) if os.path.isdir(p) else [p]):
        n, ok, none, multi, notend, other, bad = census(f)
        for i, v in enumerate((n, ok, none, multi, notend, other)): tot[i] += v
        print(f"{os.path.basename(f)}: dated={n} ok={ok} none={none} multi={multi} not_at_end={notend} other_bullets={other} bad={bad[:8]}")
print("TOTAL dated=%d ok=%d none=%d multi=%d not_at_end=%d other=%d" % tuple(tot))
