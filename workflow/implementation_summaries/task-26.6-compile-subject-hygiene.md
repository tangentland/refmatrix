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
