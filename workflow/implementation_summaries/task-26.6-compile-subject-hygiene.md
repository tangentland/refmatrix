---
gmd: "0.1"
id: impl-task-26.6-compile-subject-hygiene
title: "Task 26.6: the memory_compile op and verb, scope-aware compile, stale-marked subjects, stable names, case-folded labels, code-hash staleness, index on bridge write"
tags: [implementation-summary, plan-26, plan-19, compile, subjects, derive-stamp, memory-index, bridge]
metadata:
  node_type: implementation-summary
  status: in-progress
  created: 2026-11-09
---

# Task 26.6: build 19.4, scope-aware compile, label hygiene {#root}

rel: implements -> [[task-26.6-compile-subject-hygiene]]
rel: realizes -> [[task-19.4-keep-derived-layers-current]]
rel: part-of -> [[plan-26-memory-organisation]]
rel: derives-from -> [[refmatrix/adr-0002-subject-memory-container]]
rel: implements -> [[refmatrix/adr-0005-memory-dir-layout#topics]]

TDD GREEN over the RED commit `a3dd158` (RED re-recorded at the rebased HEAD; see
[[#red]]). No test was written or edited in this step.

## RED re-recorded at the rebased HEAD {#red}

Task 26.1 (merged at `9b2c4ac`) changed `memory_index` and the bridge, so RED was re-run at
`a3dd158` before any `src/` change:

| log | result | vs the original RED at `af141c4` |
|---|---|---|
| `workflow/review-output/plan26/26.6-red-unit-a3dd158.log` | 7 failed, 53 passed | same 7 tests, same assertion text (object addresses differ) |
| `workflow/review-output/plan26/26.6-red-e2e-a3dd158.log` | 17 failed, 2 passed | same 17 tests, same errors (daemon pids differ) |
| `workflow/review-output/plan26/26.6-red-parity-a3dd158.log` | 6 failed, 159 passed | same 6 tests, same errors |

`LEGACY_BASELINE_SIZE = 91` verified: `len(verbs.LEGACY_UNPAIRED)` was 92 at `a3dd158` with
`('memory', 'compile')` in it; removing that one path gives 91.

## What shipped {#shipped}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `cluster_cid(members)`: THE member-set hash (19.4 R6 / 19.6 R9) |
| `src/refmatrix/store.py` | `MEMORY_COMPILE_PASS`; `_DERIVE_PASS_MODULES["memory-compile"] = ("consolidate.py",)`; `_DERIVE_VERDICT_EXCLUDED`; `derive_status` splits the compile stamp out of every verdict field and reports it under `memory_compile`; `_memory_compile_status`; `upsert_subject(..., slug_prefix="")` |
| `src/refmatrix/consolidate.py` | `SCOPES`, `subject_scope`, scoped corpus in `_memory_rows`; case-folded `_concept_sets`; order-free names (`unlabeled-<cid>`, duplicate labels `<label>-<cid>`, counted on the slug); `apply_plan(..., scope=)` prunes / marks stale / un-marks only in scope, never deletes, counts `stale_total/new/unmarked`; `run_compile` (plan + apply + stamp) and `COMPILE_PARAMS` |
| `src/refmatrix/daemon.py` | `_op_memory_compile` (replaces `_op_memory_compile_apply`): plan + apply in one `_store_lock` block, single-flight, lock-free `status=True`, `dry_run`, `invoked_by`; the bridge body regenerates `MEMORY.md` (R2) before the job reads `done` |
| `src/refmatrix/ingest_gmd.py` | `regenerate_memory_index`, `regenerate_memory_index_reported`, `render_memory_index_line` |
| `src/refmatrix/verbs.py` | `rmx_memory_compile` verb; `CLI_MAP` twin `("memory", "compile")`; the path left `LEGACY_UNPAIRED` |
| `src/refmatrix/cli.py` | `memory compile --scope`, a thin adapter over the verb (daemon down: the same `run_compile` in-process); prints `N marked stale`; `memory list` shows a `state` column (`stale since <date>`) when the listing holds a subject; `daemon status` prints `render_memory_compile_warning`; the in-process `_ingest_gmd_sync` runs the same index regeneration |

Signatures (final):

- `stm.cluster_cid(members: Iterable[str]) -> str`
- `Store.upsert_subject(label: str, metadata: dict | None = None, *, slug_prefix: str = "") -> dict`
- `Store._memory_compile_status(side_rows: list) -> dict`
- `consolidate.subject_scope(meta: dict) -> str | None`
- `consolidate.compile_memories(store, *, k=8, threshold=None, threshold_pct=95.0, mutual=True, beta=1.0, gamma=0.5, bridge_min=0.35, hub_df_frac=0.10, min_size=2, signal="fused", exclude_mtypes=None, max_subjects=None, scope="memory") -> dict`
- `consolidate.apply_plan(store, plan, *, prune=True, scope=None) -> dict`
- `consolidate.run_compile(store, *, scope="memory", dry_run=True, prune=True, **params) -> dict`
- `daemon._op_memory_compile(d, args) -> dict` (registered as `OPS["memory_compile"]`)
- `ingest_gmd.regenerate_memory_index(store_root, files, *, memory_only) -> dict`
- `ingest_gmd.regenerate_memory_index_reported(store_root, files, *, memory_only) -> dict`
- `ingest_gmd.render_memory_index_line(idx) -> str`
- `verbs.memory_compile(root, *, scope="memory", apply=False, k=8, threshold=None, threshold_pct=95.0, mutual=True, beta=1.0, gamma=0.5, bridge_min=0.35, hub_df_frac=0.10, min_size=2, signal="fused", exclude_mtypes=None, max_subjects=None, prune=True, invoked_by="mcp", status=False, partition=None, timeout=None) -> dict`
- `cli.render_memory_compile_warning(status, *, partition=None) -> str`

## Per acceptance criterion {#per-ac}

| AC | code | test now GREEN |
|---|---|---|
| AC-A scopes isolated | `consolidate.apply_plan` (`subject_scope(...) == scope`), `_memory_rows`, `SCOPE_SLUG_PREFIX` | `test_ac_a_*` (3) |
| 19.4 AC-4 minus recall | `apply_plan` stale pass; `_rewrite_subject_meta` (protected, via `add_memory`); `memory list` `state` column | `test_ac4_a_subject_left_empty_*`, `test_r5_*` |
| 19.4 AC-4b | `apply_plan` counts; `cluster_cid` names | `test_ac4b_*` |
| 19.4 AC-5 (slug half) / r2 m7 | `compile_memories` label pass | `test_r6_*` (3) |
| 19.4 AC-1 + r2 s2 twin | `regenerate_memory_index` in `_run_ingest_gmd_body` | `test_ac1_*` (4) |
| 19.4 AC-6 marker-OFF twin | no compile index writer exists (R3 deferred) | `test_ac6_twin_*` |
| R1 op half | `_op_memory_compile`, `verbs.memory_compile` | `test_verb_dry_run_*`, `test_single_flight_*`, `test_verb_and_cli_twin_*` |
| AC-B | `_concept_sets` folding | `test_r_b_*` (2) |
| AC-C | unchanged `_label_candidate_ok` | `test_ac_c_*` |
| AC-D | `_DERIVE_PASS_MODULES`, `_DERIVE_VERDICT_EXCLUDED`, `run_compile` stamp, `render_memory_compile_warning` | `test_acd_*` (5), `test_memory_compile_*` in test_derive_stamp.py (3) |
| R-D parity | `CLI_MAP`, `LEGACY_UNPAIRED` | test_verb_parity.py (6 that were RED) |

## Results {#results}

All runs used `.venv-eval/bin/python -B -m pytest` with `PYTHONPATH=<clone>/src`. The machine
load average was between 95 and 143 throughout, because other agents were running suites.

| run | log | result |
|---|---|---|
| the 3 RED files + verb parity: unit + parity | `26.6-green-unit-parity.log` | 225 passed |
| test_memory_compile_scope.py (e2e) | `26.6-green-wip-e2e.log` | 19 passed |
| docs-generated, brief, inflight, mcp, plan7_10 r4 | `26.6-green-wip-misc.log` | 166 passed |
| memory family (`test_memory*`, `test_ingest_gmd*`, `test_save_state*`, `test_derive*`, verb parity, docs-generated), run at `d77dd68` in a littlebig clone | `26.6-green-family.log` | 558 passed (15 min 15 s) |

`tests/test_docs_generated.py` passed with no regeneration needed: the generated CLI tree lists
commands, not options, and nothing generates a verb table.

One flake, logged and not explained away. In an earlier family run on the uncommitted tree,
under load average 143, `test_memory_bridge.py::test_bridge_runs_its_own_ingest_after_a_job_on_another_target`
failed once. I killed that run at my 600 s bound before pytest printed the failure, so its E
line was never captured. Run alone, the test passed in 100.6 s against its 120 s
`RMX_BRIDGE_WAIT_S` (`26.6-green-bridge-one.log`). It also passed in the committed family run
above. Code only adds a path-containment check to the waited job's end, so a timing cause is
consistent with the evidence. The error itself was not seen.

## Mutations {#mutations}

Committed first (`d77dd68`); each mutation applied by a script, its test(s) run with `-x`,
then restored with `git checkout -- src` + `__pycache__` cleared in a SEPARATE command, and
`git diff HEAD -- src` checked empty after the last restore. Logs:
`workflow/review-output/plan26/26.6-mut-M<n>.log`.

| # | mutation | test that went RED | result |
|---|---|---|---|
| M1 | prune across scopes (`before` takes every compiled scope) | `test_ac_a_pattern_apply_leaves_every_memory_subject_byte_identical` (`subject_daemon_ops` leaves -> `[]`) | killed |
| M2 | stale-mark replaced by `forget_memory` (delete) | `test_ac4_a_subject_left_empty_*` ("compile removed the emptied subject row") | killed |
| M3 | single-flight removed | `test_single_flight_*` ("the second call blocked behind the first") | killed |
| M4 | `status=True` takes `_store_lock` | `test_single_flight_*` ("status=True blocked on the store lock") | killed |
| M5 | `cluster_cid` order-dependent (no `sorted`) | `test_r6_cluster_cid_is_the_one_member_set_hash` | killed |
| M6 | casefold removed from `_concept_sets` | `test_r_b_case_variants_are_one_label_candidate` (label `g2`) | killed |
| M7 | the stamp moves the verdict (`_DERIVE_VERDICT_EXCLUDED` empty) | `test_a_memory_compile_stamp_never_moves_the_partition_verdict` (`stale` False -> True) | killed |
| M8 | R2 ungated (marker check removed) | `test_ac1_twin_an_unorganised_dir_keeps_its_index_and_sidecar_byte_identical` | killed |
| M9 | `memory-compile` added to `_DERIVE_EXPECTED_PASSES["project"]` | `test_memory_compile_is_not_an_expected_pass_of_any_partition_kind` | killed |
| M10 | the stamp call skipped | `test_acd_a_real_apply_stamps_the_pass_and_keeps_the_verdict` (status line printed) | killed |
| M11 | the bridge never regenerates the index | `test_ac1_bridge_regenerates_the_index_in_an_organised_dir` | killed |
| M12 | duplicate labels suffixed by cluster ORDER (`-2`) | `test_r6_duplicate_labels_are_named_by_member_set_not_cluster_order` | killed |
| M13 | pattern slug prefix removed | `test_ac_a_memory_apply_leaves_every_pattern_subject_byte_identical` (`subject_daemon_ops` is the pattern row) | killed |

13 of 13 killed, no survivors.

## Flags for the review lenses {#flags}

- **R3 not built** (compile regenerates `MEMORY.md` marker-ON): deferred to 26.7 per the RED
  contract, since R3 needs 26.7's subject render. No compile path writes an index, so the
  marker-OFF twin (AC-6) holds by construction. 26.7 must add the marker-gated call inside
  `_op_memory_compile`'s lock block.
- **Deferred, not built**: 19.4 R1's tick registration, AC-2 and `runs.jsonl` (go to 17.2);
  the AC-4 recall leg (goes to 25.1 AC-6); AC-E, the user's grade after 26.8.
- **Drift for alignment**: `brief._memory_ids`'s docstring says it uses "the same filter as
  `consolidate._memory_rows`". That stopped being true here: compile's `memory` scope now drops
  impressions and `tag: pattern` docs, and brief does not. brief is outside 26.6, so I did not
  change it.
- **Op replaced**: `memory_compile_apply` is gone and `memory_compile` replaces it. Nothing
  else called it, but a CLI from before 26.6 talking to a 26.6 daemon gets "unknown op".
  The CLI and the daemon deploy together.
- **Planning now runs in the daemon**, as 19.4 R1 requires: it reads the memory vector matrix
  under `_store_lock`. The size is bounded by the memory corpus, but nobody has measured it on
  the live store. It is a candidate for `ch-performance-tuner` at 26.8.
- **Label surface choice**: a folded term's name is its most frequent surface across the
  CORPUS (ties go to the lexically first name), not per cluster. The tests pin only the
  per-cluster case (the two agree there).
- **The daemon-down fallback stays**: the CLI calls the verb, and on `VerbAbsentError` it runs
  the same `consolidate.run_compile` in-process through `_store(write=True)`, as the command
  always could. `test_plan7_10_remedy_r4.py::test_cli_memory_compile_out_dash_keeps_its_wikilinks`
  exercises this branch.
- **`rmx derive status`** leaves the memory-compile row out of its table: `passes` excludes
  it. `--json` carries it under `memory_compile`, and `rmx daemon status` prints its line.
- **No version bump**: this repo bumps in a separate `release:` commit (`af141c4`).

## Remedy r1 (2026-11-10) {#remedy-r1}

rel: implements -> [[task-26.6-compile-subject-hygiene#remedy-r1]]
rel: derives-from -> [[bsd-task-26.6-r1-compile-hygiene-290348a]]

TDD GREEN over RED `a170ce9` + `b135c3d` (11 failing in `tests/test_memory_compile_remedy_r1.py`,
`26.6-r1-red.log`). GREEN commit `a3b8fcb`. The R3 residual ([[task-26.6-compile-subject-hygiene#r3-residual]])
is still open, so the status stays `in-progress`.

### What changed, per item {#remedy-r1-items}

- **#rm-stamp-per-scope (s-1).** `store.MEMORY_COMPILE_PATTERN_PASS = "memory-compile:pattern"`
  and `MEMORY_COMPILE_SCOPE_PASSES`. The pattern pass is in `_DERIVE_PASS_MODULES`
  (`consolidate.py`) and `_DERIVE_VERDICT_EXCLUDED`, and it is not expected.
  `consolidate.run_compile` stamps only its scope's pass and names it in `stamp_pass`.
  `Store._memory_compile_status` returns `scopes: {memory, pattern}`; each scope's record has
  `pass`, `stamped`, `behind_code`, `compiled_subjects` and `needs_compile`, and only that
  scope's subjects count (`consolidate.subject_scope`). A subject with an unknown
  `compiled_scope` raises. The top-level fields stay the memory scope's record, because current
  callers read them. `cli.render_memory_compile_warning` prints one line per stale scope; the
  pattern line names `rmx memory compile --apply --scope pattern`. Both lines print with
  `soft_wrap=True`, so the line is never wrapped.
- **#rm-one-corpus (s-3).** `consolidate.in_corpus(name, mtype, tags, scope, exclude_mtypes)`
  is the one predicate. `_memory_rows` filters with it, and `brief._memory_ids(store, scope=)`
  IS `_memory_rows(EXCLUDE_MTYPES, scope)`. `brief.compile_briefs(..., scope="memory")` refuses
  a plan compiled for another scope and reports `stats.scope`. `_op_memory_brief` reads the
  op's wire key `scope`. `memory brief --compile` plans and briefs the one scope. The dead
  `brief._excluded_mtype` is removed. *Amended 2026-11-10 (bug-198, bug-200 m-1):* the
  `rmx_memory brief` payload no longer forwards the verb's `scope` argument. The compile scope
  arrives as `compile_scope` and goes out on the wire key `scope`. A non-None `scope` on brief
  is refused with `VerbArgsError` before any daemon call, on the MCP path too.
- **#rm-status-route (m-1).** A new op, `memory_compile_status`, is in `CLI_OPS` and `OPS`, and
  `verbs.memory_compile(status=True)` asks it. `memory_compile status=True` still answers by
  delegating, for direct callers.
- **#rm-subjects-gmd (m-5).** An applied `run_compile` result carries `subjects_gmd`
  (`render_gmd(plan, partition=...)`). The CLI writes that text to `--out` or stdout. If an
  applied result has no `subjects_gmd`, the CLI raises a `ClickException`; it never re-renders.
- **#rm-stale-refs (m-3).** The `_op_memory_brief` docstring and the `cli.py` `memory brief
  --compile` comment now describe the plan-on-replica read and the plan+apply op.
- Items 2 and 5 are test-only (RED commits). Item 8 needs no change.

### Results {#remedy-r1-results}

| run | log | result |
|---|---|---|
| RED file | `26.6-r1-green-red-file.log` | 15 passed |
| family (memory*, ingest_gmd*, save_state*, derive*, brief*, verb parity, docs-generated, plan7_10 r4) | `26.6-r1-green-family.log` | 647 passed, 1 failed, 4 skipped |
| RED file + real-fallback test, after the mutation restores | `26.6-r1-green-post-restore.log` | 16 passed |

The one family failure is `test_verb_parity.py::test_cli_twin_calls_its_verb[rmx_memory_compile]`.
Its canned verb result (`CLI_INVOKE`, `test_verb_parity.py:375`) has no `subjects_gmd`, so the
CLI raises, as #rm-subjects-gmd requires. The fix is to add the key to the fixture. That is a
test change, so it was flagged to the test-engineer and not worked around in `src/`.

### Mutations {#remedy-r1-mutations}

Committed at `a3b8fcb` before mutating. Each mutation was restored in its own command
(`git checkout -- src`, `__pycache__` cleared, the fix grepped back).

| id | mutation | killed by | log |
|---|---|---|---|
| M1 | the pattern scope stamps `memory-compile` | `a_pattern_apply_leaves_the_memory_scope_needing_compile`, `daemon_status_still_prints_the_memory_line…` | `26.6-r1-green-mut-M1.log` |
| M2 | the scopes are collapsed (one shared stamp and one count) | 4 `stamp_per_scope` tests | `26.6-r1-green-mut-M2.log` |
| M3 | brief ignores `scope` | `brief_takes_an_explicit_scope` | `26.6-r1-green-mut-M3.log` |
| M4 | status is routed through `memory_compile` (the bg pool) | `status_route_answers_while_a_bg_job_holds_the_bg_pool` | `26.6-r1-green-mut-M4.log` |
| M5 | `subjects_gmd` is dropped | `subjects_gmd_the_verb_carries_the_text_the_cli_writes` | `26.6-r1-green-mut-M5.log` |

5 of 5 killed. One note for the test-engineer: under M3,
`brief_and_compile_read_the_same_rows[pattern]` still passes. Both fixture corpora hold 4 rows,
so a row count cannot tell the scopes apart.

### Interpretations {#remedy-r1-interpretations}

- The top-level `memory_compile` keys are the memory scope's record. They are not an aggregate
  across scopes. Every renderer reads `scopes`.
- Each status line now ends `; scope <name>: <why>`.
- *Superseded 2026-11-10 (bug-198, bug-200 m-1).* As shipped here, `memory brief` had no
  `--scope` flag, and the `rmx_memory` verb forwarded its `scope` argument for `brief`. bug-198
  added `memory brief --scope memory|pattern` and the `compile_scope` verb key, and stopped
  forwarding `scope`. bug-200 m-1 makes the verb refuse a non-None `scope` on brief with
  `VerbArgsError` naming `compile_scope`, because a silently ignored `scope=pattern` answered
  from the memory corpus.
- An older CLI talking to this daemon still works for `status=True`, because the old op
  delegates. A new CLI talking to an older daemon gets "unknown op" on status. They deploy
  together.
