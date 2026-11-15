---
gmd: "0.1"
id: task-29.4-r0-durations
title: "Task 29.4 stage 0 (R0): one serial full run with durations at 4c6a0c6, per-file weights, run-tier totals and band verdicts"
tags: [implementation-summary, plan-29, task-29.4, t0, tests, durations, tiers, measurement]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-15
---

# Task 29.4 stage 0 (R0): the serial durations run {#root}

rel: implements -> [[task-29.4-suite-health#r0]]
rel: evidence-for -> [[task-29.4-suite-health#r0-bands]]
rel: evidence-for -> [[task-29.4-suite-health#baseline]]
rel: derives-from -> [[plan-29-spec-census]]
rel: reinforces -> [[feedback_compare_failures_by_error_not_name]]
rel: reinforces -> [[feedback_review_clones_cannot_see_dev_tree_failures]]

A measurement. No `src/` change and no new test. It serves T0.3's R0 (`T0#t0-3-r0`, the
25-file list below is the list T0.3's harness loads with) and 29.4 R0.1, R0.2 and the static
part of R0.3. The weights were written by a committed script,
`scripts/shard_weights_from_durations.py`, to `tests/shard_weights.json`. {#what}

## The run {#run}

| Item | Value |
|---|---|
| clone / branch / base sha | `/Volumes/littlebig/refmatrix-r0`, `task-29.4-r0`, `4c6a0c6` |
| interpreter | dev tree `.venv-eval` (Python 3.14, duckdb 1.5.3), `PYTHONPATH=<clone>/src` |
| command | `pytest -q -p no:cacheprovider --durations=0`, teed to `workflow/review-output/task-29.4/r0-serial.log` |
| exit code | 1 (`r0-exit.txt`: `PIPESTATUS=1`) |
| collected | 5,041 (`--collect-only` afterwards: `r0-collect.log`, no test run) |
| passed / failed / errors / skipped | 4,891 / 4 / 127 / 19 |
| wall | 3,267.73 s (54:27) by pytest; 3,271 s between the two `date` stamps |
| load average (1 / 5 / 15 min), before | 12.44 / 8.17 / 6.79 at 22:07 (other agents were working) |
| load average, after | 5.09 / 5.39 / 5.80 at 23:01 |
| summed phases | 3,255.09 s over 361 files; 6,778 phases under 5 ms hidden by `-q` (at most 33.9 s, not in the sums) |
{#run-table}

The 19 skips are exactly the 19 pins in conftest's `_CLONE_ONLY_SKIPS`. {#run-skips}

## R0 digest: failures by E line {#digest}

Compared with the dev tree's `workflow/review-output/release-0.84.0-full.log` (13 failed,
5,028 passed, 3,587.62 s). E lines normalised for tmp paths, pids, hex addresses and seconds.
{#digest-method}

| Node | Phase | E line (normalised) | In 0.84.0 | Class |
|---|---|---|---|---|
| `test_task21_1_agent_usage_report.py::test_ac6_frozen_fixture_prints_the_exact_counts` | call | `AssertionError: agent usage · window 2026-09-23 .. 2026-10-07T11:06:35 (since inclusive, until exclusive)` | yes, same E line | persisting (open row) |
| `test_task21_1_agent_usage_report.py::test_ac6_cli_log_recalls_are_split_per_channel` | call | same | yes, same E line | persisting (open row) |
| `test_scanorder_r2_l120.py::test_m1_an_unchanged_composite_is_delivered_again_after_compaction` | call | `FileNotFoundError: [Errno 2] No such file or directory: '<clone>/.venv-eval/bin/rmx'` | no | clone environment |
| `test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate` | call | `scripts/lint-gmd.sh did not run its checks (exit 2)`: `dev interpreter not found at <clone>/.venv-eval/bin/python` | no | clone environment |
| 127 nodes in 5 files (below) | setup | `AssertionError: dev rmx missing at <clone>/.venv-eval/bin/rmx` (all 127 identical) | no | clone environment |
{#digest-table}

The 127 setup errors: `test_bug241_rule_docs_reingest.py` 96, `test_bug240_ingest_file_arg_mcp.py`
10, `test_bug241_r2_l112.py` 9, `test_bug240_ingest_file_arg.py` 8, `test_bug241_r3_l114.py` 4.
Their fixtures expect a `.venv-eval/` inside the checkout; a littlebig clone has none. The lead
is logging this as its own bug. **Clone-environment class: 129 nodes (127 errors + 2 failures)
plus the lint-gate failure, 130 in all, one cause.** No failure outside that class is new.
{#digest-clone-class}

The 0.84.0 failures this clone cannot see: {#digest-unseen}

- `test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon` (DuckDB
  lock `IOException`) and `test_repo_hooks_in_sync.py::test_installed_hooks_match_generated`:
  pinned in `_CLONE_ONLY_SKIPS`, so skipped here.
- `test_search_hooks.py` (10 nodes): ran and **passed** here. Its 0.84.0 failures depend on the
  dev tree's own installed hooks (bug-168), which a clone does not have.
{#digest-unseen-list}

bug-231 (`test_plan4_remedy.py::test_graceful_stop_on_a_live_daemon_returns_quickly`, call
5.21 s against 8.0) and bug-228 (`test_task21_1_recall_skip.py::test_ac2b_live_daemon_recall_writes_one_ok_recall_row`,
call 5.28 s) both **passed** in this run. {#digest-bug228-231}

## Per-file weights {#weights}

`tests/shard_weights.json`: per-file seconds (setup + call + teardown), the per-phase split, and
two lists the runner must not mistake for real weights. {#weights-file}

- **Understated (errored at setup, setup time only):** the 5 files above. Their errored tests are
  counted setup-only, as instructed. `test_bug241_rule_docs_reingest.py` (96 tests, tier (b))
  has no entry at all: every phase was under 5 ms. Its working-run weight is unknown and could
  be large. The two failing files and `test_task21_1_agent_usage_report.py` are listed too.
- **No entry (every phase hidden):** `test_brief_real_daemon.py`, `test_grep_count_rows_e2e.py`,
  `test_repo_hooks_in_sync.py` (clone-skipped), `test_bug241_rule_docs_reingest.py` (errored).
  R2's no-weight rule (the tier's median per test × collected count) covers them.
{#weights-gaps}

### The 25 heaviest files {#top25}

Tier by the draft rule ([[#tiers]]). These 25 hold 1,972.1 s, 60.6% of the summed time.

| # | File | s | Tier |
|---|---|---|---|
| 1 | `test_memory_bridge.py` | 244.93 | b |
| 2 | `test_task25_1_recall_budget.py` | 156.01 | d |
| 3 | `test_bridge_move_safety.py` | 146.44 | b |
| 4 | `test_plan3_remedy_r5.py` | 143.48 | d |
| 5 | `test_task21_1_used_events.py` | 132.68 | b |
| 6 | `test_bug212_r4_red.py` | 115.50 | b |
| 7 | `test_memory_compile_scope.py` | 92.93 | b |
| 8 | `test_savestate_mtype.py` | 92.85 | b |
| 9 | `test_plan3_remedy_r4.py` | 80.99 | d |
| 10 | `test_bridge_move_safety_r1.py` | 79.83 | b |
| 11 | `test_modelsrv.py` | 67.29 | b |
| 12 | `test_bug216_hidden_no_pollution.py` | 59.76 | a |
| 13 | `test_sync_fails_loudly_r2.py` | 56.20 | b |
| 14 | `test_bug212_r6_red.py` | 53.38 | b |
| 15 | `test_task3_6_r9_remedy.py` | 52.87 | d |
| 16 | `test_task21_1_emitters.py` | 51.89 | b |
| 17 | `test_rerank_budget_real_clients.py` | 45.35 | d |
| 18 | `test_plan3_remedy_r6.py` | 44.66 | d |
| 19 | `test_plan4_remedy_r3.py` | 41.65 | d |
| 20 | `test_plan3_remedy_r3.py` | 37.42 | b |
| 21 | `test_plan4_remedy.py` | 37.25 | d |
| 22 | `test_bug225_handoff_trunk.py` | 36.27 | b |
| 23 | `test_catalog_measure.py` | 35.68 | b |
| 24 | `test_bug212_r1_remedy.py` | 34.11 | b |
| 25 | `test_memory_compile_remedy_r1.py` | 32.71 | b |
{#top25-table}

## Run-tier totals {#tiers}

**How files were assigned.** `tier_of` does not exist yet. Each file got the tier that
`workflow/measurements/plan-29-spec-census/tier_rule.py`'s `tier()` gives it, run unchanged on
`tier_signals.py`'s output at `4c6a0c6`: devtree if the file has a `_CLONE_ONLY_SKIPS` pin, reads
the real home, or is one of the two listed files; else timing if `wallclock_census.py` finds a
literal upper bound in it or it is one of the three files with a non-literal bound that
`tier_rule.py` hard-codes from `f3709d2`; else daemon if any spawn / daemon / socket / hub /
model signal is in it or in a `tests/` helper it imports; else unit. The weights were joined on
the file name (a scratch script that copies `tier()` verbatim). {#tiers-rule}

| Tier | Files | Tests | Serial s | Heaviest file |
|---|---|---|---|---|
| (a) unit | 199 | 2,043 | 392.7 | `test_bug216_hidden_no_pollution.py` 59.8 |
| (b) daemon | 126 | 2,290 | 2,064.9 | `test_memory_bridge.py` 244.9 |
| (c) devtree | 15 | 161 | 15.4 (clone: pinned tests skipped) | `test_sandbox_hardening.py` 3.4 |
| (d) timing | 25 | 547 | 782.1 | `test_task25_1_recall_budget.py` 156.0 |
| **total** | **365** | **5,041** | **3,255.1** | |
{#tiers-table}

## Band verdicts {#bands}

Tier (a) at 4 shards and tiers (a)+(b)+(d) are **projections from a serial run**, not
measurements. Shards are placed by R2's rule (heaviest first, into the lightest shard) on the
weights. The projection assumes a shard runs as fast as the same files did serially, at load
5-12. It does not price 8-12 concurrent processes contending for 12 performance cores and the
two model workers, nor the understated tier-(b) weights ([[#weights-gaps]]). {#bands-caveat}

| Measured | Arithmetic | Value | Band | Action |
|---|---|---|---|---|
| run tier (a) wall, 4 shards (projected) | 392.7 s → shards 98.2 / 98.2 / 98.2 / 98.1 s | **1.6 min** | ≤ 5 min | every review round runs the whole of tier (a) |
| tiers (a)+(b)+(d), 4 shards (projected) | max((a) 98.2, (b) 516.3) + (d) 782.1 = 1,298.4 s | **21.6 min** | 20-30 min | sweep tier-(b) shards over 4, 6, 8 |
| ... sweep at 6 | 344.3 + 782.1 = 1,126.4 s | 18.8 min | meets 20, headroom 6.1% | below the 10% the band requires |
| ... sweep at 8 | 258.3 + 782.1 = 1,040.4 s | **17.3 min** | ≤ 20, headroom 13.3% | 8 is the smallest count that meets the band (projected) |
| run tier (d) wall, serial (measured as a sum) | 782.1 s | **13.0 min** | > 6 min | **BREACH**: [[task-29.4-suite-health#r3]] replaces the heaviest files' bounds first, in duration order |
{#bands-table}

Tier (d) is 75% of the projected 8-shard wall, and it runs alone after (a) and (b). Once (b) is
at 6 shards or more, the (a)+(b)+(d) total moves with tier (d) and barely with the shard count.
Duration order for [[task-29.4-suite-health#r3-scope]]: `test_task25_1_recall_budget.py` 156.0 s
(143 tests, one bound, L735 `< 5.0`), `test_plan3_remedy_r5.py` 143.5 s (6 bounds),
`test_plan3_remedy_r4.py` 81.0 s (7), `test_task3_6_r9_remedy.py` 52.9 s (4),
`test_rerank_budget_real_clients.py` 45.4 s (11), `test_plan3_remedy_r6.py` 44.7 s (4),
`test_plan4_remedy_r3.py` 41.6 s (2). Moving the first file alone out of (d) takes it from 782 s to
626 s; the first two, to 483 s (8.0 min). {#bands-d-order}

## The baseline, re-stated {#baseline-restated}

Static numbers come from the census scripts in
`workflow/measurements/plan-29-spec-census/`, run unchanged at `4c6a0c6` from a scratch
directory, on `r0-collect.log`. They ran clean (exit 0). The scripts in
`workflow/plans/plan-29-code-quality-tasks/census/` belong to other plan-29 tasks and were not
run. {#baseline-restated-method}

| Measure | `f3709d2` | `4c6a0c6` (R0) |
|---|---|---|
| test files / tests collected | 357 / 4,883 | 365 / 5,041 |
| test lines | 95,148 | 96,590 |
| largest files by test count | `test_verb_parity.py` 167, `test_task25_1_recall_budget.py` 143, `test_memory_index_layout.py` 96 | same, with `test_bug241_rule_docs_reingest.py` 96 level with the third |
| last full serial run | 0.83.0: 14 failed, 4,869 passed, 3,517 s, load 5.6-7.6 | 0.84.0 (dev tree): 13 failed, 5,028 passed, 3,587.62 s. R0 (clone): 4 failed, 127 errors, 4,891 passed, 19 skipped, 3,267.73 s, load 12.4 → 5.1 |
| per-file durations | not known | known: `tests/shard_weights.json` |
| wall-clock upper bounds (literal / non-literal / total) | 70 in 22 / 8 in 4 / 78 in 26 | 70 in 22 / 8 in 4 / 78 in 26 (unchanged) |
| lower bounds listed by the script | 8 lines in 6 files | 8 lines in 6 files |
| tier (a) files / tests | 196 / 2,022 (41.4%) | 199 / 2,043 (40.5%) |
| tier (b) | 121 / 2,153 (44.1%) | 126 / 2,290 (45.4%) |
| tier (c) | 15 / 161 (3.3%) | 15 / 161 (3.2%) |
| tier (d) | 25 / 547 (11.2%) | 25 / 547 (10.9%) |
| real daemon / serve signal (tier b / all tiers) | 61 / 81 | 66 / 86 |
| model signal (all / tier b) | 19 / 14 | 19 / 14 |
| `mkdtemp(dir="/tmp")` (`suite_census.py`'s pattern) | 95 sites in 62 files (spec's count) | 100 hits in 67 files |
| test files importing `store` / `daemon` / `cli` / `verbs` directly | 220 / 156 / 136 / 59 | 225 / 158 / 136 / 61 |
| median direct family | 4 | 4 |
| closure family | 324 of 357, for 71 of 73 modules | 331 of 365, for 71 of 73 modules |
| test files importing no `refmatrix` module | 24 | 25 |
| test files that reach code only through a child process | 85 | 90 |
| `outcome`-vs-string tests / with a real daemon | 13 / 1 (bug-228) | 13 / 1 (bug-228) |
{#baseline-restated-table}

## What the measurement contradicts or leaves open {#findings}

1. **R1's derived devtree rule misses a `.venv-eval/` dependency.** R1 names "its own
   `.venv-eval/`" as a devtree property, but no derived signal looks for it. Seven files fail in
   a clone for that reason alone: `test_bug240_ingest_file_arg.py`, `..._mcp.py`,
   `test_bug241_r2_l112.py`, `test_bug241_r3_l114.py`, `test_bug241_rule_docs_reingest.py`,
   `test_scanorder_r2_l120.py` (all tiered (a) or (b) by the draft rule) and
   `test_gmd_lint_requires_version.py` (tier (c) by its real-home read, but its failing test is
   not pinned).
2. **Tier (d) is set per file, so most of it is not timing.** 547 tests sit in tier (d) for 77
   bounds. `test_task25_1_recall_budget.py` brings 143 tests and 156 s for one assert. Tier (d)
   breaches its 6-minute band by more than two times.
3. **R0 did not get the failing bug-228 run that `#r3-bug228` asks it to measure.** bug-228 and
   bug-231 both passed at load 5-12. The leg breakdown has to come from T0.3's harness.
4. **A 60-second tier-(a) file.** `test_bug216_hidden_no_pollution.py` has no process signal and
   takes 59.8 s, 15% of tier (a). Tier (a) still meets its band, so `#r0-bands`' re-tier action
   does not fire, but the file is the "slow file with no signal" the band describes.
5. **The suite grew:** 8 files and 158 tests since `f3709d2`, mostly in tier (b).
6. **`-q` hides phases under 5 ms** (6,778 here, at most 33.9 s). R0.1's command does not pass
   `-vv`, so the weights cannot count tests per file, and the counts above come from
   `--collect-only`.
7. **The census output still says "of 357 files"** (`family_census.py` hard-codes the
   denominator). The count at `4c6a0c6` is 331 of 365.
{#findings-list}

## Files {#files}

- `workflow/review-output/task-29.4/r0-serial.log`, `r0-uptime-before.txt`, `r0-uptime-after.txt`,
  `r0-exit.txt`, `r0-collect.log`
- `tests/shard_weights.json`
- `scripts/shard_weights_from_durations.py`
{#files-list}
