---
gmd: "0.1"
id: task-29.4-suite-health
title: "Task 29.4: heal the test suite — four tiers, a sharded runner, outcome checks for wall-clock bounds, a daemon reaper that fails the session, derived test families"
tags: [task, plan-29, tests, tiers, shards, flaky, wall-clock, daemon, reaper, families, code-quality]
metadata:
  node_type: task
  status: pending
  plan: plan-29-code-quality
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 29.4: heal the test suite {#root}

> Plan: [[plan-29-code-quality]] ([[plan-29-code-quality#t4]])
> Status: Pending
> **The T0 suite-trust sweep is this task's body.** T0 (`task-t0-suite-trust-sweep`, approved on
> branch `spec-wave-t0` at `fa1227d`; track T0 in [[plan-review-2026-11-13#p1]]) and 29.4 were
> one job split in two with a circular closure (queue review `#b3`, lead-accepted 2026-11-14).
> T0's sub-tasks keep their ids (T0.1 to T0.8) and their text. This spec orders them, adds to
> three of them, and adds what T0 does not have: run tiers, the sharded runner, the wall-clock
> rule and the reaper ([[#fold]]).
> Depends on: [[task-29.1-registry-triage]]; the 0.83.0 deploy; the frozen spec-branch merges
> (T0's spec arrives with them), with T0 amended as [[#fold-deltas]] lists.
> Runs second in plan-29's order: 29.1 → **29.4** → 29.5 → 29.2 ∥ 29.3. One part, the derived
> families ([[#r6]]), is built after 29.5.
> Closes, by this spec's text: bug-228, bug-229, bug-231. By T0's text: bug-215, bug-155's
> residual, bug-170, 168, 127, 130, 190, 091, 196, and the closure gates of plans 6, 7, 8, 15.
> **Decided by the user on 2026-11-14 (ruling L106), and built to here** ([[#user-decisions]]):
> `plan-review-fable D3` = (a), sharding only after any live touch fails the session, which is
> stage 4's gate; `plan-review-fable-store D5`, duckdb 1.5.3 before baselines;
> `plan-review-fable D4`, a standing go that covers this task's release.
> User gates: none of its own. T0 can be held by a hook-drift stop at its `#r7-4`.

rel: part-of -> [[plan-29-code-quality]]
rel: implements -> [[plan-29-code-quality#t4]]
rel: depends-on -> [[task-29.1-registry-triage]]
rel: depends-on -> [[tdd-governance]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[plan-review-2026-11-13#p1]]
rel: related-to -> [[task-29.5-split-giant-modules]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: reinforces -> [[feedback_review_clones_cannot_see_dev_tree_failures]]
rel: reinforces -> [[feedback_family_list_misses_generated_checks]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_compare_failures_by_error_not_name]]
rel: reinforces -> [[feedback_mutation_must_fail_not_hang]]

**How other documents are cited here.** Three documents this spec leans on are not on the
branch it was written on, and a link to a document the branch does not hold fails the repo
lint gate. They are written as code, and become links when the branches meet:
- **T0** = `task-t0-suite-trust-sweep` (branch `spec-wave-t0`, `fa1227d`); its anchors are
  written `T0#r7-4`.
- **queue review** = `plan-review-fable-2026-11-14-queue` (dev `master`, `3551894`);
  **store review** = `plan-review-fable-2026-11-14-store` (`ec3e0e8`); **memory review** =
  `plan-review-fable-2026-11-14-memory` (`0254373`). Their user decisions are labelled
  `plan-review-fable D<n>` and `plan-review-fable-store D<n>`.
{#citing}

## Why {#why}

The user asked on 2026-11-14 for the tests to run modularly. Today there is one way to run them:
every test, in one process, in file order. That run took 58 min 37 s for the 0.83.0 release.
Four things follow from it:

- **A review round costs an hour**, so rounds run hand-picked "families" instead, and a
  hand-picked family misses what only the whole suite shows
  ([[feedback_family_list_misses_generated_checks]]).
- **Speed is asserted, so load fails tests.** 78 assertions put an upper bound on elapsed
  seconds. One of them is an open row (bug-231 failed at 10.05 s and 9.02 s against 8.0), and
  bug-228 fails the same way through a 5 s product budget with no `<` in the test at all.
- **A daemon can outlive its test.** bug-229's ran for 20 hours. Nothing in the suite knows
  which processes it started.
- **A clone cannot see what the dev tree sees.** bug-168, bug-170 and bug-230 were each
  invisible in every littlebig review round
  ([[feedback_review_clones_cannot_see_dev_tree_failures]]).
{#why-list}

This task gives the suite four tiers that can be run apart, a runner that shards two of them,
a rule that keeps speed out of assertions, a reaper, and, after the split, a family that is
computed. It does so with the T0 sweep as its body ([[#fold]]), so that it ends on one clean,
fast, trusted run. 29.5 then runs the whole suite before and after every move commit, which
is only affordable, and only means anything, once this task is done
([[plan-29-code-quality#order]]). {#why-next}

## Measured at `f3709d2` (2026-11-14) {#baseline}

All of this is static (source reads and `pytest --collect-only`). No test was run for it. The
logs are in `workflow/review-output/`: `plan29a-tests-per-file.log`,
`plan29a-wallclock-census.log`, `plan29a-tier-census-v3.log`, `plan29a-family-census.log`. The
scripts that made them are in `workflow/measurements/plan-29-spec-census/`
([[plan-29-spec-census]]). {#baseline-method}

| Measure | Value |
|---|---|
| test files (`tests/test_*.py`) / tests collected | 357 / 4,883 |
| test lines | 95,148 |
| largest files by test count | `test_verb_parity.py` 167, `test_task25_1_recall_budget.py` 143, `test_memory_index_layout.py` 96 |
| last full serial run (0.83.0 release, `release-0.83.0-full.log`) | 14 failed, 4,869 passed, 3,517 s (58:37), load 5.6-7.6 |
| machine | 16 cores (12 performance), 128 GB |
| per-file durations | **not known**: no committed full-suite log carries them (the T0 sweep's `#t0-3-r0` found the same) |
| `scripts/ptest.sh` | exists, 24 lines: shards by `NR % N`, writes each shard to a `mktemp` dir and deletes it, prints only grep'd summary lines |
| `pytest-xdist` / `pytest-timeout` in `.venv-eval` | absent / present (not declared in `pyproject.toml`'s `dev` extra) |
| pytest configuration | none (`pyproject.toml` has no `[tool.pytest.ini_options]`; no `pytest.ini`) |
{#baseline-table}

The plan's baseline said "~4,480 tests". The release log says 4,883 (14 + 4,869), and so does
the collection at `f3709d2`. {#baseline-correction}

### Wall-clock assertions {#baseline-wallclock}

Counted from the syntax tree: an `assert` with an upper bound on a clock difference, on a name
assigned from one, or on a name such as `elapsed` / `took` / `wall`. A grep for `< N.0` finds
53 of these (`plan29-spec-wallclock-census.log`, the first draft's count); the tree finds 78.

| Kind | Asserts | Files |
|---|---|---|
| upper bound, numeric literal (`elapsed < 8.0`) | 70 | 22 |
| upper bound, named constant or expression (`elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0`) | 8 | 4 (none of them among the 22) |
| **total upper bounds** | **78** | **26** |
| ... of which a hang guard by its own name (`< HANG_BOUND_S`, 45 s, `test_bug212_r4_red.py:771`) | 1 | 1 |
| lower bounds (`elapsed >= 1.4`: "it waited at least N"). Not load-sensitive. Not counted. The script lists 8 lines in 6 files; one is the lower half of `0.9 < elapsed < 3.0` (`test_plan4_remedy.py:120`), whose upper half is among the 70, and two are name matches that are not elapsed times (`view.overrun_s > 0.2`, `cost_s_per_doc >= 0.0`) | 5 | 3 |
{#baseline-wallclock-table}

By size of the literal bound: 22 at ≤ 1 s, 27 at 1-5 s, 15 at 5-20 s, 6 above 20 s. The files
with the most: `test_plan2_remedy.py` 11, `test_rerank_budget_real_clients.py` 11,
`test_plan3_remedy_r4.py` 7, `test_plan3_remedy_r5.py` 6. {#baseline-wallclock-shape}

### Tiers, by the draft rule {#baseline-tiers}

The rule is [[#r1]]'s, applied by a script to the source at `f3709d2`. R0 re-runs it.

| Tier | Files | Tests | Share |
|---|---|---|---|
| (a) unit: in-process, no child process, no socket | 196 | 2,022 | 41.4% |
| (b) daemon / integration | 121 | 2,153 | 44.1% |
| (c) dev-tree-only | 15 | 161 | 3.3% |
| (d) timing (26 files hold a bound; one holds only the hang guard and stays in (b)) | 25 | 547 | 11.2% |
| **total** | **357** | **4,883** | |
{#baseline-tiers-table}

- 85 files run `rmx` or a generated hook command in a child process. 61 of the tier-(b) files
  start or serve a real daemon (81 files across all tiers); 28 files under `tests/` call
  `daemon.spawn_daemon_subprocess` themselves, and
  2 of those (`test_bug129_hub_pidfile.py`, `test_hub_watchdog.py`) never name `stop_daemon`.
- 95 `mkdtemp(dir="/tmp")` sites in 62 test files (and 1 in `tests/task3_7_helpers.py`) make
  roots **outside** the session's sandbox root. bug-229's daemon served one of them
  (`/private/tmp/r1-…`). 129 lines under `tests/*.py` call `shutil.rmtree` with `ignore_errors=True` (lines holding both
  words; a pattern that needs both inside one pair of parentheses finds 127).
- 19 files load a real embedding or rerank model (14 of them in tier (b)); 4 files name a fixed
  TCP port.
- Each pytest process already makes its own sandbox root (`rmx_sandbox.make_root`,
  `/tmp/rmx-XXXXXXXX`), so two shards never share a store root that the sandbox made. What
  they do share is listed in [[#r2]].
{#baseline-tiers-notes}

### Families {#baseline-families}

| Measure | Value |
|---|---|
| `src/refmatrix` modules | 73 |
| test files that import the touched module directly: median over modules | 4 |
| ... for `store` / `daemon` / `cli` / `verbs` | 220 / 156 / 136 / 59 |
| test files reached through the transitive import closure of a module | 324 of 357, for 71 of the 73 modules |
| test files that import no `refmatrix` module at all | 24 |
| test files that reach code only through a child process | 85 |
{#baseline-families-table}

The package is one strongly connected import component (lazy imports included). A family
computed from the transitive closure is the whole suite, so the closure cannot be the rule
([[#r6]]). {#baseline-families-reading}

## T0 folded in: stages and deltas {#fold}

T0 could not close without this task (its clean-suite gate stops on any failure no T0 row
owns, and bug-228 and bug-231 are owned only here), and 29.5 could not start without T0 (its
equality gate would run against a suite that fails 14 tests). T0.3's durations run and load
harness are the same measurement as this task's "measure, then shard". T0.4 and T0.5 edit the
files 29.5 needs quiet. So they are one task, in stages. {#fold-why}

| Stage | T0 sub-tasks (their text, by id) | What this spec adds | Why here |
|---|---|---|---|
| 0 | T0.3's R0 durations run (`T0#t0-3-r0`) | [[#r0]]: the same run, with this task's bands | one serial run serves both |
| 1 | **T0.1'** (T0.1 as amended, [[#fold-deltas]] row 1) | nothing | until it lands, every clone run exits 1 and no stage can quote a clean exit code |
| 2, in parallel | **T0.2** ∥ **T0.3** ∥ **T0.8** | T0.2 gains the reaper and the root rule ([[#r4]], [[#r5]]). T0.3 gains bug-228 and bug-231 as two more rows on its harness and bands, and the wall-clock census ([[#r3]]) | the reaper and the dev-tree isolation are both conftest and sandbox work; the wall-clock rows are load flakes like T0.3's three |
| lane | T0.6 (the plan-7 dense re-run) | nothing | long-running, builds no `src/`; any time after stage 1 |
| 3 | **T0.4 → T0.5** | nothing | they delete `duckdb_view.py`, the `_read_via_duckdb` state in `store.py` and `brief.parse_gmd`, and edit `cli.py`, `verbs.py`, `mcp.py`: dead code is deleted before 29.5 moves it |
| 4 | none | run tiers and the runner ([[#r1]], [[#r2]]) | its first AC is the live-touch proof ([[#ac-12]]; `plan-review-fable D3` = (a)); needs stage 2's reaper, because shards multiply daemons |
| 5 | **T0.7** | its clean runs (`T0#r7-4`, `T0#r7-5`) go through the runner; [[#ac-7]] | T0.7's clean run on the sharded runner **is 29.5's baseline** |
| after 29.5 | none | derived families ([[#r6]]) | measured useless before the split, precise after (queue review `#p29-4`) |
{#fold-stages}

### What changes in T0's text {#fold-deltas}

T0 was approved on 2026-11-13, before plan-29 existed. Each row is one amends line in T0 when
its branch merges (the queue review's step 1), or this task's first commit if that has not
happened. T0's requirements, ACs and mutations are otherwise built as written.

| # | T0 text | Becomes | Source |
|---|---|---|---|
| 1 | T0.1 "Closes bug-155" by R1.3 and R1.4 | **T0.1'**: R1.3 shipped verbatim (`988e96d`) and is dropped. R1.4 shipped as bash in `scripts/lint-gmd.sh` (`44d1a34`) and tests only that the directory exists, so an empty own-slug `memory/` defeats the fallback. R1.4 becomes "converge the shipped fallback onto one resolver, with the populated check and canonicalisation"; AC-1.5's RED is the empty-directory case; M1.3 and M1.4 are re-stated against it; the bug-155 row gains that residual | queue review `#st-8` |
| 2 | "Depends on queue item 1"; "26.5 in parallel" (`T0#merge-265`) | plan-29 runs first (L104). 26.5 is not in flight during this task | L104 |
| 3 | `T0#merge-order`: T0.2 ∥ T0.3 ∥ T0.4 ∥ T0.6 ∥ T0.8 | the stages above: T0.4 → T0.5 after stage 2 | queue review `#b3` |
| 4 | T0.3 covers bug-130, 190, 091 | plus bug-228 and bug-231, on the same harness, with the same bands (`T0#t0-3-bands`) | queue review `#b3` |
| 5 | T0.2 covers bug-170, 168, 127 | plus bug-229: [[#r4]] and [[#r5]] | queue review `#b3` |
| 6 | status `open / diagnosed-loud` (`T0#t0-3-attempts`, `#t0-3-band-none`, `#r3-1`) | `deferred: diagnosed-loud, <trial counts>; review <date>` | [[task-29.1-registry-triage#r1-other-writers]] |
| 7 | `T0#r7-4`, `#r7-5`: one `pytest -rA --junitxml` process, about 45 min, in the main tree | `scripts/ptest.sh --tier all` in the main tree (tier (c) included) and in the clone twin; `-rA` and one junit file per shard; "clean" keeps T0's definition word for word | queue review `#b3` |
| 8 | `T0#r7-8`: four plan-7 deferral rows re-owned to "plan-20 evals" | "no host plan; backlog (L33)". Plan-20's three tasks hold none of them | queue review `#dup-2` |
| 9 | Ruling O7's "immediate isolated re-run" | unchanged, and it is the **only** re-run this task allows ([[#decisions]] plan-29 D14) | this spec |
| 10 | R0.1 to R0.8 apply to T0's sub-tasks | they apply to everything in this spec too ([[#r10]]) | queue review `#ord-6` |
{#fold-deltas-table}

### Words that collide {#fold-words}

[[task-23.0-test-sandbox]] calls its three isolation levels "tiers" (tier 0 in-process, tier 1
the separate macOS user, tier 2 the VM). This spec's tiers are a different thing: four groups
of test files. To keep them apart, this spec says **run tier (a)-(d)** for its own and
**isolation lane** for 23.0's, which is also what 23.0's scripts are called
(`scripts/test-lane-user.sh`). {#fold-words-body}

## Requirements {#requirements}

### R0: measure first, and write the bands down before the numbers {#r0}

1. **One serial full run with durations.** This is T0.3's R0 (`T0#t0-3-r0`): the documented
   command plus `--durations=0`, in a fresh littlebig clone at stage 0's base sha, teed to
   `workflow/review-output/task-29.4/r0-serial.log`, with `uptime` before and after. It is the
   only full serial run the task needs. Its failures, by E line, are the **R0 digest**.
   - **Not before the dev venv is on duckdb 1.5.3** (`plan-review-fable-store D5`, decided,
     L106; the lead upgrades after the 0.83.1 runs). `.venv-eval` has 1.5.2 at `f3709d2`, below
     `pyproject.toml`'s floor and below the deploy venv.
2. **Per-file sums** of setup + call + teardown are written to `tests/shard_weights.json`
   (committed) and into the summary: the 25 heaviest files (the list T0.3's harness loads
   with), and the total per run tier.
3. **The static censuses are re-run** at the base sha (the logic of the scripts in
   [[plan-29-spec-census]] becomes `tests/tiering.py` and the census tests, so this is their
   first run). The summary gives the table of [[#baseline]] again with the new numbers.
4. **Bands, fixed here, before the run:**

   | Measured | Band | Action |
   |---|---|---|
   | run tier (a) wall, 4 shards | ≤ 5 min | every review round runs the whole of tier (a) |
   | | 5-10 min | a round runs the tier-(a) files its change touches or imports directly; the whole tier runs before a merge |
   | | > 10 min | the unit rule is wrong (a slow file has no signal). Name the 10 heaviest tier-(a) files, find the missing signal, re-tier, re-measure. Raised to the lead if a second pass is still > 10 |
   | tiers (a) + (b) + (d) wall at the chosen shard count | ≤ 20 min | done ([[#ac-7]]) |
   | | 20-30 min | sweep the tier-(b) shard count over 4, 6, 8 once and take the smallest that meets 20 with ≥ 10% headroom |
   | | > 30 min after the sweep | the task does not close on a guess: the summary names the 10 heaviest files and what each spends its time on, and the lead decides |
   | tier (d) wall, serial | ≤ 6 min | as is |
   | | > 6 min | [[#r3]] replaces the heaviest files' bounds first, in duration order |
   {#r0-bands}

### R1: four tiers, assigned by one function {#r1}

`tests/tiering.py` holds `tier_of(path) -> str`. It is the only place a tier is decided. The
rule is ordered; the first match wins, so a file has exactly one tier by construction.

1. **`devtree`** — the file's verdict depends on the checkout being the owning one: its own
   `.venv-eval/`, its own `.refmatrix/`, the hooks installed for it, a path under `$HOME`.
   - **Derived:** any file with an entry in conftest's `_CLONE_ONLY_SKIPS` (7 files, 19 pinned
     tests at `f3709d2`), and any file whose source reads the real home
     (`rmx_sandbox.real_home(` or `RMX_SANDBOX_REAL_HOME`: 6 files).
   - **Listed:** `DEVTREE_FILES` in `tests/tiering.py`, each with a one-line reason and the bug
     that showed it. At `f3709d2`: `test_search_hooks.py` (bug-168) and
     `test_bug230_repo_scope_gate.py` (bug-230). A file leaves the list when its dependency is
     removed (T0.2 removes `test_search_hooks.py`'s).
   - **Arriving later:** a test that needs the real home or the real machine belongs here from
     its first commit. 16.3 AC-5's re-scan of the installed Claude Code binary (33 s, 235 MB,
     and it cannot resolve `~/.local/bin/claude` under the sandbox's `HOME`) is the known case
     (store review `#p16-binary-extraction-test`).
2. **`timing`** — the file holds at least one assertion in the wall-clock allow list ([[#r3]]).
   The tier is derived from that list. It has no list of its own. When a file's last bound is
   replaced, it moves to tier (a) or (b) with no edit to `tiering.py`.
3. **`daemon`** — the file, or a `tests/` helper module it imports (followed transitively),
   contains a process or socket signal: `subprocess.` / `Popen`, `os.fork` / `posix_spawn` /
   `exec*` / `system`, `multiprocessing`, `pytester`, `spawn_daemon_subprocess`, `SandboxDaemon`,
   `serve_forever` / `serve_foreground`, `socket.socket(` / `AF_UNIX` / `socketserver` /
   `uvicorn`, a hub start, or a real model worker. The signal set is a table in `tiering.py`,
   matched on the syntax tree where a call can be recognised and on source text otherwise.
4. **`unit`** — everything else.

Also:
- conftest's `pytest_collection_modifyitems` adds the marker `tier_<name>` to every item from
  `tier_of`, so `-m tier_unit` selects a tier. The four markers are registered in
  `pytest_configure`, beside `sandbox_probe`.
- **The plain command stays valid.** `pytest -q` with no `-m` runs every tier, as today. Tiers
  are a way to select, not a second suite.
- A test file in a subdirectory of `tests/`, or a `test_*.py` that `tier_of` cannot read, is an
  error, not a default.
{#r1-also}

**Fixture suites are not part of the suite.** AC-2, AC-5 and AC-9 need small test files that
fail, error at teardown, skip unpinned or leak a daemon on purpose. There is no `testpaths`,
`norecursedirs` or `collect_ignore` at `f3709d2`, so a file named `test_*.py` under
`tests/fixtures/` would be collected by the plain command and would break [[#ac-10]].
- They are named `case_*.py` under `tests/fixtures/suite_health/`, which pytest's default
  patterns do not collect. The tests that use them copy them into a tmp tree under the name
  `test_*.py` and run pytest there, in a child process.
- `[tool.pytest.ini_options]` also gets `norecursedirs = ["fixtures", "sandbox_site"]`, so a
  later `test_*.py` dropped under `tests/fixtures/` is not collected by accident. AC-1 checks
  that no `test_*.py` exists there.
- **The censuses scan them, with one named exemption.** The wall-clock, tmp-root and
  budget-outcome censuses read `tests/**/*.py`, fixtures included. `tests/fixtures/suite_health/`
  is exempt **by path**, in the census's own source, with the reason beside it (its
  `mkdtemp(dir="/tmp")` and its leak are the fixture). A violation anywhere else under
  `tests/fixtures/` fails the census, and a must-fail case shows it.
{#r1-fixtures}

### R2: the runner {#r2}

`scripts/ptest.sh` stays the entry point and becomes a thin wrapper over
`scripts/ptest.py` (the logic is Python so it can be tested; the dev shell is bash 3.2).

- `scripts/ptest.sh --tier unit|daemon|devtree|timing|all [--shards N] [--name RUN]`.
  `all` runs (a) and (b) sharded and **at the same time**, then (d) alone in one process, then
  (c) if the checkout is the owning one. In a clone it prints
  `tier devtree: NOT RUN here (clone); run it in the owning checkout before the merge commit`
  and the summary's last line says the run is incomplete for a merge. It never says "all green"
  for a run that skipped a tier.
- **A shard is a plain pytest process** over a list of whole files. The runner prints each
  shard's exact command line, so any shard can be re-run by copy and paste.
- **Shard assignment is deterministic:** files sorted by weight from `tests/shard_weights.json`,
  placed greedily into the lightest shard. A file with no weight gets its tier's median weight
  per test × its collected test count, and the runner says so.
- **Every shard has its own sandbox root.** It has one already (a root per process); the runner
  asserts it by reading each shard's root from its log header and failing if two are equal.
- **Shared between shards, and what is done about each** (R0 confirms the list by reading
  `rmx_sandbox.py`, and adds to it):

  | Shared | Rule |
  |---|---|
  | `workflow/review-output/live-socket-touches.log`, `live-log-growth.jsonl` | appended by every process; lines carry the pid and the test id; a test's check filters on its own id. Stays shared. A test that asserts on the **file's size** is pinned to the serial group |
  | fixed TCP ports (4 files) | pinned to the serial group until they bind port 0 |
  | real model workers (14 tier-(b) files) | at most 2 shards hold model-loading files; the placer puts those files in shards 0 and 1 |
  | `/tmp` roots outside the sandbox (62 files) | moved under the sandbox root by [[#r5]] |
  | `__pycache__` under `src/` | the runner compiles `src/` once (`compileall`) and runs the pyc guard before the shards start, so shards and their children read bytecode and do not all compile `cli.py` at once. Bytecode writing is not turned off: a child that had to compile 75,000 lines on every spawn would be the slowest part of the run |
  {#r2-shared}

  The **serial group** is a named set in `tiering.py` (file + reason). It runs as one extra
  shard after the others finish. It is not a tier.
- **Every run is a directory of logs:** `workflow/review-output/<RUN>/<tier>-<k>.log` (the
  shard's full output), `failures.jsonl`, `outcomes.jsonl`, and `summary.txt`. `summary.txt` has one line per
  shard (command, exit code, collected, passed / failed / errors / skipped, wall seconds, sandbox
  root), the totals, the sha, the load average at start and end, and the checkout kind
  (`owning` or `clone`).
- **`failures.jsonl` is written by conftest, not parsed from text.** When `RMX_FAILURES_OUT` is
  set, the existing `pytest_runtest_makereport` hook appends one record per failed **or
  errored** phase: node id, phase (`setup` / `call` / `teardown`), and the first `E` line. A
  teardown error is a failure here ([[feedback_review_clones_cannot_see_dev_tree_failures]]:
  "read every ERROR as well as every FAILED"). SkipGate and reaper findings are records too.
- **`outcomes.jsonl` is written for every run, by the same hook.** One record per test node and
  phase that produced a report: node id, phase (`setup`, `call`, `teardown`), and outcome. The
  runner always sets `RMX_OUTCOMES_OUT`; each shard writes its own file and the runner
  concatenates them. `failures.jsonl` records what went wrong; `outcomes.jsonl` records what
  every test did, which is the only way to tell that a test that was expected to fail now
  passes, or that a test stopped running.
  - **The outcome is normalised from pytest's report, by this table.** Pytest's reports have
    no `xfailed` or `xpassed` outcome (`_pytest/skipping.py::pytest_runtest_makereport`); the
    hook derives them, and nothing else:

    | Pytest's report | Recorded outcome |
    |---|---|
    | `passed`, no `wasxfail` | `passed` |
    | `skipped`, no `wasxfail` | `skipped` |
    | `skipped` with `wasxfail` (an expected failure that failed) | `xfailed` |
    | `passed` with `wasxfail` (a **non-strict** xfail that passed) | `xpassed` |
    | `failed` in the `call` phase, including a **strict** xfail that passed (pytest reports it `failed`, longrepr `[XPASS(strict)] …`, no `wasxfail`) | `failed` |
    | `failed` in `setup` or `teardown` | `error` |
    {#r2-outcomes}

    A strict XPASS is a failure and is recorded as one, in `outcomes.jsonl` and in
    `failures.jsonl`. It is never recorded `xpassed`: that failure is what keeps a strict xfail
    honest, and after the marker is removed it is what the test's own pass replaces.
- **`scripts/ptest.sh --compare --outcomes RUN_A RUN_B [--expect '<node id>:<phase>:<from>-><to>' …]`**
  exits 0 only if every node id has the same outcome, phase by phase, in both runs, apart from
  the `--expect` entries. An entry names one phase of one node; it is parsed from the right,
  because a node id may itself hold a colon. Each expected change must hold exactly: that
  node's `<phase>` had `<from>` in A and has `<to>` in B, and the node's other phases are
  unchanged. It fails, naming the node id and phase, on: any other change of outcome, in
  either direction; a node id or a phase present in one run only; an `--expect` whose node and
  phase did not change as stated. 29.5's gate G5 runs this mode after the failure comparison,
  at every commit, with one `--expect` at its rename commit
  ([[task-29.5-split-giant-modules#r4-probe]]).
- **`scripts/ptest.sh --compare RUN_A RUN_B`** exits 0 only if the two runs have the same set of
  (node id, phase, normalised E line). Normalisation replaces sandbox roots, `/tmp` random
  segments, pids, hex addresses and decimal seconds with placeholders, and nothing else. The
  rule is one function with its own tests. This is the "equal by E line" check that 29.5 runs
  around every commit.
- **No reruns.** The runner has no retry flag. A test that fails only when sharded is a finding:
  it gets a wall-clock replacement ([[#r3]]), a place in the serial group with a reason, or a
  registry row. It is never run again until it passes. The one re-run this task knows is T0's
  ruling O7 (`T0#r7-6`): a `diagnosed-loud` row's node id, re-run once, alone, with both
  outcomes recorded. That is a recorded diagnostic on a named row, not a retry.
- **Stage 4's gate: no sharding until a live touch fails the session** (`plan-review-fable D3`,
  decided (a), L106). Four shards are four processes that can each reach a live socket
  (bug-088, bug-101). Before the runner starts a second process, this is shown, and it is
  stage 4's first AC ([[#ac-12]]):
  - a probe test that touches a deny-set target (a live socket path, the hub port, a path under
    a live `.refmatrix/`) fails **its own test, its shard, and the whole run**;
  - the same when the touch is made by a child the test spawned;
  - in every shard position, and in the serial group;
  - and the run's `summary.txt` names the test and the target.
  The 23.0 sandbox already refuses such a touch and fails the test that made it. What stage 4
  adds is the proof that the refusal still fails the **run** when the run is several
  processes, and the runner's rule that one shard's violation is the run's exit code.
- **A hang guard, not a speed check.** `pytest-timeout` is added to the `dev` extra and
  configured once (`[tool.pytest.ini_options]`: `timeout = 600`, `timeout_method = "signal"`).
  The `signal` method raises inside the test, so teardown and the session-finish hooks still
  run, which the reaper needs. On a timeout pytest-timeout prints every thread's stack; the
  runner also records `ps -o pid,etime,time,command` for the shard's process group
  ([[feedback_mutation_must_fail_not_hang]]).
{#r2-list}

### R3: outcome checks in place of wall-clock bounds {#r3}

**The rule.** A test does not assert an upper bound on elapsed time, and does not assert an
outcome that a real-time budget decides unless the test controls which side of the budget the
run falls on. What a bound was protecting is asserted directly. {#r3-rule}

Each of the 78 sites is one of four classes. R0 classifies all of them in a table in the
summary (file, test, bound, class, replacement); the classes and their replacements are fixed
here:

| Class | What the bound meant | Replacement |
|---|---|---|
| **A. hang guard** | "this must not block forever" (`stop took < 8.0`) | wait for the outcome under `HANG_GUARD_S`, a single constant in `tests/timing.py` (≥ 60 s); assert the outcome (the op answered, the pid exited, the row exists). The elapsed time goes in the failure message only |
| **B. budget honoured** | "it gave up within its budget" (`elapsed < BUDGET + 3.0`) | assert the mechanism: the timeout value that reached the transport, the number of attempts, the busy / skipped result returned. Where the code reads a clock, inject it, so the budget arithmetic is tested without waiting |
| **C. did not block** | "start returned at once" (`elapsed < 1.0`) | an ordering check: the call returned **while** the worker was still held on an event the test owns. No clock |
| **D. a latency measurement** | "this is fast" | not a suite test. It moves to `eval/` with its number, or is deleted with a note of what it measured |
{#r3-classes}

- **bug-231** (`test_graceful_stop_on_a_live_daemon_returns_quickly`, `< 8.0` on a
  `grace=10.0` stop; failed at 10.05 s and 9.02 s). Class A. The test passes
  `grace=HANG_GUARD_S` and asserts `True` and `not is_alive(pid)`: the daemon stopped.
  - `True` alone does not say the call returned early. `daemon.graceful_stop` polls
    `is_alive(pid)` every 50 ms until the deadline and then checks once more
    (`daemon.py::graceful_stop`, its last eight lines), so a daemon that dies at 10.0 s of a 10 s grace still gives `True`.
    The 10.05 s run is that case.
  - That the wait ends when the pid is gone, and not at the deadline, is asserted in a second
    test with no daemon: `daemon.is_alive` is replaced by a function that turns false on its
    k-th call, the polls are counted, and the call returns `True` after k of them under a grace
    it never comes near.
  - What the 10.05 s says about the product is not this task's to fix, and it is not lost in a
    closing note either: it is logged as **its own registry row** ("a daemon took the whole 10 s
    grace to exit at load 12-20; `graceful_stop(grace=10)` returned at the deadline"), in
    29.1's grammar, `deferred: …; review <date>` unless a task takes it.
  {#r3-bug231}
- **bug-228** (`test_ac2b_live_daemon_recall_writes_one_ok_recall_row`: `outcome == "ok"`
  against the generated hook's 5 s budget on a live sandbox daemon). There is no `<` in this
  test: the product's budget is the bound. R0 measures one failing run and says which leg spent
  the time (the row asks for exactly this), then:
  - **if ≥ 90% of the overrun is before the recall op starts** (boot, model warm-up): the test
    waits on the harness's readiness signal before it runs the hook, as bug-184's fix does;
  - **otherwise** the test is split. One test asserts, with no daemon, that the generated
    command carries the 5 s budget. The live test runs the same generated command with that
    one budget value replaced by `HANG_GUARD_S`, through `tests.timing.with_budget` (which
    asserts it changed exactly one token), and asserts `outcome == "ok"`. The `skipped_budget` leg keeps its
    existing test, which already uses a silent peer and does not depend on speed.
  - Either way the test no longer shows whether a **live** recall meets its 5 s budget under
    load, which is a product question. R0's measurement of the failing run answers it once, and
    the answer is logged as **its own registry row** ("live recall over its 5 s budget at load
    N: <leg> spent <t>"), `deferred: …; review <date>` unless a task takes it. The registry's
    threshold to log is low.
  {#r3-bug228}
- **The census** (`tests/test_wallclock_census.py`) reads every file under `tests/` as a syntax
  tree and finds each upper bound on a clock difference, on a name assigned from one, or on an
  elapsed-like name, **whatever the limit is** (a literal, a named constant, an expression). It
  compares the set with `tests/wallclock_allow.json`.
  - An entry's key is `file::test function::normalised assert source`. It has no line number.
  - A bound that is not in the list fails the census, with the file, the test and the fix
    classes named.
  - An entry whose assert no longer exists fails the census too, so the list is exact and only
    shrinks.
  - **Exempt by form:** a lower bound; and `< HANG_GUARD_S` where the name is imported from
    `tests/timing.py`. The census checks the constant is ≥ 60.
  - The list starts at the R0 count (77 at `f3709d2`, once `HANG_BOUND_S` is renamed).
  {#r3-census}
- **Two kinds of entry, and only one of them can be added.** The store review counted about 43
  wall-clock clauses in approved specs that have not been built (23.5: 14; 18.3: 7 ACs;
  16.1-16.5: 7; 23.1: 4; 18.2: 4 ACs; 17.1 and 17.4: 4; 23.2: 3). Their tests would fail this
  census on the day they are written. So each allow-list entry has a kind:
  - **`legacy`**: a bound that exists at this task's base. The set only shrinks.
  - **`feature-bound`**: the bound **is** the feature under test (a deadline that must fire: 23.2's
    fail-not-hang deadlines; 23.5 R2's `RMX_CLI_WRITER_WAIT_S`). The test shrinks the bound
    through the product's own knob so that it waits fractions of a second, not the production
    value, and it runs in tier (d). An entry records three things, and the census checks each:
    - **`ac`**, as `<spec id>#<anchor>`. The census resolves it: a spec with that frontmatter id
      exists under `workflow/plans/`, and it has that anchor. An AC that does not exist fails.
    - **`knob`**, what sets the bound, in one of three forms:
      - `env:<NAME>`: an environment variable. The test sets it (`monkeypatch.setenv`, or an
        `env=` mapping passed to the child);
      - `const:<module.NAME>`: a named constant. The test patches it (`monkeypatch.setattr`);
      - `arg:<parameter>`: an argument of the function under test (ruling L107). The bound is a
        **literal** the test passes at the call, and the census reads it there. 29.3's
        `run_git(…, timeout=…)` has no environment knob; its AC-a1 timeout leg is
        `knob: arg:timeout`.

      The census reads the test function and finds the knob set in the form the entry names. A
      test that names a knob and never sets it fails: it would be waiting the production value.
      For `arg:`, a call that does not pass the parameter, or passes a name or an expression in
      place of a literal, fails too: the census cannot see what it would wait.
    - **`max_s`**, the shrunk value's ceiling (≤ 2.0). The value the test sets is a literal the
      census can read, and it is under the ceiling.
  - **One AC, one entry.** An AC id may own at most as many entries as it has wall-clock clauses
    in its own text; the entry quotes the clause. Naming one's own AC is not enough to get in:
    the bound has to be a deadline the product enforces, which is why there is a knob to check.
  - Everything else in those specs is written as an ordering outcome from the start ("answers
    while the test thread still holds the lock"; "the hook exits before the competitor
    releases"), by [[#r3-classes]] class C. 23.1 AC-21 step 2 (spawn-to-exit under 5.0 s with a
    dial of up to 4.0 s) and 18.3 AC-7 (±25 %, where 18.3's own measurement had loaded at twice
    idle) are bug-231's shape by construction and get no entry.
  - A census run prints the two counts apart. A new `legacy` entry fails it.
  {#r3-kinds}
- **The second half of the rule gets a census too.** "Does not assert an outcome that a real-time
  budget decides" is bug-228's shape, and no `<` appears in it. The census
  (`tests/test_budget_outcome_census.py`) finds every test function that (a) uses a real daemon
  or runs a real hook or CLI child (`SandboxDaemon`, `spawn_daemon_subprocess`, directly or
  through a fixture) and (b) asserts a comparison of an `outcome` field with a string. Such a
  test must control the budget, in the same function, in one of two forms the census can
  see:
  - it sets the budget's knob, in one of the three forms of [[#r3-kinds]] (`env:`, `const:`,
    `arg:`); or
  - it builds the command it runs with **`tests.timing.with_budget(command, seconds)`**, the one
    helper that returns a generated command with its budget replaced (and raises unless it
    replaced exactly one token). The census matches the call by that name, and reads `seconds`
    as a literal or as `HANG_GUARD_S`. A budget edited into the command any other way (a
    `str.replace`, an f-string) is not seen by the census, and the test fails it.
 Otherwise it fails the census, or holds a
  `budget-outcome` entry in the allow list with its reason.
  - At `f3709d2`, 13 test functions assert an `outcome` against a string and **one** of them
    uses a real daemon: `test_ac2b_live_daemon_recall_writes_one_ok_recall_row`, which is
    bug-228 (`plan29a-r2-budget-outcome.log`). The others use a test-owned peer and are not
    hits.
  - The list of real-daemon helpers and the field names the census treats as outcomes
    (`outcome` at base) are a table in `tests/tiering.py`, beside the signal table, so a new
    helper or a new field is one line.
  - What this census cannot see is an outcome asserted through some other shape (an exit code,
    a row count). That remainder is enforced by review, and the spec says so here so that
    nobody takes the census for the whole rule.
  {#r3-budget-census}
- **Sleep is budgeted like time.** A test that sleeps or holds a lock for a fixed production
  interval (23.1 AC-21 step 1 holds a lock 70 s, and steps 4 and 5a repeat it) spends the
  20-minute target on waiting. Such a test shrinks the interval through the product's knob, as
  a `feature-bound` test does. `summary.txt` lists every test over 30 s, so one that does not
  is seen.
  {#r3-sleep}
- **The freshness pass for those specs is not this task's.** The specs the store review names
  are revised by their owners after 29.5, in the one pass per track the reviews schedule. This
  section is the rule they are revised against.
  {#r3-freshness}
- **bug-228 and bug-231 are rows of T0.3.** They run on T0.3's harness with its bands
  (`T0#t0-3-bands`): a reproducer is ≥ 3 failures in 10 trials at base, at 3, then 5, then 8
  concurrent processes; a fix is proven by 45 consecutive passes at the reproducer's level; at
  most two fix attempts; a row that does not reproduce gains its diagnostic and its mechanism
  test and reads `deferred: diagnosed-loud, …`. The replacements above are the fix attempts.
  bug-231 has already failed twice under suite load, at 12-20 and at 5.6-7.6.
  {#r3-t03}
- **How far this task goes.** bug-228 and bug-231 are replaced. So is every site in a file whose
  serial duration puts tier (d) over its band ([[#r0-bands]]), and every class C and D site
  (they are the cheapest and the most load-sensitive: 22 bounds are ≤ 1 s). The rest stay in the
  allow list, in tier (d), each with its class recorded. The summary gives the count left, and
  29.1's grammar gives the remainder one row: `scheduled` or `deferred`, never silence.
  {#r3-scope}

### R4: a reaper that fails the session {#r4}

Every process the suite starts is known, and one that is still alive at the end fails the run.

1. **The ledger.** Each Python process that starts under the sandbox appends one line to
   `<sandbox root>/children.jsonl`: pid, parent pid, start time, argv, the working directory,
   the value of `REFMATRIX_ROOT` in the child's environment (`spawn_daemon_subprocess` passes
   the store root there), and the test id from `PYTEST_CURRENT_TEST`. Two hooks write it, both in `tests/sandbox_site/rmx_sandbox.py`:
   `install_from_env()` (every exec'd child runs it through `sitecustomize`) and an
   `os.register_at_fork(after_in_child=…)` callback, registered by `enter()` in the pytest
   process and by `install_from_env()` in every child (a daemon double-forks with no exec, so
   its final pid is only visible there). One `write` of one line under `O_APPEND`.
2. **At session finish** (the outermost session only), for every ledger pid that is still
   alive **and** whose process start time matches the ledger's:
   - print one line: `LEAKED PROCESS pid=<n> age=<s> spawned in <test id> argv=<…> root=<store
     root>`. The root is the ledger's `REFMATRIX_ROOT` for that pid, which is known whether the
     root is under the sandbox or not (bug-229's was not); if the ledger has none, the line says
     `root=unknown (cwd=<…>)` and does not guess;
   - stop it: `daemon.stop_daemon(root)` when the ledger gives a root, else SIGTERM, a bounded wait,
     then SIGKILL, each step printed;
   - set the session's exit status to failed and add a `failures.jsonl` record.
   A pid whose start time does not match is a reused pid. It is not signalled, and the line
   says so.
3. **A run that was killed cannot reap.** bug-229's most likely cause is a run that died before
   teardown. So at session **start**, every `/tmp/rmx-*/owner.json` whose owner (pid and start time) is no longer running is a
   sandbox that a killed run left behind: its ledger's survivors are stopped the same way,
   each is printed (`ORPHAN from a killed run: …`), its root is removed, and the count is in the
   session header and in `workflow/review-output/leaked-processes.log`. This does not fail the
   new session ([[#decisions]] plan-29 D13). `enter()` writes `owner.json`. Only roots matching
   `/tmp/rmx-*` are listed; nothing is searched.
4. **Teardown says what it left.** `rmx_sandbox.remove_tree` already counts what it could not
   remove. The session-finish hook prints the count of sandbox store roots that still hold a
   live `rmxd.pid` before removal.
5. **It is keyed on the spawn, not on a root.** bug-229's row proposed finding daemons "by socket
   path under the sandbox root". Its own daemon lived under `mkdtemp(prefix="r1-", dir="/tmp")`,
   outside that root, as do 95 other sites (the store review counts 96 lines). The ledger
   records the process when it starts, whatever root it serves, so the root does not matter
   (store review `#one-reaper-keyed-on-spawn`).
6. **In-process daemons are spawns too.** A `Daemon` built and served inside the pytest process
   is not in the ledger. conftest keeps a weak registry of `Daemon` instances (it wraps
   `Daemon.__init__` to record the instance and changes nothing else). At session finish an
   instance that is still serving (its socket is bound, or its serve thread is alive) is
   printed as `LEAKED IN-PROCESS DAEMON root=<…> built in <test id>`, stopped, and fails the
   session like a leaked process.
7. **One registration call, for fixtures that own a daemon.**
   `rmx_sandbox.register_spawn(pid_or_daemon, root, why)` adds an entry by hand. 23.2 `#r4`'s
   `recorded_daemon` fixture registers with it and does not grow a teardown of its own; so do
   18.3's SIGKILLed subprocess daemons, 17.2's blocked ops, 16.1's detached learners and the
   throwaway daemons of D-Q1 and 22.5. A registered entry's teardown asserts the stop answered
   and the pid exited.
8. **A stopped process is still a leak.** A SIGSTOPped daemon (the `stopped` fixture in
   `test_plan4_remedy.py`; 25.1b AC-28 leaves one, per the memory review) is sent SIGCONT before
   it is stopped, and is reported like any other. A test that stops a daemon on purpose
   continues and stops it in its own teardown.
9. **The sweep is a function others call.** `rmx_sandbox.sweep_orphans(ledger_path)` is item 3's
   logic. 28.2's paired-run clone daemons use it for their pre-run sweep, from the runner's own
   ledger (store review `#p28-orphan-clone-daemon-sweep`).
{#r4-list}

### R5: test roots live under the sandbox root {#r5}

`rmx_sandbox.short_root(prefix)` returns a fresh directory under `<sandbox root>/t/`. The path
stays short (`/private/tmp/rmx-XXXXXXXX/t/XXXXXXXX/proj/.refmatrix/rmxd.sock`, the resolved form,
is 62 bytes, against macOS's 104).

- The 28 files that call `spawn_daemon_subprocess` use it for their roots in this task.
- `tests/test_tmp_root_census.py` fails on a `mkdtemp(` whose `dir=` is `/tmp` or `/private/tmp`
  outside `tests/tmp_root_allow.json`. The list starts with the sites left after the 28 files
  are moved, and only shrinks, by the same exact-list rule as [[#r3-census]].
{#r5-list}

With the roots under the sandbox, a leaked root is removed with the sandbox, a leaked daemon's
pid file is found by one `rglob` under one directory, and two shards cannot collide on a root
by construction. {#r5-why}

### R6: families are derived (built after 29.5) {#r6}

**When.** Not in stages 0-5. Before the split, 136 of 357 test files import `refmatrix.cli`
and 220 import `store`, so a family computed today is most of the suite for any change to the
two largest modules; after the split the same rule is precise. This requirement is built as
sub-task 29.4f on the tree 29.5 leaves, and its back-test is run there (queue review
`#p29-4`). Until then a review round runs tier (a) whole (if [[#r0-bands]] allows), the tier-(b)
and tier-(d) files its change touches or names, and `ALWAYS_FILES`. `ALWAYS_FILES` and the
runner's `--files` form exist from stage 4, because [[#r7]] needs them. {#r6-when}

`scripts/ptest.sh --family <base-rev>` prints, then runs, the test files for the change
`<base-rev>..HEAD` plus the working tree. Each file is printed with the reason it is in the
family. A family is the union of:

| Part | Rule |
|---|---|
| **touched** | every test file the change touches |
| **direct** | every test file that imports a touched `src/refmatrix` module, itself or through a `tests/` helper (syntax tree; lazy imports count). A child-process test counts as importing `refmatrix.cli`, and `refmatrix.daemon` if it starts one |
| **named** | every test file whose source names a touched non-module file (a script, a template, a generated doc) by repo-relative path or by base name |
| **always** | `ALWAYS_FILES` in `tests/tiering.py`, each with its reason: the generated-artifact and census tests. At `f3709d2`: `test_docs_generated.py` (the CLI tree and hooks table), `test_verb_parity.py`, `test_bug212_r4_red.py` (the catalog-opener census), `test_repo_hooks_in_sync.py`, `test_gmd_lint_requires_version.py`, `test_version_single_source.py`, and this task's own census tests |
| **tier (a), whole** | if R0's band says so ([[#r0-bands]]) |
| **after 29.5** | `ALWAYS_FILES` gains 29.5's census tests ([[task-29.5-split-giant-modules#r4]]) |
{#r6-parts}

- **The closure is not used.** It is 324 of 357 files for 71 of 73 modules ([[#baseline-families]]).
- **A family is for the inner loop.** It is what a RED / GREEN / mutation round runs. It is not
  the merge gate: tiers (a), (b) and (d) run whole before a merge, and tier (c) runs on the
  merged dev tree ([[#r7]]). The spec says this in the runner's output too, on every family run.
- **Back-test, with bands fixed here.** For at least 12 registry rows where a change broke a
  test its author did not run (bug-010 and bug-110 are two; R0 lists the rest by searching the
  registry for "full suite"), compute the family at the breaking commit and record whether the
  failing file is in it.

  | Selected | Action |
  |---|---|
  | ≥ 90% | the rule stands |
  | 70-90% | name the class of the misses; add one rule for it (for example: importers at depth 1 of modules under 500 lines); re-run the back-test |
  | < 70% | the direct rule is not good enough to call a family. The runner's `--family` prints the misses' class as a warning on every run, and the lead decides between depth 1 and "tier (a) + (b) every round" |
  {#r6-bands}

### R7: the merge gate runs on the dev tree {#r7}

`scripts/ptest.sh --merge-gate`, run in the owning checkout after `git merge --no-commit` and
before the merge commit:

1. refuses (exit 2, saying why) in a checkout that is not the owning one: no `.refmatrix/`, or a
   `.venv-eval` that resolves outside the checkout;
2. runs tier (c), every test file the merge touches, `ALWAYS_FILES`, and
   `./scripts/lint-gmd.sh`. From 29.4f on it runs the family of `HEAD..MERGE_HEAD` ([[#r6]]) in
   place of "every test file the merge touches";
3. fails on any failed test, any **errored** phase (teardown included), any SkipGate or reaper
   finding, and any non-zero exit of the lint gate;
4. writes `workflow/review-output/merge-gate-<merge head sha>/`, as [[#r2]] does.

`CLAUDE.md`'s git workflow and `#before-commit` list name this command. The gate compares by
E line against the previous gate's `failures.jsonl`: a row that is still open is recorded as
seen, and a new node id or a new E line fails the gate. After stage 5 the previous gate's file
is empty, and so any failure fails it. {#r7-list}

### R8: the docs say what is true {#r8}

- `CLAUDE.md#development-commands` and `.claude/PROJECT_PROFILE.md#commands`: the run-tier
  commands and the merge gate, beside the plain full command. Suite size and time are quoted
  from stage 5's `summary.txt`, with its date. (29.1 has already replaced the stale "~13 min"
  and "~1380 tests" with the measured 4,883 and 58:37; this is the second, final update.)
- `workflow/TDD_GOVERNANCE.md`: one paragraph: what a review round runs and what the merge gate
  runs.
- `workflow/test_mock_registry.md`: any new double.
{#r8-list}

`CLAUDE.md` and `.claude/PROJECT_PROFILE.md` are instruction files. Their edits are part of
what the user approves with this plan; the implementer makes exactly the edits named here and
quotes the diff in the summary. {#r8-instruction-note}

### R9: 23.0's open ends {#r9}

[[task-23.0-test-sandbox]] is `completed` with two ACs open and one requirement that no longer
matches the code (store review `#task230-completed-with-open-acs`). This task is the next one
to rework the sandbox, so it settles them:

1. **23.0 `#r3` is amended.** It forbids "any `open` (write OR read)" under a live `.refmatrix/`.
   bug-230 added one read-only allow, for the checkout's own `.refmatrix/.refmatrix_ignore`
   (`rmx_sandbox.read_allow`). One amends line in 23.0 says so and names bug-230.
2. **23.0 AC-7 and AC-8 (the user lane and the VM lane) are deferred, with rows.** Neither has
   run: 23.0's summary says so, and there is no deferral row. Both need one-time operator setup
   that only the user can do (the `rmxtest` account and its sudoers entry; the Tart VM, which
   the user placed on the M1 Mac mini). Each gets a row in `workflow/deferral_registry.md` with
   that reason, 23.0 as its origin and a review date, and 23.0's status line says "completed,
   AC-7 and AC-8 deferred (rows …)". ([[#decisions]] plan-29 D20.)
3. **The lanes run the plain command**, which stays valid ([[#r1-also]]). When a lane is set up
   it can run `scripts/ptest.sh` too; nothing here prevents it and nothing here builds it.
{#r9-list}

### R10: rules for every stage {#r10}

- **T0's R0.1 to R0.8 apply to this spec's additions as they do to T0's sub-tasks**
  (`T0#rules`): re-verify every cited site at the branch base; compare failures by E line; every
  run is a log that states its exit code; RED first, and a mutation fails and does not hang; no
  skip is added and no test is weakened; sandbox discipline; one ch-bsd round per sub-task
  range.
- **No install window (R0.7).** Nothing in this task may make `rmx install-hooks --check` report
  drift on an existing install. The queue review asks for this rule on all five plan-29 tasks.
- **One release point, after stage 5.** What ships is test, script and doc changes, T0.4's and
  T0.5's `src/` deletions and remedies, and any clock parameter [[#files-src-note]] allows.
  T0.5 changes an MCP tool, so the release carries a `/mcp` reconnect note. It changes neither
  hooks nor the store on disk, so it ships under the user's standing go (`plan-review-fable
  D4`, decided, L106): the suite equals the baseline by E line, and the user is told first.
- **Branches.** One branch per sub-task from the `master` that holds the stage before, merged
  `--no-ff`. T0's sub-tasks keep T0's branch names. Work happens in littlebig clones.
{#r10-list}

## Acceptance criteria {#acceptance}

- **AC-1: every test file has exactly one tier.** `tests/test_suite_tiers.py`:
  - `tier_of` returns one of the four names for every `tests/**/test_*.py`, and raises for a
    file it cannot read;
  - the four per-tier file lists are pairwise disjoint and their union is the collected set;
  - the sum of `pytest --collect-only -m tier_<name>` counts over the four tiers equals the
    plain collection count (4,883 at `f3709d2`), so a tier that the marker misses is seen;
  - every name in `DEVTREE_FILES`, `ALWAYS_FILES` and the serial group exists on disk;
  - **must-fail, on synthetic sources fed to the rule:** a source with `subprocess.run(` is not
    `unit`; one that imports a helper that calls `spawn_daemon_subprocess` is not `unit`; one
    with a `_CLONE_ONLY_SKIPS` entry is `devtree`; one with an allow-listed bound is `timing`;
    a `test_*.py` in a subdirectory is an error.
  {#ac-1}
- **AC-2: the runner's logs are the evidence.** For a run of `--tier all`: one log per shard;
  `summary.txt` with an exit code for every shard; two shards never share a sandbox root; a
  shard that exits non-zero makes the run exit non-zero; a tier that did not run is named on the
  last line. Tested on a fixture suite of four tiny test files in a tmp tree, including one
  that fails, one that errors at teardown and one that skips unpinned. {#ac-2}
- **AC-3: `--compare` is exact, in both modes.**
  - **Failures:** two fixture runs that differ only in a sandbox path, a pid and a duration
    compare equal. Two that differ in one E line, in one node id, or in one phase (`call`
    against `teardown`) compare unequal, and the output names the difference.
  - **Outcomes:** `outcomes.jsonl` of a fixture run holds one record per node and phase, and
    the fixture has a test for every row of [[#r2-outcomes]]: a pass; a skip; a strict xfail
    that fails (`xfailed`); a non-strict xfail that passes (`xpassed`); a plain failure; a
    teardown error (`error`); and **a strict xfail that passes, which must read `failed` in its
    `call` phase** and must also be in `failures.jsonl`. A hook that records that last one as
    `xpassed` fails this AC. `--compare --outcomes`:
    - equal runs compare equal;
    - a test whose `call` phase went `xfailed` → `passed` compares **unequal** with no
      `--expect`, and equal with `--expect '<that node id>:call:xfailed->passed'`;
    - with that `--expect` given, it still fails when a second test changed outcome, when the
      named test's `call` phase is still `xfailed` in B, when it was not `xfailed` in A, and
      when the same node's `setup` or `teardown` outcome changed;
    - an `--expect` that names the wrong phase (`setup`) fails;
    - a node id missing from B (a test that stopped running) fails.
  {#ac-3}
- **AC-4: no new wall-clock bound.** The census passes on the tree and **fails** on synthetic
  sources holding: `assert time.monotonic() - t0 < 2.0`; `assert elapsed < 2.0` where `elapsed`
  came from a clock difference; `assert took < LIMIT`; `assert 0.5 < wall < 3.0`. It passes on
  `assert elapsed >= 1.0` and on `assert time.monotonic() - t0 < HANG_GUARD_S`. A stale allow
  entry fails it. bug-228's and bug-231's tests hold no entry in the list. {#ac-4}
- **AC-5: a leaked daemon fails the session, by name.** An inner pytest run (a child process)
  over a fixture test that starts a real daemon with `spawn_daemon_subprocess` **on a root made
  by `mkdtemp(dir="/tmp")`, outside the sandbox root** (bug-229's shape) and never stops it:
  - exits with pytest's "tests failed" status although its one test passed;
  - prints `LEAKED PROCESS` with the daemon's pid, the fixture test's id and the store root;
  - leaves no process: the outer test asserts the pid is gone and the pid file's socket does
    not answer.

  Five more fixtures:
  - a test that stops its daemon properly: the inner run exits 0 and prints no `LEAKED` line;
  - a ledger line naming a live, unrelated process with a different start time: it is not
    signalled;
  - a run killed with SIGKILL mid-test: the next inner session's start prints `ORPHAN from a
    killed run` with the pid, stops it, and exits 0;
  - an in-process `Daemon` left serving: `LEAKED IN-PROCESS DAEMON`, stopped, session failed;
  - a daemon left SIGSTOPped: continued, stopped, reported, session failed.

  A fixture registered through `register_spawn` whose teardown does not stop it fails its own
  test, by name, before the session ends.
  {#ac-5}
- **AC-6: bug-228, bug-229 and bug-231 are closed with evidence, on T0.3's bands.**
  - **228 and 231:** the summary records, per row, what `T0#ac-3-1` asks of T0.3's own rows: the
    reproducer level and the base failure count out of 10 with E lines; each fix attempt's run of
    45; and the outcome (fixed, or `deferred: diagnosed-loud` with the counts). The mechanism
    tests of [[#r3-bug231]] and [[#r3-bug228]] are green either way, and neither test holds an
    entry in the wall-clock allow list.
  - **229:** AC-5.
  - Each row's status is written in 29.1's grammar with the fixing sha, after
    `git merge-base --is-ancestor <sha> master` succeeds.
  {#ac-6}
- **AC-7: T0.7's clean run, through the runner, in at most 20 minutes.**
  - **Clean, by T0's definition** (`T0#r7-4`): in the main tree, `scripts/ptest.sh --tier all`
    (tier (c) included) at a committed `master` sha that holds every stage: every shard exits 0;
    0 failed and 0 errors; no SkipGate line; no reaper line; collected = passed + pinned skips.
    T0's preconditions hold as written (GMD gate green, hooks in sync, a clean and unmoved tree,
    the lead told first). Ruling O7 is the only exception to "exit 0".
  - **The clone twin** (`T0#r7-5`): the same sha, the same command, in a littlebig clone; tier (c)
    is reported as not run there; its only skips are the pinned clone-only set.
  - **The time:** three consecutive clone runs of tiers (a) + (b) + (d), each started at a
    1-minute load average ≤ 8.0 on the 16-core dev machine, each ≤ 20:00 by the runner's own
    measurement, each clean. A run that started above 8.0 is labelled and does not count; it is
    not discarded from the summary. Tier (c)'s wall time is reported beside them.
  - **Every failure of the R0 digest is accounted for:** each maps to a row this task or T0
    closed, with the closing sha, or to a `diagnosed-loud` row.
  - **The main-tree run's directory is 29.5's baseline.** Its sha, its `summary.txt` and its
    `failures.jsonl` are committed, and [[task-29.5-split-giant-modules#r4]] names them.
  {#ac-7}
- **AC-8 (sub-task 29.4f, after 29.5): the family is computed and back-tested.** `--family`
  prints a reason for every file. For a synthetic change to one module, a test that imports it
  only through a `tests/` helper is in the family, and a child-process test is in the family of
  `cli`. The back-test table ([[#r6-bands]]) is in 29.4f's summary with its percentage and the
  action its band names, and [[#baseline-families]] is re-measured on the split tree beside
  the numbers of `f3709d2`. This AC does not hold up stage 5 or 29.5. {#ac-8}
- **AC-9: the merge gate refuses a clone and fails on a teardown error.** In a clone it exits 2
  and says why. On a fixture checkout whose merge touches a test that passes and errors at
  teardown, it exits non-zero and names the test (bug-230's shape). {#ac-9}
- **AC-10: the plain command is unchanged.** `pytest -q -p no:cacheprovider` with no `-m`
  collects, before and after the task, the same node ids in the same order, apart from the ids
  this task adds, renames or splits (bug-228's and bug-231's tests, the new test files). The two
  `--collect-only -q` listings are diffed and every differing line is in the summary with its
  reason. No id disappears without one. {#ac-10}
- **AC-11: the allow list cannot be used as a way round the census.** The wall-clock census:
  - fails on a new `legacy` entry;
  - passes on a `feature-bound` entry whose `ac` resolves, whose test sets its `knob`, and whose
    value is under `max_s`;
  - passes on a fixture entry of each knob form (`env:`, `const:`, `arg:`), the `arg:` one being
    a call that passes `timeout=0.2`;
  - **fails**, naming the entry, on each of: no `ac`; an `ac` whose spec id does not exist; an
    `ac` whose anchor does not exist in that spec; a test that never sets the knob it names; a
    value over `max_s`; a second entry for an AC that has one wall-clock clause; **an `arg:`
    entry whose call omits the parameter; one whose call passes a variable; one whose literal is
    over `max_s`**;
  - prints the two counts.

  The budget-outcome census fails on bug-228's test as it stands at base (the RED), passes on
  the same test with the budget substituted through `tests.timing.with_budget`, **fails** on
  the same test with the budget substituted by a bare `str.replace`, passes on the silent-peer
  `skipped_budget` leg,
  and fails on a synthetic test that asserts `outcome == "ok"` against a `SandboxDaemon` with no
  knob set. {#ac-11}
- **AC-12: a live touch fails the run, in every shard** (`plan-review-fable D3` = (a); stage 4's
  first AC, met before any other stage-4 work is accepted). With the fixture suite of AC-2 and
  a `sandbox_probe`-style test that touches a deny-set target without the probe marker: the
  test fails, its shard exits non-zero, the run exits non-zero and `summary.txt` names the test
  and the target. The same for a touch made by a spawned child, for each shard position 0 to
  N-1, and for the serial group. **Mutation:** the runner takes the run's exit code from the
  last shard only (a violation in shard 0 passes, so the test is red). {#ac-12}
- **AC-13: 23.0's open ends are closed on paper.** 23.0 carries the amends line for the bug-230
  read allow; `workflow/deferral_registry.md` holds one row each for 23.0 AC-7 and AC-8 with a
  reason and a review date; 23.0's status line names both rows. {#ac-13}
- **AC-14: T0's sub-tasks meet T0's own acceptance**, as amended by [[#fold-deltas]]. Each
  sub-task's implementation summary is T0's (`task-t0.<n>-…`), and this task's summary links
  them and gives one line per sub-task: sha, ch-bsd verdict, rows closed. **T0's frontmatter
  flips to `completed` in stage 5's closing commit**, by sub-task T0.7 + 29.4d, in the same
  commit that flips this spec's; from then on 29.1's checker refuses a `scheduled` row that
  still points at T0, so every T0 row is closed or re-homed in that commit. {#ac-14}
- **AC-15: this task flipped no derive pass.** Every file named in `_DERIVE_PASS_MODULES` is
  byte-identical at the task's base sha and at stage 5's sha; the check fails on a planted
  one-character edit to `pagerank.py`. The summary lists every `src/` file the task changed,
  and none is one of the seven. {#ac-15}

## Test strategy {#test-strategy}

- **RED first, per sub-task** ([[#order]]). Each new test file is run at the sub-task's base sha
  and recorded failing, with its E line, before any `scripts/`, `tests/tiering.py` or sandbox
  code is written. A census test that passes at base is not a RED test: its must-fail cases are
  what is RED.
- **The fixtures are real.** AC-5 starts real daemons on throwaway roots under the inner
  session's sandbox. Nothing is mocked there: the reaper is the thing under test and a faked
  process list would test the fake.
- **Mutations** (each must turn a named test RED within its deadline, and each is reverted in
  its own command; commit before the loop; clear `__pycache__` after it):
  1. `tier_of` ignores helper imports (AC-1's helper case);
  2. the marker hook skips files in one tier (AC-1's collection sum);
  3. the runner returns 0 when a shard exits non-zero (AC-2);
  4. the runner reports "all green" when tier (c) did not run (AC-2);
  5. `--compare` ignores the phase (AC-3);
  6. the E-line normaliser also replaces words, so different errors compare equal (AC-3);
  7. the census matches only numeric literals (AC-4's `LIMIT` case);
  8. the census ignores stale allow entries (AC-4);
  9. the ledger is not written after a fork (AC-5: the double-forked daemon is missed);
  10. the reaper prints but does not stop the process (AC-5: the pid survives);
  11. the reaper stops the process but does not fail the session (AC-5: exit 0);
  12. the reaper drops the start-time check (AC-5's reused-pid fixture is signalled);
  13. the session-start orphan sweep is removed (AC-5's fourth fixture);
  14. `--family` drops the `always` part (AC-8, in 29.4f);
  15. the merge gate ignores teardown errors (AC-9);
  16. the `Daemon.__init__` wrapper records nothing (AC-5's in-process fixture passes unseen);
  17. the reaper skips a stopped process (AC-5's SIGSTOP fixture survives);
  18. the census accepts a new `legacy` entry (AC-11);
  19. the census does not resolve the `ac` (a made-up AC id gets in; AC-11);
  20. the census does not check that the test sets its knob (AC-11);
  21. the budget-outcome census ignores fixtures (a test that reaches the daemon through a
      fixture passes unseen; AC-11);
  22. the reaper prints `root=` from a sandbox pid file only (AC-5's out-of-sandbox fixture
      prints `unknown`, so the test is red);
  23. for `arg:`, the census accepts any call that names the parameter, literal or not (AC-11's
      variable case passes, so the test is red);
  24. the hook does not record `xfailed` or `xpassed` (they are written as `passed`; AC-3's
      xfail case compares equal with no `--expect`, so the test is red);
  25. `--compare --outcomes` ignores a node id that is missing from one run (AC-3);
  26. the hook records a strict XPASS as `xpassed` (AC-3's strict-xpass row is not `failed`, so
      the test is red);
  27. `--expect` ignores its phase (AC-3's wrong-phase case passes, so the test is red).
- **T0's sub-tasks carry their own mutations** (M1.x to M7.x in T0's text). They are not
  repeated here.
- **All output to files.** Every run in this task goes through the runner or through
  `2>&1 | tee workflow/review-output/task-29.4/<name>.log`. The summary quotes, for each run,
  the exit code, the collected count, passed / failed / errors / skipped, the sha and the load.
{#test-strategy-list}

## Order of work {#order}

The stages of [[#fold-stages]], as sub-tasks. Each is its own branch from the `master` that
holds the stage before, with RED → GREEN → ch-bsd.

| Stage | Sub-task | Holds | Parallel with |
|---|---|---|---|
| 0 | 29.4-r0 | [[#r0]] (= T0.3's R0), after the dev venv is on duckdb 1.5.3 | — |
| 1 | T0.1' | T0's `#t0-1` as amended | — |
| 2 | T0.2 + 29.4b | T0's `#t0-2`; [[#r4]], [[#r5]] | T0.3, T0.8 |
| 2 | T0.3 + 29.4c | T0's `#t0-3`; [[#r3]] with bug-228 and bug-231 | T0.2, T0.8 |
| 2 | T0.8 | T0's `#t0-8` (bug-196) | T0.2, T0.3 |
| lane | T0.6 | T0's `#t0-6` | anything after stage 1 |
| 3 | T0.4, then T0.5 | T0's `#t0-4`, `#t0-5` | — |
| 4 | 29.4a | [[#ac-12]] first, then [[#r1]], [[#r2]], [[#r7]] | — |
| 5 | T0.7 + 29.4d | T0's `#t0-7` through the runner; [[#r8]], [[#r9]]; [[#ac-7]] | — |
| after 29.5 | 29.4f | [[#r6]] | 29.2, 29.3 |
{#order-table}

T0.2 and 29.4b both edit `tests/conftest.py` and `tests/sandbox_site/rmx_sandbox.py`, and T0.3
and 29.4c both edit the flaky tests' files. Each pair is one branch and one ch-bsd range, so
that two branches do not meet in one file. {#order-pairs}

## Files {#files}

T0's sub-tasks touch the files T0 lists for them (`T0#t0-1-files` to `T0#t0-8-files`). This
table is what this spec adds.

| File | Change |
|---|---|
| `tests/tiering.py` | new: `tier_of`, the signal table, `DEVTREE_FILES`, `ALWAYS_FILES`, the serial group |
| `tests/timing.py` | new: `HANG_GUARD_S`, the wait-for-outcome helper, and `with_budget` |
| `tests/conftest.py` | run-tier markers; `failures.jsonl` and `outcomes.jsonl` records; reaper hooks at session start and finish; the `Daemon` instance registry |
| `tests/sandbox_site/rmx_sandbox.py` | the ledger (exec and fork), `owner.json`, `short_root`, `register_spawn`, `sweep_orphans`, the reaper |
| `scripts/ptest.sh`, `scripts/ptest.py` | the runner: tiers, shards, `--files`, `--compare` (failures and `--outcomes`), `--merge-gate`; `--family` in 29.4f |
| `tests/shard_weights.json`, `tests/wallclock_allow.json`, `tests/tmp_root_allow.json` | new: measured weights and the two shrinking lists |
| `tests/test_suite_tiers.py`, `tests/test_ptest_runner.py`, `tests/test_wallclock_census.py`, `tests/test_budget_outcome_census.py`, `tests/test_tmp_root_census.py`, `tests/test_daemon_reaper.py` | new |
| `tests/test_family_derivation.py` | new, in 29.4f |
| `tests/fixtures/suite_health/` | new: the fixture suites for AC-2, AC-5, AC-9, as `case_*.py` files ([[#r1-fixtures]]) |
| `tests/test_plan4_remedy.py`, `tests/test_task21_1_recall_skip.py` | bug-231, bug-228 |
| the 28 files that call `spawn_daemon_subprocess`; the files R0's band selects for [[#r3-scope]] | roots; bound replacements |
| `pyproject.toml` | `pytest-timeout` in `dev`; `[tool.pytest.ini_options]` (`timeout`, `timeout_method`, `norecursedirs`) |
| `CLAUDE.md`, `.claude/PROJECT_PROFILE.md`, `workflow/TDD_GOVERNANCE.md` | [[#r8]] |
| `workflow/plans/plan-23-bounded-write-harness-tasks/task-23.0-test-sandbox.md`, `workflow/deferral_registry.md` | [[#r9]] |
| `workflow/plans/task-t0-suite-trust-sweep.md` | the amends lines of [[#fold-deltas]], if the lead has not already made them |
| `workflow/bug_registry.md` | rows 228, 229, 231 (and T0's rows, by T0's sub-tasks); two new rows for the product observations of [[#r3-bug231]] and [[#r3-bug228]] |
| `workflow/implementation_summaries/task-29.4-suite-health.md` | new: R0 tables, the class table, AC-7's runs, one line per T0 sub-task. `…/task-29.4f-derived-families.md` for the back-test |
{#files-table}

`src/refmatrix/` changes only if [[#r3-classes]] class B needs a clock to be injectable where
the code now calls `time.monotonic()` directly. Each such change is listed in the summary with
the test that needs it, and it adds a parameter with the current behaviour as its default.
- **Never in a derive file.** No commit of this task edits a file that
  `_DERIVE_CODE_MODULES` or `_DERIVE_PASS_MODULES` names (the eight files 29.2's
  `census_derive_modules.py` lists at `f3709d2`: `ingest.py`, `ingest_gmd.py`,
  `session_ingest.py`, `embedder.py`, `vectors.py`, `pagerank.py`, `consolidate.py`, `store.py`),
  with one stated exception below. An edit to a pass module flips its passes on every fleet
  store under the raw-bytes hash, which would put this task's release outside the standing go
  that [[#r10]] claims for it (ch-bsd r2 `#m11`).
- A class-B test that needs a clock in one of those files does not get it here: the test
  stays in the allow list, and the edit is routed to 29.2 R7's release, as a line in the
  summary and a note on the allow-list entry.
- **The exception is T0.4's deletion of the `_read_via_duckdb` state in `store.py`**, which is
  T0's text. `store.py` is in the union only, and the union is compared with no stamp
  ([[task-29.5-split-giant-modules#fact-derive]]), so it flips no pass. A check in stage 5
  shows the seven pass modules byte-identical (`git hash-object`) at this task's base and
  final sha.
{#files-src-note}

## Out of scope {#out-of-scope}

- **Re-specifying T0.** Its requirements, ACs and mutations are built from its own text.
- **Moving test files into directories.** A run tier is a marker and a function. 357 renames
  would conflict with every branch and buy nothing the marker does not.
- **Replacing all 78 bounds.** [[#r3-scope]] says which. The rest are listed, tiered and owned.
- **Revising the specs that carry new wall-clock ACs** ([[#r3-freshness]]).
- **Setting up the isolation lanes** ([[#r9]]).
- **A coverage gate, a formatter gate.**
{#out-of-scope-list}

## The user's decisions this spec is built to {#user-decisions}

All decided on 2026-11-14 (ruling L106, [[plan-review-2026-11-13#lead]]).

| Label | Decided | What it means here |
|---|---|---|
| `plan-review-fable D3` | (a): shard only once any live touch fails the session | stage 4's gate ([[#r2-list]]) and its first AC ([[#ac-12]]) |
| `plan-review-fable-store D5` | duckdb 1.5.3 in `.venv-eval` before baselines; the lead upgrades after the 0.83.1 runs | [[#r0]]: the durations run and every baseline are taken after the upgrade |
| `plan-review-fable D4` | a standing go for plan-29 releases whose suite equals the baseline by E line, the user told first, excluding releases that change the store on disk | [[#r10]]: this task's release changes neither hooks nor the store, so it is under the standing go |
| `plan-review-fable-memory D2` | 25.1b's `legs_ms` timing pair lands before 29.5 | it touches `cli.py` and `scan.py`, not this task's files; it has no owner task yet ([[task-29.1-registry-triage#homes-new-work]]) |
{#user-decisions-table}

## Decisions taken in this spec {#decisions}

- **plan-29 D10: shards are plain pytest processes over whole files; `pytest-xdist` is not
  added.**
  - **Why:** each process already has its own sandbox root, so file-level process shards are
    isolated with no new mechanism. A shard's log reads like today's logs, and a shard is
    reproduced by pasting its command. xdist distributes single tests across workers; the
    sandbox attributes a touch to a test by pid and by `PYTEST_CURRENT_TEST`, and module-level
    setup such as `h.mark_token(...)` runs per importing process. Whether that survives xdist is
    unknown, and finding out is a task of its own.
- **plan-29 D11: a run tier is decided per file, by a function, with two short lists.**
  - **Why:** the lead asked for a mechanical rule with a test that each file lands in exactly
    one tier. An ordered rule gives "exactly one" by construction. The two lists (`devtree`,
    serial) hold what cannot be read from the source, each entry with its reason and its bug.
  - **Cost:** a file with one bound among 143 tests (`test_task25_1_recall_budget.py`) sits in
    tier (d) whole until that bound is replaced. [[#r3-scope]] replaces by duration, so such
    files go first.
- **plan-29 D12: a family is the direct importers, the named files and a fixed always-set.
  The import closure is not used. It is built after 29.5.**
  - **Why:** measured, the closure is the suite. The direct rule is checked against history
    with bands fixed before the check ([[#r6-bands]]). The queue review moved the build after
    the split, where the direct rule becomes precise; the lead accepted that.
- **plan-29 D13: this session's leak fails this session; a killed run's orphan is stopped and
  reported, and does not fail the next run.**
  - **Why:** failing an unrelated run for an older run's leak teaches people to ignore the
    failure. It is still loud: a header line, a log file, a count.
- **plan-29 D14: no retries, and one hang guard.**
  - **Why:** a retry turns a load-dependent test into a slower load-dependent test and hides
    which one it was. T0's ruling O7 is not a retry: it re-runs a row that is already named
    `diagnosed-loud`, once, alone, and records both outcomes. The hang guard is not a speed
    check: it is one number, far above any real duration, whose only job is to turn a hang into
    a stack trace.
- **plan-29 D15: "normal load" is a 1-minute load average ≤ 8.0 at the start of a run on the
  16-core machine.**
  - **Why:** the 0.83.0 release run saw 5.6-7.6 with agents working; bug-231 failed at 12-20
    and also at 5.6-7.6. A target with no stated load cannot be failed.
- **plan-29 D20: 23.0's two lane ACs are deferred with rows; they are not adopted into this
  task.**
  - **Why:** the store review left the choice to this spec ("adopts or defers"). Both lanes
    need operator setup that only the user can do, and neither is needed for 29.5's baseline,
    which is T0.7's clean run in the main tree and its clone twin. Adopting them would put a
    user-gated setup on the path of the split.
  - **Cost:** 23.0's rule "tier 1 gates every merge to `master`" stays unmet, now with a row
    and a date in place of silence.
- **Not this spec's decisions:** that T0 is this task's body, the stage order, T0.3's bands for
  bug-228 and bug-231, and the families' move after 29.5 are the queue review's findings as
  the lead accepted them on 2026-11-14.
{#decisions-list}

## Revision note (2026-11-14, after ch-bsd r1 and ruling L105) {#rev-note}

`bsd-plan29-spec-r1` (dev `master` `549458e`) reviewed `dba9afd`. This spec's share, as ruling
L105 decided it:

| Finding | Change here |
|---|---|
| S8: `feature-bound` was an unguarded way round the census; the budget-outcome clause had no census | [[#r3-kinds]]: an entry's `ac` is resolved, its `knob` is checked in the test, its value is bounded, one entry per clause; [[#r3-budget-census]]: a census for bug-228's shape, measured at one hit; [[#ac-11]] with a must-fail per rule |
| M8: AC-5 asked for a root that R4 could not supply | [[#r4]] items 1 and 2: the ledger records `REFMATRIX_ROOT`, and the `LEAKED` line takes the root from it |
| M10: two product observations went to closing notes | [[#r3-bug231]], [[#r3-bug228]]: each is its own registry row |
| M12: fixture test files would join the real suite | [[#r1-fixtures]]: `case_*.py`, `norecursedirs`, and a named census exemption |
| M4: numbers that depend on the method | [[#baseline-wallclock-table]] (5 pure lower bounds in 3 files, with what the other 3 lines are); the `rmtree` count is 129 by the stated method |
| M1: who flips T0's frontmatter | [[#ac-14]] |
{#rev-note-table}

## Revision note 2 (2026-11-14, after ruling L106) {#rev-note-2}

- `plan-review-fable D3` = (a): the live-touch proof is stage 4's gate and its first AC
  ([[#r2-list]], [[#ac-12]]); the text for answers (b) and (c) is gone.
- `plan-review-fable-store D5` and `plan-review-fable D4` are decided ([[#user-decisions]],
  [[#r0]], [[#r10]]).
- A `feature-bound` entry's knob has three forms, `env:`, `const:` and `arg:<parameter>`
  ([[#r3-kinds]]; ruling L107), the last for 29.3's AC-a1, with a fixture row and three
  must-fail cases in [[#ac-11]].
{#rev-note-2-list}

## Revision note 3 (2026-11-14, round 3: ch-bsd r2 and ruling L108) {#rev-note-3}

- **M7:** the budget-outcome census sees a substituted budget in one form only, a call to
  `tests.timing.with_budget` ([[#r3-budget-census]], [[#ac-11]]).
- **M11:** no `src/` edit of this task touches a derive file, with T0.4's `store.py` deletion as
  the one stated exception, and [[#ac-15]] checks the seven pass modules byte for byte
  ([[#files-src-note]]).
- **M8:** the earlier revision note said "4 files" for the pure lower bounds; the table's 3 is
  right, and the note now agrees.
{#rev-note-3-list}

## Revision note 4 (2026-11-14, round 4: ch-bsd r3 and ruling L110) {#rev-note-4}

M1: the runner writes `outcomes.jsonl` for every run, and `--compare --outcomes` with `--expect`
compares per-node outcomes ([[#r2-list]], [[#ac-3]], two mutations). 29.5's gate G5 could not be
computed from failure sets alone. {#rev-note-4-body}

## Revision note 5 (2026-11-14, ch-bsd r4 GO with MEHs; ruling L111) {#rev-note-5}

M1: `--expect` names the phase (`<node id>:<phase>:<from>-><to>`); [[#r2-outcomes]] states how
the recorded outcome is derived from pytest's report, and a strict XPASS is `failed`;
[[#ac-3]] has a fixture row that pins it, and two mutations. {#rev-note-5-body}
