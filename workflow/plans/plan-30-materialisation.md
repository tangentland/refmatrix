---
gmd: "0.1"
id: plan-30-materialisation
title: "Plan 30: adjacency and bitmap materialisation — a vectorised CSR adjacency the daemon keeps warm for the per-prompt rerank, the disk tier's fate by measurement, and a stateless bitmap row read"
tags: [plan, performance, adjacency, ppr, scan-prompt, bitmap, daemon, materialisation]
metadata:
  node_type: plan
  status: drafting
  created: 2026-11-14
  updated: 2026-11-15
---

# Plan 30: adjacency and bitmap materialisation {#root}

**Date:** 2026-11-14, revised 2026-11-15. **Status:** drafting: the plan and six task specs under
`workflow/plans/plan-30-materialisation-tasks/`, written by ch-architect on Fable 5.2. ch-bsd's
spec review r1 was DIRTY (0 BULLSHIT, 3 SKETCHY, 5 MEH; [[bsd-plan30-spec-r1]]); ruling L116
folded all eight, and [[#rev-note-2]] says where. The confirm-lite r2 was MEH-only (0 BULLSHIT, 0 SKETCHY, 4 MEH), GO
([[bsd-plan30-spec-r2]]); its four are folded ([[#rev-note-3]]). plan-30 D1-D3 are with the user.
Nothing here is approved until they are answered.
**Origin:** the user asked for "a plan for materialization changes" from the measurement report
[[perf-bitmap-materialisation-2026-11-14]], then "add the adjacency change too" (bug-243).
**Sequencing:** after plan-29. Plan-29 splits `cli.py` and `store.py` and adds the census kit, the
type gate and the derive digest this plan builds on ([[#depends]]).

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[bug_registry#registry]]
rel: derives-from -> [[perf-bitmap-materialisation-2026-11-14#recommendation]]
rel: related-to -> [[bsd-plan30-spec-r1]]
rel: related-to -> [[bsd-plan30-spec-r2]]
rel: catalogs -> [[task-30.0-disk-tier-probe]]
rel: catalogs -> [[task-30.1-adjacency-mapping-adapter]]
rel: catalogs -> [[task-30.2-vectorised-adjacency-build]]
rel: catalogs -> [[task-30.3-disk-tier-fate]]
rel: catalogs -> [[task-30.4-daemon-adjacency-ppr-op]]
rel: catalogs -> [[task-30.5-load-bitmap-row-read]]
rel: related-to -> [[feedback_go_no_go_ranges_not_predrop]]
rel: related-to -> [[feedback_measure_the_outcome_not_the_wall]]
rel: related-to -> [[feedback_measure_the_path_users_run]]
rel: related-to -> [[feedback_prefer_existing_infra]]
rel: related-to -> [[feedback_no_silent_failures]]

## Why {#why}

- **Every prompt rebuilds the whole graph.** The installed UserPromptSubmit hook runs
  `rmx scan-prompt` with the default `--rank ppr`. `ppr.py::rank_related_for_prompt` calls
  `pagerank.py::build_adjacency` directly: 1322 ms median per prompt, 389 prompts a week, against
  8.4 ms over a warm CSR with identical output on 18 of 18 seed sets (bug-243,
  [[perf-bitmap-materialisation-2026-11-14#q2]]). Live scan-prompt latency is p50 2818 ms.
- **The cache that exists cannot help it.** `cached_adjacency` returns a `CSRAdjacency`, which
  lacks the dict methods `overlay_prompt_clique` and `seed_coverage` use. Its disk tier is keyed
  on the size of `facts.log`, and a write fell between 365 of 390 consecutive prompts
  ([[perf-bitmap-materialisation-2026-11-14#q2]]). Whether that key can serve a stale graph was
  left open by the report.
- **`Store.load_bitmap` spends 6.5 ms to read a 30 µs row.** Measured for this plan
  ([[#baseline]]): 2.9 ms is `len(frag)` and 3.3 ms is a 65,536-container range mask. Every
  caller pays it: `match_concepts` on each prompt, `neighbors`, `topn`, the context bundles.
{#why-list}

## Measured {#baseline}

From [[perf-bitmap-materialisation-2026-11-14]] (dev tree at `e82233a`, a read-only copy of the
live read snapshot: partition `refmatrix`, 127,047 entities, 1,177,027 fragment bits), and from
this plan's own probe on the same copy (`workflow/measurements/plan-30-load-bitmap-2026-11-14/`,
clone at `6676f39`, two runs minutes apart at 1-minute loads 5.1 and 12.0).

| Measure | Value | Source |
|---|---|---|
| `build_adjacency` + `CSRAdjacency.from_dict` | 1559 ms (1364 + 195) | report `#q1` |
| vectorised CSR build prototype, same edge set | 506 ms; 116,552 nodes, 1,888,764 directed edges, max weight difference 0 | report `#q1` |
| per-prompt PPR rerank today / over a warm CSR | 1322 ms / 8.4 ms; outputs identical 18 of 18 | report `#q2` |
| CSR in memory / dict-of-dicts | 40.1 MB traced / 196 MB traced | report `#q1` |
| consecutive prompts with no write signal between | 25 of 390 | report `#q2` |
| `load_bitmap`, `mentions` row of 317 | 6.51 ms and 6.72 ms median (two runs) | this plan, `row_read.out`, `row_read.run2.out` |
| of which `len(frag)` (239,239 containers) | 2.90 ms and 3.00 ms | this plan |
| of which range mask build and free | 3.35 ms and 3.71 ms | this plan |
| stateless row read (no mask, no `len`) | 30.7 µs and 29.7 µs; 123,448 of 123,448 rows identical | this plan |
| 20 concepts × 34 linkages | 2224 ms → 2.56 ms, and 2233 ms → 2.61 ms | this plan |
| `neighbors` calls / PQL `TopN` calls in 7 days | 1 / 0 | report `#q3`, `#q6` |
{#baseline-table}

**One correction to the report.** Its row "`iter_equal_or_larger` scan: 2.80 ms" is the cost of
the `len(fr) == 0` guard its prototype kept, not of the iterator. `len()` of a `BitMap64` counts
every container. Without the guard the same read takes 30 µs on the same data. That changes the
choice in [[task-30.5-load-bitmap-row-read]]: the stateless read is as fast as the report's
decoded-array variant and needs no memory and no invalidation. {#baseline-correction}

Every task re-measures its own rows before and after. {#baseline-rule}

## What plan-30 depends on {#depends}

Plan-30 lands after plan-29 and is written against the tree plan-29 leaves.

- **Symbols, not lines.** Citations name symbols as they are at `6676f39`. Each task's R0
  re-resolves them at its base sha through `tools/split_maps/symbol_map.json`
  ([[task-29.5-split-giant-modules#r8]]). After 29.5: `Store.load_bitmap` and the fragment
  loaders are in `store_fragments.py`; `content_rank` and its caches are in `store_rank.py`; the
  `scan-prompt` command is in `cli/session_cmds.py`; `pagerank` is in `cli/query_cmds.py`
  ([[task-29.5-split-giant-modules#map-store]], [[task-29.5-split-giant-modules#map-cli]]).
  `daemon.py` and `pagerank.py` are not split.
- **`pagerank.py` is a derive-pass module.** A real edit to it makes the `pagerank` pass read
  `behind_code` on every fleet store, correctly ([[task-29.2-mypy-gate#r7-release]]). So every
  edit this plan makes to `pagerank.py` ships in ONE release, with one re-derive ([[#releases]]).
- **The derive digest** (`scripts/derive-digest.py`, [[task-29.2-mypy-gate#derive-digest]]) has a
  PageRank prior leg, rounded to 1e-9. It is 30.2's proof that the new build did not move the
  prior.
- **The census kit and the broad-except census** ([[task-29.3-converge-shapes#slice-k]]): new
  handlers here re-raise or count and surface; none is silent.
- **The type gate** (29.2): new signatures are annotated.
{#depends-list}

## Tasks {#tasks}

Each spec is authoritative over its summary here. {#task-specs}

### 30.0 Probe the disk tier {#t0}

Tests only. Can `adjacency.cache.npz` serve a graph that is not the store's? One probe per
graph-changing operation (purge, merge, rename, vacuum, repair, log compaction, slot merge) and
one for the lag between the writer's log and the read snapshot. The bands are stated before the
measurement; the verdict (drop, re-key or keep) is a row 30.3 reads.
Spec: [[task-30.0-disk-tier-probe]]. {#t0-summary}

### 30.1 A mapping adapter over the CSR {#t1}

`CSRAdjacency` and its row view become complete read-only mappings; `overlay_prompt_clique`
returns an overlay over any adjacency without copying it; `seed_coverage`, `enrich.walk`,
`net.build_net` and `pagerank.pagerank` are shown to give equal results on a dict and on a CSR.
No caller changes its source of adjacency yet. Spec: [[task-30.1-adjacency-mapping-adapter]].
{#t1-summary}

### 30.2 The vectorised build {#t2}

`build_adjacency` builds the CSR with numpy and returns it, in one canonical row order. The
dict builder becomes a test oracle. The five call sites that rebuilt per call read
`cached_adjacency`. Edge sets are equal to the oracle's in every mode; rankings are identical;
the derive digest's prior leg is equal. Spec: [[task-30.2-vectorised-adjacency-build]].
{#t2-summary}

### 30.3 The disk tier's fate {#t3}

Applies 30.0's verdict to `cached_adjacency`, in the same release as 30.2. If the verdict is
drop, the tier's code is removed and the two files are deleted from each store by an announced
step. Spec: [[task-30.3-disk-tier-fate]]. {#t3-summary}

### 30.4 The daemon keeps the adjacency; the hook asks for the ranking {#t4}

A service in the daemon keeps the CSR in memory. After each snapshot publish it reads the
build's inputs from the published snapshot, off the store lock, and rebuilds a key only when
that key's inputs changed. A read op, `ppr_rank`, runs the same `rank_related_for_prompt` over
it and returns the ranking. `scan-prompt` asks the daemon first and falls back to its own in-process
build, and every fallback is counted and named. No new file is written. Fixes bug-243.
Spec: [[task-30.4-daemon-adjacency-ppr-op]]. {#t4-summary}

### 30.5 `load_bitmap` reads the row, statelessly {#t5}

`Store.load_bitmap` seeks to the row and reads it: no range mask, no `len()`. No derived state,
so no invalidation. Independent of the adjacency tasks. Its closing measurement re-times
`neighbors` and `topn` end to end, which is the evidence the deferred item below waits on.
Spec: [[task-30.5-load-bitmap-row-read]]. {#t5-summary}

## Order {#order}

30.0 ∥ 30.5 (independent; tests only, and one method) → 30.1 → 30.2 → 30.3 → 30.4. Each task
runs RED → GREEN → mutation → ch-bsd. {#order-list}

## Releases {#releases}

| Release | Holds | Edits a derive-pass file? | Store event |
|---|---|---|---|
| **A** | 30.5 | no (`store_fragments.py` is in no pass's set) | none |
| **B** | 30.1 + 30.2 + 30.3: every `pagerank.py` edit of the plan | yes: `pagerank.py` | the `pagerank` pass is re-derived on every partition of every fleet store, in one announced window ([[#decisions]] D2); the tier's files are deleted if the verdict is drop (D3) |
| **C** | 30.4 | no: 30.4 has an AC that its diff touches no file `_DERIVE_PASS_MODULES` names | none on disk; daemons restart as in any deploy |
{#releases-table}

- A may ship before or after B. C needs B.
- After B alone the hook's rerank costs one vectorised build per prompt (about 0.5 s against
  1.3 s). After C it costs one daemon call (about 8 ms warm, measured in-process; the op's own
  latency is 30.4's acceptance).
- 30.1 is not released alone: it changes no caller.
- Version numbers are the lead's, at each release.
{#releases-notes}

## Not doing {#not-doing}

- **Transposed fragments on disk** ([[perf-bitmap-materialisation-2026-11-14#q4]], recommendation
  6). Measured slower than what they would replace: a forward lookup takes 3.5-14.0 ms against
  0.41-0.86 ms for the `entity_links` query. They would also be 5.2 MB of new on-disk derived
  state, which needs a census of the merge, purge and slot paths (bug-105, bug-216, bug-227). No
  hot forward-lookup caller was found. If one appears, in-memory forward rows (2.9 µs, 195 ms to
  build) are the shape to measure. {#not-transposed}
- **A new on-disk copy of anything.** The daemon's adjacency is memory only. It dies with the
  process and is rebuilt from the published snapshot. {#not-on-disk}
- **A verb or MCP tool for `ppr_rank`.** It is transport for `scan-prompt`, which is a hook, not
  a capability an agent calls ([[task-30.4-daemon-adjacency-ppr-op#decisions]]). {#not-verb}

## Deferred, with a trigger {#deferred}

**Pre-split per-concept rows and filter bitmaps (noise, protected, kind, partition) in daemon
memory** (report recommendations 4 and 5) are not built by this plan. {#deferred-rows}

- **Why not now.** The report measured them against `load_bitmap` at 3-6 ms a call. 30.5 removes
  that cost with no state. `topn` today is about 123,000 `load_bitmap` calls; at 30 µs to
  0.3 ms a row that is seconds, not 462 s. The logs show 1 `neighbors` call and 0 `TopN` calls
  in 7 days. A cache with invalidation rules, built for one call a week, on a cost 30.5 is
  about to remove, is not justified by any number in hand.
- **The trigger.** Reopen when BOTH hold, read from [[task-30.5-load-bitmap-row-read#r5]]'s
  closing measurement and from 7 days of `query.log`: (1) after 30.5, `neighbors` at depth 2
  from a seed of in-degree 100 or more still has a median over 250 ms, or `topn` over 2 s; and
  (2) the path is called 20 or more times in 7 days, or a planned task names it as a per-prompt
  step. With (1) false there is nothing to buy; with (2) false nobody is waiting.
- **Where it is recorded.** A row in [[deferral_registry#registry]], owner plan-30, added with
  this plan.
{#deferred-list}

## Decisions {#decisions}

**For the user.** Each has a recommendation; none is taken. {#decisions-user}

1. **plan-30 D1: may the daemon answer `ppr_rank` from a graph that is one or more publishes
   behind?** A rebuild takes about 0.5 s after a write batch that changed the key's inputs.
   The question is about a service that is late. A service or a publish that has FAILED is not
   "behind": past the same bound it is `build-failed` and is said in the hook's output, under
   every option ([[task-30.4-daemon-adjacency-ppr-op#r4]]).
   - (a) **Recommended:** yes, bounded. The op waits up to 0.25 s for a build in flight; then it
     serves the newest finished graph if it was superseded at most 10 s ago, and the reply says
     how far behind it is; past that it answers `unavailable` and the hook builds in-process.
   - (b) Never behind: wait for the build up to the caller's deadline, else `unavailable`.
   - (c) Never behind and never wait: any pending build means `unavailable`.
   - Why (a): the rerank is a heuristic over a graph that already lags the writer by the snapshot
     debounce; (b) adds up to 0.5 s to the prompts that follow a write, which is most of them
     (365 of 390); (c) sends those same prompts to the 0.5 s in-process build.
2. **plan-30 D2: release B re-derives the `pagerank` pass on every fleet store.** It is a
   store-changing release, outside the standing go.
   - **Recommended:** go, in one announced window, run by the lead, checked as
     [[task-29.2-mypy-gate#r7-release]] step 4 checks it (stamp time moved; no `behind_code`).
     About 2 s per partition.
   - The alternative, leaving `behind_code` until each store's next reingest, breaks ruling
     L109's rule that `behind_code` from a release is allowed only inside its window.
3. **plan-30 D3: if 30.0's verdict is drop, delete `adjacency.cache.npz` and
   `adjacency.cache.json` from every fleet store at release B.** About 29-33 MB per store.
   - **Recommended:** yes, by the lead, announced, each file counted and named.
   - The alternative is to leave the orphans. Nothing would read them.
{#decisions-user-list}

**Taken in the specs** (registered here; each has its reasons in the owning spec).
{#decisions-spec}

4. **plan-30 D4:** pre-split rows and filter bitmaps are deferred with the trigger in
   [[#deferred]].
5. **plan-30 D5:** the hook asks the daemon for the ranking and keeps an in-process fallback
   ([[task-30.4-daemon-adjacency-ppr-op#decisions]]). This puts one bounded daemon read on the
   prompt path again; the bounds that keep it from repeating bug-115 and bug-116 are ACs.
6. **plan-30 D6:** the graph version is the daemon's snapshot publish sequence; the service
   rebuilds from the published snapshot, never from the writer
   ([[task-30.4-daemon-adjacency-ppr-op#decisions]]). A test holds a write unpublished and
   shows it is not in the served graph ([[task-30.4-daemon-adjacency-ppr-op#ac-17]]).
7. **plan-30 D7:** `load_bitmap` uses the stateless iterator, not a decoded array per linkage
   ([[task-30.5-load-bitmap-row-read#decisions]]).
8. **plan-30 D8:** `build_adjacency` returns the CSR; the dict builder lives on only as a test
   oracle ([[task-30.2-vectorised-adjacency-build#decisions]]).
9. **plan-30 D9:** a failure to read the graph raises from the builder; it no longer returns a
   partial graph ([[task-30.2-vectorised-adjacency-build#decisions]]).
10. **plan-30 D10:** rows of the CSR are in ascending node order with ascending neighbours, so
    `net`'s order among equal-support nodes becomes deterministic
    ([[task-30.2-vectorised-adjacency-build#decisions]]).
11. **plan-30 D11:** the disk tier's fate follows 30.0's bands with no further question, except
    D3's deletion ([[task-30.0-disk-tier-probe#bands]]).
12. **plan-30 D12 (round 2):** a key is rebuilt only when its own inputs changed, decided by
    reading those inputs from the snapshot with the build's own read step, not by per-partition
    marks set on the write path ([[task-30.4-daemon-adjacency-ppr-op#r3-why-not-marks]]). Ruling
    L116 named per-partition versions; this keeps the purpose and changes the mechanism, for
    two reasons read from the code. **Accepted** by ch-bsd r2 ([[bsd-plan30-spec-r2]]) and by
    the lead (ruling L117, written on `master` at the merge).
13. **plan-30 D13 (round 2):** only the hook's op creates demand for a key, and at most 2 keys
    are live. A `context` degree walk reads a live key and never creates one
    ([[task-30.4-daemon-adjacency-ppr-op#r7]]).
{#decisions-spec-list}

## Risks {#risks}

| Risk | Where it is held |
|---|---|
| The new build differs from the old in an edge or a weight | 30.2: edge-set equality against the oracle in all three mentions modes; the derive digest's prior leg |
| A ranking changes | 30.1 and 30.2: identical ids and order on committed seed sets; 30.4: the daemon path and the in-process path give equal output on one snapshot |
| The hook waits on a busy daemon (bug-115, bug-116, bug-182) | 30.4: the op takes no store lock, carries a deadline, is dialled once with a 0.5 s budget; the worst case is bounded and measured under load |
| A rebuild in the daemon starves pings or grows the process past the jetsam line | 30.2's band is on live keys × entry bytes plus one build's peak; 30.4 caps live keys at 2, reads the daemon's resident memory against the band, and counts pings answered during rebuilds |
| Every publish rebuilds every key | 30.4 prices the service per key per publish, and assembles only when the key's inputs changed |
| A failed or foreign publish leaves the service silently behind | 30.4: the sequence's second counter moves in a `finally`; a failed publish and a snapshot the daemon did not write are `build-failed`, recorded and said |
| A stale graph is served | 30.0 measures the disk tier, and each probe first proves the tier was written; 30.4's graph is versioned by publish sequence, the reply states it, and a test shows an unpublished write is not served |
| A fallback hides a failure | 30.4: every fallback is counted and named in the query row and in daemon status; a rerank that did not run puts a line in the hook's output |
| `pagerank.py` is edited in two releases | [[#releases]]: 30.4's AC forbids it |
{#risks-table}

## Constitution check {#constitution-check}

| Principle | How the plan holds it |
|---|---|
| [[constitution#concrete]] | nothing in `src/` is a stub; the old builders move to `tests/oracles/`, not kept beside the new ones. One thing ships ahead of its `src/` caller: the `adj` parameter 30.1 adds (the equality tests hand in the oracle's graph through it) gets its production caller, the op, in 30.4 |
| [[constitution#project-1]] one writer | the adjacency service reads the published snapshot only and never opens or locks the writer (30.4 AC-4) |
| [[constitution#project-2]] no silent failures | a failed graph read raises (30.2 R2); a rerank that did not run and a fallback that was taken are counted and named (30.2 R5, 30.4 R6); the disk tier's two silent handlers go (30.3) |
| [[constitution#project-3]] verbs first | no new capability for an agent; `ppr_rank` is transport for a hook ([[#not-verb]]) |
| [[constitution#project-4]] hooks are generated | the generated hook command does not change (30.4 AC-11) |
| [[constitution#project-5]] measure the path users run | the hook is measured through the CLI entry (30.2 AC-9, 30.4 AC-11), the eval harness runs the same function (30.4 AC-15), and production-scale numbers are taken twice or more under load |
| [[constitution#project-6]] supervisors | pings are counted during rebuilds (30.4 AC-8) |
{#constitution-check-table}

## Could not be settled here {#open}

- The op's latency through the socket and the cli pool under load. The 8.4 ms figure is an
  in-process prototype. 30.4's R0 measures it and has bands.
- The vectorised build's peak memory and an entry's size. The report did not measure the
  first. 30.2's R0 measures both, with bands on their sum that decide whether 30.4 may build
  inside the daemon process.
- What the input check costs beside a full build. 30.4's R0 measures it, with a band that
  turns the check off if it is over a quarter of the build.
- Why the live store's `adjacency.cache.json` was last written on 2026-11-13 16:35 with a key
  that predates the shape element, while `facts.log` grew by 149 MB. Observed on 2026-11-14;
  the cause is not established. 30.0's R0 reads it.
{#open-list}

## Revision note 2 (2026-11-15, ch-bsd r1 and ruling L116) {#rev-note-2}

All eight findings of [[bsd-plan30-spec-r1]] are folded. Each touched spec has its own table.

| Finding | Task | Answered in |
|---|---|---|
| S1: "never the writer" untested | 30.4 | [[task-30.4-daemon-adjacency-ppr-op#ac-17]]: a write held unpublished is not in the entry; a census of writer access with an empty allow list; mutation 1 re-aimed. The op's own reads take `writer="never"` |
| S2: one key priced, every key rebuilt | 30.4, 30.2 | the replay and the band are per key per publish ([[task-30.4-daemon-adjacency-ppr-op#r0]]); a key is assembled only when its inputs changed ([[task-30.4-daemon-adjacency-ppr-op#r3-inputs]], [[task-30.4-daemon-adjacency-ppr-op#ac-18]]); live keys capped at 2, and a degree walk creates no demand; 30.2's band prices the steady state ([[task-30.2-vectorised-adjacency-build#r0-memory-bands]]) |
| S3: a publish failing after `begin` | 30.4 | `end` in a `finally`, at most 3 opens, a failed publish is `build-failed` and said ([[task-30.4-daemon-adjacency-ppr-op#r2]], [[task-30.4-daemon-adjacency-ppr-op#ac-20]]) |
| M1: RED labels on tests green at the base | 30.2, 30.5, 30.4 | every AC in the three specs is labelled RED, characterization, gate or measurement; 30.2 AC-1 and AC-9 gain RED legs; 30.4 AC-12 is a gate with a planted failing input |
| M2: two reasons unclassified | 30.4 | [[task-30.4-daemon-adjacency-ppr-op#r6-table]]: `names-unavailable` and `partition-unknown` are said, each with its reason; the test fails on a reason with no row |
| M3: a probe could pass on a tier that never wrote | 30.0 | each probe asserts the tier was written; a failed write is `not-run` and counts in K ([[task-30.0-disk-tier-probe#r1-no-swallow]]) |
| M4: bug-243's status against 29.1's grammar | registry | the cell reads `scheduled → task-30.4-daemon-adjacency-ppr-op (P30); …`. The lead amends 29.1's track rule to `P<n>` at the plan-30 merge |
| M5: a snapshot writer outside the daemon | 30.4 | a census of every writer of the snapshot file, with 29.3's slice d as a checked precondition for the one outside the daemon; a foreign snapshot is detected at run time ([[task-30.4-daemon-adjacency-ppr-op#r8]], [[task-30.4-daemon-adjacency-ppr-op#ac-21]]) |
{#rev-note-2-table}

**One departure from the ruling's wording** (plan-30 D12). L116 asks that only keys whose
partition was written be rebuilt, by per-partition versions. The specs do rebuild only those
keys, and decide it by reading each key's inputs from the published snapshot. A version bumped
by the write path would be wrong in two ways the base code shows: the request for a snapshot is
made after the store lock is released, so a publish can carry a write before its mark arrives;
and a partition's graph is written under other partitions' bindings too.
{#rev-note-2-departure}

**plan-30 D1, D2 and D3** are unchanged in substance. D1's text now says that a failed service
or publish is never answered as "behind". {#rev-note-2-decisions}

## Revision note 3 (2026-11-15, ch-bsd r2: GO with four MEHs) {#rev-note-3}

| Finding ([[bsd-plan30-spec-r2]]) | Task | Answered in |
|---|---|---|
| M1: digest before the operational filter | 30.4, 30.2 | the digest is of the effective edges, after the fold and the filters ([[task-30.4-daemon-adjacency-ppr-op#r3-inputs]]); 30.2 names that stage |
| M2: census scope; `partition=None` reaches the writer's binding | 30.4 | scope stated; `partition` required in `open_snapshot_store` and in the op ([[task-30.4-daemon-adjacency-ppr-op#ac-17]]) |
| M3: which service time the 2% band reads | 30.4 | the replay's worst case ([[task-30.4-daemon-adjacency-ppr-op#r0]]) |
| M4: AC-4's leg answered `building` | 30.4 | the entry is built first ([[task-30.4-daemon-adjacency-ppr-op#ac-4]]) |
{#rev-note-3-table}

plan-30 D12 is accepted (ch-bsd r2; lead, ruling L117). plan-30 D1, D2 and D3 are open, with the
user. {#rev-note-3-decisions}
