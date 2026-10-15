---
gmd: "0.1"
id: task-19.4-keep-derived-layers-current
title: "Task 19.4: subjects recompile on a schedule with stable names and stale subjects marked, never removed; the index regenerates after compile and on every bridged memory write"
tags: [task, memory, compile, index, schedule]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-15
---

# Task 19.4: keep the derived memory layers current {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 19.3; plan-17 task 17.2 (the nightly tick and its step registry; no fallback, plan
> review C6); 23.0 (sandbox).

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[task-19.3-subject-tiered-index]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]
rel: depends-on -> [[feedback_daemon_call_retries_multiply_timeouts]]
rel: specified-by -> [[bsd-plan19-spec-review-3104a81]]

## Why {#why}

- `rmx memory compile --apply` (`cli.py:12696-12740`, re-read at `3d3c798`) runs only by hand, so subjects go stale as
  memories accrue.
- `consolidate.apply_plan` unlinks the compiler's own prior leaves and relinks them, but never
  touches a subject NODE that lost every member: on a nightly schedule each label drift leaves
  another empty, protected, embedded `subject_*` row.
- Unlabeled clusters are named `unlabeled-{ci + 1}` (`consolidate.py:585`), by cluster ORDER: after
  a re-compile, `--subject unlabeled-21` in `MEMORY.md` can name a different cluster.
- `memory_index` runs only from save-state (`handoff._ss_update_index`, `handoff.py:224`). A memory
  written any other way, or a compile, reaches the index only at the next save-state.

{#why-body}

## Requirements {#requirements}

1. **R1 Scheduled compile: one registered step on plan-17's tick** (plan review C6). Memory
   compile registers as a per-store step in 17.2's step registry. It runs serially, skips paused
   stores, and is logged and published with the rest of the run.
   - No second stamp file and no save-state fallback: 17.2's `maintain.json` holds the only
     stamps.
   - A hub-callable daemon op `memory_compile` PLANS and applies (today only
     `memory_compile_apply` is a daemon op, `_op_memory_compile_apply`, `daemon.py:5265`, registered in `OPS` at `:6336`; planning
     runs CLI-side). It is a verb too (verb-parity test).
   - The hub calls it with `retries=0`, and the op is single-flight per store: a second call while
     one runs returns `already_running`, so a timed-out call is never re-sent onto a running
     compile ([[feedback_daemon_call_retries_multiply_timeouts]]). Since 0.78.2 (bug-116)
     `daemon.call` never re-sends after a post-send TIMEOUT (`daemon.call`, `daemon.py:658-661`:
     the `sent` check breaks out), so on the timeout path `retries=0` changes nothing; it is kept
     as defence because it additionally stops a connect-timeout retry and a re-send after a
     post-send `ConnectionResetError` / `JSONDecodeError`, which that loop still retries
     (`daemon.py:664-670`; round-8 #nm-6). The single-flight guard, not `retries`, is what keeps a
     second compile from starting.
2. **R2 Index on write.** The ingest-gmd memory bridge, after a batch that added or changed memory
   files, regenerates `MEMORY.md` through `memory_index.write`, the function save-state calls.
   That covers the SessionStart detached bridge (`ingest_gmd_start`).
   - The memdir is resolved as the store's memory root, `handoff.default_memory_dir(<the store's
     project root>)`, never from the bridge's target path (a subdirectory such as `impressions/`
     or a single file resolves to the same root). A store with no project memory root (the
     global store) skips regeneration and reports the skip.
   - Inside the daemon the render's subjects, members and scores are read from the WRITER store
     (`d._st()` under `d._store_lock`, bound to the memory partition) at the end of the ingest
     job, after its last memory write: `_run_ingest_gmd_body` (`daemon.py:3535`), which both the
     synchronous `_op_ingest_gmd` and the detached `_op_ingest_gmd_start` run (19.3 R5; round-6
     #s-3), never from the replica, the in-memory mirror, `search.cached_replica` or
     `Store(read_only=True)`: each lags the write by the snapshot debounce, and the last two are
     bug-112's openers. It writes through 19.3 R8's atomic, locked triple, outside the store
     lock.
3. **R3 Compile regenerates the index.** After a successful apply, the compile op regenerates
   `MEMORY.md` for that store's memory root (R2's resolution) IN THE SAME OP, reading subjects,
   members and scores from `d._st()` inside the apply's own `with d._store_lock,
   d._st().with_partition(…)` block (the block `_op_memory_compile_apply` holds today,
   `daemon.py:5276`) and rendering after it (19.3 R5; round-6 #s-3). So the index names exactly
   the subjects the apply wrote, with no wait on the snapshot tick, and subject lines are never
   stale until the next memory write. The round-5 wording ("the render reads the replica") was
   false by construction: the replica is regenerated after the op returns.
4. **R4 Compile never loses.** Compile only re-files `part-of` edges between subjects and members.
   A memory that leaves every subject renders in its type section (19.3 R1). No memory and no
   subject node is removed.
5. **R5 Stale subjects are marked, never reaped** (d8a, replacing d5a). After re-filing, every
   compiled subject (`compiled_by` stamp) with 0 leaves gets `metadata.stale = true` and
   `stale_since`. It stays `protected`, is hidden from recall (19.1 R2, even with
   `--include-subjects`) and from the index (19.3 R1), and is still readable by name
   (`rmx memory get subject_<slug>`) and listed by `rmx memory list --type subject` with its
   stale mark. A stale subject that regains members is unmarked. Removal of a stale subject goes
   ONLY through plan-22's audited path (dry-run → manifest → apply); compile has no delete call.
   - **Who audits the accumulation** (re-review #s-6; reference only, not built here): R6's
     hash-named subjects mean a membership change mints a new subject and marks the old one
     stale, so stale rows accrete. Their reviewer is plan-22's `stale-subject` audit class
     ([[task-22.1a-provenance-free-classes#r1]], unit ENTITY), which reports them and is inert
     until this task writes the mark; any removal is that plan's apply, behind its ablation gate.
     This task only makes the growth visible: every compile run reports `stale_total`,
     `stale_new` and `stale_unmarked`, and AC-4b bounds the growth per run.
6. **R6 Stable names for unlabeled clusters** (19 #s-7). An unlabeled cluster's slug is
   `unlabeled-<h>`, `<h>` = `stm.cluster_cid(members)` (19.6 R9; ONE member-set hash shared with the topic cache — d9ca), the first 8 hex chars of sha256 over its sorted member names, so the
   name is independent of cluster order. A changed membership is a different subject; the old
   one is marked stale by R5.
7. **R7 Loud.** Every path reports compiled / skipped / failed / marked-stale with counts (no
   `|| true`, no bare except, per the memory-path rule).

## Acceptance criteria {#acceptance}

All ACs run in task 23.0's sandbox: a tmp memory dir passed explicitly, tmp stores, and a tmp
registry. 17.2's tick runs only over its INJECTED roots (17.2 `#r3-roots`), so the step never
reaches a live store's subject graph. This step registers with 17.2's hub step registry as
`MaintenanceStep(name="memory_compile", op="memory_compile", …, requires_arming=True, reason=…)`
(reason: it rewrites `MEMORY.md` and compiled subjects, user-visible state), so it dry-runs until a
hand run's `run_id` arms it (17.2 `#r7-unarmed`). Per 17.2 R2, the op accepts `dry_run` and
`invoked_by`, answers `status=True`, and appends one `runs.jsonl` line per completed run with
`step: "memory_compile"`.

1. **Bridge writes the index.** Writing a new memory file into the tmp memory dir and running only
   the SessionStart bridge (no save-state) produces an index that names the new memory. The
   sandbox daemon runs with `RMX_SNAPSHOT_DEBOUNCE_MS=60000` (round-6 #s-3), so the replica is
   certainly older than the write: the index is read right after the bridge op returns, with no
   sleep and no retry.
2. **Scheduled step, unarmed then armed** (nm17-r3-5). On 17.2's tick (injected clock), per
   sandbox store:
   - **Unarmed (day 1).** The compile step runs once on the scheduled day with `dry_run=True`
     (plan only): the run summary reports it `dry_run:unarmed`, and `MEMORY.md` and the compiled
     subject rows are byte-identical before and after.
   - **Arm, in 17.2's order.** By hand through the CLI verb: a dry run of `memory_compile`, then a
     real run, each appending its `runs.jsonl` line (17.1 R12 shape, `step: "memory_compile"`,
     `invoked_by: "cli"` set by the adapter); then `rmx hub maintain arm --root <store> --step
     memory_compile --run-id <the real run's run_id>` writes `armed_at`. Arming with the dry run's
     id, or with a real run's id that has no earlier dry-run line, is refused (17.2
     `#r7-unarmed`).
   - **Armed (day 2).** The step runs once through the `memory_compile` op (plan + apply), the
     index and subjects change as the plan says, and the summary reports `ok`. Under
     `RMX_SNAPSHOT_DEBOUNCE_MS=60000`, `MEMORY.md` read straight after the op returns (no sleep,
     no retry) names every subject the plan created (round-6 #s-3).
   - A second call during a run returns `already_running`.
3. **Reachable after compile.** A compile that moves memory X out of every subject leaves X
   reachable (19.3 R4's executed check passes), checked against the `MEMORY.md` the same op
   wrote, under `RMX_SNAPSHOT_DEBOUNCE_MS=60000` and with no sleep or retry: the index no longer
   lists X under its old subject (round-6 #s-3).
4. **Stale marked, not removed** (d8a). A re-compile after which subject S has 0 leaves: S's row
   still exists, is `protected`, carries `stale = true`, is absent from `rmx memory recall`
   (with and without `--include-subjects`) and from `MEMORY.md`, and `rmx memory get subject_S`
   returns it.
4b. **Bounded stale growth.** A re-compile in which exactly one unlabeled cluster gains one member
   (all other memberships unchanged) creates exactly ONE new `unlabeled-<h>` subject and marks
   exactly ONE subject stale; a re-compile with no membership change creates and marks none. The
   run summary reports `stale_new = 1` and `stale_total` incremented by 1 in the first case, 0 in
   the second. Mutation: minting a new hash slug when only cluster ORDER changed fails this AC.
5. **Stable slugs.** A re-compile that reorders clusters (same memberships, different order)
   leaves every printed `--subject` command in `MEMORY.md` returning its printed members.
6. **Index after compile.** After the compile step, `memory_index.check` against the new snapshot
   is in sync without a save-state.
7. **Isolation.** 23.0's guard records 0 live connects for this task's test files.
8. **Mutations that must FAIL a test:**
   - the bridge not regenerating the index (AC-1);
   - the step not registered (AC-2);
   - the step registered with `requires_arming=False` (AC-2: day 1 applies, `MEMORY.md` changes);
   - (WITHDRAWN round 8, #nm-6: "`retries` left at the default (AC-2's single-flight check)" is
     an equivalent mutant since 0.78.2: `daemon.call` never re-sends after a post-send timeout,
     and AC-2 never exercises a reset after send) the single-flight guard removed (AC-2: the
     second call starts a second compile instead of returning `already_running`);
   - compile deleting a stale subject (AC-4);
   - a stale subject visible in recall (AC-4);
   - slugs by cluster order (AC-5);
   - the over-budget path silent;
   - the in-op render reading through `search.cached_replica` (or `d._open_read_store`, or
     `Store(read_only=True)`) straight after the apply or the bridge write (AC-1: the new memory
     is absent; AC-2 day 2: a new subject is absent; AC-3: X is still listed under its old
     subject).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/ingest_gmd.py` | regenerate the index after a memory batch (R2) |
| `src/refmatrix/consolidate.py` | stale marking (R5), stable unlabeled slugs (R6) |
| `src/refmatrix/daemon.py`, `verbs.py` | the `memory_compile` (plan + apply) op and verb, single-flight; `dry_run` / `invoked_by` / `status=True` and its `runs.jsonl` line (17.2 R2); index regeneration after apply in the same op, reading the writer store inside the apply's `_store_lock` block (R3; 19.3 R5) |
| `src/refmatrix/ingest_gmd.py` / `daemon.py` (`_run_ingest_gmd_body`, `:3535`, run by `_op_ingest_gmd` `:3651` and `_op_ingest_gmd_start` `:3670`) | the bridge's index regeneration at the end of the ingest job reads the writer store under `_store_lock`, after its last write (R2; 19.3 R5) |
| `src/refmatrix/hub.py` / plan-17's tick | the compile step registered, `retries=0` |

## Test strategy {#test-strategy}

- **Sandbox:** task 23.0 (d1a/d1b): tmp `HOME`, global root, registry and LaunchAgents dir;
  injected store roots; spawned `rmx` children refuse sockets outside the tmp root; the conftest
  guard fails a test that touches `~/.refmatrix`, the live memdir or a registered live store.
- **RED** on AC-1 (the bridge never touches the index) and AC-4 (no stale mark exists today).
- Real fixture stores; the clock is injected for 17.2's tick; no mocks of compile.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 19 #s-7; d8a (replaces d5a); decision-log #b-1 | R3, R5, R6, AC-4, AC-5, AC-6, mutations |
| 19 #s-8 (memdir resolution, no self-call) | R2 |
| 19 #b-7; d1a/d1b | [[#test-strategy]], AC-7 |
| 19 #s-6 (header) | header |
| 19 #m-1 (`cli.py:12695`) | [[#why]] |
| d3e amendment applied to this step (retries, single-flight) | R1, AC-2 |
| plan-22 #m-7 (one removal path) | R5 |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]].

| finding / decision | answered at |
|---|---|
| re-review #s-6 (stale subjects accrete; no reviewer named) | R5 "Who audits the accumulation" (plan-22's `stale-subject` class, reference only); AC-4b |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan23-17-spec-rereview-r3-6091648#nm17-r3-5]] (the 23+17 round-3 review, which
named this plan-19 file).

rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648]]

| finding / decision | answered at |
|---|---|
| nm17-r3-5 (AC-2 asserted plan + apply on the scheduled day for a step declared `requires_arming=True`) | [[#acceptance]] preamble (`MaintenanceStep(name="memory_compile", …)`, 17.2 R2's op duties); AC-2 (day 1 `dry_run:unarmed`, byte-identical outputs; hand dry run then real run, then 17.2's `hub_maintain_arm` with the real run's id, matching 17.2's current order gate; day 2 plan + apply); mutation; [[#files-to-modify]] |

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan19-21-spec-rereview-r6-0e77da3#s-3]] (the 19.4 side) and the stale citations
of #m-1 in this file. Code facts read at write time at HEAD `3d3c798`: `daemon.py:1782`, `:2451-2460`,
`:2693`, `:2708-2716` (the tick sleeps `RMX_SNAPSHOT_DEBOUNCE_MS` after a write), `:3450`, `:3566`,
`:3585`, `:5180-5193`, `:6251`; `search.py:38`; `cli.py:12696-12740`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r6-0e77da3]]

| finding / decision | answered at |
|---|---|
| round-6 #s-3 (R2 / R3's in-daemon render reads the stale replica; "never stale" false; bug-112) | R2 (writer store under `_store_lock`, same op, after the bridge's last write); R3 (same op as the apply, inside its `_store_lock` block, render after; the round-5 wording withdrawn); AC-1, AC-2 (day 2), AC-3 (no sleep or retry, `RMX_SNAPSHOT_DEBOUNCE_MS=60000`); mutation (render through `cached_replica` / the mirror / `Store(read_only=True)`); [[#files-to-modify]]. The rule itself: [[task-19.3-subject-tiered-index#rev-round-6]] |
| round-6 #m-1 (citations stale since the merge) | [[#why]] (`cli.py:12696-12740`); R1 (`daemon.py:5180`, `:6251`) |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]] #nm-6 and #nm-7 (the 19.4 side). Code facts
read at write time at HEAD `23ad703`: `daemon.py:622-670` (`call`; the post-send timeout break
`:658-661`, the reset/decode retry `:664-670`), `:3535` (`_run_ingest_gmd_body`), `:3651`
(`_op_ingest_gmd`), `:3670` (`_op_ingest_gmd_start`), `:5265` (`_op_memory_compile_apply`, its
`with d._store_lock` at `:5276`), `:6336` (its `OPS` entry). Older revision tables keep the lines
of their own HEAD.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]

| finding / decision | answered at |
|---|---|
| round-8 #nm-6 (the "`retries` left at the default" mutation is equivalent since 0.78.2) | R1 (the 0.78.2 behaviour stated; `retries=0` kept as defence for connect-timeout and post-send reset/decode retries; single-flight named as the guard); mutation replaced by "single-flight guard removed" (AC-2) |
| round-8 #nm-7 (`daemon.py:5180`, `:6251`, `:3450`, `:5191`, `:3566`, `:3585`) | R1 (`:5265`, `:6336`); R2 (`:3535`); R3 (`:5276`); [[#files-to-modify]] (`:3535`, `:3651`, `:3670`) |
