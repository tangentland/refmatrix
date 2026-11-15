---
gmd: "0.1"
id: agent-briefs-inflight-2026-11-15d
title: "Agents in flight, 2026-11-15 evening (session 8adeba5c): T0.3 and 31.5 folds"
tags: [agent-brief, in-flight, handoff]
metadata:
  node_type: brief
  created: 2026-11-15
---

# Agents in flight, 2026-11-15 evening {#root}

State lives in [[plan-of-plans]] (rulings L176-L178, Q50 open). Reviews are persisted:
[[bsd-t03-r1-041e3ab]], [[bsd-315-r1-51bbdfb]]. If an agent is gone, re-dispatch the same type from
its row with "resume from <branch>@<tip>; inspect the clone first".

rel: supersedes -> [[agent-briefs-inflight-2026-11-15c]]
rel: depends-on -> [[plan-of-plans#rulings]]

## Folds running {#folds}

| agent | type | clone | branch / base | doing | next |
|---|---|---|---|---|---|
| red-t03 | ch-test-engineer | `/Volumes/littlebig/refmatrix-t03` | `task-t0.3-load-flakes-wallclock` from `041e3ab` | L177 RED: bug-278 shared-close case, bug-269 node moved to `test_daemon_shutdown.py` with S1/S2 log assertions (proved by M3-M6), bug-272 race test if deterministic, census must-fail ×5, mechanism test patches only `is_alive`, `test_t03_*` allowlisted | green-t03 builds bug-278 retire, the bug-272 recheck, the M4 warning and summary fixes; then bsd-t03 confirm-lite (probe as a test + M3-M6); merge |
| red-315 | ch-test-engineer | `/Volumes/littlebig/refmatrix-315` | `task-31.5-s0-capture` from `51bbdfb` | L178 RED: bug-276 (surrogate, 0o300 dir, pack path), bug-277 (P2), S3 fixture + M2-1a, S4 four readers, X-1/X-2/X-3 nodes, M3 denominator | green-315 folds src; red-315 re-runs the survivors + S1/S2/S4 mutations; the lead reads the diff and merges (no second bsd round) |
{#folds-table}

## Idle, nothing owed {#idle}

bsd-t03 (confirm-lite pending GREEN), bsd-315 (done), green-t03, green-315 (wait on their RED),
every other teammate. Isolated slot 2 smoke passed (L176); no isolated agent running. {#idle-body}
