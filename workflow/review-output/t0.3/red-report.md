---
gmd: "0.1"
id: t0-3-red-report
title: "T0.3 + 29.4c RED report: load flakes, the load harness, wall-clock and budget-outcome censuses"
tags: [report, tdd, red, t0-3, task-29.4]
metadata:
  node_type: report
  created: 2026-11-15
---

# T0.3 + 29.4c RED report {#root}

rel: derives-from -> [[task-t0-suite-trust-sweep#t0-3]]
rel: derives-from -> [[task-29.4-suite-health#r3]]
rel: derives-from -> [[task-29.4-r0-durations#top25]]

Branch `task-t0.3-load-flakes-wallclock` in `/Volumes/littlebig/refmatrix-t03`, base `c4b44d0`.
RED commits: `1bedf9e` (tests), `84ca55d` (bug-091 fold), `d8d304c` (harness + logs), and the
tip that adds this report and the validation trial. Interpreter: the dev tree's `.venv-eval`
with `PYTHONPATH=<clone>/src`; every run under `/usr/bin/lockf
/private/tmp/claude-501/rmx-test-lane.lock`.

## The RED run {#red-run}

`workflow/review-output/t0.3/red-base-all-new-nodes.log`, at `84ca55d`, with the harness absent
from the tree (moved aside for the run, so the harness tests are RED too): **exit 1, 84
collected, 0 passed / 84 failed / 0 errors / 0 skipped**, 13.04 s. No SkipGate line.
(The first run, `red-base-new-nodes.log`, 68 failed, predates the harness tests and the bug-091
fold.)

| File | Nodes | Base E line |
|---|---|---|
| `tests/test_wallclock_census.py` | 41 | 37: `ImportError: cannot import name 'wallclock_census' from 'tests'`; 4 (the tree nodes that read the list first: bug-228/231 entries, the four R3-scope files, class C/D, tier (d) band): `FileNotFoundError: … tests/wallclock_allow.json` |
| `tests/test_budget_outcome_census.py` | 15 | `ImportError: cannot import name 'budget_outcome_census' from 'tests'` |
| `tests/test_timing_helpers.py` | 6 | `ImportError: cannot import name 'timing' from 'tests'` |
| `tests/test_t03_outcome_mechanisms.py` | 2 | `ModuleNotFoundError: No module named 'tests.timing'` |
| `tests/test_t03_flake_diagnostics.py` | 4 | each its own, below |
| `tests/test_t03_load_harness.py` | 16 | `FileNotFoundError: … scripts/t03_load_harness.py` |
{#red-table}

The four diagnostics nodes, each RED on the flake's own failure shape:

- `test_r3_1_bug130_a_failed_store_fails_on_its_error_not_on_a_keyerror`: `AssertionError:
  R3.1/M3.1: the test indexed rewrite_bytes_all before checking `failed`` over the child's
  `E KeyError: 'rewrite_bytes_all'`, bug-130's registry E line, reproduced on demand.
- `test_r3_4_bug190_a_spawn_on_the_skip_path_names_its_stack`: `AssertionError: R3.2/R3.4: the
  failure does not name the stack of the spawn` over the child's `E AssertionError: (0.0002…, 1)`
  / `assert (… < 0.3 and 1 == 0)`, bug-190's `spawns == 1`, reproduced on demand.
- `test_r3_3_bug091_the_delivery_deadline_is_a_named_constant_of_at_least_30s`:
  `AssertionError: R3.3: tests/test_watch.py has no WATCHER_DELIVERY_DEADLINE_S >= 30 (got None)`.
- `test_r3_4_bug091_a_watcher_that_never_fires_reports_elapsed_and_state`: `AssertionError:
  R3.4: the failure does not give the elapsed time` over the child's `watcher did not fire` /
  `wait(timeout=3.0)`, bug-091's E line.
{#red-diagnostics}

**Census RED cases** (a census that passes at base is not a RED test; its must-fail cases are
what is RED). Wall-clock: the five upper-bound shapes found (`clockdiff < 2.0`, a name bound from
a clock, `elapsed < 2.0`, `took < LIMIT`, `0.5 < wall < 3.0`); an unlisted bound fails naming
file, test and the four classes; a local `HANG_GUARD_S` is not exempt; a `HANG_GUARD_S` of 30
fails; a stale entry fails; `tests/fixtures/other/` is not exempt; a new `legacy` entry fails;
`ac` missing / unknown spec id / a file stem in place of the frontmatter id / unknown anchor;
a knob never set; a value over `max_s`; `max_s` over 2.0; a second entry for a one-clause AC;
a clause not in its AC; `arg:` omitted, passed as a variable, literal over `max_s`.
Budget-outcome: bug-228's test as it stands at base (frozen copy
`tests/fixtures/suite_health/case_bug228_base.py`), a bare `str.replace`, `with_budget` given a
name, a synthetic `SandboxDaemon` with no knob, a `spawn_daemon_subprocess` with no knob, a
daemon reached through a fixture, a `budget-outcome` entry with no reason,
`tests/fixtures/other/` not exempt. The pass cases (lower bound, imported `HANG_GUARD_S`,
`fixtures/suite_health/`, the three knob forms, two clauses for a two-clause AC, the silent-peer
`skipped_budget` leg, `with_budget(…, HANG_GUARD_S)` and `with_budget(…, 60.0)`, a test-owned
peer, a reasoned entry) are RED at base only by the missing module.
{#census-red}

**Preview (not committed code).** A scratch GREEN for the three flaky tests (the patch is in the
scratchpad, reverted after) makes all four diagnostics nodes and the three flaky tests pass:
`preview2-flake-diagnostics-with-scratch-green.log`, exit 0, 7 passed. The first preview caught
an over-broad text check of mine (`timeout=3.0` matched a legitimate `t.join(timeout=3.0)`); it
was replaced by a forced deadline of 4.0 s, above the old 3 s wait, so a test that reads the
constant and still gives up at 3 s fails M3.3 (`84ca55d`).
{#preview}

## The contract GREEN builds to {#contract}

The spec names files and behaviours; these names are the tests' (RED owns the contract):

- `tests/wallclock_census.py`: `find_bounds(source, relpath)` → objects with `.key` (`relpath::
  function::normalised assert`, no line number), `.function`, `.lineno`;
  `run_census(tests_root, *, allow_path, specs_root, legacy_baseline=None)` → `.ok`, `.errors`,
  `.counts == {"legacy": n, "feature-bound": m}`, `.report()`. `legacy_baseline=None` means a
  baseline GREEN freezes at the task's base.
- `tests/budget_outcome_census.py`: `violations(source, relpath)` → `relpath::function` keys;
  `run_census(tests_root, *, allow_path)` → `.ok`, `.errors`.
- `tests/wallclock_allow.json`: `{"entries": [...]}`; kinds `legacy` (`key`, `class`),
  `feature-bound` (`key`, `ac`, `knob`, `max_s`, `clause`), `budget-outcome` (`key`, `reason`).
  The `const:` pass case uses `monkeypatch.setattr("pkg.mod.NAME", 0.2)`.
- `tests/timing.py`: `HANG_GUARD_S >= 60`; `wait_for(predicate, *, timeout=HANG_GUARD_S,
  interval, what)` (returns the value; at the deadline `AssertionError` naming `what` and the
  elapsed seconds); `with_budget(command, seconds)` (the one `--timeout` value; raises on zero
  or two).
- `tests/test_watch.py`: module constant `WATCHER_DELIVERY_DEADLINE_S >= 30`, read at call time
  (the forcing plugin patches it on the module).
- The three flaky tests' failure messages (R3.4), read from the child's `E` lines: bug-130 carries
  the failed store's `error`; bug-190 carries the stack of every spawn (the forcing frame
  `_t03_forced_spawn` must appear); bug-091 carries `elapsed <n>` (≥ the deadline) and the
  watcher's state (`alive`/`running`/`started`/`stopped`/`state` after the word `watcher`).
{#contract-list}

## Mutation-to-node map {#mutations}

| Mutation | Node(s) that must go red |
|---|---|
| T0 M3.1 bug-130 indexes before its `failed` check | `test_t03_flake_diagnostics.py::test_r3_1_bug130_a_failed_store_fails_on_its_error_not_on_a_keyerror` |
| T0 M3.2 the bug-190 skip path spawns (`src/`) | `test_rerank_budget_real_clients.py::test_a_cold_private_worker_is_skipped_without_spawning` (existing; the forced spawn above shows it catches a spawn) |
| T0 M3.3 the watcher is never started | `test_watch.py::test_run_watcher_picks_up_new_file` at its 30 s deadline; `test_r3_4_bug091_a_watcher_that_never_fires_reports_elapsed_and_state` at the forced 4.0 s |
| T0 M3.4 each R3.4 message drops its cause | the three forced nodes: `test_r3_1_bug130…` (store error), `test_r3_4_bug190…` (spawn stack), `test_r3_4_bug091…` (elapsed, state) |
| 29.4 #7 numeric literals only | `test_wallclock_census.py::test_ac4_must_fail_each_upper_bound_is_found[took_lt_LIMIT]`, `…unlisted_bound…[took_lt_LIMIT]`, `test_ac4_must_fail_a_local_hang_guard_name_is_not_exempt` |
| 29.4 #8 stale entries ignored | `test_ac4_a_stale_entry_fails` |
| 29.4 #18 a new `legacy` entry accepted | `test_ac11_a_new_legacy_entry_fails` |
| 29.4 #19 `ac` not resolved | `test_ac11_feature_bound_whose_spec_id_does_not_exist_fails`, `…_spec_id_is_only_a_file_name_fails`, `…_anchor_does_not_exist_fails` |
| 29.4 #20 knob not checked | `test_ac11_feature_bound_whose_test_never_sets_its_knob_fails` |
| 29.4 #21 budget census ignores fixtures | `test_budget_outcome_census.py::test_must_fail_a_daemon_reached_through_a_fixture` |
| 29.4 #23 `arg:` accepts a non-literal | `test_ac11_arg_knob_passed_as_a_variable_fails` |
| (bug-231 mechanism, src) `graceful_stop` waits out its grace | `test_t03_outcome_mechanisms.py::test_bug231_graceful_stop_returns_when_the_pid_is_gone_not_at_the_deadline` (poll count k → hundreds; slow, about `HANG_GUARD_S`, but it fails, it does not hang) |
{#mutation-table}

## The harness {#harness}

`scripts/t03_load_harness.py` (`plan` / `trial` / `run`) and `scripts/t03_capture.py` (the
target-process plugin). Bands, cap, placement and outcome rules are pinned by
`tests/test_t03_load_harness.py` (16 nodes; RED with the harness absent, then 16 passed, exit 0:
`harness-logic-tests.log`, `harness-logic-tests-2.log`). The load list is the frozen top 25
(1,972.13 s). Level splits by the R2 rule: 3 → 667.7 / 669.0 / 635.5 s; 5 → 388.7 … 417.0 s;
8 → 234.1 … 260.2 s. Cap at level 3 for one row: about 5,926-6,023 s. Each trial takes the lane
lock on its own. The capture plugin records each target's outcome and E line and the base
evidence the spec needs before any fix (bug-130 rows; bug-190 spawn stacks; bug-091 threads;
bug-228 boot, hook wall and log tails, from which the leg breakdown of the first failing trial
is read; bug-231 `graceful_stop` grace, wall and report).
{#harness-body}

### Validation trial, and why I stopped there {#validation}

One trial, level 3, all five targets in one target process, `--load-mode complete`, at
`d8d304c` (`workflow/review-output/t0.3/harness/validation-l3-all5/`). It is a harness check and
is **not counted** toward any band.

- Targets: all five passed. bug-231 call 7.65 s against its 8.0 bound, `graceful_stop` 6.89 s
  (`stop_op: sent`); bug-228 call 6.60 s (SandboxDaemon boot 0.43 s, `run_hook` 3.42 s, outcome
  `ok`); bug-130 0.62 s; bug-091 0.38 s; bug-190 no spawn.
- The five targets finished 36.2 s after the trial began (20 s warm-up included).
- **The host slept through most of it.** `pmset -g log`: `Sleep` at 03:52:01 ("Dark Wake
  Thermal Emergency"), `DarkWake` 04:08:15, `Sleep` 04:13:37, `DarkWake` 04:30:10, `Sleep`
  04:31:13, `DarkWake` 04:47:26. The trial held the lane 58 min of wall clock and got 605.7 s
  awake (the harness's monotonic clock does not advance in sleep). In those 10 awake minutes the
  load processes were at about 29% and 48% of their tests.
- I aborted it at 58 min wall to free the lane (other agents were queued): `ps`/`lsof` first
  (`aborted-ps-lsof.txt`), then SIGINT to the three process groups. SIGINT ended one; the other
  two ran on until SIGTERM. No embed worker or daemon from the trial was left afterwards. The
  harness now kills SIGINT → SIGTERM → SIGKILL and records `wall_clock_s` beside the awake wall.
- Load average 11.0 at the start, 38.5 at the end. Live-socket recorder lines added: **0**
  (`workflow/review-output/live-socket-touches.log` in the clone; the stage-0 count re-read
  today in `/Volumes/littlebig/refmatrix-r0`: 41 lines).
{#validation-body}

### Lane time {#lane-time}

**Used:** RED and previews about 1 min of test time; harness logic tests 2 s; the validation
trial 605.7 s awake, 58 min of lane held by wall clock. About 11 min awake, about 60 min held.

**Projected**, from the validation trial: a level-3 trial in `complete` mode is about 25-35 min
awake (about 30-48% of the load done in 10 awake min; serial would be 11 min), level 5 roughly
15-20 min, level 8 roughly 10-15 min (its heaviest process is `test_memory_bridge.py` alone,
245 s serial). A `until-target` trial is about 1-1.5 min (20 s warm-up, the targets' 36 s, the
kill).

| Plan | Base (≤ 3 levels × 10) | One fix attempt (45 at the reproducer's level) |
|---|---|---|
| spec text: one row per trial, `complete` | about 25 h per level-3 sweep of five rows; up to ~50 h if no row reproduces at 3 or 5 | about 20-26 h per row at level 3 |
| five rows share a trial, `complete` | about 5 h at level 3; up to ~10 h through level 8 | about 20-26 h at level 3 (all rows fixed at that level share it) |
| five rows share a trial, `until-target` | about 30-45 min through all three levels | about 45-70 min |
{#lane-time-table}

All of these are far over the 60-minute lane budget except the last row's base sweep, so no
base trial was run. Host sleep is a second problem: with Dark Wake Thermal Emergency sleeps,
an unattended multi-hour run holds the lane for several times its awake length.
{#lane-time-verdict}

**Decisions for the lead** (I take none of them):
1. Whether several rows may share one trial. The spec says "one harness run gives one trial";
   sharing keeps each row's outcome its own, and the five targets add 36 s to a trial.
2. Whether a trial may stop the load when the target exits (`until-target`). Then `#t0-3-cap`'s
   void rule can never fire, and the load the target sees is the load's first minute (here that
   was enough to put bug-231 at 7.65 s of its 8.0 bound).
3. Whether the machine is kept awake for the harness (`caffeinate -i` around a run), or whether
   trials are scheduled for attended hours.
{#lead-decisions}

## Base sweep (ruling L141) {#base-sweep}

rel: derives-from -> [[task-t0-suite-trust-sweep#t0-3-bands]]

Ruling L141: the five rows share one trial and each keeps its own outcome; `--load-mode
until-target`; every trial runs under `caffeinate -i`, with the lane lock taken per trial. A
level stops early once every row is decided (`base_band(...)["decided"]`: 3 failures reached,
or too few trials left to reach them). The harness for the sweep is at `dcebb15`. The logs are
`workflow/review-output/t0.3/harness-base-l{3,5,8}.log` and
`harness/base-l{3,5,8}/trial-NNN/` (`trial.json`, `target-outcomes.jsonl`, `diag.jsonl`,
load logs). Level 3 ran all five rows. Levels 5 and 8 ran the rows still open, plus bug-231 so
that the strict reading below has data at every level.
{#base-sweep-lead}

### Per row {#base-sweep-rows}

| Row | Level 3 | Level 5 | Level 8 | Verdict (spec band) |
|---|---|---|---|---|
| bug-130 | 1/9 | 1/9 | 0/8 | not reproduced (fewer than 3 in 10 at every level) |
| bug-190 | 0/9 | 0/9 | 0/8 | not reproduced |
| bug-091 | 0/9 | 0/9 | 0/8 | not reproduced |
| bug-228 | **5/9, reproducer at level 3** | not run (decided) | not run | reproducer, level 3 |
| bug-231 | 6/9 (1 on the row's E line, 5 on a new E line) | 9/9 (all on the new E line) | 3/8 (all on the new E line; trials 4-8 passed, stop 5.7-6.0 s) | see the strict reading below |
{#base-sweep-table}

E lines seen, by row:
- **bug-130:** `E KeyError: 'rewrite_bytes_all'` (the registry's E line), L3 trial 5 and L5
  trial 4. The capture plugin recorded the failed store's error both times:
  `step: unexpected, error: IndexError: tuple index out of range`. Cause, read from
  `eval/catalog_maint/measure_catalogs.py::_measure_copy`: under load the three rehearsal timings
  are noisy, `_is_noisy(times)` runs a second batch, `ix` reaches 3, and the TEST's own
  `bytes_hook=lambda ix, b: b + (0, 100, 300)[ix]` indexes past its three entries. This is a
  test defect: the test lets real timing noise decide how many runs there are. It is neither of
  R3.1's two routes (a harness defect in `measure_catalogs.py`, a product defect). The lead
  rules which route it takes. Not a reproducer by the band (1/9, 1/9).
- **bug-190, bug-091:** no failure.
- **bug-228:** five failures at level 3 (trials 5-9), each `AssertionError: {…row…}` on
  `assert rows[0]["outcome"] == "ok", rows[0]`. The row the plugin copied from `query.log` reads
  `"outcome": "skipped_budget", "latency_ms": 5018` (trial 5) and `5027` (trial 6),
  `budget_s: 5.0`. That is the registry's `'skipped_budget' == 'ok'`; pytest prints the
  assertion's message (the row) as the E line in place of the comparison.
- **bug-231:** two E lines.
  - The row's own: `assert (733208.75… - 733200.72…) < 8.0`, once (L3 trial 4, 8.83 s).
  - A new one: `AssertionError: assert False is True`, i.e. `hub_mod.graceful_stop(root,
    grace=10.0)` returned **False**. In L3 trials 5-9, all nine L5 trials and L8 (below), the
    spy shows the stop op `sent` and the call returning False at 10.01-10.06 s: the daemon was
    still alive when the 10 s grace ran out. The test's `finally` (`stop_daemon`) then found it
    not answering ping, sent SIGTERM, and it exited 3.8-10.6 s later.
  - **The strict reading** (T0 `#t0-3-band-found`: "each with the row's E line"): 1/9, 0/9,
    0/8. That is not a reproducer at any level. **Counting the grace-exhausted
    variant** as the same failure (a stop slower than its bound): 6/9 at level 3, a reproducer
    at level 3. 29.4 `#r3-bug231` foresaw the shape ("a daemon that dies at 10.0 s of a 10 s
    grace still gives True"), and here the daemon outlived the grace. Which reading holds is the
    lead's ruling to make.
{#base-sweep-elines}

### bug-228's leg breakdown (first failing trial: level 3, trial 5) {#base-sweep-bug228-legs}

From `harness/base-l3/trial-005/diag.jsonl` (spies plus the sandbox store's log tails):

| Leg | Time | Source |
|---|---|---|
| `SandboxDaemon` boot, until ping answers | 1.26 s, before the hook, outside the budget | `bug228.sandbox_daemon_boot` |
| the hook, end to end | 5.50 s; the row `latency_ms: 5018`, `outcome: skipped_budget` at 05:14:40 | `bug228.run_hook`, `query.log` |
| embed worker cold load | spawned 05:14:34 at daemon start, `embedder warm in 9.1s` at 05:14:43 | `rmxd.log` |
| the `memory_recall` op | in flight from the hook's arrival (about 05:14:35) through the budget's expiry, waiting on the embedder; it raised `WorkerError('embed worker retired …')` at 05:14:44, when the test had stopped the daemon | `rmxd.log` |
{#base-sweep-bug228-table}

So the 5 s budget was spent waiting for the embedder's cold load, which finished about 3 s after
the budget ran out. The recall itself never ran. Trial 6 shows the same: embedder warm in 5.6 s,
the row at 5027 ms. By 29.4 `#r3-bug228` that is "≥ 90% of the overrun before the recall op
starts (model warm-up)", which is the readiness branch (the test waits on the models being warm,
as bug-184's `wait_models_warm` does) and not the split. The product row's leg text, for the id
the lead allocates: "live recall over its 5 s budget at load 3: the embedder's cold load (5.6-9.1
s from daemon start) spent the budget; the recall op waited and never ran".

The no-daemon test I wrote for the split
(`test_t03_outcome_mechanisms.py::test_bug228_the_generated_recall_command_carries_the_5s_budget_and_with_budget_swaps_only_it`)
is still true under the readiness branch. Whether it stays is the lead's call: the readiness
branch keeps the live test on the real 5 s budget, so the budget-outcome census still flags it
unless it holds a reasoned `budget-outcome` entry (L141: no knob forms).
{#base-sweep-bug228-reading}

### Trials: awake and held wall, sockets, leaks {#base-sweep-trials}

"Awake" is the harness's monotonic wall (it does not advance in sleep). "Held" is the wall clock
from lock to release (`wall_clock_s`). Queue waits are not held time.

| Level | Trials | Awake s per trial | Held s per trial | Held total | Live-socket lines added | Leaks swept |
|---|---|---|---|---|---|---|
| 3 | 9 | 46-94 | 46-94 | 667 s | 0 in every trial | 3 (trial 8) |
| 5 | 9 | 84-110 | 84-110 | 883 s | 0 in every trial | 0 |
| 8 | 8 | 77-121 | 77-121, except trial 4: 1,002 (asleep) | 1,674 s | 0 in every trial | 4 (trials 2, 3) |
{#base-sweep-trial-table}

- **Held lane in all: 3,225 s (53.8 min); awake 2,304 s (38.4 min)**, of which about 15.5 min was asleep (below), plus the
  validation trial's 58 min earlier.
- **`caffeinate -i` did not keep the host awake.** In L8 trial 4, `pmset -g log` shows `Sleep`
  at 07:24:51 ("Dark Wake Thermal Emergency") and `DarkWake` at 07:40:19. That trial got 81 s
  awake inside 1,002 s held. Its target had finished at 33 s, before the sleep, so the outcome
  stands. A thermal-emergency sleep in DarkWake is not an idle sleep, and `-i` cannot hold it
  off. `caffeinate -s` (AC power) might not either; that is unmeasured.
- **Leaks.** Three trials (L3 8, L8 2, L8 3; 7 processes) left a `src/refmatrix/cli.py daemon start --no-watch` (ppid 1, cwd the
  clone) and its embed worker or workers behind. A load process killed mid-test (`until-target`)
  leaves them. The harness recorded each one (`leaked-ps-lsof.txt`) and sent SIGTERM. Nothing
  from the sweep was running afterwards.
- **The failures cluster in time.** At level 3, trials 1-4 passed bug-228 and three of the four
  passed bug-231 (bug-231 at 5.4-8.0 s). From trial 5 on, every trial failed both, and trial
  walls doubled (46-59 s, then 88-94 s). Load averages at the start do not separate the two
  groups (9.1-18.1 vs 9.5-17.0). The grace-exhausted stops ran from 05:14 (L3 trial 5) through
  L8 trial 3 (about 07:20), at levels 3, 5 and 8 alike. After the host's sleep and wake at
  07:24-07:40, L8 trials 4-8 stopped in 5.7-6.0 s. So the slow stop follows a time window, not
  the load level. The data do not say what changed.
{#base-sweep-notes}

## Mock registry rows {#mock-rows}

Added to `workflow/test_mock_registry.md#registry` (three rows): the `t03_force` fault
injections in child pytest runs (`n/a (fault injection)`); the daemon-boundary fakes of the
bug-231 poll test (`external`); the capture plugin's spies (`internal-active (observer)`, the
harness only, never the suite).
{#mock-rows-body}

## Stale citations reconciled {#stale}

1. **Branch name.** T0 `#scope` names `task-t0.3-load-flakes`; the lead's brief named
   `task-t0.3-load-flakes-wallclock`. I used the brief's.
2. **Log directory.** T0 `#r0-3` says `workflow/review-output/t0/`, 29.4 says `task-29.4/`; the
   brief says `t0.3/`. I used the brief's.
3. **Where the budget census's helper table lives.** 29.4 `#r3-budget-census` puts it in
   `tests/tiering.py`, which is stage 4's file (29.4a), not on this branch. The tests do not pin
   its location.
4. **The wall-clock count.** Re-run at `c4b44d0` with the census scripts: 70 literal bounds in 22
   files and 8 non-literal in 4, 78 in all, as at `f3709d2` and `4c6a0c6`. The test pins
   `legacy <= 77`.
5. **`HANG_BOUND_S`.** The site is `tests/test_bug212_r4_red.py:771` as cited; the constant is
   45 (`:714`) and is also the `bound=` of four bounded calls (`:761`, `:786`, `:972`, `:993`).
   Renaming it to `HANG_GUARD_S` (≥ 60) raises those four kill bounds from 45 s to ≥ 60 s
   unless GREEN keeps them on their own name. That is GREEN's choice, and I am flagging it.
6. **Tier (d) arithmetic.** From `tests/shard_weights.json`: the 25 files with a bound sum to
   782.13 s; without the four R3-scope files, 348.78 s ≤ 360. That matches
   `task-29.4-r0-durations#bands-d-order`.
7. **The top-25 sum** is 1,972.13 s (the summary's 1,972.1).
8. **bug-190's test holds a class-C bound itself** (`wall < 0.3`); R3-scope replaces class C
   everywhere, so its fix edit and its bound replacement are the same edit.
{#stale-list}

## Not followable as written, or left open {#open}

- **The budget census's knob forms.** 29.4 `#r3-budget-census` lets a hit "set the budget's
  knob" (`env:`/`const:`/`arg:`), but nothing says which env or constant is a budget's knob, so a
  census cannot tell `setenv("RMX_X", "60")` from an unrelated env. The tests pin only
  `with_budget` and reasoned entries. The lead decides whether a declared knob table is wanted.
- **bug-228's no-daemon test assumes the split.** If a failing trial shows ≥ 90% of the overrun
  before the recall op, `#r3-bug228` builds a readiness wait instead. The test still holds
  (the command does carry 5 s, and `with_budget` swaps one token), but it is then not "the split".
- **bug-091's 0.2 s subscribe sleep.** A write made before the observer subscribes is never
  delivered, and no deadline fixes that. GREEN should wait for the subscription or re-touch the
  file while polling. The forced test does not cover this race.
- **Separation of duties.** The brief gave me the harness, so its author wrote the harness tests
  too. They were RED before the harness was in the tree (16 `FileNotFoundError`), but a ch-bsd
  pass should treat them as self-tested.
- **Product rows.** AC-6's two registry rows (bug-231's full-grace exit, bug-228's live budget)
  and any R3.1 row need ids from the lead.
- **Base trials and the bug-228 leg breakdown:** done under ruling L141 ([[#base-sweep]]).
{#open-list}
