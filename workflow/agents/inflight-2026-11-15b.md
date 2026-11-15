---
gmd: "0.1"
id: agent-briefs-inflight-2026-11-15b
title: "Agents in flight at the 2026-11-15 evening save-state (session 070141d0)"
tags: [agent-brief, in-flight, handoff]
metadata:
  node_type: brief
  created: 2026-11-15
---

# Agents in flight at the 2026-11-15 evening save-state {#root}

State lives in [[plan-of-plans]] (`#queue`, `#ledgers`); this file only says who was mid-task
and where, so a fresh lead can collect or re-dispatch. Every test run on the machine goes
through `/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock` (one test process at a
time). If an agent is gone, re-dispatch the same agent type from its section, adding "resume
from <branch>@<tip>; inspect the clone's uncommitted work first". Agents can miss the end of
their own background run: read their logs yourself after the expected duration.

rel: supersedes -> [[agent-briefs-inflight-2026-11-15]]
rel: depends-on -> [[plan-of-plans#queue]]

## Stage 2 of 29.4 (plan-29), ships in R1 {#stage-2}

| agent | type | clone | branch | last tip | doing | next |
|---|---|---|---|---|---|---|
| green-t02 | ch-implementer | `/Volumes/littlebig/refmatrix-t02-green` | `task-t0.2-reaper-roots-bug253` | `1121b4e` (bug-267 fix L151 + resource-tracker exemption L154; red-t02's `efa0813` merged at `b4ba751`) | verify re-runs queued on the lane: `green-l151-verify-own.log`, then `green-l151-verify-tierb.log` | ch-bsd review + mutations (incl. R4.6b), then the lead merges |
| red-t03 | ch-test-engineer | `/Volumes/littlebig/refmatrix-t03` | `task-t0.3-load-flakes-wallclock` | `d81ed07` | writing **bug-269's RED** (L161): an artificially slow warm-up; the stop completes within a bound independent of warm-up time | green-t03 merges it |
| green-t03 | ch-implementer | `/Volumes/littlebig/refmatrix-t03-green` | same | `83c2711` (all but bug-228) | bug-228 readiness wait on the real budget + census third form (L159); merge red-t03 `cdc9c88`/`d81ed07` (L160); then bug-269's fix (L161) | ch-bsd review, then merge |
{#stage-2-table}

T0.1' (`a0c7560`) and T0.8 (`e997154`) are merged. After stage 2: stage 3 (T0.4 → T0.5),
stage 4 (29.4a runner), stage 5 (T0.7 + 29.4d), then R1's major release gate. {#stage-2-next}

## Plan-31 task 31.5 release A (ships in R1) {#t315}

| agent | type | clone | branch | last tip | doing | next |
|---|---|---|---|---|---|---|
| red-315 | ch-test-engineer | `/Volumes/littlebig/refmatrix-315` | `task-31.5-s0-capture` | `30ac2f6` (L155 AC-0.8 widening) | committing L156 (store double for 3 `test_composite` nodes), proven on `c3e04d3`; re-proving AC-0.8 there | green-315 merges both |
| green-315 | ch-implementer | `/Volumes/littlebig/refmatrix-315-green` | same | `c3e04d3` (capture, both modes, default `names` L158; R2.0; bug-256; bug-268) | waiting for red-315's commit | merge, re-run the 3 files, then ch-bsd review |
{#t315-table}

Plan-31 is approved (all six specs; L140, L149). 31.3 and 31.4 RED start after T0.2 merges
(both edit `scripts/lint-gmd.sh`); then 31.1 → 31.6 (linter order 31.4 → 31.1 → 31.6); 31.2
after 29.5. {#t315-next}

## Held for a ch-bsd confirm-lite before their RED (Q41 = a) {#held}

- bug-218: `spec-t56-fresh` `b2e2451` in `/Volumes/littlebig/refmatrix-t56-fresh` (L137; RED
  notes [[agent-brief-bug218-red-notes]]).
- T2 (26.5-26.9, plan-27): `spec-t2-fresh` `3a4d430` in `/Volumes/littlebig/refmatrix-t2-fresh`
  (L138; RED notes [[agent-brief-t2-red-notes]]).
{#held-body}
