---
gmd: "0.1"
id: plan-23-bounded-write-harness
title: "Plan 23: a test sandbox, then one bind/recorder core (durable drain, non-consuming tail, bounded steps) with one tick registry — built once, used by every writer"
tags: [plan, daemon, queue, lock, harness, sandbox, partition, bug-085, bug-093, bug-098, bug-099]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
  updated: 2026-10-15
---

# Plan 23: the bounded-write harness {#root}

**Date:** 2026-10-07, revised 2026-10-14.
**Status:** Drafting (revision round 9 after the b84fd8d diff check: 23.5's snapshot flushes
dirty bitmap fragments, bug-112 FIXED on `master` gates 23.5, 23.5 stands alone of plan-18;
[[#rev-round-9]]. Round 8 after the 23ad703 re-review and d9bn, which settles
23.5's read path; [[#rev-round-8]]. Round 7 after the 331b414 re-review and d9az, which adds task
23.5; [[#rev-round-7]]. Round 6 after the 0e77da3 re-review and d9ag/d9ao/d9ap;
[[#rev-round-6]]. Round 5 after the 878647c re-review, d9y and the writer-handle
idea: [[#rev-round-5]]. Round 3: [[#rev-round-3]]. Round 2: [[#rev-round-2]]).
Task specs 23.0-23.5 are written (23.5 had its first review in round 8 and is revised under
d9bn).
This is Wave 1's FIRST build: plans 16 (16.6's Wave 1 slice), 17, 19 and 22 consume it, and every
Wave 1 test runs in 23.0's sandbox.
**Origin:** the plan review's C5, applied by the user on 2026-10-07; revised from the Wave 0
decision log.

rel: derives-from -> [[plan-review-2026-10-07]]
rel: derives-from -> [[plan-review-2026-10-14#t1]]
rel: derives-from -> [[plan-review-2026-10-14#t2]]
rel: derives-from -> [[plan-review-2026-10-14#t8]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2]]
rel: derives-from -> [[project_daemon_wedge_per_entity_lance_delete]]
rel: related-to -> [[project_grep_learn_wall_and_queue]]
rel: related-to -> [[project_bug098_writer_partition_race]]
rel: related-to -> [[exploration-storage-concurrency-redesign]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648]]
rel: derives-from -> [[plan-review-2026-10-14#t9-approvals]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703]]

## Why {#why}

Every wedge so far had one of two shapes: many small writes inside one hold of `_store_lock`, or
one long hold.
- bug-085: one Lance delete per entity.
- bug-093: one upsert per concept, and one watch flush holding the lock across all its files.
- r9 #s-1: model calls under the lock.

And every yield added to cure them has to keep the writer's partition binding, or it re-creates
bug-098 (a writer resuming into another op's partition).

Four specs each re-derived the cure: the 0.72.3 `learn_queue`, 16.6 R4's marks, 19.2's usage
events, 17.1's per-dataset holds. Built once, every writer uses one tested mechanism: a `bind` seam
that takes the lock and the partition together per batch, one transaction per hold with its
offset inside it, a recorder that counts holds AND writes, and one tick registry. The binding is
every piece of state keyed by the partition: the id AND the fragment cache (bug-105, d9a), the
guards that decide whether to flush, and every op that renames or merges a partition (nb23-r3-1).
A rolled-back batch leaves nothing behind: no cache bit, no dropped earlier bit, no `facts.log`
event (ns23-r3-1, ns23-r3-2). The tests that
prove it run in a sandbox that cannot reach a live store (bug-088, bug-101). {#why-body}

## Tasks {#tasks}

Order ([[plan-review-2026-10-14#t8-wave1]]): **23.0 ∥ 23.4 → 23.2 → 23.1 (+ tick registry) →
23.3 ∥ 23.5.** 23.5 (d9az, round 7) also waited for bug-115/116 (0.78.2) merged to `master`;
that is satisfied (`607d759`, `1c86d9c` are ancestors of `master` `b381b6d`, round 8). It
also waits for **bug-112 FIXED and reachable from `master`** (round 9, nb23-r9-2): OPEN; the
fix is on branch `bugs-112-113-118` (`7c38c46`, `0fed0d5`), not yet on `master`.

| task | what | acceptance (summary) |
|---|---|---|
| [[task-23.0-test-sandbox]] | `$HOME`, `RMX_HOME`, registry and LaunchAgents redirected before `refmatrix` is imported; store roots injected; an audit-hook guard that REFUSES any touch of a live store, in the suite and in every spawned child | canaries prove every root resolver lands in the sandbox; live paths are refused in-process and in children (mutations fail); a full run adds no tagged, pytest-path or fixture-shaped row to any live log (content, not size) |
| [[task-23.4-option-a-measurement]] | Option A measurement #4: one writer thread vs N per-op cursor writers on a cliquet copy, a pinned 20,000-event workload including `bitmap_fragments` upserts, drained to completion with in-place retry; go/no-go ranges CONFIRMED (d9l), procedure corrected (d9m, d9y, and d9ap: dangling `entity_links` rows counted, not hashed; new pin; round 7: the `dead-linkage` sub-class added and the cliquedb count corrected, pin d9ba) | the verdict is mechanical from the ranges; integrity compared by NAME; an error at N=1 is INVALID, not NO-GO; the detector proven to fire AND a correct N=2 run proven to pass; runs ordered after the confirmation; the live store untouched by the audit guard |
| [[task-23.2-lock-hold-fixture]] | `lock_free_during(lock)`, a `HoldRecorder` on the real `_FairLock` that counts holds, DuckDB statements and Lance versions, markers that fail on zero holds | reverting r8 #s-2 / r9 #s-1 fails; re-introducing bug-085's and bug-093's per-row writes fails; no test keeps its own probe |
| [[task-23.1-queue-and-drain]] | starts only after the bug-105 hotfix is MERGED TO `master`; `bounded.py`: `bind(partition_name)` (lookup-only; the merged hotfix's per-binding cache, all-binding guards, rename/merge flush, merge's fragment work under the writer lock, live-concept predicate adopted as the contract; a held-writer-lock check ADOPTED (d9ag), wired through one writer-Store installer) + one `batch_transaction` per hold (pre-flush before `BEGIN`; fragments and offset inside it; `facts.log` events after `COMMIT`) under three front-ends (`drain(queue)`, `tail(log)`, `bounded_steps(items)`); stop paths, error policy, finalize, per-hold `hold_s`; the daemon tick registry with one budget; `queue_status` / `queue_redrive`; learn re-based with insert-if-absent evidence | two-partition competitor AC on rows AND fragment rows; AC-3d (the merged hotfix suite, five files, as cases (ii)-(ix), 23.1's tick and decision-search cases); the writer-lock check survives every writer reopen (AC-20); a rolled-back batch leaves no phantom fragment bit; lost post-commit events re-derived at the next boot; exactly-once under five injected faults; learn crash-replay counts evidence rows; bug-099 RED→GREEN; finalize once; tail never mutates its file; overflow printed by `rmx learn status` |
| [[task-23.3-sync-between-file-yield]] | `_sync_paths` on `bounded_steps`: one transaction per step, the lock released between steps, the partition bound per step, each file stamped in its LAST step; one sync at a time per store (`_sync_mutex`), insert-if-absent semantic evidence; bug-093's op-start log line | competitor wins between files; two concurrent syncs equal one; never released inside a transaction; write counts flat in concept count; a crash, cancel or budget stop before the semantic steps loses nothing; same graph as HEAD |
| [[task-23.5-read-path-and-holder-bounds]] | d9az + d9bn: the non-harness `_store_lock` holders. Every cli-reachable read (the 11 cli READ ops that take the lock today AND the 10 bare `_read_with_fallback` sites) goes through ONE helper, `_cli_read`, that always bounds the writer fallback and answers "writer busy" naming the holder; an op stays on the shared mirror only if its measured p99 is under 50 ms, else a private reader; `snapshot`, `partition_add` and `partition_rename` move to the bg pool, so `replica_audit` is the one cli op that needs the writer and waits at most `min(deadline, RMX_CLI_WRITER_WAIT_S)`; `stats(include_health)` runs its health off the writer connection; `context`'s learn write goes to the learn queue; the compaction reuses the snapshot's hold (L0 recorded inside it, the snapshot hard-linked) and dumps off the lock before one short tail hold; every hold over an alarm names its holder from the existing `_inflight_ops` registry; the wait is clamped under the heartbeat's stale window | reads answer and the heartbeat stays fresh through a 10 s writer hold (`_op_stats` back on the lock FAILS; an absent-partition `memory_search` answers); a stalled private read does not park mirror reads; an AST rule that follows helpers from every `CLI_OPS` handler to a fixpoint; compaction loses no event written during the dump; the clamp; a census of every holder's hold length; a `link` is visible to `query` (a bitmap read) within one debounce because the snapshot flushes dirty fragments; overlapping private readers see the newest snapshot (bug-112's fix; round 9) |

{#tasks-body}

## The one core, three front-ends {#core}

| front-end | input | durability | consumers |
|---|---|---|---|
| `drain(BoundedQueue)` | a JSONL queue appended without a lock; required `key_fn` + `merge_fn`; overflow counted | segments kept until their last offset commits; offset in the batch transaction | learn (23.1 R9), 16.6 R4 marks |
| `tail(TailLog)` | an append-only log shared with other readers; never rotated, unlinked or rewritten | offset in the batch transaction; reads to the last complete newline | 19.2's fold of `recall-events.jsonl` (d4a) |
| `bounded_steps(items)` | an in-memory list | none claimed; the consumer recovers (manifest, mtime gate) | 17.1 datasets, 22.2 apply, 23.3 sync |

All three run each batch as `with bind(partition_name): with handle.batch_transaction(): apply;
flush fragments; write offset`, through the same stop paths, error policy, hold alarm and
`finalize`, and are observed by 23.2's recorder. Under Option A, `bind` becomes a per-op cursor
handle and no consumer changes. {#core-body}

## Consumers {#consumers}

| consumer | uses | note |
|---|---|---|
| learn (`learn_queue`) | `drain`, `scope="segment"`, `idempotent=True` checked by 23.1 AC-16, `batch=1` | re-based in 23.1; bug-099 fixed (d2d); evidence insert-if-absent (bug-106) |
| 16.6 Wave 1 slice (marks) | `drain`, `bind`, recorder | its overflow is counted and printed; 16.6 reads `stale_seen` as a lower bound |
| 19.2 (usage counters) | `tail` over `recall-events.jsonl`, SUM `merge_fn`, tick registrant | d4a; its `memory_usage` `replica_merge` rule is 19.2 R6 |
| 17.1 (per-dataset maintenance) | `bounded_steps` (one dataset per step, `batch=1`), `bind(partition_name)`, `RunResult.hold_s`, recorder; no queue, no per-dataset Lance lock | d2b; revisit triggered by 23.4's verdict. 17.2's hub `maintenance_steps` is NOT 23.1's daemon `tick_registry` |
| 22.2 (repair / removal apply) | `bounded_steps`, `bind`, recorder, `finalize` (one Lance delete per kind) | no lossy queue (#t2-fixes, 22 #s-1/#s-2) |
| 23.3 (bug-093 between-file yield) | `bounded_steps`, `bind`, recorder | d2c |
| plan-21 | 21.1 PRODUCES `recall-events.jsonl` lock-free and does not depend on plan-23's code (d4a); plan-21's tests need only 23.0 | the consumer edge 23 #s-3 asked for |

{#consumers-body}

## Dependencies {#dependencies}

- 23.0 and 23.4: none; they run in parallel.
- 23.2 → 23.0. 23.1 → 23.2, 23.0, and the bug-105 hotfix MERGED TO `master` (not a sha list;
  nb23-r4-1). 23.3 → 23.1. 23.5 → 23.1, 23.2, 23.0, and bug-115/116 (0.78.2) MERGED TO `master`
  (round 7, d9az; satisfied at `23ad703`, round 8), and **bug-112 FIXED and reachable from
  `master`** (round 9, nb23-r9-2; the same gate as 18.3's header; OPEN at `b84fd8d`: the fix
  `backend.open_duckdb` is on branch `bugs-112-113-118`, `7c38c46` + `0fed0d5`). 23.5 does NOT
  depend on plan-18 (Wave 4; ns23-r9-1): its obligations on plan-18's shared catalog-hold
  helper are a hand-off list, [[task-23.5-read-path-and-holder-bounds#cross-plan-18]].
- Downstream (from [[plan-review-2026-10-14#t8-wave1]]): after 23.1, 16.6's Wave 1 slice → 22.1a →
  22.2 → 22.5 → 22.3; 17.1 → 17.2; 19.0, 19.1, 19.2. 21.1 needs only 23.0.
- 23.1 is NOT gated on 23.4 (decision-log #s-2). 23.4's verdict triggers the d2b revisit.

rel: depends-on -> [[plan-review-2026-10-14#t8-wave1]]

## Scope added by d9az (round 7) {#scope-d9az}

The user's decision d9az ([[plan-review-2026-10-14#t12-approvals]]): plan-23 OWNS the
non-harness `_store_lock` holders, `_op_stats` and the other lock-taking cli-pool reads and the
facts.log compaction tick, and the heartbeat's coupling to the cli pool. Both 2026-10-15
incidents went through that coupling ([[bsd-plan23-17-spec-rereview-r7-331b414#live-evidence]]).
It is task [[task-23.5-read-path-and-holder-bounds]], kept out of 23.1 so the harness, which
blocks 16.6, 17.1, 19.2 and 22.2, does not grow.
- **What 0.78.2 (bug-115/116) already does:** `ping` on the dispatcher thread; a heartbeat on
  every cli-pool completion; a queued cli op dropped, said, once its caller's `deadline_s` has
  passed before a worker reaches it; no re-send after a sent request.
- **What 23.5 still does:** no cli op waits on `_store_lock` without a bound. Every
  cli-reachable read goes through one helper over `_read_with_fallback` (mirror / snapshot) that
  always bounds the writer fallback (d9bn, round 8); `snapshot`, `partition_add` and
  `partition_rename` leave the cli pool, so the one cli op that needs the writer
  (`replica_audit`) waits at most `min(deadline, RMX_CLI_WRITER_WAIT_S)` and answers "writer
  busy" with the holder's name;
  `context`'s learn write goes to the learn queue; the compaction tick's dump runs off the lock
  between the snapshot's hold and one short tail hold; every long hold names its holder. Writer holds themselves are bounded
  where they live: harness writers by 23.1, `sync` and the watch flush by 23.3 (the 80-110 s
  shape of the second incident), plan-17's maintenance steps by 17.1 / 17.3. Once reads stop
  waiting on the writer, a writer hold no longer parks the cli pool, so the heartbeat stops
  depending on it.
- **Correction to the list d9az was given:** `replica_relink` does not take `_store_lock` at
  HEAD (its docstring says so, `daemon.py:5354`), so the lock-taking cli ops are 15, not 16
  ([[task-23.5-read-path-and-holder-bounds#facts]]).

rel: implements -> [[plan-review-2026-10-14#t12-approvals]]

## Open after revision {#open-after-revision}

Round 3 status (2026-10-14): items 1-5 are settled; item 6 is a docs chore outside spec files.
Original text kept as history.

1. **SETTLED (d9l, d9m).** The ranges are CONFIRMED as written (d9l) and the procedure is
   corrected under them (d9m: integrity by name, no 60 s cap, retry in place in key order, a pinned
   20,000-event workload, AC-1 orders runs, a positive control;
   [[task-23.4-option-a-measurement#rev-round-3]]). Nothing about 23.4 waits on the user.
   Original text: **23.4's numbers (OPEN, user).** Amended per ns23-1 and d9d (fragment rows in the workload;
   concurrency decoupled from binding removal; an error at N=1 is INVALID; speedup and conflict
   rate defined) and PROPOSED in [[task-23.4-option-a-measurement#ranges]]: conflict ≤ 1 % and
   speedup ≥ 1.5× → GO; conflict > 5 %, speedup < 1.1×, or any error / integrity mismatch at N > 1
   → NO-GO; otherwise GO-serial. The user confirms or changes them before the run (23.4 AC-1).
2. **SETTLED (nb23-2, bug-106): the premise below was false** (`add_evidence` is a plain INSERT).
   Learn keeps segment coalescing; its evidence write becomes insert-if-absent
   ([[task-23.1-queue-and-drain#r9]] 5) and `idempotent=True` is checked by
   [[task-23.1-queue-and-drain#ac-16]]. Original text: **d2a for learn.** Learn keeps whole-segment coalescing (N greps → M patterns) with one pattern
   per hold, so 23.1 commits the covered PREFIX per hold, and a crash can re-apply an entry whose
   lines lie past it. Its effects stay exactly-once only because learn's writes are idempotent
   (set bits, insert-if-absent evidence); the harness refuses that mode for any non-idempotent
   queue. Confirm this reading of d2a for learn, or require window coalescing (which gives up
   most of learn's coalescing).
3. **SETTLED (nm23-2): `telemetry.is_test_artifact_row` in `telemetry.py`, owned by 21.1 R5;**
   23.0 AC-4 and 19.2's fold import it. Original text: **d8d's shared predicate has no named
   owner.** d8d says every `query.log` /
   `recall-events.jsonl` reader skips pytest-temp-dir rows through ONE shared predicate. 23.1's
   `tail` returns rows raw and leaves filtering to the consumer (19.2 R5 applies it). Where the
   predicate lives (`bounded.py`, `telemetry`, or 21.1) is not decided.
4. **SETTLED (nm23-1): counted, retained forever, re-drivable** ([[task-23.1-queue-and-drain#r6]] 7).
   Original text: **Dead-lettering is new behaviour.** 23.1 R2 replaces "log and skip a failed batch" (learn
   today) with a counted dead-letter file, so no batch is silently lost or blocks the queue. No
   decision names it; confirm, or name the policy you want.
5. **SETTLED (nb23-4): 23.3 takes it** ([[task-23.3-sync-between-file-yield#r7]], AC-8). Original
   text: **bug-093's other open item**, the watch flush's op-start log line, is in the bug row but
   not in d2c; 23.3 does not take it.
6. **SETTLED (nm23-r4-2 item 2): the bug-099 row is NOT stale.** `workflow/bug_registry.md`
   records d2a in the bug-099 row (updated by `a820b22`); this item's round-3 text was wrong.
   The bug-105 row describes the hotfix through its r2 remedies (`27b3653`); its r3 remedies
   (`fc4c8d1`/`fb285cc`) and the merge are the docs step's to record, not a spec's. The bug-105
   and bug-106 rows name plan-23 as spec owner; their owner anchors are
   [[task-23.1-queue-and-drain#r1]] and [[task-23.1-queue-and-drain#r9]]. Original text: the
   bug-099 row still says the decision is "pending with the user"; d2a decided it.
7. **SETTLED (d9ag, round 6): ADOPTED as written**, with round 6's single writer-Store installer
   so the check survives every reopen (ns23-r6-2). Original text: **PROPOSED, needs the user: a held-writer-lock check** in `Store.flush_fragments`,
   `repair_fragments`, `transaction`, `batch_transaction`, `with_partition` and the partition
   rebind sites, reachable from the daemon's `_FairLock` through a new owner-thread field
   ([[task-23.1-queue-and-drain#r1-6-proposed]], AC-20). It is the assert half of the user's
   writer-handle idea; `bind` already is the handle for harness writers.
8. **RETIRED, not open (d9ao, round 6): 23.1 R8 / AC-13** (`replica_merge` merging
   `queue_offsets`). Writer rotation is dropped (`Daemon._refresh_replica_now` is a no-op), so
   nothing produces two diverged slots holding queue tables. The frozen inactive slots that
   `rmx replica audit` found (2026-10-15) are a SEPARATE item under d9ao (a by-name census decides
   recover-after-bug-113 or discard); plan-23 does not own it, and bug-113 is not a 23.1
   dependency ([[task-23.1-queue-and-drain#r8]]).
   - **Cross-plan: SETTLED (d9ay), both plans applied (round 8, nm23-r8-4).** The r7
     re-review's ns-x-r7-1 found that d9ao's reasons apply equally to 19.2 R6 / AC-10 and 16.6
     R1c, which built on `replica_merge`. d9ay retired both: `plan-19` records it as "RETIRED,
     not closed by 23.1 R8 (round 7, d9ay)" and `task-16.6` as "R1c … RETIRED (d9ay)"
     ([[bsd-plan23-17-spec-rereview-r8-23ad703#prior-status]]). Round 7's text ("plans 19 and
     16 own that decision") is superseded.
9. **SETTLED (d9az, round 7): plan-23 owns the non-harness lock holders** ([[#scope-d9az]],
   [[task-23.5-read-path-and-holder-bounds]]). 23.5 is a new spec and needs its own review.
10. **Pin row needed (round 7):** 23.4's procedure text changed (r7 plan-16/22 m-5: the
    `dead-linkage` sub-class and the corrected cliquedb count), so the orchestrator records
    d9ba = the round-7 revision commit as 23.4's new procedure pin
    ([[task-23.4-option-a-measurement#rev-round-7]]).

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| d1a, d1b (sandbox first; task 23.0) | [[#tasks]], [[task-23.0-test-sandbox]] |
| #t1-scope | [[task-23.0-test-sandbox#requirements]] |
| d2a (offset in the batch's transaction) | [[task-23.1-queue-and-drain#r3]], [[#core]] |
| #t8-amendments d2a (fragments, `replica_merge`, retention) | [[task-23.1-queue-and-drain#r7]], [[task-23.1-queue-and-drain#r8]], [[task-23.1-queue-and-drain#r4]] |
| d2b (plan-23 first with `bind`; plan-17 through `bind`; revisit) | [[#core]], [[#consumers]], [[task-23.4-option-a-measurement#ranges]] |
| d2c (task 23.3) | [[task-23.3-sync-between-file-yield]] |
| d2d (bug-099 via 23.1) | [[task-23.1-queue-and-drain#ac-5]] |
| d2e + #t8-amendments d2b/d2e (task 23.4, ∥ 23.0, ranges first, verdict triggers the revisit) | [[task-23.4-option-a-measurement]], [[#dependencies]], [[#open-after-revision]] 1 |
| d4a + #t8-amendments d4a (tail reader; tick registry; one budget; `bounded_steps` vs `drain`; plan-21 as consumer) | [[#core]], [[#consumers]], [[task-23.1-queue-and-drain#r4]], [[task-23.1-queue-and-drain#r6]] |
| #t2-fixes (all clauses) | [[task-23.1-queue-and-drain#rev-2026-10-14]], [[task-23.2-lock-hold-fixture#rev-2026-10-14]] |
| #t8-wave1 (order) | [[#tasks]], [[#dependencies]] |
| 23 #b-1, #b-2, #b-3 | [[task-23.1-queue-and-drain#rev-2026-10-14]], [[task-23.2-lock-hold-fixture#r3]] |
| 23 #s-1, #s-2, #s-3, #s-6 | [[task-23.1-queue-and-drain#rev-2026-10-14]]; #s-3 also [[#consumers]] |
| 23 #s-4, #s-5 | [[task-23.2-lock-hold-fixture#rev-2026-10-14]], [[task-23.1-queue-and-drain#ac-1]] |
| 23 #s-7 | [[task-23.0-test-sandbox]], each task's test strategy |
| 23 #m-1, #m-2 | [[task-23.2-lock-hold-fixture#r1]], [[task-23.2-lock-hold-fixture#r6]] |
| 23 #m-3 | [[task-23.1-queue-and-drain#r9]] |
| 23 #option-a (neutral; cut the seam) | [[#core]], [[task-23.4-option-a-measurement#why]] |
| decision-log #s-1 | [[task-23.1-queue-and-drain#r3]] 7, [[task-23.1-queue-and-drain#r7]], [[task-23.1-queue-and-drain#r8]] |
| decision-log #s-2 | [[task-23.4-option-a-measurement]] |
| decision-log #s-3 (23 #s-3 was uncited) | [[#core]], [[task-23.1-queue-and-drain#r6]], [[task-23.3-sync-between-file-yield#r1]] |
| decision-log #b-6 item 2 (d2b revisit unscheduled) | [[task-23.4-option-a-measurement#ranges]] |
| decision-log #b-3 (Wave 1 order) | [[#dependencies]] |
| decision-log #m-3 (16.6 on the overflow-dropping queue) | [[task-23.1-queue-and-drain#r3]] 6, [[#consumers]] |
| decision-log #m-5 (d2a confirmation) | the "1 - yes agree" answered "Confirm d2a and d3b?" ([[plan-review-2026-10-14#t8-amendments-body]]); d2a is taken as confirmed |
| decision-log #m-6 (enumerate the MEH ids) | 23 #m-1, #m-2, #m-3 and decision-log #m-3, #m-5, #m-6 are each listed in this table |

## Revision round 2 (2026-10-14) {#rev-round-2}

Source: [[bsd-plan23-17-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]] (d9a, d9d) with
[[plan-review-2026-10-14#t9-fixes]].

| finding / decision | answered at |
|---|---|
| nb23-1 (fragment cache unbound; auto-create) | [[#why]], [[#tasks]], [[task-23.1-queue-and-drain#r1]], [[task-23.1-queue-and-drain#ac-3]] |
| d9a (bug-105 hotfix now; 23.1 owns the contract) | [[task-23.1-queue-and-drain#r1]] 1 |
| nb23-2 (learn not idempotent), bug-106 | [[#consumers]], [[#open-after-revision]] 2, [[task-23.1-queue-and-drain#r9]], [[task-23.1-queue-and-drain#ac-16]] |
| nb23-3 (23.3 stamps before semantics) | [[#tasks]], [[task-23.3-sync-between-file-yield#r4]], [[task-23.3-sync-between-file-yield#ac-5]] |
| nb23-4 (bug-093 op-start line unowned) | [[#open-after-revision]] 5, [[task-23.3-sync-between-file-yield#r7]] |
| ns23-1 (23.4 ranges unsound in five places), d9d | [[#open-after-revision]] 1, [[task-23.4-option-a-measurement#rev-round-2]] |
| ns23-2 (23.0 AC-4 size/mtime) | [[#tasks]], [[task-23.0-test-sandbox#ac-4]] |
| nm23-1 (dead-letter) | [[#open-after-revision]] 4, [[task-23.1-queue-and-drain#r6]] |
| nm23-2 (d8d predicate owner) | [[#open-after-revision]] 3, [[task-23.0-test-sandbox#ac-4]] |
| nm23-3 (stale bug-099 row) | [[#open-after-revision]] 6 (for the docs step; registry not edited by a spec revision) |
| nm23-4 (name the batch primitive) | [[#core]], [[task-23.1-queue-and-drain#r1]] 3 |
| ns17-1, ns17-2 (the contract plan-17 consumes) | [[#consumers]], [[task-23.1-queue-and-drain#r10-contract]] |

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]] and [[plan-review-2026-10-14#t9-approvals]]
(d9l, d9m).

| finding / decision | answered at |
|---|---|
| nb23-r3-1 (hotfix adopted "unchanged" still leaks the binding) | [[#why]], [[#tasks]], [[task-23.1-queue-and-drain#r1]] 1, [[task-23.1-queue-and-drain#ac-3]] AC-3d |
| ns23-r3-1 (rollback drops pre-batch dirty bits) | [[#why]], [[task-23.1-queue-and-drain#r1]] 3, [[task-23.1-queue-and-drain#ac-4]] (f) |
| ns23-r3-2 (`facts.log` events of rolled-back holds) | [[#why]], [[task-23.1-queue-and-drain#r3]] 7, [[task-23.1-queue-and-drain#ac-16]] AC-16b |
| ns23-r3-3 (23.3 concurrent syncs; plain evidence insert) | [[#tasks]], [[task-23.3-sync-between-file-yield#r8]], [[task-23.3-sync-between-file-yield#ac-9]] |
| ns23-r3-4 (23.4 oracle by id; 60 s cap; post-run re-apply; unpinned workload; AC-1 orders commits), d9m | [[#tasks]], [[#open-after-revision]] 1, [[task-23.4-option-a-measurement#rev-round-3]] |
| nm23-r3-1 (23.4 status stated three ways) | [[#open-after-revision]] 1, [[task-23.4-option-a-measurement#ranges]] |
| nm23-r3-2 (repair described as a rebuild) | [[task-23.1-queue-and-drain#r1]] 1 |
| nm23-3 (stale bug-099 row; carried open) | [[#open-after-revision]] 6 (docs chore, registry not edited) |
| d9l (23.4 ranges confirmed) | [[#open-after-revision]] 1 |

## Revision round 5 (2026-10-14) {#rev-round-5}

Source: [[bsd-plan23-17-spec-rereview-r4-878647c]], [[plan-review-2026-10-14#t11-approvals]]
(d9y; d9x/d9aa are 23.0's R7-R9, against which this re-review raised no finding), and the
user's writer-handle idea.

| finding / decision | answered at |
|---|---|
| nb23-r4-1 (23.1's contract is the superseded `4fb803b`; cherry-pick fallback; unkillable mutant) | [[#tasks]], [[#dependencies]], [[task-23.1-queue-and-drain#rev-round-5]] |
| nb23-r3-1 (partial) | [[task-23.1-queue-and-drain#rev-round-5]] |
| ns23-r4-1 (AC-4 dirties no fragment; rollback drop undefined) | [[#tasks]], [[task-23.1-queue-and-drain#rev-round-5]] |
| ns23-r4-2 (at-most-once event residual never forced closed) | [[#tasks]], [[task-23.1-queue-and-drain#rev-round-5]] |
| ns23-r4-3 (23.4 dealing, absolute dead bits, copy's birth time), d9y | [[task-23.4-option-a-measurement#rev-round-5]] |
| nm23-r4-1 (AC-3d (v) allow-list) | [[task-23.1-queue-and-drain#rev-round-5]] |
| nm23-r4-2 (offsets unread; bug-099 not stale; AC-1 spec sha) | [[#open-after-revision]] 6, [[task-23.1-queue-and-drain#rev-round-5]], [[task-23.4-option-a-measurement#rev-round-5]] |
| nm23-r4-3 (23.3 AC-9 race not forced) | [[task-23.3-sync-between-file-yield#rev-round-5]] |
| writer-handle idea (PROPOSED) | [[#open-after-revision]] 7, [[task-23.1-queue-and-drain#r1-6-proposed]] |

## Revision round 6 (2026-10-15) {#rev-round-6}

Source: [[bsd-plan23-17-spec-rereview-r6-0e77da3]] and [[plan-review-2026-10-14#t12-approvals]]
(d9ao, d9ap), with d9ag (R1.6 adopted) and d9aj (old revision tables keep PROPOSED as history)
applied. The round-5 table above is unchanged history.

| finding / decision | answered at |
|---|---|
| ns23-r6-1 (R1.6 / AC-20 still PROPOSED after d9ag) | [[#root]] status, [[#tasks]] 23.1 row, [[#open-after-revision]] 7 (SETTLED), [[task-23.1-queue-and-drain#rev-round-6]] |
| ns23-r6-2 (`writer_lock` set at one of 8 writer-Store sites) | [[#tasks]] 23.1 row, [[task-23.1-queue-and-drain#rev-round-6]] |
| ns23-r6-3 (R8 / AC-13 on a `replica_merge` bug-113 breaks), d9ao option (b) | [[#open-after-revision]] 8, [[task-23.1-queue-and-drain#rev-round-6]] |
| ns23-r6-4 (23.4's by-name hash has no rule for dangling `entity_links`), d9ap | [[#tasks]] 23.4 row, [[task-23.4-option-a-measurement#rev-round-6]] |
| nm23-r6-1 (hotfix moved again: d9ae fence, fifth test file, bug-111) | [[#tasks]] 23.1 row, [[task-23.1-queue-and-drain#rev-round-6]] |
| nm23-r6-2 (boot compaction "in the same hold" vs a non-re-entrant lock) | [[task-23.1-queue-and-drain#rev-round-6]] |

## Revision round 7 (2026-10-15) {#rev-round-7}

Source: [[bsd-plan23-17-spec-rereview-r7-331b414]], [[plan-review-2026-10-14#t12-approvals]]
(d9az), and the plan-16/22 r7 re-review's m-5, which it assigned to plan-23
([[bsd-plan16-22-spec-rereview-r7-331b414#m-5]]). The round-6 table above is unchanged history.

| finding / decision | answered at |
|---|---|
| nb23-r7-1 (the "named safe" census route; a raise inside `Store.close()`'s bare `except`) | [[task-23.1-queue-and-drain#rev-round-7]] |
| ns23-r7-1 (purge's check after its Lance delete) | [[task-23.1-queue-and-drain#rev-round-7]] |
| nm23-r7-1 (the one-installer AST rule) | [[task-23.1-queue-and-drain#rev-round-7]] |
| nm23-r7-2 (`HoldRecorder` lacks `held_by_current_thread`) | [[task-23.1-queue-and-drain#rev-round-7]] (23.1 owns the one-method edit; 23.2's approved spec is not reopened) |
| nm23-r7-3 (AC-3b's dangling row is alive) | [[task-23.1-queue-and-drain#rev-round-7]] |
| ns-x-r7-1 (19.2 / 16.6 on `replica_merge`) | cross-reference only: [[#open-after-revision]] 8; owned by plans 19 and 16 |
| d9az (non-harness holders; heartbeat coupling) | [[#root]] status, [[#tasks]] (23.5 row, order), [[#dependencies]], [[#scope-d9az]], [[#open-after-revision]] 9, [[task-23.5-read-path-and-holder-bounds]] |
| plan-16/22 r7 m-5 (23.4 cites "8 dead-concept"; no `dead-linkage` case) | [[#tasks]] 23.4 row, [[#open-after-revision]] 10 (new pin d9ba), [[task-23.4-option-a-measurement#rev-round-7]] |

## Revision round 8 (2026-10-15) {#rev-round-8}

Source: [[bsd-plan23-17-spec-rereview-r8-23ad703]] (plan-23: 1 BULLSHIT, 4 SKETCHY, 4 MEH; all 9
r7 findings closed in text) and d9bn ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until
its ch-bsd loop is clean). Code facts re-read at HEAD `23ad703` (0.78.3). The round-7 table
above is unchanged history.

| finding / decision | answered at |
|---|---|
| nb23-r8-1 (`snapshot` and 10 bare `_read_with_fallback` calls in cli handlers wait on `_store_lock` unbounded; R7 sees only a handler's own body) | [[#tasks]] 23.5 row, [[#scope-d9az]], [[task-23.5-read-path-and-holder-bounds#rev-round-8]] |
| ns23-r8-1 (`_store_health` nests the mirror's use-lock and reads the writer) | [[task-23.5-read-path-and-holder-bounds#rev-round-8]] |
| ns23-r8-2 (long reads move the coupling to the mirror's one use-lock) | [[#tasks]] 23.5 row, [[task-23.5-read-path-and-holder-bounds#rev-round-8]] |
| ns23-r8-3 (R2's deadline has no plumbing; its writes contradict 0.78.2) | [[#tasks]] 23.5 row, [[#scope-d9az]], [[task-23.5-read-path-and-holder-bounds#rev-round-8]] |
| ns23-r8-4 (23.1 AC-20's shutdown case passes on `_final_flush`) | [[task-23.1-queue-and-drain#rev-round-8]] |
| nm23-r8-1 (replay sorts by `ts`; hold 1 copies the whole slot) | [[#tasks]] 23.5 row, [[task-23.5-read-path-and-holder-bounds#rev-round-8]] |
| nm23-r8-2 (R4's thread-local on the wrong thread; `_inflight_ops` ignored) | [[task-23.5-read-path-and-holder-bounds#rev-round-8]] |
| nm23-r8-3 (AC-7 branches on its result; bug-112) | [[task-23.5-read-path-and-holder-bounds#rev-round-8]] |
| nm23-r8-4 (line drift; 23.5's dependency satisfied; open item 8 stale) | [[#tasks]], [[#dependencies]], [[#open-after-revision]] 8 (SETTLED, d9ay), [[task-23.1-queue-and-drain#rev-round-8]], [[task-23.5-read-path-and-holder-bounds#rev-round-8]], [[task-17.3-fleet-rollout#rev-round-8]] |
| d9bn (23.5 read path, four rulings) | [[task-23.5-read-path-and-holder-bounds#rev-round-8]] |

rel: implements -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 9 (2026-10-15) {#rev-round-9}

Source: [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d]] (diff check of round 8 at `9dd923c`, HEAD
`b84fd8d`; plan-23: 2 BULLSHIT, 2 SKETCHY, 3 MEH, all in 23.5; 23.1 and 23.3 READY). The
round-8 table above is unchanged history.

| finding | answered at |
|---|---|
| nb23-r9-1 (the snapshot drops dirty bitmap bits) | [[task-23.5-read-path-and-holder-bounds#rev-round-9]] (R1.9, AC-7) |
| nb23-r9-2 (the bug-112 gate pinned the bug) | [[#tasks]], [[#dependencies]] (bug-112 FIXED and reachable from `master`), [[task-23.5-read-path-and-holder-bounds#rev-round-9]] (R1.10, AC-7) |
| ns23-r9-1 (one-sided plan-18 interface; Wave 4 `depends-on`) | [[#dependencies]] (23.5 stands alone), [[task-23.5-read-path-and-holder-bounds#cross-plan-18]] (the obligations list for the plan-18 reviser) |
| ns23-r9-2 (untyped `writer busy`) | [[task-23.5-read-path-and-holder-bounds#rev-round-9]] (R1.1, AC-2) |
| nm23-r9-1, nm23-r9-2, nm23-r9-3 | [[task-23.5-read-path-and-holder-bounds#rev-round-9]] |

rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d]]
