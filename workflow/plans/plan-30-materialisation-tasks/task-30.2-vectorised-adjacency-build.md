---
gmd: "0.1"
id: task-30.2-vectorised-adjacency-build
title: "Task 30.2: the vectorised adjacency build — build_adjacency builds the CSR with numpy in one canonical order, the dict builder becomes a test oracle, and the per-call rebuild sites read the cache"
tags: [task, plan-30, adjacency, csr, numpy, pagerank, ppr, scan-prompt, derive-pass]
metadata:
  node_type: task
  status: pending
  plan: plan-30-materialisation
  created: 2026-11-14
  updated: 2026-11-15
---

# Task 30.2: the vectorised adjacency build {#root}

> Plan: [[plan-30-materialisation]] ([[plan-30-materialisation#t2]])
> Status: Pending
> Depends on: [[task-30.1-adjacency-mapping-adapter]] (the CSR must be a mapping before it is
> the only adjacency). plan-29 released (the derive digest, the census kit).
> Followed by: [[task-30.3-disk-tier-fate]], then [[task-30.4-daemon-adjacency-ppr-op]].
> Ships in release B with 30.1 and 30.3: it edits `pagerank.py`, a derive-pass file
> ([[plan-30-materialisation#releases]]).
> User gates: release B's re-derive (plan-30 D2).
> Revised 2026-11-15 after ch-bsd r1 and ruling L116 ([[#rev-note-2]]).

rel: part-of -> [[plan-30-materialisation]]
rel: implements -> [[plan-30-materialisation#t2]]
rel: depends-on -> [[task-30.1-adjacency-mapping-adapter]]
rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[tdd-governance]]
rel: derives-from -> [[perf-bitmap-materialisation-2026-11-14#q1]]
rel: evidence-for -> [[task-30.4-daemon-adjacency-ppr-op]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]

## Why {#why}

`pagerank.py::build_adjacency` takes 1.36 s, of which the measured phases (two queries and the
fragment walk) are 0.18 s; by subtraction about 1.2 s is the loop that adds one edge at a time
to a dict of dicts, which the report did not profile on its own. `CSRAdjacency.from_dict` then
spends 195 ms turning the result into arrays. A numpy build over the fragment's array and the typed rows produced the same
116,552 nodes and 1,888,764 directed edges, with a maximum weight difference of 0, in 506 ms
([[perf-bitmap-materialisation-2026-11-14#q1]]). The dict costs 196 MB; the CSR 40 MB. {#why-cost}

Every miss pays the build: `cached_adjacency` cold, the context degree walk, the PageRank pass,
and the four call sites that never use the cache. This task changes the builder and points
those four at the cache. After it, the installed hook's rerank costs one build per prompt, about
0.5 s where it costs 1.3 s. 30.4 removes the rest. {#why-effect}

## The graph model, unchanged {#model}

The build is rewritten. What it builds is not. For the store's bound partition:

1. **Operational exclusion.** With `exclude_operational`, every entity of any kind and any
   partition whose name matches `^(session|digest)[-_]`, case-insensitive, is dropped with
   every edge that touches it.
2. **Mention edges.** Every bit of the partition's `mentions` fragment is an edge (concept,
   entity) of weight 1.0. In mode `weighted` there are none.
3. **Typed edges.** Every `entity_links` row whose two ends are both in the partition, with
   weight `link_weight × |weight|`, a NULL weight counting as 1.0. In mode `flat` the rows of the
   `mentions` linkage are left out, because step 2 already counted them.
4. **`denotes` folds.** A `denotes` row is not an edge. A typed row of a non-term linkage whose
   entity side is a concept that denotes one or more targets is credited to those targets, the
   weight split evenly.
5. Self-loops and non-positive weights are dropped. Parallel edges sum. The graph is
   undirected: each edge is stored in both rows.
{#model-list}

**New: one canonical order.** Rows are in ascending node id, and each row's neighbours are in
ascending id. Today the order follows `entity_links`, which is read without `ORDER BY`
([[perf-bitmap-materialisation-2026-11-14#q1]]). {#model-order}

## Requirements {#requirements}

### R0: baseline, and the memory bands {#r0}

1. Re-resolve symbols at the base sha. Read what 29.3's broad-except census left in
   `build_adjacency` and in each caller's handler ([[task-29.3-converge-shapes#c-pass-rows]]).
2. Re-run [[#census]].
3. **Measure the base**, with `workflow/measurements/plan-30-adjacency-build/measure.py`, on a
   throwaway copy of a read snapshot under a short temp root, opened read-only (the lead
   supplies the copy): build time and `from_dict` time (median, p90, n of 7 or more, two runs
   minutes apart, the 1-minute load printed at each end); **peak memory** of one build in a fresh
   process (`tracemalloc` peak and the `ru_maxrss` delta); nodes and directed edges.
4. **Memory bands, stated now.** The dict build peaks at 272 MB traced today
   ([[perf-bitmap-materialisation-2026-11-14#q1]]), and the daemon already runs it, briefly.
   30.4's service is not brief: it holds an entry per live key for as long as the key is live,
   and builds one more beside them. So the band is on the sum, not on one build:

   **T = K × E + P**, where E is one entry's bytes (the CSR's arrays, its index and the node
   array, measured by item 3 on the production-scale copy), K is 30.4's cap on live keys
   (`RMX_ADJ_MAX_KEYS`, default 2), and P is one build's peak traced memory, the inputs it read
   included.

   | T | Action |
   |---|---|
   | at or under today's dict-build peak, re-measured in item 3 | go; 30.4 builds in the daemon process |
   | above it, up to 400 MB | P's temporaries are reduced (item 3's script lists the largest live arrays at the peak), or K is lowered to 1, and it is re-measured; go only once T is under today's peak |
   | above 400 MB after that | no-go for an in-daemon build; 30.4 takes the out-of-process variant its spec names, and the daemon then holds K × E only, which must itself be under today's peak |
   {#r0-memory-bands}

   From the report's numbers, before re-measuring: E is about 40 MB, so K × E is about 80 MB;
   P is not measured. Release B alone holds no entry (K = 0); the band binds release C.
5. Record the fixture's golden rankings with the ORACLE adjacency ([[#r3]]), for [[#ac-3]].

### R1: the build {#r1}

`build_adjacency(store, *, link_weight=2.0, exclude_operational=True) -> CSRAdjacency` builds
[[#model]] with numpy: the `mentions` fragment through `to_array()`, the typed rows as arrays,
one sort, one reduction of parallel edges. All three values of `RMX_ADJ_MENTIONS` are
implemented. Both backends are supported: the rows are fetched as arrays on DuckDB and converted
from the fetched rows on SQLite. An empty partition gives an empty `CSRAdjacency`. {#r1-body}

`pagerank._ADJ_SHAPE` changes, because the row order is part of the shape: a cached adjacency
in the old order must not be served as the new one. {#r1-shape}

**Two steps.** The build is `assemble_adjacency(read_adjacency_inputs(store, …))`:
- `read_adjacency_inputs(store, *, link_weight, exclude_operational)` does every read of the
  store and returns one object: the `mentions` fragment's values, the typed rows as arrays, the
  operational ids, the linkage ids it resolved (or their absence), and the parameters. It is
  where [[#r2]]'s failures raise.
- `assemble_adjacency(inputs)` touches no store. It is a pure function of that object.
- `build_adjacency` is their composition and nothing else.
This is the build's own structure, used in this release: the targeted cases of [[#ac-1]] that
no ingest produces are driven through `assemble_adjacency` directly. It is also the seam 30.4
needs: its service reads the inputs at every publish and assembles only when they differ, and
it must read exactly what the build reads. {#r1-two-steps}

### R2: a failed read raises {#r2}

The base build has six handlers that turn a failed read into a smaller graph: the operational
query, the fragment load, three linkage-id lookups (`mentions`, `denotes`, each term linkage)
and the typed-rows query. A reader cannot tell
"no typed edges" from "the query failed".

- A linkage TYPE that does not exist in the store (`denotes` on an old store, `mentions` on an
  empty one) is a defined state: that linkage contributes nothing. It is detected by asking
  whether the type exists, not by catching.
- Any other failure propagates from `build_adjacency`. `cached_adjacency` then caches nothing.
- **The rerank's failure is named** ([[#r5]]).

### R3: the dict builder becomes the oracle {#r3}

- The base sha's `build_adjacency` body is copied verbatim to `tests/oracles/adjacency_dict.py`
  as `oracle_build_adjacency`, with a header naming the sha it was copied from, by
  `ch-test-engineer`, in the RED commit. It is frozen: a later change to [[#model]] changes the
  oracle in the same commit, deliberately.
- `CSRAdjacency.from_dict` has no caller in `src/` after this task. It moves to the same test
  module (`csr_from_dict`), and 30.1's tests are re-pointed in the RED commit. `src/` keeps no
  code that only tests call.

### R4: the callers {#r4}

| Caller | After this task |
|---|---|
| `ppr.py::rank_related_for_prompt`, `ppr.py::rank_related`, `enrich.py::enrich_concepts`, `net.py::build_net`, when `adj` is `None` | `cached_adjacency(store, link_weight=link_weight)` |
| `context.py`'s degree walk | unchanged: `cached_adjacency(s)` |
| `pagerank.py::compute`, `daemon.py::_op_pagerank` | `build_adjacency`, every time: the derive pass must see the current graph, never a cached one |
| `pagerank.py::pagerank` | given a `CSRAdjacency`, builds its sparse matrix from the CSR's arrays, with no per-edge Python loop; the pure-Python fallback reads the mapping surface |
| `pagerank.py::cached_adjacency` | calls the new build; no `from_dict`; **serves the instance cache only while the store has no unflushed fragment** (`Store.has_dirty_fragments()` is false) |
{#r4-table}

The dirty check closes one hole the wider use opens: four more callers now read a cache whose
only invalidation is `Store._invalidate_content_rank_caches`, called at `flush_fragments`. A
store that has linked and not flushed must not be served the graph from before the link.
{#r4-dirty}

### R5: a rerank that did not run says so {#r5}

`scan.py::_ppr_rerank`, `_enrich_rerank` and `_net_rerank` catch every exception and return the
salience order, so that the hook never goes dark. That stays. What changes: each reports the
failure through a list the caller passes in, the way `reranker.shared_reranker` reports through
`why`. `scan_prompt` then:

- puts `{"mode": <rank>, "ran": false, "reason": <type and message>}` in `trace["rerank"]`
  (`"ran": true` otherwise), and `scan_prompt_cmd` writes that object to the `query.log` row;
- adds one line to the text output, in the place the bundle warnings go:
  `# <rank> rerank did not run (<reason>); salience order kept`.

The installed hook discards stderr (`hooks.py` generates `2>/dev/null || true`), so a stderr
line would reach nobody on the path that matters. 30.4 adds the daemon path to the same object.
{#r5-body}

## Acceptance criteria {#acceptance}

Each AC says what it is at the base sha: **RED** (the test fails there, and the red run is
recorded), **characterization** (green there by construction, and proven able to fail by the
mutations named in [[#mutations]]), or **gate** (a check on the final tree). The fixture is
[[task-30.1-adjacency-mapping-adapter#fixture]]. {#acceptance-labels}

- **AC-1 (characterization, with one RED leg): the edge set equals the oracle's.** The oracle
  is the base body, so at the base the equality holds; mutations 1-11 are what prove the test
  can fail. The RED leg: the value `build_adjacency` returns is a `CSRAdjacency` (a dict at the
  base), and `assemble_adjacency(read_adjacency_inputs(store))` equals it (neither function
  exists at the base). On the fixture store and on the targeted stores
  below, for each of 3 mentions modes × `exclude_operational` true and false × `link_weight` 2.0
  and 1.0: the node sets are equal; the directed edge sets are equal; every weight is equal
  within 1e-12 relative. The number of weights that are not bit-equal is recorded (0 is
  expected; a non-zero count is reported, and AC-3 must still hold).
  Targeted stores: three parallel edges between one pair under different linkages; a negative
  weight; a NULL weight; a zero weight; a self-loop; a `denotes` fold onto one target and onto
  three; a term-linkage row into a denoting concept (not folded); an operational entity as a
  concept and as a doc; a typed row with one end in another partition; an empty store; a store
  with no `denotes` linkage type; a store with mentions only.
  Test: `test_vectorised_build_equals_oracle` in `tests/test_adjacency_build.py`. {#ac-1}
- **AC-2 (RED): the order is canonical.** Node ids ascend; each row's neighbour ids strictly ascend;
  two builds from two fresh `Store` opens give byte-equal arrays. Test:
  `test_build_order_is_canonical_and_repeatable`. {#ac-2}
- **AC-3 (characterization): rankings are identical.** The golden is recorded with the oracle,
  so the base passes; mutations 1-11 and 14 prove it can fail. For every seed set, with the hook's parameters:
  `rank_related_for_prompt` over the new CSR returns the ids of R0's golden in the same order,
  with scores within 1e-9 relative; the count of bit-equal results is recorded (the report had
  18 of 18). `enrich_concepts` returns the same ids with scores within 1e-9. `net_concepts`
  returns the same (id, support) pairs, and the same list on two fresh builds. Test:
  `test_rankings_identical_to_oracle`. {#ac-3}
- **AC-4 (gate): the PageRank prior did not move.** `scripts/derive-digest.py check` exits 0, all four
  legs. A differing prior leg stops the task: it is a finding, and the golden is not
  re-recorded to pass. {#ac-4}
- **AC-5 (RED): a failed read raises, and the hook says so.** With the typed-rows query made to fail
  (fault injected at the store's connection, classified in the mock registry):
  `build_adjacency` raises; `cached_adjacency` raises and a following call builds again;
  `scan_prompt(rank="ppr")` still returns its bundles, in salience order, with the line of
  [[#r5]] and `trace["rerank"]["ran"]` false. With no `denotes` type in the store nothing
  raises. Tests: `test_failed_read_raises`, `test_rerank_failure_is_named`. {#ac-5}
- **AC-6 (RED): the callers read the cache; the pass does not.** With `build_adjacency` counted by a
  wrapper: two `rank_related_for_prompt` calls on one store with no write between cost 1 build;
  the same for `rank_related`, `enrich_concepts` and `build_net`; after a link with no flush, a
  call builds again and does not store the result; after `flush_fragments()` one build serves
  the next two calls; `compute` and the `pagerank_compute` op build on every call. Test:
  `test_who_builds_and_who_reads_the_cache`. {#ac-6}
- **AC-7 (RED): no test-only code in `src/`.** `CSRAdjacency` has no `from_dict`; nothing under
  `src/refmatrix` builds a dict-of-dicts adjacency (a census family on 29.3's kit, with a
  planted site that fails it). {#ac-7}
- **AC-8 (measurement): on a production-scale copy.** [[#r0]] item 3's script, re-run on the
  same copy: nodes and directed edges equal the oracle's on that copy; the build's median is at
  most half of the base's build-plus-`from_dict` median from the same session (the report:
  0.32); E and P are recorded, and T, with K = 2, is placed in a row of [[#r0-memory-bands]]
  (a row other than go does not stop release B, which holds no entry; it is 30.4's input). Each number has its n, p90 and loads. {#ac-8}
- **AC-9 (characterization, with one RED leg): the hook's own path.** `rmx scan-prompt` run
  through the CLI entry against a throwaway store with a daemon stand-in publishing its
  snapshot, for the committed synthetic prompts (`tests/fixtures/adjacency/prompts.txt`;
  written for the fixture corpus, not taken from any log): the output is byte-equal to the base
  sha's for every prompt, and each invocation costs exactly one build (both true at the base
  for the default `--rank ppr`; mutations 1-11 change the output). Two RED legs: the
  `query.log` row of each invocation carries `rerank` with `ran: true` ([[#r5]]), where the
  base row has no such object; and with `--rank net`, on a prompt whose net comes back empty so
  that `_net_rerank` falls back to `_ppr_rerank`, the invocation costs one build, where the
  base costs two (mutation 14 makes it two again). Test: `test_scan_prompt_output_unchanged_one_build`. {#ac-9}
- **AC-10 (gate): the suite.** Equal by E line to the base run, apart from tests re-pointed in the RED
  commit, which are listed. {#ac-10}

## Mutations that must fail {#mutations}

Each alone, seen RED on the named AC, reverted in its own command, with `__pycache__` cleared
after the batch.

1. keep self-loops → AC-1.
2. keep the first of parallel edges, do not sum → AC-1.
3. store one direction only → AC-1.
4. drop the `abs()` → AC-1 (negative weight).
5. NULL weight counts as 0 → AC-1.
6. fold `denotes` on term linkages too → AC-1.
7. credit a fold with the whole weight to each target → AC-1.
8. scope the operational filter to the bound partition → AC-1.
9. mode `flat` keeps the `mentions` rows → AC-1.
10. mode `weighted` still adds the fragment's edges → AC-1.
11. include a typed row with one end in another partition → AC-1.
12. leave neighbours unsorted → AC-2.
13. swallow the typed-rows failure and return what was built → AC-5.
14. `rank_related_for_prompt` calls `build_adjacency` → AC-6.
15. `compute` reads `cached_adjacency` → AC-6.
16. `cached_adjacency` ignores the dirty check → AC-6.
17. `cached_adjacency`'s key drops `link_weight` → `test_cache_key_varies_by_params`.
18. `_ppr_rerank` drops the reason → AC-5.
{#mutations-list}

## Test strategy {#test-strategy}

- **RED first, by `ch-test-engineer`.** The tests named in [[#acceptance]] are written before
  any `src/` edit and run at the base sha; the red run is kept
  (`workflow/review-output/task-30.2/red.log`) with each test's E line. A test this spec marks
  characterization is recorded green at the base and says so. A test expected RED that passes
  at the base is a finding about the test.
- **GREEN by `ch-implementer`,** who writes no test.
- **Mutation gate.** The fix is committed before the first mutation. Each mutation of
  [[#mutations]] is applied alone, must FAIL its named test (a hang is not a failure), and is
  reverted in its own command; `__pycache__` is cleared after the batch; the fix is shown
  present after the last revert.
- **Test families are derived from imports** of the touched modules (29.4), and the merged dev
  tree runs them before the merge commit.
- **The oracle is test code** ([[#r3]]), copied in the RED commit and never imported by `src/`.
- **Mocks.** AC-5's fault at the connection and AC-6's counting wrapper, both on a
  collaborator of the function under test; classified in `workflow/test_mock_registry.md`.
- **Measurements** ([[#ac-8]]) are counts and medians with n, p90 and load, from two runs
  minutes apart. A single quiet run is not accepted.
- **All output to files** under `workflow/review-output/task-30.2/`.
{#test-strategy-list}

## Caller census {#census}

At `6676f39`. R0 re-runs it.

| Changed | Callers in `src/` | Tests that name it |
|---|---|---|
| `build_adjacency` (return type) | `pagerank.py::cached_adjacency`, `pagerank.py::compute`, `ppr.py::rank_related`, `ppr.py::rank_related_for_prompt`, `enrich.py::enrich_concepts`, `net.py::build_net`, `daemon.py::_op_pagerank` | `tests/test_adjacency_cache.py`, `tests/test_bug216_binding.py`, `tests/test_scan_prompt_expansion.py`, `tests/test_structural_signal.py`, `tests/test_v2_features.py` |
| `cached_adjacency` | `context.py`'s degree walk; after this task the four of [[#r4]] | `tests/test_adjacency_cache.py` (11 sites) |
| `CSRAdjacency.from_dict` (removed) | `pagerank.py::cached_adjacency` | `tests/test_adjacency_cache.py`, 30.1's tests |
| `pagerank.pagerank` | `pagerank.py::compute`, `daemon.py::_op_pagerank` | R0 lists |
| `read_adjacency_inputs`, `assemble_adjacency` (new) | `pagerank.py::build_adjacency`; in release C, 30.4's service | `tests/test_adjacency_build.py` |
| `pagerank.compute` | none found in `src/`; R0 confirms | `tests/test_v2_features.py`, R0 lists |
| `scan._ppr_rerank`, `_enrich_rerank`, `_net_rerank` (gain the reason list) | `scan.py::scan_prompt`; `_net_rerank` calls `_ppr_rerank` twice | `tests/test_scan_prompt_dedup.py` (5 sites); `eval/spike_hypertree/m4_render_tokens.py` (1) |
| `scan_prompt` (`trace["rerank"]`, the warning line) | `cli/session_cmds.py::scan_prompt_cmd`; R0 lists the eval callers | R0 lists |
{#census-table}

## Invalidation {#invalidation}

- The instance cache keeps its contract: dropped by `Store._invalidate_content_rank_caches` at
  `flush_fragments`. New: not served while the store has an unflushed fragment ([[#r4-dirty]]).
- Its key is unchanged apart from `_ADJ_SHAPE`.
- No new cache is added. The disk tier is 30.3's.
- **A known limit, characterised here and not fixed here.** An entity renamed into or out of
  the operational pattern, with no link written in the same batch, dirties no fragment, so
  nothing drops the instance cache until the next flush. `test_rename_only_batch_is_characterised`
  records what happens. If the cached graph is stale, the lead logs a registry row; the fix
  belongs with the BM25 caches that share the boundary.
{#invalidation-list}

## Files {#files}

| File | Change |
|---|---|
| `src/refmatrix/pagerank.py` | [[#r1]], [[#r2]], [[#r4]] |
| `src/refmatrix/ppr.py`, `src/refmatrix/enrich.py`, `src/refmatrix/net.py` | [[#r4]] |
| `src/refmatrix/scan.py`, `src/refmatrix/cli/session_cmds.py` | [[#r5]] |
| `tests/oracles/adjacency_dict.py` | new, in the RED commit ([[#r3]]) |
| `tests/test_adjacency_build.py`, `tests/fixtures/adjacency/prompts.txt` | new |
| `tests/test_adjacency_cache.py`, `tests/test_adjacency_mapping.py` | re-pointed in the RED commit |
| `tests/census/` | one family for AC-7 |
| `workflow/measurements/plan-30-adjacency-build/` | the script and its logs |
| `workflow/test_mock_registry.md` | AC-5's fault injection |
| `docs/PERFORMANCE.md` | the adjacency rows, with the measured numbers |
| `workflow/implementation_summaries/task-30.2-vectorised-adjacency-build.md` | new |
{#files-table}

`daemon.py::_op_pagerank` needs no edit if `pagerank.pagerank` accepts the CSR; R0 confirms.
`consolidate.py` is not edited: its docstring's reference to `build_adjacency` stays true.
{#files-notes}

## Risks {#risks}

- **A difference from the old build in a case the fixture lacks.** AC-1's targeted stores are
  the list of every branch in the old body; mutations 1-11 show each is tested. AC-8 compares
  on a production-scale copy.
- **Float sums in a new order.** Parallel edges are summed in sorted order, not arrival order.
  AC-1 records how many weights are not bit-equal; AC-3 and AC-4 hold the consequences.
- **`net`'s order among ties changes.** It was arbitrary (it followed an unordered query); it
  becomes repeatable. AC-3 states exactly what is compared.
- **A caller relied on a partial graph.** [[#r2]] makes that an exception; [[#r5]] and AC-5 show
  where it lands.
- **Peak memory in the daemon.** [[#r0-memory-bands]].
{#risks-list}

## Out of scope {#out-of-scope}

- The disk tier (30.3). The daemon's adjacency and the op (30.4).
- Narrowing or changing [[#model]].
- `scan-prompt`'s other legs (bug-182).
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **plan-30 D8: `build_adjacency` returns the CSR, and the dict builder survives only as the
  oracle.** Two production builders of one graph would drift. A frozen copy in `tests/` is the
  reference the equality needs and cannot be called by `src/`.
- **plan-30 D9: a failed read raises.** A smaller graph returned in silence changes every
  ranking built on it and tells nobody.
- **plan-30 D10: canonical order.** It makes the build repeatable, lets `pagerank` map
  neighbours to rows by search, and makes row lookups in `_NeighborView` a binary search. The
  one visible effect is `net`'s tie order.
- **The surfacing of a failed rerank lands here, not in 30.4,** because release B ships without
  30.4 and is the release in which a failed read starts to raise.
{#decisions-list}

## Revision note 2 (2026-11-15, ch-bsd r1 and ruling L116) {#rev-note-2}

| Finding ([[bsd-plan30-spec-r1]]) | Answered in |
|---|---|
| M1: AC-1, AC-3, AC-4, AC-9 and AC-10 were called RED and are green at the base by construction | [[#acceptance-labels]]: every AC is labelled. AC-1 and AC-9 are characterization with RED legs (the return type and the two-step equality; the `rerank` object in the row and the single build under `--rank net`); AC-3 is characterization; AC-4 and AC-10 are gates |
| S2 (30.4), the part that lands here: the memory band priced one build | [[#r0-memory-bands]]: the band is on T = K × E + P, live keys times entry bytes plus one build's peak; AC-8 records E, P and T |
| S2 (30.4), the part that lands here: rebuild only what changed | [[#r1-two-steps]]: the build is a read step and a pure assemble step, so 30.4 can compare inputs with the build's own read |
{#rev-note-2-table}
