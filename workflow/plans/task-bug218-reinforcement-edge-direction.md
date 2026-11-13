---
gmd: "0.1"
id: task-bug218-reinforcement-edge-direction
title: "Task bug-218: one storage orientation for reinforces / contradicts edges — R0 confirms or refutes the reversed read, then both writers and the reader agree"
tags: [task, bug-218, reinforcement, linkages, direction, memory, t6]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
---

# Task bug-218: reinforcement reads its edges in one orientation {#root}

> Status: Drafting (2026-11-13, spec wave G20). Not approvable until open decision [[#o-1]] is
> taken; every requirement below is written so that it holds for either option except the lines
> marked "per O-1".
> Track: T6 (graph integrity), queue item 9, first ([[plan-review-2026-11-13#queue]]; L8 puts
> bug-218 on T6).
> Depends on: bug-216 merged and live. Its R6 changes which entity a bare `rel:` target binds
> (doc / memory first), so the rows this task counts and re-orients are the post-bug-216 rows, and
> its R8 recount is the census tool this task reuses.
> The bug row is `suspected`: [[#r0]] confirms or refutes it before any fix is written.

rel: derives-from -> [[bug_registry]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r6]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r8]]
rel: related-to -> [[task-bug216-rule-docs-in-graph#out-of-scope]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: depends-on -> [[feedback_red_test_must_fail_at_head]]

## Why {#why}

The bug-218 row (found 2026-11-13 while diagnosing bug-216) says `reinforcement.py` reads
`reinforces` / `contradicts` edges reversed against "the only writer (the GMD ingester)". Re-read
at `1cf3b9f`, the defect is real in shape but the row's premise is wrong: there are TWO writers,
and they store the same statement in opposite orientations. {#why-lead}

`Store.link(linkage, concept_id, entity_id, …)` (`store.py:4810`) writes
`entity_links(entity_id, linkage_id, concept_id)`. {#why-writers}

| writer | call | statement "memory m reinforces target c" stored as |
|---|---|---|
| GMD ingester, a `rel: reinforces -> [[c]]` line in m | `ingest_gmd.py:1766` `store.link(verb, src_eid, target_eid)`, evidence at `:1769` `add_evidence(verb, src_eid, target_eid, …)` | `concept_id = m`, `entity_id = c` (bug-216's "storage direction", the same for every `rel:` verb) |
| `rmx memory link m reinforces c` (CLI local path) | `cli.py` `memory_link`: `s.link(linkage, cid, m["id"], weight=…)` | `concept_id = c`, `entity_id = m` |
| daemon op `memory_link` (the CLI's daemon route; MCP `rmx_memory` action `link` through `verbs._MEMORY_OPS`) | `daemon.py` `_op_memory_link`: `d._st().link(linkage, cid, m["id"], weight=…)` | `concept_id = c`, `entity_id = m` |

The reader, `reinforcement.reinforcement_scores` and `reinforcement_components`, selects
`WHERE el.concept_id IN (<targets>)` and decays on `entities.created_at` of `el.entity_id`. That
is the `memory_link` orientation. For a GMD-written row the signal lands on the reinforcing
memory's id and decays by the target's age, which is the row's description. {#why-reader}

Every fixture agrees with the `memory_link` orientation, so no test can see the GMD rows:
`tests/test_reinforcement.py:33,102,121,167` and both benches, `eval/reinforcement_bench.py:143,149`
and `eval/reinforcement_csn_bench.py:117,135`, seed with a raw `s.link(linkage, cid, mid)`. The
benchmarks measure an orientation the GMD path never writes ([[feedback_measure_the_path_users_run]]).
{#why-fixtures}

Live exposure is small today: `RMX_REINFORCE_ALPHA` defaults to 0.0, `apply_to_concept_scores`
has no caller, and the `RMX_BOOST_REINFORCE` term boost in `Store.content_rank` (`store.py:5610`)
is unset. What does read the signal today is `rmx memory score` (CLI and `_op_memory_score`), and
the two direction-sensitive graph readers of the same rows: `pagerank.py` (which keeps
`contradicts` connectivity) and `brief.contradicted` (which de-duplicates pairs, so it does not
depend on orientation). {#why-exposure}

## Open decision O-1: the canonical orientation {#o-1}

No D-Q or L-row settles which orientation wins. Options, recommendation first:

1. **(A, recommended) The GMD orientation is canonical** (`concept_id` = source, `entity_id` =
   target, as for every `rel:` verb). `memory_link` (CLI local path and daemon op) changes to
   `link(linkage, m_id, cid)`; the reader keys the signal on `entity_id` and decays on the
   `concept_id` side's `created_at`. Why: it is the graph-wide convention that bug-216's R6-R8,
   `denotes`, `check-rel-landing.py`, PageRank and every other `rel:` reader already assume; the
   rows to re-orient are only `memory_link`-written ones, which [[#r0b]] expects to be few.
2. **(B) The `memory_link` orientation is canonical for these two verbs.** The GMD ingester
   special-cases `reinforces` / `contradicts` and writes them reversed; every existing GMD row of
   these verbs is re-oriented. Cost: a per-verb exception that every `rel:` reader (bug-216's
   recount and `denotes`, PageRank, `brief`) must learn, and the larger repair.
3. **(C) The reader infers the source by kind** (the `kind='memory'` side is the source).
   Rejected: a memory reinforcing another memory, the common GMD case, has no answer.

Under B, [[#r2]] and [[#r4]] change as noted in each; everything else stands. {#o-1-impact}

## Requirements {#requirements}

1. **R0 Confirm or refute, at HEAD, before any fix.** {#r0}
   - **R0a RED on the real writers.** In task 23.0's sandbox (a throwaway store under a short
     `mkdtemp()` root), two statements of "m reinforces c": one ingested from a GMD memory file
     carrying `rel: reinforces -> [[c]]` (through `ingest_gmd_paths`, the bridge's path), one
     written by the `memory_link` daemon op. Read `reinforcement_scores` and
     `reinforcement_components` for c and for m. At HEAD the expected result is: the
     `memory_link` statement scores on c, the GMD statement scores 0 on c and non-zero on m. If
     the GMD statement scores on c at HEAD, the bug is REFUTED: the test is kept as a guard, the
     row is closed `not a bug` with the run log, and R1-R5 are not built. The RED run is logged
     ([[feedback_red_test_must_fail_at_head]]). {#r0a}
   - **R0b Census, read-only.** On copies of each fleet store's `catalog.read.duckdb` (the ONE
     census procedure, [[task-16.6-learned-row-validation#r7]]: copy into a short `/tmp` dir,
     `duckdb.connect(read_only=True)`, no `Store()`, no daemon, no socket), count `reinforces` and
     `contradicts` rows in `entity_links` by writer: rows with a `linkage_evidence` row at the same
     `(entity_id, linkage_id, concept_id)` whose `detail` starts `rel:` are GMD-written; the rest
     are `memory_link`-written or of unknown origin, counted apart. For each writer class, also
     count: the kind of each end (memory / doc / concept / other), rows with a dead end, and
     rows whose source (per its writer's orientation) is not `kind='memory'` ([[#r3]]'s drop).
     Results go to `workflow/measurements/bug218-direction-census-<date>.md`, counts only, one
     row per store, with the copy's timestamp. {#r0b}
2. **R1 One orientation, both writers (per O-1).** The GMD ingester and `memory_link` (the CLI's
   local path and `_op_memory_link`, which the MCP `rmx_memory` `link` action reaches) store "m
   reinforces / contradicts c" as the SAME `entity_links` row. The orientation is written once, as
   a named constant or docstring in `reinforcement.py` that both the writer change and the reader
   cite. {#r1}
3. **R2 The reader reads that orientation (per O-1).** `reinforcement_scores(store, ids)` returns
   the signal of each TARGET id: the sum over its incoming `reinforces` / `contradicts` rows,
   decayed on the SOURCE entity's `entities.created_at`, clamped to ±cap.
   `reinforcement_components(store, id)` lists the SOURCE entities (id, name, kind, age, decay,
   contribution). Under A this swaps both SQL joins; under B the SQL is unchanged and the change
   is in the ingester. {#r2}
4. **R3 Only memories reinforce.** A row contributes only when its source is `kind='memory'`,
   which is the module docstring's definition ("Memories accumulate confidence on a concept") and
   the bug row's proposed fix. A doc that cites a memory with `rel: reinforces` (task specs do)
   contributes nothing and is counted by R0b, so the drop is measured, not silent. {#r3}
5. **R4 Existing rows in the non-canonical orientation.** If R0b finds any (under A: the
   `memory_link`-written rows; under B: every GMD-written row of the two verbs), they are
   re-oriented by a one-shot, dry-run-by-default repair that prints each row by name, writes a
   manifest before any change, logs `unlink` + `link` events through `edge_records.edge_fields`
   so a rebuild reproduces the result, and is applied by the lead, announced first, with a backup
   (CLAUDE.md `#permissions`). The route is open decision [[#o-2]]. Under A with R0b at 0
   re-orientable rows on every store, R4 builds nothing and says so in the summary. {#r4}
6. **R5 Fixtures and benches seed through the writers.** `tests/test_reinforcement.py`, both
   `eval/reinforcement_*bench.py` scripts and the new tests create reinforcement edges only
   through the production writers (the `memory_link` op's store-level body or a GMD ingest),
   never a raw `Store.link` with a hand-chosen orientation, so a future orientation change cannot
   hide behind fixtures. {#r5}
7. **R6 Stated where a reader looks.** The `reinforcement.py` module docstring and `rmx memory
   link --help` state the stored orientation; the bug-218 row's "only writer" premise is corrected
   when the row is updated. {#r6}

## Acceptance criteria {#acceptance}

1. **AC-1 (R0a) RED at HEAD.** The R0a test fails at HEAD on the GMD statement (signal on c is 0;
   on m it is non-zero) and passes after R1-R2. Its run log is cited in the summary. If it passes
   at HEAD, see R0a's refute branch. {#ac-1}
2. **AC-2 (R1) Writer parity.** For the same m and c, the GMD ingest, the `memory_link` daemon
   op, and the CLI's local `memory_link` path each produce exactly one `entity_links` row, and the
   three rows have equal `(entity_id, concept_id)`. Mutations, each FAILS it: revert the
   `memory_link` op's orientation; revert the CLI local path's orientation (the daemon-down
   route); under B, drop the ingester's two-verb case. {#ac-2}
3. **AC-3 (R2) Signal and decay.** c is created now; m (created 30 days ago) reinforces c with
   weight 1.0; m2 (created now) contradicts c with weight 0.4; halflife 30 days, cap 5. `reinforcement_scores`
   gives c = 0.5 − 0.4 = 0.1 (±1e-6) and m = m2 = 0.0. Mutations, each FAILS it: key the signal
   on the source (c reads 0); decay on the target's `created_at` (c reads 0.6); drop the sign
   from the linkage name (c reads 0.9). {#ac-3}
4. **AC-4 (R2) Components name the sources.** `rmx memory score c --explain` (and the daemon op's
   `components`) lists m and m2, ordered by |contribution|, and never c. Mutation: select the
   target's name for the component row: FAILS. {#ac-4}
5. **AC-5 (R3) Memory-only.** A `kind=doc` source created now, with `rel: reinforces -> [[c]]`
   beside AC-3's rows, leaves c at 0.1. Mutation: drop the kind filter: FAILS (c reads 1.1). {#ac-5}
6. **AC-6 (R5) No raw seeding.** A check over `tests/test_reinforcement*.py`, `tests/test_bug218*.py`
   and `eval/reinforcement_*bench.py` finds no `.link(` call whose first argument is
   `"reinforces"`, `"contradicts"` or a variable bound to them. Mutation: restore
   `tests/test_reinforcement.py`'s raw helper: FAILS. {#ac-6}
7. **AC-7 (R5) The benches still measure the same thing.** `eval/reinforcement_bench.py` and
   `eval/reinforcement_csn_bench.py`, run with their recorded seeds before and after the change,
   print identical metrics: the change re-orients storage and reading together and moves no
   score. A difference is a defect in R1/R2, not a new baseline. Logs in
   `workflow/review-output/`. {#ac-7}
8. **AC-8 (R0b) Census committed.** The measurement file exists with one row per fleet store
   that has a catalog, each with the writer split, the end-kind split, the dead-end count and
   R3's drop count, and the copy's timestamp. {#ac-8}
9. **AC-9 (R4, only if R0b found rows to re-orient).** On a sandbox store holding rows in both
   orientations, the repair's dry run prints each non-canonical row and changes nothing; the
   apply leaves only canonical rows, AC-2's parity holds for every pair, and a rebuild from
   `facts.log` of a copy reproduces the applied rows. On the live stores, the post-apply R0b
   census reads 0 non-canonical rows. Mutation: apply without the `unlink` event: the rebuild
   holds both orientations and FAILS. {#ac-9}

## Open decision O-2: the route for R4's repair {#o-2}

Only needed if R0b finds rows to re-orient. Options, recommendation first:

1. **(a, recommended) A one-shot repair in the bug-195 shape** ([[task-bug195-cut-hook-repair#r1]]:
   one committed command, dry-run default, `--apply`), with the manifest and events of R4. A
   re-orientation removes no knowledge (the same statement is written back), so it is not
   plan-22's knowledge removal under [[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]].
2. **(b) Through plan-22's engine** as a repair class, after 22.2 lands. Cost: bug-218 waits for
   22.2, which queue item 9 places after it.

## Q8 note {#q8-b}

Under Q8 b (save-states and `workflow/` excluded at ingest), the GMD rows whose source is a
`workflow/` doc disappear on re-ingest. R3 already gives them no weight, so no requirement changes;
R0b's counts would differ.

## Out of scope {#out-of-scope}

- Turning the channel on (`RMX_REINFORCE_ALPHA`, `RMX_BOOST_REINFORCE`): a ranking change, gated
  by ADR-0004's per-type evaluation, not by this fix.
- The `except Exception: pass` around the `RMX_BOOST_REINFORCE` read in `Store.content_rank`
  (`store.py:5626`): a silent failure on a ranking path, reported to the lead for its own bug row.
- bug-219 (stale evidence rows): plan-22's census, [[task-22.1a-provenance-free-classes#rev-round-9]].

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/reinforcement.py` | R1 orientation stated once; R2 reader joins (under A); R3 kind filter; docstring (R6) |
| `src/refmatrix/cli.py` (`memory_link`, `--help`) | R1 under A (local path orientation); R6 help text |
| `src/refmatrix/daemon.py` (`_op_memory_link`) | R1 under A |
| `src/refmatrix/ingest_gmd.py` | R1 under B only |
| `tests/test_bug218_reinforcement_direction.py` (new) | AC-1..AC-6, AC-9 sandbox half |
| `tests/test_reinforcement.py` | fixtures seed through the writers (R5) |
| `eval/reinforcement_bench.py`, `eval/reinforcement_csn_bench.py` | seed through the writers (R5); AC-7 runs |
| `scripts/census_on_copy.py` (16.6's) or a scratch census script | R0b (read-only, copies only) |
| `workflow/measurements/bug218-direction-census-<date>.md` (new) | AC-8 |
| `workflow/bug_registry.md` | bug-218 row: premise corrected (two writers), status, fix sha |

## Definition of done {#done}

- RED run (AC-1) and GREEN run recorded under `workflow/review-output/`, mutation check noted.
- Implementation summary at `workflow/implementation_summaries/task-bug218-reinforcement-edge-direction.md`.
- Committed on branch `task-bug218-reinforcement-edge-direction`; merged `--no-ff` to `master`;
  the bug-218 row updated with the sha.
