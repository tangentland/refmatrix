---
gmd: "0.1"
id: task-30.1-adjacency-mapping-adapter
title: "Task 30.1: a mapping adapter over the CSR adjacency — CSRAdjacency and its row view become read-only mappings, the prompt clique becomes an overlay, and every walker gives equal results on a dict and on a CSR"
tags: [task, plan-30, adjacency, csr, ppr, mapping, overlay, scan-prompt]
metadata:
  node_type: task
  status: pending
  plan: plan-30-materialisation
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 30.1: a mapping adapter over the CSR adjacency {#root}

> Plan: [[plan-30-materialisation]] ([[plan-30-materialisation#t1]])
> Status: Pending
> Depends on: plan-29 released. No plan-30 task (30.0 and 30.5 run beside it).
> Followed by: [[task-30.2-vectorised-adjacency-build]], which makes the CSR the only adjacency.
> **Not released alone.** It edits `pagerank.py`, a derive-pass file, so it ships in release B
> with 30.2 and 30.3 ([[plan-30-materialisation#releases]]).
> User gates: none.

rel: part-of -> [[plan-30-materialisation]]
rel: implements -> [[plan-30-materialisation#t1]]
rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[tdd-governance]]
rel: derives-from -> [[perf-bitmap-materialisation-2026-11-14#q2]]
rel: related-to -> [[task-30.4-daemon-adjacency-ppr-op]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: reinforces -> [[feedback_check_the_sibling_condition]]

## Why {#why}

Four of the five places that rebuild the adjacency on every call do so because the cached form
cannot do what they need ([[perf-bitmap-materialisation-2026-11-14#q2]]):

- `ppr.py::overlay_prompt_clique` starts with `dict(adj)`;
- `ppr.py::seed_coverage` does `set(adj.get(n, {}))`, which iterates a row's keys;
- `net.py::build_net` iterates `adj.get(cid, {})`;
- `pagerank.py::pagerank` needs `adj.keys()` and `adj.items()`.

`pagerank.py::CSRAdjacency` has `in`, `[]`, `get` and `len`; its row view `_NeighborView` has
`items`, `values` and `len`. Neither can be iterated. {#why-list}

This task gives the CSR the missing read surface and proves, walker by walker, that results on a
dict and on a CSR are equal. It changes no caller's source of adjacency: that is 30.2. Doing the
adapter first means it is tested against today's dict as the oracle, before the builder moves.
{#why-order}

## Requirements {#requirements}

### R0: baseline {#r0}

1. Re-resolve every symbol named here at the base sha ([[task-29.5-split-giant-modules#r8]]).
   29.3 may have renamed `pagerank._OPERATIONAL_RE` ([[task-29.3-converge-shapes#c-pass-rows]]).
2. Re-run the caller census of [[#census]] and put the counts beside the ones below.
3. Record, on the fixture store of [[#fixture]]: nodes, directed edges, and for each committed
   seed set the output of `rank_related_for_prompt` with the hook's parameters. That is the
   golden the equalities compare against.

### R1: `CSRAdjacency` and `_NeighborView` are read-only mappings {#r1}

Both subclass `collections.abc.Mapping`.

- `_NeighborView`: `__iter__` yields the neighbour ids as Python ints; `__getitem__(v)` returns
  the weight to `v` and raises `KeyError` when there is no such edge; `__contains__`;
  `keys()`, `items()`, `values()`, `get()`, `__len__`. `values()` keeps returning something
  `sum()` accepts.
- `CSRAdjacency`: `__iter__` yields the node ids in row order; `keys()`, `items()`, `values()`.
- **`CSRAdjacency.get(u)` returns `None` for a missing node, as a dict does.** Today it returns
  an empty view when `default` is `None`. [[#census]] lists every `.get(` on an adjacency in
  `src/`; each passes `{}` or tests the result for truth, so none depends on the old answer.
- Neither class gains a method that writes.
- `dict(adj)` on a `CSRAdjacency` works and is a shallow copy whose values are views.

### R2: the prompt clique is an overlay {#r2}

- `ppr.py` gains `OverlayAdjacency(base, rows)`: a `Mapping` that answers from `rows` for the
  nodes it holds and from `base` otherwise. Its length and iteration are the base's. It holds a
  reference to `base` and copies nothing from it.
- `overlay_prompt_clique(adj, seeds, weight=...)` returns an `OverlayAdjacency` whose `rows`
  holds one plain dict per present seed: that seed's base row plus `weight` to every other
  present seed. With `weight <= 0`, fewer than two seeds, or fewer than two present, it returns
  `adj` itself, as today.
- The caller's `adj` is not changed. For a dict base that is today's contract
  (`test_clique_does_not_mutate_the_caller_adjacency`); for a CSR it holds by construction.
- **No whole-graph pass.** Building the overlay, `seed_coverage`, and the walk over the overlay
  touch only the rows the walk visits. [[#ac-4]] proves it with a base that refuses iteration.

### R3: the walkers accept an adjacency {#r3}

`ppr.rank_related`, `ppr.rank_related_for_prompt`, `enrich.enrich_concepts` and `net.build_net`
gain a keyword `adj=None`. Given an adjacency, they use it; given `None`, they do what they do
at the base sha. `net.net_concepts` passes it through. No call site in `src/` passes it in this
task. 30.2 and 30.4 do. {#r3-body}

### R4: one annotation {#r4}

A type alias for "a read-only adjacency" (`Mapping[int, Mapping[int, float]]`) lives beside
`CSRAdjacency` and annotates the `adj` parameters of R3, `local_push_ppr`, `seed_coverage`,
`overlay_prompt_clique`, `enrich.walk` and `pagerank.pagerank`. The comment on
`local_push_ppr`'s parameter that says "duck-typed" goes. {#r4-body}

## The fixture {#fixture}

A throwaway store under a short temp root, built through the production ingest path from the
derive digest's corpus (`tests/fixtures/derive_digest/`, [[task-29.2-mypy-gate#derive-digest]]),
with `denotes` edges and at least one operational (`session-…`) entity in it. A committed list
of seed sets by concept NAME (`tests/fixtures/adjacency/seed_sets.json`): 12 or more sets, of
sizes 1, 2, 3 and 6 or more, at least two with a seed absent from the graph, at least two whose
seeds share neighbours and two whose seeds share none. Names are resolved to ids at test time.
{#fixture-body}

## Acceptance criteria {#acceptance}

Each is RED at the base sha unless marked.

- **AC-1: the mapping surface.** For the fixture's dict `d` and `c = CSRAdjacency.from_dict(d)`:
  `list(c) == list(d)`; for every node `u`, `dict(c[u]) == d[u]` and `list(c[u]) == list(d[u])`;
  `c.get(missing) is None`; `c.get(missing, {}) == {}`; `c[u][v] == d[u][v]` for every edge and
  `c[u][not_a_neighbour]` raises `KeyError`; `isinstance(c, Mapping)`. Test:
  `test_csr_is_a_mapping_equal_to_its_dict` in `tests/test_adjacency_mapping.py`. {#ac-1}
- **AC-2: every walker is equal on both forms.** For every seed set, with `adj=d` and `adj=c`:
  `local_push_ppr` returns equal dicts; `seed_coverage` equal; `overlay_prompt_clique(...)`
  compares equal as mappings; `enrich.walk` equal; `net.build_net` equal in `net`, `core` and
  `prompt_core`; `pagerank.pagerank` equal to 1e-12 per node. Recorded as counts: sets equal of
  sets run, per walker. Test: `test_walkers_equal_on_dict_and_csr` (parametrised by walker).
  {#ac-2}
- **AC-3: the ranking is identical.** For every seed set, `rank_related_for_prompt(store, ids,
  k=5, clique_weight=2.0, coverage_alpha=3.0, adj=c)` equals the same call with `adj=d` and
  equals R0's golden: the same ids in the same order, scores bit-equal. Also with both terms
  off, against `rank_related`. Test: `test_prompt_ranking_identical_on_csr`. {#ac-3}
- **AC-4: the prompt path never iterates the graph.** A wrapper around `c` that raises on
  `__iter__`, `keys`, `items`, `values` and `__len__` is passed as `adj`. `rank_related_for_prompt`
  with the hook's parameters returns the golden for every seed set and the wrapper never raises.
  The same wrapper passed to `pagerank.pagerank` does raise (the wrapper works). Test:
  `test_prompt_rerank_touches_only_visited_rows`. {#ac-4}
- **AC-5: the overlay copies nothing from the base.** `overlay_prompt_clique(c, seeds, weight=2.0)`
  returns an `OverlayAdjacency` whose `base is c` and whose `rows` has exactly one entry per
  present seed. The existing dict tests in `tests/test_scan_prompt_expansion.py` pass unchanged
  (characterization). Test: `test_overlay_holds_the_base_by_reference`. {#ac-5}
- **AC-6: `adj=None` is today's behaviour.** For every seed set, each function of [[#r3]] called
  without `adj` returns what it returned at the base sha (R0's golden). (Characterization.) {#ac-6}
- **AC-7: nothing else moved.** `scripts/derive-digest.py check` exits 0. The full suite is equal
  by E line to the base run. {#ac-7}

## Mutations that must fail {#mutations}

Each is applied alone, seen RED on the named test, and reverted in its own command.

1. `_NeighborView.__iter__` yields weights, not ids → AC-2 (`seed_coverage`).
2. `CSRAdjacency.get` returns the empty view for a missing node with no default → AC-1.
3. `CSRAdjacency.__iter__` yields dense row numbers, not node ids → AC-1, AC-2 (`pagerank`).
4. `overlay_prompt_clique` adds the weight from `a` to `b` only → AC-2 (overlay), AC-3.
5. `overlay_prompt_clique` builds the row from an empty dict, dropping the base row → AC-3.
6. `OverlayAdjacency.__contains__` consults `rows` only → AC-3.
7. `overlay_prompt_clique` starts with `dict(adj)` again → AC-4.
8. `seed_coverage` builds its sets from the whole graph's keys → AC-4.
9. A walker ignores `adj` and builds its own → AC-4 (the wrapper is never touched, so the test
   also asserts the build counter stayed at zero).
10. `_NeighborView.__getitem__` returns the first weight for any key → AC-1.
{#mutations-list}

## Test strategy {#test-strategy}

- **RED first, by `ch-test-engineer`.** The tests named in [[#acceptance]] are written before
  any `src/` edit and run at the base sha; the red run is kept
  (`workflow/review-output/task-30.1/red.log`) with each test's E line. A test this spec marks
  characterization is recorded green at the base and says so. A test expected RED that passes
  at the base is a finding about the test.
- **GREEN by `ch-implementer`,** who writes no test.
- **Mutation gate.** The fix is committed before the first mutation. Each mutation of
  [[#mutations]] is applied alone, must FAIL its named test (a hang is not a failure), and is
  reverted in its own command; `__pycache__` is cleared after the batch; the fix is shown
  present after the last revert.
- **Test families are derived from imports** of the touched modules (29.4), and the merged dev
  tree runs them before the merge commit.
- **Mocks.** None. AC-4's refusing wrapper is a real `Mapping` around the real CSR; it is
  classified in `workflow/test_mock_registry.md`.
- **All output to files** under `workflow/review-output/task-30.1/`.
{#test-strategy-list}

## Caller census {#census}

At `6676f39`. R0 re-runs it.

| Changed | Callers in `src/` | Tests that name it |
|---|---|---|
| `CSRAdjacency` (gains methods; `get` changes) | `pagerank.py::cached_adjacency`; `.get(` on an adjacency: `ppr.py::local_push_ppr` (passes `{}`), `ppr.py::seed_coverage` (passes `{}`), `enrich.py::walk` (tests truth), `net.py::build_net` (passes `{}`) | `tests/test_adjacency_cache.py` |
| `_NeighborView` | `pagerank.py` only | none by name |
| `overlay_prompt_clique` | `ppr.py::rank_related_for_prompt`, `enrich.py::enrich_concepts` | `tests/test_scan_prompt_expansion.py` (12 sites) |
| `seed_coverage` | `ppr.py::rank_related_for_prompt` | `tests/test_scan_prompt_expansion.py` (6) |
| `rank_related_for_prompt` (+`adj`) | `scan.py::_ppr_rerank` | `tests/test_scan_prompt_expansion.py` (4), `tests/test_scan_prompt_dedup.py` (2) |
| `rank_related` (+`adj`) | none | `tests/test_v2_features.py` (2), `tests/test_scan_prompt_expansion.py` (2) |
| `enrich_concepts` (+`adj`) | `scan.py::_enrich_rerank` | R0 lists |
| `build_net` (+`adj`) | `net.py::net_concepts` ← `scan.py::_net_rerank` | `tests/test_net.py` (18 sites over `build_net` and `net_concepts`) |
{#census-table}

## Invalidation {#invalidation}

None is added. An overlay is built per call and never stored. The mapping methods read the
arrays the CSR already holds. {#invalidation-body}

## Files {#files}

| File | Change |
|---|---|
| `src/refmatrix/pagerank.py` | [[#r1]], [[#r4]] |
| `src/refmatrix/ppr.py` | [[#r2]], [[#r3]], [[#r4]] |
| `src/refmatrix/enrich.py`, `src/refmatrix/net.py` | [[#r3]], [[#r4]] |
| `tests/test_adjacency_mapping.py` | new |
| `tests/fixtures/adjacency/seed_sets.json` | new |
| `workflow/implementation_summaries/task-30.1-adjacency-mapping-adapter.md` | new |
{#files-table}

## Risks {#risks}

- **A walker reads something the mapping surface does not cover.** AC-2 runs every walker on
  both forms; the census names every `.get(`.
- **`Mapping.__eq__` hides an ordering difference.** AC-1 compares `list(...)` as well as
  `dict(...)`.
- **The pass file is edited.** It is, and release B carries it
  ([[plan-30-materialisation#releases]]).
- **The `adj` parameter has no `src/` caller until 30.4.** Between releases B and C only tests
  pass it. It is how AC-2 to AC-4 hand a chosen graph to the walkers, and the op is its
  production caller. If 30.4 is stopped by its bands, the parameter stays as the test seam it
  is, and the summary says so.
{#risks-list}

## Out of scope {#out-of-scope}

- Changing which adjacency any caller reads (30.2).
- The vectorised build (30.2). The daemon (30.4).
- A write surface on the CSR.
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **The adapter comes before the builder.** It is then proven against the dict the code builds
  today, and 30.2's change is only the builder.
- **`get` takes dict semantics.** A mapping whose `get` cannot return `None` is a trap for the
  next caller. The census shows no caller needs the old answer.
- **The overlay is a class in `ppr.py`, not in the pass file.** The prompt terms are PPR's, and
  an edit to them should not make every store's `pagerank` pass read behind.
{#decisions-list}
