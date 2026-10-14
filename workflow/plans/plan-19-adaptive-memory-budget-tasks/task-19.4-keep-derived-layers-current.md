---
gmd: "0.1"
id: task-19.4-keep-derived-layers-current
title: "Task 19.4: subjects recompile on a schedule with stable names and stale subjects marked, never removed; the index regenerates after compile and on every bridged memory write"
tags: [task, memory, compile, index, schedule]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
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

- `rmx memory compile --apply` (`cli.py:12695`) runs only by hand, so subjects go stale as
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
     `memory_compile_apply` is a daemon op, `daemon.py:5238`, registered at `:6286`; planning
     runs CLI-side). It is a verb too (verb-parity test).
   - The hub calls it with `retries=0`, and the op is single-flight per store: a second call while
     one runs returns `already_running`, so a timed-out call is never re-sent onto a running
     compile ([[feedback_daemon_call_retries_multiply_timeouts]]).
2. **R2 Index on write.** The ingest-gmd memory bridge, after a batch that added or changed memory
   files, regenerates `MEMORY.md` through `memory_index.write`, the function save-state calls.
   That covers the SessionStart detached bridge (`ingest_gmd_start`).
   - The memdir is resolved as the store's memory root, `handoff.default_memory_dir(<the store's
     project root>)`, never from the bridge's target path (a subdirectory such as `impressions/`
     or a single file resolves to the same root). A store with no project memory root (the
     global store) skips regeneration and reports the skip.
   - Inside the daemon the render reads the replica directly (19.3 R5), and writes through 19.3
     R8's atomic, locked triple.
3. **R3 Compile regenerates the index.** After a successful apply, the compile step regenerates
   `MEMORY.md` for that store's memory root (R2's resolution), so subject lines are never stale
   until the next memory write.
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
6. **R6 Stable names for unlabeled clusters** (19 #s-7). An unlabeled cluster's slug is
   `unlabeled-<h>`, `<h>` = the first 8 hex chars of sha256 over its sorted member names, so the
   name is independent of cluster order. A changed membership is a different subject; the old
   one is marked stale by R5.
7. **R7 Loud.** Every path reports compiled / skipped / failed / marked-stale with counts (no
   `|| true`, no bare except, per the memory-path rule).

## Acceptance criteria {#acceptance}

All ACs run in task 23.0's sandbox: a tmp memory dir passed explicitly, tmp stores, and a tmp
registry. 17.2's tick enumerates only the sandbox registry, so the step never reaches a live
store's subject graph.

1. **Bridge writes the index.** Writing a new memory file into the tmp memory dir and running only
   the SessionStart bridge (no save-state) produces an index that names the new memory.
2. **Scheduled step.** On 17.2's tick (injected clock), the compile step runs once per scheduled
   day per sandbox store, through the `memory_compile` op (plan + apply), and appears in the run
   summary; a second call during a run returns `already_running`.
3. **Reachable after compile.** A compile that moves memory X out of every subject leaves X
   reachable (19.3 R4's executed check passes).
4. **Stale marked, not removed** (d8a). A re-compile after which subject S has 0 leaves: S's row
   still exists, is `protected`, carries `stale = true`, is absent from `rmx memory recall`
   (with and without `--include-subjects`) and from `MEMORY.md`, and `rmx memory get subject_S`
   returns it.
5. **Stable slugs.** A re-compile that reorders clusters (same memberships, different order)
   leaves every printed `--subject` command in `MEMORY.md` returning its printed members.
6. **Index after compile.** After the compile step, `memory_index.check` against the new snapshot
   is in sync without a save-state.
7. **Isolation.** 23.0's guard records 0 live connects for this task's test files.
8. **Mutations that must FAIL a test:**
   - the bridge not regenerating the index (AC-1);
   - the step not registered (AC-2);
   - `retries` left at the default (AC-2's single-flight check);
   - compile deleting a stale subject (AC-4);
   - a stale subject visible in recall (AC-4);
   - slugs by cluster order (AC-5);
   - the over-budget path silent.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/ingest_gmd.py` | regenerate the index after a memory batch (R2) |
| `src/refmatrix/consolidate.py` | stale marking (R5), stable unlabeled slugs (R6) |
| `src/refmatrix/daemon.py`, `verbs.py` | the `memory_compile` (plan + apply) op and verb, single-flight; index regeneration after apply |
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
