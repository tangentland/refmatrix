---
gmd: "0.1"
id: task-30.3-disk-tier-fate
title: "Task 30.3: the adjacency disk tier's fate — apply 30.0's verdict to cached_adjacency: drop the tier and its files, re-key it on the file the store reads, or keep it with its failures surfaced"
tags: [task, plan-30, adjacency, cache, disk-tier, derive-pass, release]
metadata:
  node_type: task
  status: pending
  plan: plan-30-materialisation
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 30.3: the adjacency disk tier's fate {#root}

> Plan: [[plan-30-materialisation]] ([[plan-30-materialisation#t3]])
> Status: Pending
> Depends on: [[task-30.0-disk-tier-probe]] (the verdict and the probes) and
> [[task-30.2-vectorised-adjacency-build]] (the final shape of `cached_adjacency`).
> Ships in release B with 30.1 and 30.2: it edits `pagerank.py`
> ([[plan-30-materialisation#releases]]).
> **Exactly one of [[#drop]], [[#rekey]], [[#keep]] is built.** At the task's start the lead
> records 30.0's verdict here and strikes the other two sections in a spec revision commit.
> User gates: plan-30 D3, if the verdict is drop (moving the files out of live stores).

rel: part-of -> [[plan-30-materialisation]]
rel: implements -> [[plan-30-materialisation#t3]]
rel: depends-on -> [[task-30.0-disk-tier-probe]]
rel: depends-on -> [[task-30.2-vectorised-adjacency-build]]
rel: depends-on -> [[tdd-governance]]
rel: derives-from -> [[task-30.0-disk-tier-probe#bands]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: reinforces -> [[feedback_mcp_server_reload_and_orphans]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]

## Why {#why}

`adjacency.cache.npz` is the one on-disk derived copy of the graph that exists today. 30.0
measures whether it can be stale and what it can be worth, and reads a verdict off bands that
were written before the measurement ([[task-30.0-disk-tier-probe#bands]]). This task does what
the verdict says, in the same release as the new builder, so that `pagerank.py` is edited once.
{#why-body}

The numbers in hand point at drop: the tier's best case is about 47 s a week
([[task-30.0-disk-tier-probe#bands-numbers]]), and the live store's copy has not been rewritten
for 25 hours ([[task-30.0-disk-tier-probe#known]]). That is an expectation, not the verdict.
All three outcomes are specified. {#why-expectation}

## Requirements common to every verdict {#common}

- **R0.** Re-resolve symbols at the base sha; re-run [[#census]]; copy 30.0's verdict, K, S and
  V into this spec's header.
- **RC-1: 30.0's probes are green.** Every probe of [[task-30.0-disk-tier-probe#r1]] and the lag
  probe pass at this task's final sha. They are this task's RED: the ones that failed at 30.0
  are listed with their E lines from 30.0's log.
- **RC-2: no silent handler.** `cached_adjacency` has no handler that swallows. 29.3's
  broad-except census has no allow-listed row for it.
- **RC-3: nothing derived moved.** `scripts/derive-digest.py check` exits 0.
{#common-list}

## If the verdict is drop {#drop}

### Requirements {#drop-requirements}

- **D-R1.** `cached_adjacency` has one tier: the cache on the `Store` instance, as 30.2 left it.
  `_adj_disk_paths`, `_adj_log_size`, the npz read, the npz write and their two handlers are
  removed. The docstring says what is left and why the disk tier went, with 30.0's numbers.
- **D-R2. No code reads or writes `adjacency.cache.npz` or `adjacency.cache.json`.** An existing
  file is ignored, not deleted by `rmx`: a store is not cleaned up as a side effect of a read.
- **D-R3. The files leave the fleet by an announced step** (plan-30 D3), run by the lead after
  every daemon and hub is on release B and every MCP server has been reconnected:
  1. per fleet store, list the two files with their sizes;
  2. move them into the deploy's backup directory, outside every store;
  3. record the count and the bytes per store in the release summary;
  4. **one day later, check again.** A file that has reappeared was written by a process still
     running the old code ([[feedback_mcp_server_reload_and_orphans]]); it is found, restarted,
     and the file moved again. The check's result is recorded.
- **D-R4.** 30.0's two planted cases patch `_adj_log_size`, which no longer exists.
  `ch-test-engineer` replaces them in the RED commit with [[#d-ac-2]]'s planted file, which is
  the case that must fail from now on.
- **D-R5. Docs.** No file under `docs/` describes the tier at `6676f39` (R0 re-greps). The
  adjacency rows 30.2 adds to `docs/PERFORMANCE.md` gain one line: the tier was removed, with
  30.0's K, S and V. The `scan-prompt --degree` help text in `cli/session_cmds.py` that cites
  "the adjacency cache" is corrected to what is true after 30.2.

### Acceptance {#drop-acceptance}

- **D-AC-1: no consumer creates the files.** On a throwaway store with logging on, after each
  of: a one-shot context call with degree 1, `scan-prompt` with each `--rank`, and the
  `pagerank_compute` op, the store root holds no `adjacency.cache.*`. RED at the base: the
  context call writes both. Test: `test_no_consumer_writes_an_adjacency_file`. {#d-ac-1}
- **D-AC-2: a planted file is never served.** A valid npz and sidecar for a DIFFERENT graph are
  written into the store root under the key the base sha would accept. A fresh `Store` calling
  `cached_adjacency` returns an edge set equal to a fresh build. RED at the base: the planted
  graph is served. Test: `test_planted_adjacency_file_is_ignored`. {#d-ac-2}
- **D-AC-3: the names are gone.** No file under `src/` contains `adjacency.cache`,
  `_adj_disk_paths` or `_adj_log_size` (a census family with a planted site that fails it). {#d-ac-3}
- **D-AC-4: the release step ran and was checked.** The release summary holds D-R3's table for
  every fleet store, and the day-later check. (The lead's; not an agent's.) {#d-ac-4}

### Mutations {#drop-mutations}

1. `cached_adjacency` writes the npz after a build → D-AC-1.
2. `cached_adjacency` loads a matching npz → D-AC-2.
3. A handler around the build returns an empty CSR → RC-2's census and 30.2's AC-5.
{#drop-mutations-list}

## If the verdict is re-key {#rekey}

### Requirements {#rekey-requirements}

- **K-R1.** The disk key replaces the `facts.log` size with the identity of the catalog file the
  store reads: device, inode, modification time in nanoseconds and size of `Store.db_path`,
  taken from the open file where the backend exposes it and otherwise by a stat before and
  after the open that must agree.
- **K-R2. Only a read-only store uses the tier.** A writer's file identity does not change with
  each write, so a writer neither reads nor writes it.
- **K-R3. A failed read or write of the tier is counted and said.** One line on stderr naming
  the file and the error, once per process; the build proceeds. The handler is classified
  counted-and-surfaced in 29.3's census.
- **K-R4. The writer census stays, as a gate.** `tests/census/adjacency_writers.py`
  ([[task-30.0-disk-tier-probe#r0]]) fails on a new writer with no probe row. This is the
  merge, purge and slot census an on-disk derived copy owes.
- **K-R5.** Old files carry old keys, never match, and are overwritten by the first miss. No
  fleet step.

### Acceptance {#rekey-acceptance}

- **K-AC-1.** RC-1: every probe and the lag probe are green under the new key. {#k-ac-1}
- **K-AC-2.** A second read-only `Store` on the same snapshot file is served from disk (hit
  counted by the test's wrapper around the npz load); after the snapshot file is replaced by an
  equal-size file with different content, it is not. Test: `test_disk_key_is_the_read_file`. {#k-ac-2}
- **K-AC-3.** A writer `Store` calling `cached_adjacency` creates no file and loads none. {#k-ac-3}
- **K-AC-4.** A truncated npz, and an unwritable store root, each produce the stderr line and a
  correct result. {#k-ac-4}

### Mutations {#rekey-mutations}

1. the key omits the modification time → K-AC-2.
2. a writer store uses the tier → K-AC-3.
3. the read handler passes silently → K-AC-4.
4. the key is taken from `facts.log` again → RC-1 (the lag probe).
{#rekey-mutations-list}

## If the verdict is keep {#keep}

### Requirements {#keep-requirements}

- **P-R1.** The tier's key and behaviour are unchanged.
- **P-R2.** K-R3: failures counted and said.
- **P-R3.** K-R4: the writer census stays as a gate, and 30.0's probes stay as its tests.

### Acceptance {#keep-acceptance}

- **P-AC-1.** RC-1 (the probes were green at 30.0 and still are). {#p-ac-1}
- **P-AC-2.** K-AC-4. {#p-ac-2}
- **P-AC-3.** The census family's planted writer fails it by name. {#p-ac-3}

### Mutations {#keep-mutations}

1. the read handler passes silently → P-AC-2.
2. the census allow list accepts an entry that matches nothing → P-AC-3.
{#keep-mutations-list}

## Test strategy {#test-strategy}

- **RED first, by `ch-test-engineer`.** The tests named in the verdict's acceptance section are written before
  any `src/` edit and run at the base sha; the red run is kept
  (`workflow/review-output/task-30.3/red.log`) with each test's E line. A test this spec marks
  characterization is recorded green at the base and says so. A test expected RED that passes
  at the base is a finding about the test.
- **GREEN by `ch-implementer`,** who writes no test.
- **Mutation gate.** The fix is committed before the first mutation. Each mutation of
  the verdict's mutation list is applied alone, must FAIL its named test (a hang is not a failure), and is
  reverted in its own command; `__pycache__` is cleared after the batch; the fix is shown
  present after the last revert.
- **Test families are derived from imports** of the touched modules (29.4), and the merged dev
  tree runs them before the merge commit.
- **The RED is 30.0's.** The probes that failed there, plus this verdict's own ACs.
- **All output to files** under `workflow/review-output/task-30.3/`.
{#test-strategy-list}

## Caller census {#census}

At `6676f39`. R0 re-runs it.

| Changed | Callers in `src/` | Tests that name it |
|---|---|---|
| `cached_adjacency` | `context.py`'s degree walk; after 30.2 also `ppr.py::rank_related`, `ppr.py::rank_related_for_prompt`, `enrich.py::enrich_concepts`, `net.py::build_net` | `tests/test_adjacency_cache.py` (11 sites, one on the disk tier: `test_disk_tier_serves_a_fresh_process_stand_in`); 30.0's probes |
| `_adj_disk_paths`, `_adj_log_size` | `pagerank.py::cached_adjacency` only | 30.0's two planted cases |
{#census-table}

Processes that reach the tier today: any one-shot CLI that runs a degree walk; the daemon,
through its private read stores and the mirror (a read-only `Store` has a `log_path`, so by
the code the daemon can write the file too; 30.0's R0 records which processes do); a long-lived MCP server. {#census-processes}

## Invalidation {#invalidation}

- **Drop:** the only cache left is the instance cache, with 30.2's rules.
- **Re-key:** the disk copy is valid for exactly one catalog file identity. A publish replaces
  the file, so the key changes with every publish.
- **Keep:** the `facts.log` size, shown sound by 30.0 for every writer in the census; the
  census gate keeps it sound.
{#invalidation-list}

## Files {#files}

| File | Change |
|---|---|
| `src/refmatrix/pagerank.py` | the verdict's requirements |
| `src/refmatrix/cli/session_cmds.py` | D-R5 (drop only) |
| `tests/test_adjacency_cache.py`, `tests/test_adjacency_disk_tier_probe.py` | re-pointed in the RED commit |
| `tests/census/` | D-AC-3's family, or the writer census as a gate |
| `docs/PERFORMANCE.md` | the verdict, beside 30.2's adjacency rows |
| `workflow/implementation_summaries/task-30.3-disk-tier-fate.md` | new, with the verdict and, for drop, the release table |
{#files-table}

## Risks {#risks}

- **Drop slows the one-shot context walk on the calls that would have hit.** By at most the
  difference between a build and a load (about 0.48 s), on a hit rate the report bounds from
  below at 6%. V is that cost summed, and the band accepts it.
- **An old process rewrites the file after it is moved** (drop). D-R3 step 4.
- **Re-key's stat races a publish.** K-R1 requires the two stats to agree.
{#risks-list}

## Out of scope {#out-of-scope}

- The daemon's in-memory adjacency (30.4). It writes no file under any verdict.
- A new on-disk form of the adjacency.
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **The verdict is not re-argued here** (plan-30 D11). The bands were written first.
- **`rmx` does not delete the files itself.** Removing files from a live store is the lead's
  announced step, with a count, not something a read path does on the side.
- **Three outcomes are specified so that none is improvised.** Two will be struck.
{#decisions-list}
