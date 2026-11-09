---
gmd: "0.1"
id: task-26.6-compile-subject-hygiene
title: "Task 26.6: build plan-19's task 19.4 (stale-marked subjects, stable names, compile op, index on write), plus compile scope, case-folded labels, a graded label check and code-hash staleness"
tags: [task, plan-26, compile, subjects, labels, derive-stamp, decay, plan-19]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
---

# Task 26.6: build 19.4, scope-aware compile, label hygiene {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: task 23.0 (sandbox; done in 0.79.1). R3 and AC-3 of 19.4 also need
> [[task-26.7-memory-index-by-subject]]. The 19.4 R1 tick registration depends on task 17.2 and
> is NOT built here.

rel: part-of -> [[plan-26-memory-organisation]]
rel: realizes -> [[task-19.4-keep-derived-layers-current]]
rel: derives-from -> [[refmatrix/adr-0002-subject-memory-container]]
rel: related-to -> [[task-22.1a-provenance-free-classes]]
rel: related-to -> [[task-12.4-derive-version-stamp]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_reuse_shared_stoplist]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]

## Requirements {#requirements}

The junk live labels are not a regression of the 0.34.0 stoplist fix. They were compiled on
2026-07-31, before that fix existed. Nothing has re-compiled them since, and nothing has marked
them stale ([[plan-26-memory-organisation#measured]]).

Plan-19's approved task 19.4 already specifies the remedy, so this task BUILDS it and does not
restate it. Its R2 and R4-R7, its ACs and its mutation list, all in
[[task-19.4-keep-derived-layers-current]], are this task's requirements verbatim, except for the
delta in [[#plan-19-delta]]. The new scope is R-A to R-D below.

### What is built from 19.4, and what differs {#plan-19-delta}

| 19.4 item | here | difference |
|---|---|---|
| R1 scheduled compile | The daemon op `memory_compile` (plan + apply), its verb, single-flight, `retries=0`, `dry_run`/`invoked_by`/`status=True` | NOT built: the `MaintenanceStep` registration on 17.2's tick, and AC-2 (the armed and unarmed days). Task 17.2 is unbuilt; both land with 17.2. Until then, compile runs on demand (26.8, 27.6). |
| R2 index on bridge write | built | none |
| R3 compile regenerates the index | built once 26.7 exists | none |
| R4 never loses | built | none |
| R5 `stale` + `stale_since`, never reaped | built | none. This replaces round 0's `retired_at` (B1), so plan-22's `stale-subject` audit sees these subjects. |
| R6 `unlabeled-<cluster_cid>` | built: `stm.cluster_cid`, unless 19.6 merges first | none |
| R7 loud | built | none |
| ACs 1, 3, 4, 4b, 5, 6, 7, 8 | built | AC-8 drops the "step not registered" and `requires_arming` mutations (they belong to R1's tick half) |

**What plan-19's owner records when this lands** (plan-19 files are not edited here):
- 19.4 is realized by task-26.6;
- R1's tick registration and AC-2 remain open, pending 17.2.

### New scope {#new-scope}

1. **R-A: one compile path, scope-aware (B3).**
   - Every compiled subject carries `metadata.compiled_scope`. The default scope is `memory`;
     26.9 uses scope `pattern`.
   - `apply_plan` prunes leaves, marks subjects stale (19.4 R5) and un-marks them ONLY among
     subjects whose `compiled_scope` equals the run's scope.
   - A row with no `compiled_scope` that has `compiled_by` set (a pre-26.6 row) belongs to scope
     `memory`.
   - Scope `pattern` slugs are prefixed `pattern_`, so a pattern subject can never share an
     identity with a memory subject (`store.py:2703-2718`: the identity is the label slug).
   - Corpus selection: scope `memory` excludes mtype `impression` and every doc tagged `pattern`.
     Scope `pattern` takes exactly mtype `impression`, minus `tag: pattern` docs.
   - There is one compile code path (`compile_memories` / `apply_plan`) with a `scope` parameter.
     No second clusterer.
2. **R-B: case-folded labels and evidence.**
   - Concept names that differ only by case (`Guardrail`/`guardrail`, `Tandem`/`tandem`) are one
     candidate.
   - The label takes the most frequent surface form.
   - Evidence lists each term once.
3. **R-C: code-hash staleness, kept out of the partition verdict (S6).**
   - `memory-compile → ("consolidate.py",)` is registered in `_DERIVE_PASS_MODULES`
     (`store.py:577`), so staleness means "the compile code changed since this compile ran"
     (`behind_code`). It does not mean "the release version changed".
   - `apply` stamps the pass.
   - `memory-compile` is NOT added to `_DERIVE_EXPECTED_PASSES`, and it is excluded from the
     partition's `oldest_version`/`stale` verdict. On post-merge stores the memory partition IS
     the project partition, and a stale compile must not make the whole graph read derive-stale.
   - `rmx daemon status` prints a separate line for it: `memory-compile: behind code — rmx memory
     compile --apply`. It prints nothing when the pass is current.
   - When there are compiled subjects but no stamp (the 2026-07-31 case), the line also prints.
4. **R-D: the stale mark reaches every listing surface (ch-bsd r1 #m4).**
   - `rmx memory list --type subject` shows each subject's stale mark, per 19.4 R5.
   - The `rmx_memory` verb (`verbs.py:1443`) returns `stale`/`stale_since` in its subject
     listing, so the CLI and MCP agree.
   - `memory compile` is LEGACY in the verb table (`verbs.py:1893`). The new `memory_compile` verb
     (19.4 R1's op half) replaces it there, and its `scope` parameter is the parity surface 26.9
     uses.

## Acceptance criteria {#acceptance}

- **AC-0: 19.4's ACs.** 19.4 AC-1, AC-3, AC-4, AC-4b, AC-5, AC-6, AC-7, and the AC-8 mutations
  minus the R1-tick ones ([[#plan-19-delta]]) all pass in task 23.0's sandbox.
- **AC-A: scopes do not touch each other (B3).**
  - Setup: a throwaway store with project memories and impressions. Run
    `memory_compile --apply` (scope `memory`), then `memory_compile --apply --scope pattern`.
  - The second run leaves every scope-`memory` subject's leaves, `stale` flag and metadata
    byte-identical. The reverse order holds too.
  - A pattern labelled `daemon_ops` is the row `subject_pattern_daemon_ops`. It is never
    `subject_daemon_ops`.
  - At HEAD, a scoped `--apply` (`--exclude-mtype '[!i]*'`) unlinks every project subject's
    leaves, so this is RED.
- **AC-B: case-folding.** Labels and evidence fold case (R-B).
- **AC-C: the stoplist fix stays pinned.** `_label_candidate_ok` keeps reading
  `scan._PROMPT_STOPWORDS`. No fixture cluster can produce the labels `from`, `existing` or
  `feedback`.
- **AC-D: staleness follows the code (R-C).**
  - A change to `consolidate.py`'s content hash makes the status line print.
  - A version bump with `consolidate.py` unchanged does NOT make it print.
  - The partition's derive verdict is unchanged in both cases.
- **AC-E: pre-registered label grade.** This gate controls whether any further label change is
  built.
  - After the live re-compile in 26.8, freeze the list of labels and their evidence (derived
    terms only) in `workflow/review-output/26.6-labels.md`.
  - The user grades each label: `names a body of work`, `weak but findable`, or `junk`.
  - The band below decides the action.

### Pre-registered bands {#bands}

| junk share of graded labels | action |
|---|---|
| ≤ 10% | Ship AC-0 through AC-D only. Record the grade. |
| 10–25% | For bare-word winners only, label with two terms: the bare word plus the strongest identifier-shaped co-term at ≥ 0.5× its lift. Then re-grade. |
| 25–40% | As above, and also raise the default `--min-size` to 3. Re-measure the unclustered count. |
| > 40% | Stop. Labels are a design problem (an ADR-0002 open question), not a tweak. Open a new task. |

## Files to Create / Modify {#files}

| file | change |
|---|---|
| `src/refmatrix/consolidate.py` | 19.4 R4-R6 stale/unmark/stable slugs; `scope`; casefold |
| `src/refmatrix/daemon.py`, `src/refmatrix/verbs.py` | the `memory_compile` op and verb (19.4 R1, op half); `rmx_memory` subject listing with `stale` |
| `src/refmatrix/ingest_gmd.py` / `daemon.py` `_run_ingest_gmd_body` | 19.4 R2 (index on bridge write; the writer store under `_store_lock`) |
| `src/refmatrix/store.py` | `_DERIVE_PASS_MODULES` entry; exclusion from the partition verdict |
| `src/refmatrix/stm.py` | `cluster_cid`, unless 19.6 merges first |
| `src/refmatrix/cli.py` | the status line; `memory compile --scope`; `memory list` showing `stale` |
| `tests/test_memory_compile.py`, `tests/test_derive_stamp.py` | extend |
| `tests/test_memory_compile_scope.py` | create |

## Test Strategy {#test-strategy}

- Use the real `memory_compile` verb and CLI against a throwaway daemon store in task 23.0's
  sandbox, over a synthetic memory corpus with deterministic embeddings (the existing compile
  fixtures).
- Do not mock `apply_plan`.
- The mutations are 19.4's (minus the tick ones), plus:

| mutation | test that goes RED |
|---|---|
| prune across scopes | AC-A |
| `memory-compile` added to `_DERIVE_EXPECTED_PASSES` | AC-D |
| the stamp call skipped | AC-D (the wiring test runs the real compile) |

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| B1 (re-specifies approved 19.4; `retired_at` hidden from 22.1a) | Builds 19.4; `realizes` edge; delta table; 19.4's `stale` mark; plan-19 record list | [[#plan-19-delta]], AC-0 |
| B3 (the scoped compile destroys the other scope) | `compiled_scope`; scope-local prune/stale; `pattern_` namespace; corpus split; RED AC-A | R-A, AC-A |
| S6 (version staleness nags; partition verdict) | Code-hash pass; excluded from expected passes and the verdict | R-C, AC-D |
| M4 (parity: LEGACY compile; `rmx_memory` listing) | `memory_compile` verb with `scope`; `rmx_memory` returns `stale` | R-D |
| Q5 verdict (use 19.4's `stale`) | Adopted | [[#plan-19-delta]] |
