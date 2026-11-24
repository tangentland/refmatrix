---
gmd: "0.1"
id: agent-brief-bsd-reprobe
title: "ch-bsd confirm-lite brief: re-probe the 9 unconfirmed SKETCHY fixes and the 9 GATE rows under the consequence rubric (L213)"
tags: [agent-brief, ch-bsd, confirm-lite, consequence-package, gate]
metadata:
  node_type: brief
  created: 2026-11-24
---

# bsd-reprobe: the F8 census, re-checked live {#root}

rel: implements -> [[refmatrix/ch-bsd-assessment-2026-11-23#order]]

You are ch-bsd on a **confirm-lite**: one pass, no new round. Your definition's severity table was
just replaced by the consequence rubric (`.claude/agents/ch-bsd.md` `#severity-levels`, commit
`d0598dc9`); rate everything by it, including the new **GATE** level. The findings come from
[[refmatrix/ch-bsd-assessment-2026-11-23#f8-tables]]. {#role}

## Where {#where}

- Clone: `/Volumes/littlebig/refmatrix-bsd-reprobe`, branch `bsd-reprobe-2026-11-24` at master
  `c7550ad5` (deployed build 0.85.1 + docs). Probe on throwaway stores under a short `mkdtemp()`
  root, on this clone, and through `scripts/lane-local.sh <clone> <sha> <log> <files…>`.
- Read-only against every live store (lookups: `/Users/tholley/claude_tools/refmatrix/scripts/rmx-master`
  or the read-only refmatrix MCP tools). Never `find /`.
- Mutations: one at a time on a scratch commit or a detached checkout in the clone, restored in
  its own command, `__pycache__` cleared after each; a mutation must FAIL a test, not hang.

## Part A — re-run each finding's own probe against master (cah s-3 FIRST) {#part-a}

Read each finding in its report under `workflow/bullshit/`, re-run its probe (or the closest
honest equivalent at master), and say: **closed** (with the evidence), or **still live** (rated by
the new rubric, with the consequence that decides it).

1. `2026-11-24-0700-cah-confirm-4784cdd5.md` s-3: MCP `rmx_memory_recall(recent=true, pack=true)`
   raised `VerbArgsError` — call it through the verb AND the MCP tool on a sandbox store.
2. `2026-11-15-2009-t02-r1-1121b4e.md` S3 (stop drain outside `_StopDeadline`; conftest 30 s
   slack) and S4 (`register_spawn` has no adopter).
3. `2026-11-15-2203-315-r1-51bbdfb.md` S1 (capture flips the scan-prompt / recall exit to 1 with
   a traceback, hidden by `2>/dev/null || true`), S2 (an unchanged composite re-sent), S4
   (bug-268 fixed on one of five readers).
4. `2026-11-24-0209-294a-r1-1bb14a5b.md` s-1 (the tier tests' own file classed `devtree`, never
   run in a clone or lane).
5. `2026-11-15-0340-scanorder-r1-ca22b79.md` S2 (tier 1 empty on the real hook run) and S3
   (composite marked sent when dropped) — no ruling was located for these.

## Part B — the 9 GATE rows: does the mutation still survive at master? {#part-b}

t08 r1 S1, S2 (`2026-11-15-1310-t08-r1-e314b19.md`); t02 r1 S1, S2; t03 r1 S1, S2, S3
(`2026-11-15-2202-t03-r1-041e3ab.md`); 315 r1 S3; t05 r1 s-1 (`2026-11-19-1145-t05-r1-61b0666c.md`).
For each: apply the mutation the finding describes (or the smallest one that removes the
protected behaviour) at master and run the relevant tests on the lane. Report **killed** (the
test and its E line) or **survives** (GATE: name the test that should exist).

## Report (as text, to the lead; the lead persists it) {#report}

One table per part: finding, probe/mutation, result, rating by the new rubric with the deciding
consequence, evidence (log name, E line or output). Then your verdict line in the new format.
