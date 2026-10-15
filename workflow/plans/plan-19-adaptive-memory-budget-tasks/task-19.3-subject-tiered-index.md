---
gmd: "0.1"
id: task-19.3-subject-tiered-index
title: "Task 19.3: MEMORY.md is grouped by compiled subject and folded by value, and every memory stays reachable by a command that actually returns it"
tags: [task, memory, memory-index, subjects, budget]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-15
---

# Task 19.3: subject-tiered, value-ranked MEMORY.md {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 19.2 (scores) only; 23.0 (sandbox). It is built and tested on a STATIC catalog copy
> carrying compiled subjects, so it does not wait for 19.4 (19 #s-6). No dependency on plan-22's
> protection source (d8b).

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[task-19.2-memory-usage-record]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]
rel: specified-by -> [[bsd-plan19-spec-review-3104a81]]
rel: depends-on -> [[bug_registry]]

## Why {#why}

`memory_index.render` (`memory_index.py:239`) lists entries in a fixed type order, alphabetically
within each type, and folds the oldest projects **by file mtime** (`:275`) to stay under
`MAX_INDEX_CHARS=24000` (`:63`). On 2026-10-14 it held 22,368 chars and 134 lines, with 95
projects folded into one line and 131 entries inline (53 feedback, 11 reference, 67 project).
mtime moves on edit, not on use. Feedback never folds, so an all-feedback index would end in
`STILL OVER` (`:351`). The 39 compiled subjects (`mtype=subject`, `part-of` edges; 15 of them
`unlabeled-N`) are unused by the index. {#why-body}

## Requirements {#requirements}

1. **R1 A subject block.** For each LIVE compiled subject (not marked `stale` by 19.4 R5): one
   line `- **<subject>** (<n> memories): <top hooks …> — rmx memory recall --subject <slug> --k <n>`,
   followed by its top members inline (by 19.2's effective score) while the budget allows. `<n>`
   is the subject's member count, so the printed command returns every member (`verbs.memory_recall`
   truncates `subject_leaves` to `[:k]`, `verbs.py:731`). Memories in no live subject render in
   the existing type sections.
2. **R2 Value order.** Within each section the order is by effective score from the score
   SNAPSHOT (R7), descending; ties break by `created` (older first), then by name.
3. **R3 Fold by value, in tiers** (d8b). When over budget, entries fold into their subject line
   or their type's fold line in this order:
   - first the **rest** tier, lowest score first;
   - then the **curated-inbound** tier: memories that are the target of a `rel:` edge from a
     curated memory (`type` feedback, project or reference; save-states and impressions are not
     curated sources);
   - last the **feedback** tier.

   Within a tier, lower score folds first; at equal score the NEWER `created` folds first. A
   folded memory is never removed (ADR-0004 #rule-no-delete). This fold-order tier is separate
   from 19.2's asserted FLOOR, which keeps ADR-0004 #rule-asserted-floor's definition. Measured
   2026-10-14 over 329 files: feedback 52; curated-inbound 178; feedback ∪ curated-inbound 192
   (58%). `STILL OVER` stays the loud last resort.
4. **R4 Operational reachability** (19 #b-3). A memory is reachable if and only if either
   - an inline line names its file, or
   - a fold or subject line printed in the index carries a command that, EXECUTED against the
     sandbox copies of the memory dir and catalog, returns it.

   Fold lines therefore print enumerating commands: a subject line
   `rmx memory recall --subject <slug> --k <n>`; a type fold line
   `rmx memory list --type <type> --limit <count of that type>` (the CLI default is 20,
   `cli.py:11554`). The check runs each printed command, unions the names, and FAILS listing every
   memory file on disk that is neither inline nor returned. It is a function in `memory_index`,
   run by the tests and by a new `rmx memory index --check-reach` command (no `memory index`
   command exists today).
5. **R5 Subjects and scores source.** Outside the daemon (save-state), subjects, members and scores
   come from a daemon read op over the replica. **Inside the daemon (19.4's compile and bridge
   paths) they come from the WRITER store, in the same op as the write they follow** (round-6
   #s-3): after its write, the op reads subjects, members and scores through `d._st()` under
   `d._store_lock`, bound to the memory partition (`with d._store_lock,
   d._st().with_partition(<memory partition>)`, the pattern of `_op_memory_compile_apply`,
   `daemon.py:5265-5278`, `with` at `:5276`; for compile, inside the apply's own block), then
   releases the lock and renders and writes R8's triple outside it. The writer store sees every
   committed write, so the read is current whether or not the write's own block is still held. The replica is the wrong
   source there:
   - it lags the write. `catalog.read.duckdb` is regenerated by the snapshot tick, debounced
     after each write op (`RMX_SNAPSHOT_DEBOUNCE_MS`, default 250 ms; `_request_snapshot`,
     `daemon.py:2741`; "regenerated within ~250ms after each write op", `:1816`), and the
     in-memory mirror `d._open_read_store` serves first carries the same lag (`:2499-2508`). A
     render read from either right after the apply sees the catalog BEFORE it;
   - an in-process opener of the snapshot is exposed to bug-112 (open in `workflow/bug_registry.md`):
     DuckDB's per-path instance cache can hand `search.cached_replica` (`search.py:38`) or a bare
     `Store(root, read_only=True)` the old, unlinked snapshot after it is replaced.
   So no in-daemon render path calls `search.cached_replica`, `Store(…, read_only=True)` or
   `d._open_read_store`. Never `Store()` on the live catalog from outside the daemon.
6. **R6 Hooks preserved.** Curated hooks (`.memory_hooks.json`, bug-050) are reused verbatim for
   any entry or folded member.
7. **R7 A score snapshot, not the wall clock** (19 #s-9).
   - `write()` computes every score once at `t_snap`, quantizes it to 3 significant digits, and
     records `{t_snap, scores, tiers}` in `.memory_scores.json` beside the index.
   - `render()` and `check()` take the snapshot as input, so `check()` reads in sync until a
     memory, a subject or a usage count changes, never because time passed.
   - With no daemon, `render()` uses the last snapshot plus a one-line note. With no snapshot ever
     written, it uses virtual scores computable from the files alone (every memory at `base`,
     feedback and `rel:`-anchored at `asserted_floor`, R7 of 19.2) plus the note. It never falls
     back to the mtime layout and never crashes save-state.
8. **R8 Atomic, single-writer index files** (19 #s-8). `MEMORY.md`, `.memory_hooks.json` and
   `.memory_scores.json` are each written to a tmp file and `os.replace`d, under one `fcntl` lock
   on `.memory_index.lock` held for the whole triple. A writer that cannot take the lock within
   its budget reports it and leaves the old triple intact.

## Acceptance criteria {#acceptance}

All ACs run in task 23.0's sandbox on COPIES of this project's memory dir and catalog (39
subjects); the baseline numbers are frozen from that copy at RED time (19 #m-2), not from this
spec.

1. **Fit and reach.** The rendered index is ≤ `MAX_INDEX_CHARS`, and the number of memories
   NAMED (inline or in a subject line) is ≥ 1.5x the inline count measured on the frozen copy.
2. **Operational reachability.** R4's check passes. A synthetic subject with 15 members, 5 of them
   folded, is fully returned by its printed command. Deleting one subject line makes the check
   fail listing exactly that subject's members that no other line returns.
3. **Tier order on the real distribution.** On the frozen copy the tier sizes are printed, and
   under a budget that forces folding, every `rest` entry folds before any `curated-inbound` one,
   and every `curated-inbound` entry before any feedback one. With every feedback memory forced
   cold, feedback still renders inline until the other two tiers are exhausted.
4. **Never-recalled ties.** Two memories with equal score, one older: the newer folds first.
5. **Clock-free check.** After `write()`, advancing the clock by 10 half-lives with no other
   change leaves `check()` in sync and the render byte-identical.
6. **No daemon.** The render uses the last snapshot (or the virtual scores) plus the note, never
   the mtime order, and save-state succeeds.
7. **Concurrent writers.** Two concurrent regenerations leave `.memory_hooks.json` and
   `.memory_scores.json` parseable and each equal to one writer's complete output.
8. **Stale subjects.** A subject marked `stale` renders no subject line; its former members are
   reachable by R4.
9. **Isolation.** 23.0's guard records 0 live connects for this task's test files.
10. **Mutations that must FAIL a test:**
    - mtime order restored;
    - fold tiers collapsed into one (AC-3);
    - the printed `--k <n>` dropped, so `[:k]` stays 10 (AC-2);
    - reachability judged by "a fold line names a command" without running it (AC-2);
    - the reachability check made vacuous (an empty memory set);
    - `render()` reading `now()` (AC-5);
    - a non-atomic `write_text` of the sidecar (AC-7);
    - subjects read from a direct `Store()`;
    - the in-daemon render reading through `search.cached_replica`, `Store(read_only=True)` or
      `d._open_read_store` straight after the apply (19.4 AC-1, AC-2, AC-3: the new subject or
      memory is missing from the index; those ACs run with `RMX_SNAPSHOT_DEBOUNCE_MS=60000`, so the
      replica is stale for certain, not by timing).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/memory_index.py` | subject block, tiers, value order, fold by score, R4 check, R7 snapshot, R8 atomic triple |
| `src/refmatrix/daemon.py` | a read op returning live subjects + members + scores + tiers for a memory dir's partition (save-state's path, over the replica); for in-daemon callers, the same read as a function over the WRITER store, called inside the write's `_store_lock` block (R5; round-6 #s-3) |
| `src/refmatrix/handoff.py` (`_ss_update_index`, `:224`) | pass the snapshot through; `check()` against it |
| `src/refmatrix/cli.py` | the new `rmx memory index --check-reach` command |

## Test strategy {#test-strategy}

- **Sandbox:** task 23.0 (tmp `HOME`, global root and registry; injected store roots; the conftest
  guard). The memory dir is always passed explicitly as a tmp copy; R4's commands run against the
  sandbox daemon of the catalog copy.
- **RED:** AC-1 and AC-2 on the copies fail today (mtime fold, no subjects, no executed check).
- R4's check also runs over a fixture with 300 memories under a 24k budget.
- The char-budget assertion counts **characters** with a multibyte fixture (the bug-045 lesson).

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 19 #b-3 | R1 (`--k <n>`), R4, AC-2, mutations |
| 19 #b-4 (fold order of never-recalled memories) | R2, R3, AC-4 |
| 19 #b-7; d1a/d1b | [[#test-strategy]], AC-9 |
| 19 #s-5; d8b (replaces d5c) | R3, AC-3 |
| 19 #s-6 | header |
| 19 #s-7 (stale subjects not rendered) | R1, AC-8 |
| 19 #s-8 | R5 (no self-call), R8, AC-7 |
| 19 #s-9 | R7, AC-5, AC-6 |
| 19 #m-1 (`:351`) | [[#why]] |
| 19 #m-2 | [[#why]], AC-1 |
| d8a (stale subjects hidden) | R1, AC-8 |
| decision-log #b-2 (no protection-source dependency) | header, R3 |

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan19-21-spec-rereview-r6-0e77da3#s-3]] (the 19.3 side). Code facts read at write
time at HEAD `3d3c798`: `daemon.py:334`, `:740` (`_store_lock`), `:830-835` (`_st`), `:1782`,
`:2451-2460` (`_open_read_store`), `:2621-2640` (`_snapshot_catalog`), `:2693`
(`_request_snapshot`), `:5180-5193` (`_op_memory_compile_apply`); `search.py:38`
(`cached_replica`); bug-112's row in `workflow/bug_registry.md` (status open).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r6-0e77da3]]

| finding / decision | answered at |
|---|---|
| round-6 #s-3 (the in-daemon render reads the replica right after the daemon's own write: stale by the snapshot tick, exposed to bug-112) | R5 (inside the daemon: the writer store `d._st()` under `d._store_lock` in the same op as the write, render outside the lock; replica, mirror, `cached_replica` and `Store(read_only=True)` barred there; bug-112 cited); mutation (pinned by 19.4 AC-1-AC-3 under `RMX_SNAPSHOT_DEBOUNCE_MS=60000`); [[#files-to-modify]] (`daemon.py`). The ACs: [[task-19.4-keep-derived-layers-current#rev-round-6]] |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]] #nm-7 (the 19.3 cites). Code facts read at
write time at HEAD `23ad703`, by symbol: `_op_memory_compile_apply` `daemon.py:5265` (its
`with d._store_lock, d._st().with_partition(…)` at `:5276`), `_request_snapshot` `:2741`, the
"regenerated within ~250ms" comment `:1816`, `_open_read_store` `:2499-2508`. The round-6 table's
list keeps the lines of its own HEAD (`3d3c798`).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]

| finding / decision | answered at |
|---|---|
| round-8 #nm-7 (`daemon.py:5180-5193` / `:5191`, `:2693`, `:1782`, `:2451-2460`) | R5 (`:5265-5278` / `:5276`, `:2741`, `:1816`, `:2499-2508`) |
