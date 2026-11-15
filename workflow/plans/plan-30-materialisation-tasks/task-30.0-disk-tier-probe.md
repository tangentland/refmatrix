---
gmd: "0.1"
id: task-30.0-disk-tier-probe
title: "Task 30.0: probe the adjacency disk tier — can adjacency.cache.npz serve a graph that is not the store's; bands stated first, verdict by the bands"
tags: [task, plan-30, adjacency, cache, facts-log, probe, measurement, census]
metadata:
  node_type: task
  status: pending
  plan: plan-30-materialisation
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 30.0: probe the adjacency disk tier {#root}

> Plan: [[plan-30-materialisation]] ([[plan-30-materialisation#t0]])
> Status: Pending
> Depends on: plan-29 released (the probes are written against the post-29.5 tree and use
> 29.4's sandboxed short temp roots). No plan-30 task.
> Runs first, beside 30.5. Tests and one measurement script only: **no file under `src/`
> changes.** Its output is a verdict that [[task-30.3-disk-tier-fate]] applies.
> User gates: none here. plan-30 D3 (deleting the files) is asked at 30.3.

rel: part-of -> [[plan-30-materialisation]]
rel: implements -> [[plan-30-materialisation#t0]]
rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[tdd-governance]]
rel: derives-from -> [[perf-bitmap-materialisation-2026-11-14#recommendation]]
rel: evidence-for -> [[task-30.3-disk-tier-fate]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_causal_story_before_evidence]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]

## Why {#why}

`pagerank.py::cached_adjacency` keeps a second copy of the graph on disk:
`.refmatrix/adjacency.cache.npz`, with its key in `adjacency.cache.json`. The key is the
partition id, the build parameters, the shape version and **the size of `facts.log`**. The
helper that reads the size, `_adj_log_size`, says why: "every logged write grows it ... so equal
size == same graph". The measurement report left that sentence unchecked
([[perf-bitmap-materialisation-2026-11-14#recommendation]]). {#why-key}

An on-disk derived copy that can outlive the state it was derived from is how bug-105 put
195,003 foreign bits in one fragment. Before this plan builds anything on the adjacency, the
tier is measured. {#why-history}

## What the code says, unmeasured {#known}

Read at `6676f39`. None of this is a finding until a probe shows it.

- `Store._log_event` appends only when `RMX_LOG` is not `0` and the store is not replaying. Its
  docstring records that a 2026-09 audit of `facts.log` found "three write paths that never
  logged at all" and calls the log "an observability surface, not a journal".
- Of the store's graph-changing methods, these call neither `_log_event` nor `_log_events` in
  their own body (read from the syntax tree): `merge_partition`, `rename_partition`,
  `fold_concept_dups`, `repair_fragments`, `repair_entity_links_index`, `vacuum`,
  `untrack_by_path`, `save_bitmap`, `_merge_fragment_all_partitions`. Some reach a logging
  method through one they call. Whether the log grows is what the probes record.
- **The key and the content come from different files.** A one-shot process reads the read
  snapshot (`catalog.read.duckdb`), which lags the writer by the snapshot debounce. It keys what
  it builds on the size of the WRITER's log. A reader of snapshot N can therefore store graph N
  under the log size of N+1, and a later reader of snapshot N+1 would be served it.
- Both the read and the write of the tier are wrapped in `except Exception: pass`. A tier that
  never hits and a tier that fails every write look the same from outside.
- **Observed on the live store, 2026-11-14 17:33, by reading the sidecar only:** the key is
  `[4, 2.0, true, "flat", 420425982]`, written 2026-11-13 16:35. It has no shape element (added
  to the key on 2026-11-13, shipped in 0.83.0), and `facts.log` is now 569,694,431 bytes. So no
  process has completed a build-and-write on that store for 25 hours. The cause is not
  established ([[#r0]] item 4).
{#known-list}

## The bands, stated before measuring {#bands}

Two numbers decide the tier's fate.

- **K + S, the stale paths.** K is the number of operations in [[#r1]]'s table after which a
  fresh process is served an edge set that differs from a fresh build. S is 1 if the lag probe
  ([[#r2]]) is served a stale graph, else 0.
- **V, the best the tier can be worth.** V = (one-shot adjacency consumers in 7 days of
  `query.log`, excluding `scan-prompt`, which leaves the tier at 30.4) × (the vectorised build's
  median − the disk tier's load median), in seconds per week. It assumes every call is a hit, so
  it is an upper bound. From the report's numbers it would be 96 × (0.506 − 0.021) = 47 s; R0
  re-counts.
{#bands-numbers}

| K + S | V | Verdict | What 30.3 does |
|---|---|---|---|
| 1 or more | under 300 s/week | **drop** | removes the tier's code; the files are deleted (plan-30 D3) |
| 1 or more | 300 s/week or more | **re-key** | keys on the identity of the catalog file the store reads; every probe here must then pass; a writer census is added |
| 0 | under 300 s/week | **drop** | as above: a sound copy that saves under five minutes a week is not worth a census duty |
| 0 | 300 s/week or more | **keep** | the tier stays; its two silent handlers are counted and surfaced; the probes stay as its census |
{#bands-table}

The verdict is read off the table. No other consideration enters ([[plan-30-materialisation#decisions]]
D11). A probe that could not be run counts as a stale path, not as a clean one. {#bands-rule}

## Requirements {#requirements}

### R0: baseline and census {#r0}

1. Re-resolve every symbol this spec names at the task's base sha
   ([[task-29.5-split-giant-modules#r8]]).
2. **Consumers.** List every caller of `cached_adjacency` in `src/`, and for each the process it
   runs in (one-shot CLI on the snapshot; the daemon's mirror store; a private read store; a
   writer). At `6676f39` there is one: `context.py`'s degree walk. After 30.2 there are more
   ([[task-30.2-vectorised-adjacency-build#r4]]); the list is taken at the base sha.
3. **Writers.** List every `src/` site that changes what `build_adjacency` reads: rows of
   `entity_links`; `bitmap_fragments` rows or an in-memory fragment; `entities.name`,
   `entities.partition_id`; the `denotes` linkage; the `partitions` table. The list is produced
   by a census family on 29.3's kit (`tests/census/adjacency_writers.py`,
   [[task-29.3-converge-shapes#slice-k]]: a predicate, an allow list with reasons, a synthetic
   module), printed by `tests/census/report.py adjacency_writers --list`, not by hand. Every
   site maps to a row of [[#r1]]'s table or to a stated exclusion with its reason.
4. **The live sidecar.** On a throwaway copy of a read snapshot, with a placeholder `facts.log`
   (as the report's `q1_adjacency.py` did), run each consumer once and record which branch of
   `cached_adjacency` ran: hit, miss-and-write, miss-and-write-failed, tier-off. The probe
   harness counts the two silent handlers by wrapping the store's module-level file calls, not
   by editing `src/`. The summary states what is established about the 25-hour gap and what is
   not.
5. **V.** `workflow/measurements/plan-30-disk-tier/consumers.py` counts one-shot consumer calls
   in 7 days of the live `query.log`, read as text. Its output holds counts and timestamps
   only: no prompt, no query body ([[feedback_no_raw_prompts_in_public_repo]]).

### R1: one probe per graph-changing operation {#r1}

`tests/test_adjacency_disk_tier_probe.py`. Each probe:

1. builds a throwaway store under a short temp root through the production ingest path, with
   logging on, two partitions where the operation needs them;
2. calls `cached_adjacency` in a first `Store` (a build and a write of the tier);
3. runs the operation;
4. opens a **second** `Store` (the stand-in for a fresh process), calls `cached_adjacency`, and
   compares its edge set with `build_adjacency` on that same second store;
5. records `facts.log` size before and after, whether the edge set changed, and whether the
   second store was served from disk.

The assertion is the invariant, not the mechanism: **what a fresh process is served equals a
fresh build.** It holds for any fate of the tier, so the tests survive 30.3. {#r1-invariant}

| # | Operation | Entry point |
|---|---|---|
| P1 | link a new edge (control: must change the key) | `Store.link` |
| P2 | unlink an edge | `Store.unlink` |
| P3 | purge an entity | `Store.purge_entity` |
| P4 | purge a path | `Store.purge_path` |
| P5 | purge many paths at once | the bulk path over `Store._bulk_purge_ids` |
| P6 | untrack a path | `Store.untrack_by_path` |
| P7 | vacuum | `Store.vacuum` |
| P8 | prune noise | `Store.prune_noise` |
| P9 | fold duplicate concepts | `Store.fold_concept_dups` |
| P10 | merge a partition into another | `Store.merge_partition` |
| P11 | rename a partition | `Store.rename_partition` |
| P12 | repair fragments, applied | `Store.repair_fragments` |
| P13 | repair the `entity_links` index | `Store.repair_entity_links_index` |
| P14 | merge the verb aliases | `Store._merge_fragment_all_partitions` |
| P15 | compact the log | the `compact-log` command's store path |
| P16 | dump the catalog to the log, then rebuild from it | `Store.dump_catalog_to_log`, `Store.rebuild_index_from_log` |
| P17 | merge diverged slots | `replica_merge.merge_slots` |
| P18 | a write made with `RMX_LOG=0` while a `facts.log` exists | `Store.link` |
| P19 | rename an entity so that it becomes, or stops being, operational (`session-…`, `digest-…`) | `Store.upsert_entity` |
| P20 | a `denotes` edge added or removed | `Store.link`, `Store.unlink` |
| P21 | `RMX_ADJ_MENTIONS` changed between the two stores (control: the key carries the mode) | environment |
| P22 | a `mentions` row replaced whole | `Store.save_bitmap` (public; no caller in `src/` at `6676f39`) |
{#r1-table}

R0 item 3 may add rows. It may not remove one without a reason in the summary. {#r1-rule}

### R2: the lag probe {#r2}

One test for the path in [[#known]]: a writer store with a published snapshot N; the writer
links more, so `facts.log` grows, and no snapshot is published; reader A opens the snapshot
read-only and calls `cached_adjacency`; snapshot N+1 is published; reader B opens it and calls
`cached_adjacency`. The assertion is [[#r1-invariant]] for reader B. The snapshot is published
the way the daemon publishes it (a checkpoint and a file copy to `catalog.read.duckdb`); the
test does not start a daemon. {#r2-body}

### R3: the probes are shown able to fail {#r3}

A planted case: the tier holds graph G1; the graph is changed; the key is held equal by
patching `pagerank._adj_log_size` to a constant (a helper, not the function under test). The
invariant assertion must fail on it. A harness that passes this case measures nothing
([[feedback_clean_corpus_hides_a_dead_gate]]). {#r3-body}

### R4: the verdict {#r4}

The implementation summary carries: the table of [[#r1]] with its three recorded columns; S; K;
V with its inputs; the verdict, read from [[#bands-table]]. If K + S is 1 or more, a row is
added to the bug registry (id from the lead), naming each stale operation, and this spec's
probes are its RED. The plan's D11 row gets the verdict and the date. {#r4-body}

## Acceptance criteria {#acceptance}

- **AC-1: the writer census is complete.** Every site R0 item 3 lists is in [[#r1-table]] or in
  the exclusions. Proven by `test_writer_census_matches_probe_table`: it runs the family and
  fails on a site with neither; the family's synthetic module (a planted `entity_links` writer
  in a temp copy of a module) fails it by name. {#ac-1}
- **AC-2: every probe ran and recorded.** 22 rows or more, none skipped. A probe that errors
  before its comparison is reported as `not-run` and counted in K. Proven by the test file's own
  result table, written to `workflow/review-output/task-30.0/probe-table.json`. {#ac-2}
- **AC-3: the probes that find a stale path are RED at the base sha**, and the red run is
  recorded (`workflow/review-output/task-30.0/red.log`) with the E line of each. A probe that is
  green is listed as green; nothing is marked expected-to-fail. {#ac-3}
- **AC-4: the lag probe ran**, RED or green, recorded the same way. {#ac-4}
- **AC-5: the planted case fails the invariant** ([[#r3]]). Proven by
  `test_probe_detects_a_planted_stale_tier`, which asserts the invariant assertion raises. {#ac-5}
- **AC-6: V is computed from counts**, the script and its output are committed, and the output
  contains no prompt text (a test greps it for the `body` field and for any line over 200
  characters). {#ac-6}
- **AC-7: the verdict is the table's.** The summary's verdict equals the row of
  [[#bands-table]] its K + S and V select. {#ac-7}
- **AC-8: no source change.** `git diff --stat <base> <final>` lists no file under `src/`. {#ac-8}

## Test strategy {#test-strategy}

- **This task is characterization plus RED.** The code under test exists. The probes are
  written against the invariant; the ones that fail are the RED for 30.3, whatever 30.3 does.
- **Mutations.** There is no implementation to mutate. The planted case of [[#r3]] is the proof
  that the harness can fail; a second planted case removes one edge with the key held equal, so
  that the comparison is shown to see a removal as well as an addition.
- **Mocks.** None of the store. The planted cases patch `_adj_log_size`, a helper; this is
  classified in `workflow/test_mock_registry.md`.
- **Outcome measures, not clocks.** K, S and the three recorded columns are counts and
  equalities. V uses two medians from committed logs (the report's and 30.2's R0), each with its
  n and p90 beside it.
- **All output to files** under `workflow/review-output/task-30.0/`.
{#test-strategy-list}

## Files {#files}

| File | Change |
|---|---|
| `tests/test_adjacency_disk_tier_probe.py` | new: P1-P22, the lag probe, the two planted cases, the census check |
| `tests/census/adjacency_writers.py` | new: R0 item 3's census family, on 29.3's kit |
| `workflow/measurements/plan-30-disk-tier/consumers.py`, `consumers.out` | new: V's count |
| `workflow/test_mock_registry.md` | the `_adj_log_size` patch |
| `workflow/bug_registry.md` | a row, if K + S is 1 or more |
| `workflow/plans/plan-30-materialisation.md` | D11's verdict |
| `workflow/implementation_summaries/task-30.0-disk-tier-probe.md` | new |
{#files-table}

## Out of scope {#out-of-scope}

- Changing `cached_adjacency`. That is 30.3.
- The in-process tier (the cache on the `Store` instance). Its contract is the write-batch
  boundary (`Store._invalidate_content_rank_caches`), and 30.2 tests it.
- Auditing whether any live store was ever served a stale graph. The tier's content is not
  recoverable history.
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **The invariant is tested, not the key.** A probe asks what a fresh process is served. That
  keeps the tests meaningful under drop, re-key and keep.
- **V is an upper bound on purpose.** The real hit rate cannot be read back from the logs (the
  log's size at each call was never recorded). A bound in the tier's favour means a drop
  verdict is safe.
- **`scan-prompt` is not counted in V.** After 30.4 it reads the daemon's graph. Counting it
  would value the tier for a consumer that is leaving it.
- **A probe that cannot run counts against the tier.**
{#decisions-list}
