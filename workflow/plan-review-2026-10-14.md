---
gmd: "0.1"
id: plan-review-2026-10-14
title: "Wave 0 spec-review decisions, 2026-10-14"
tags: [plan-review, decisions, wave-0, spec-review]
metadata:
  node_type: review
  created: 2026-10-14
---

# Wave 0 spec-review decisions, 2026-10-14 {#root}

The user, 2026-10-14: "lets review each bsd report and its questions. if it makes sense to cluster
by topic, feel free." The six ch-bsd spec reviews of Wave 0 (plans 16 r5, 17, 19, 21, 22, 23) are
walked topic by topic; every decision is written here the moment it is taken, and the spec
revisions are driven from this file.

rel: amends -> [[plan-review-2026-10-07]]
rel: derives-from -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan19-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan22-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81]]
rel: related-to -> [[exploration-session-phased-context]]

## Topics {#topics}

1. Test isolation (all reports).
2. Write harness and concurrency (plan-23; 17 s-1/s-7; 22 s-1/s-2; Option A).
3. Lance nightly maintenance (plan-17).
4. Recall-event schema (plan-21, shared with 19).
5. Memory budget, recall, phased context and the topic cache (plan-19).
6. Audited removal and repair, with plan-16's 16.6 (plan-22, plan-16 r5).
7. Grep shim (plan-16 r5, remaining items).

## Topic 1: test isolation {#t1}

Findings: 17 #b-5, 19 #b-7, 21 #s-7, 22 #b-8 (bug-101), 23 #s-7; bug-088's recorder cannot see
spawned subprocesses.

| id | decision | by |
|---|---|---|
| d1a | A shared test sandbox is the FIRST build of Wave 1, ahead of the rest of plan-23. | user, 2026-10-14 |
| d1b | It is a new task **23.0** at the front of plan-23 (not a separate plan). | user, 2026-10-14 |
| d1c | The 1,655 pytest entities in the live global store and the 235 fixture rows in the live `query.log` (bug-101) are removed by plan-22 task **22.3**'s audited apply, not by a one-off forget. | user, 2026-10-14 |

Scope of 23.0 (proposal accepted with d1a): `$HOME`, global root, registry path and LaunchAgents
dir redirected to a tmp dir BEFORE `refmatrix` is imported; store roots injected so discovery
cannot find live stores; spawned `rmx` children refuse any socket outside the tmp dir (bug-088's
refuse stage); a conftest guard fails any test that touches `~/.refmatrix` or a registered live
store. {#t1-scope}

## Topic 2: write harness and concurrency {#t2}

Findings: 23 #b-1..b-3, #s-1..s-7, #m-1..m-3; 17 #s-1, #s-7; 22 #s-1, #s-2.

| id | decision | by |
|---|---|---|
| d2a | Exactly-once drain: the drain offset is committed in the SAME DuckDB transaction as the batch (option 1), not an event-id dedupe table. Answered "2a - opt"; read as option 1, the recommendation — to be confirmed. | user, 2026-10-14 |
| d2b | Plan-23 stays first in Wave 1 (after 23.0), with the `bind(batch)` seam; Option A is not folded in. Plan-17 takes no per-dataset Lance lock now; it goes through `bind`, and a revisit is recorded for when Option A lands. | user, 2026-10-14 |
| d2c | bug-093's between-file yield becomes task **23.3** (after 23.1): a transaction boundary inside `_sync_paths`, the same `bind` seam and write-count tests. | user, 2026-10-14 |
| d2d | bug-099 (learn queue unlinks `*.draining` before apply) stays logged; fixed by 23.1. | user, 2026-10-14 |

Spec fixes taken without a decision (proposed, not objected to): per-batch `bind` inside the hold
with a two-partition competitor AC (#b-1); a write-count recorder and a finalize step (#b-3); one
event per hold by default with drain budget, shutdown stop, error policy and requeue (#s-1); a
required `merge_fn` (#s-2); 17.1 and 22's apply use `bind` + the recorder but not the lossy queue
(17 #s-1, 22 #s-1/#s-2); real `_FairLock` in tests, every-batch-released AC, recorder required,
23.2 before 23.1 (#s-4, #s-5); overflow reaches `rmx learn status` through a daemon op (#s-6);
the MEH items. {#t2-fixes}
