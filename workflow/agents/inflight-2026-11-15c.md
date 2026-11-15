---
gmd: "0.1"
id: agent-briefs-inflight-2026-11-15c
title: "Agents in flight at the 2026-11-15 afternoon save-state (session 817dd0e8)"
tags: [agent-brief, in-flight, handoff]
metadata:
  node_type: brief
  created: 2026-11-15
---

# Agents in flight at the 2026-11-15 afternoon save-state {#root}

State lives in [[plan-of-plans]] (`#queue`, `#ledgers`). This file says who was mid-task and
where. Test runs now go to isolated slots (`scripts/lane-mini.sh`, `scripts/lane-local.sh`; CLAUDE.md
`#test-discipline` rule 9). If an agent is gone, re-dispatch the same type from its row, adding
"resume from <branch>@<tip>; inspect the clone first".

rel: supersedes -> [[agent-briefs-inflight-2026-11-15b]]
rel: depends-on -> [[plan-of-plans#queue]]

## Reviews running (lean process: one ch-bsd pass) {#reviews}

| agent | type | review clone | range | doing | next |
|---|---|---|---|---|---|
| bsd-t03 | ch-bsd | `/Volumes/littlebig/refmatrix-bsdt03-r1` | `c4b44d0..041e3ab` (`task-t0.3-load-flakes-wallclock`, source clone `refmatrix-t03-green`) | one pass on T0.3 + 29.4c; mutations M1-M6 on the bug-269 src change ran (M6 survived, 43 passed); early word: bug-272's race is real (up to 45 s with a mute hub; the embed role too) | the lead rules; persist the report; fold if BULLSHIT; merge (add `test_bug269_stop_during_warmup.py` to `tests/round_named_allow.json` at the merge: T0.3 predates rule 1) |
| bsd-315 | ch-bsd | `/Volumes/littlebig/refmatrix-bsd315-r1` | merge-base..`51bbdfb` (`task-31.5-s0-capture`, source clone `refmatrix-315-green`) | one pass on 31.5 release A, lane runs on the mini | the lead rules; add bug-268's registry row at the merge |
{#reviews-table}

## Done, idle, nothing owed {#idle}

green-t02 and red-t02 (T0.2 merged `b0d5eabf`), green-t03 (T0.3 at `041e3ab`, waits on bsd-t03),
red-315 and green-315 (31.5 at `51bbdfb`, waits on bsd-315), spec-t09 (T0.9 spec merged),
test-audit (merged as a measurement). {#idle-body}

## Isolated agents (L174, L175) {#isolated}

No isolated agent is running. The smoke test of `scripts/agent-isolated.sh` / `agent-say.sh` /
`agent-peek.sh` (start, addendum, commit, REPORT.md) is owed: the first run stopped at the
folder-trust prompt (fixed in the launcher, not yet re-run). The pilot (L173) ran headless and
merged as `12b534c4`. {#isolated-body}
