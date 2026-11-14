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
> Depends on: [[task-29.1-registry-triage]] (its checker test is one more file to tier; its
> grammar is how this task closes rows). The 0.83.0 deploy and the frozen spec-branch merges
> ([[plan-29-code-quality#decisions]] D2).
> Runs second in plan-29's order: 29.1 → **29.4** → 29.5 → 29.2 ∥ 29.3.
> Closes: bug-228, bug-229, bug-231, bug-239.
> Does NOT close bug-168, 170, 127, 215, 130, 190, 091: those are
> the T0 suite-trust sweep's, which runs after plan-29 ([[#t0-boundary]]).
> User gates: none. No step opens a live store, starts a fleet daemon or installs a hook.

rel: part-of -> [[plan-29-code-quality]]
rel: implements -> [[plan-29-code-quality#t4]]
rel: depends-on -> [[task-29.1-registry-triage]]
rel: depends-on -> [[tdd-governance]]
rel: related-to -> [[plan-review-2026-11-13#p1]]
rel: related-to -> [[task-29.5-split-giant-modules]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: reinforces -> [[feedback_review_clones_cannot_see_dev_tree_failures]]
rel: reinforces -> [[feedback_family_list_misses_generated_checks]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_compare_failures_by_error_not_name]]
rel: reinforces -> [[feedback_mutation_must_fail_not_hang]]

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
a rule that keeps speed out of assertions, a reaper, and a family that is computed. 29.5 then
runs the whole suite before and after every move commit, which is only affordable once this
task is done ([[plan-29-code-quality#order]]). {#why-next}

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
| lower bounds (`elapsed >= 1.4`: "it waited at least N"). Not load-sensitive. Not counted | 8 | 6 |
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
  (`/private/tmp/r1-…`). 127 `shutil.rmtree(..., ignore_errors=True)` sites remove them.
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

## What T0 does and what this task does {#t0-boundary}

The T0 suite-trust sweep (`task-t0-suite-trust-sweep`, approved on branch `spec-wave-t0` at
`fa1227d`, not yet on `master`; track T0 in [[plan-review-2026-11-13#p1]]) runs after plan-29.
Its id is written as code here, not as a link, because a link to a document that `master` does
not hold fails the repo lint gate; it becomes a link when that branch merges. The two tasks touch the same
files (`tests/conftest.py`, the sandbox). They do not touch the same lines:

| Concern | Owner |
|---|---|
| The skip gate in clones (bug-215), checkout identity (bug-155) | T0.1 |
| Three tests that read the real HOME or cwd ancestry (bug-170, 168, 127) | T0.2. This task only **places** those files in tier (c) |
| Three load flakes (bug-130, 190, 091), with a reproducer harness and bands | T0.3. This task does not fix them. Its R0 durations file is the one T0.3's R0 asks for, so T0.3 reads it and does not run the suite again for that |
| Wall-clock bounds as a class; bug-228, bug-231 | **this task** |
| Leaked daemons (bug-229) | **this task** |
| Tiers, shards, the runner, families, the merge gate | **this task** |
| "The clean full suite" (T0.7) | T0.7, run with this task's runner; the plain single-process command stays valid ([[#r1]]) |
{#t0-boundary-table}

## Requirements {#requirements}

### R0: measure first, and write the bands down before the numbers {#r0}

1. **One serial full run with durations**, in a fresh littlebig clone at the task's base sha:
   the documented command plus `--durations=0`, teed to
   `workflow/review-output/task-29.4/r0-serial.log`, with `uptime` before and after. This is
   the only full serial run the task needs. Its failures, by E line, are the **baseline digest**.
2. **Per-file sums** of setup + call + teardown are written to `tests/shard_weights.json`
   (committed) and into the summary: the 25 heaviest files, and the total per tier.
3. **The static censuses are re-run** at the base sha (the logic of the scripts in
   [[plan-29-spec-census]] becomes `tests/tiering.py` and the census tests, so this is their
   first run). The summary gives the
   table of [[#baseline]] again with the new numbers.
4. **Bands, fixed here, before the run:**

   | Measured | Band | Action |
   |---|---|---|
   | tier (a) wall, 4 shards | ≤ 5 min | every review round runs the whole of tier (a) ([[#r6]]) |
   | | 5-10 min | a round runs tier (a)'s derived family; the whole tier runs before a merge |
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
  shard's full output), `failures.jsonl`, and `summary.txt`. `summary.txt` has one line per
  shard (command, exit code, collected, passed / failed / errors / skipped, wall seconds, sandbox
  root), the totals, the sha, the load average at start and end, and the checkout kind
  (`owning` or `clone`).
- **`failures.jsonl` is written by conftest, not parsed from text.** When `RMX_FAILURES_OUT` is
  set, the existing `pytest_runtest_makereport` hook appends one record per failed **or
  errored** phase: node id, phase (`setup` / `call` / `teardown`), and the first `E` line. A
  teardown error is a failure here ([[feedback_review_clones_cannot_see_dev_tree_failures]]:
  "read every ERROR as well as every FAILED"). SkipGate and reaper findings are records too.
- **`scripts/ptest.sh --compare RUN_A RUN_B`** exits 0 only if the two runs have the same set of
  (node id, phase, normalised E line). Normalisation replaces sandbox roots, `/tmp` random
  segments, pids, hex addresses and decimal seconds with placeholders, and nothing else. The
  rule is one function with its own tests. This is the "equal by E line" check that 29.5 runs
  around every commit.
- **No reruns.** The runner has no retry flag. A test that fails only when sharded is a finding:
  it gets a wall-clock replacement ([[#r3]]), a place in the serial group with a reason, or a
  registry row. It is never run again until it passes.
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
  - What the 10.05 s says about the product (a daemon took the whole 10 s grace to exit at load
    12-20) is not this task's. It is one line in bug-231's closing note, so the next reader of
    the hub watchdog's grace has it.
  {#r3-bug231}
- **bug-228** (`test_ac2b_live_daemon_recall_writes_one_ok_recall_row`: `outcome == "ok"`
  against the generated hook's 5 s budget on a live sandbox daemon). There is no `<` in this
  test: the product's budget is the bound. R0 measures one failing run and says which leg spent
  the time (the row asks for exactly this), then:
  - **if ≥ 90% of the overrun is before the recall op starts** (boot, model warm-up): the test
    waits on the harness's readiness signal before it runs the hook, as bug-184's fix does;
  - **otherwise** the test is split. One test asserts, with no daemon, that the generated
    command carries the 5 s budget. The live test runs the same generated command with that
    one budget value replaced by `HANG_GUARD_S` (the replacement is asserted to have changed
    exactly one token) and asserts `outcome == "ok"`. The `skipped_budget` leg keeps its
    existing test, which already uses a silent peer and does not depend on speed.
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
- **How far this task goes.** bug-228 and bug-231 are replaced. So is every site in a file whose
  serial duration puts tier (d) over its band ([[#r0-bands]]), and every class C and D site
  (they are the cheapest and the most load-sensitive: 22 bounds are ≤ 1 s). The rest stay in the
  allow list, in tier (d), each with its class recorded. The summary gives the count left, and
  29.1's grammar gives the remainder one row: `scheduled` or `deferred`, never silence.
  {#r3-scope}

### R4: a reaper that fails the session {#r4}

Every process the suite starts is known, and one that is still alive at the end fails the run.

1. **The ledger.** Each Python process that starts under the sandbox appends one line to
   `<sandbox root>/children.jsonl`: pid, parent pid, start time, argv, and the test id from
   `PYTEST_CURRENT_TEST`. Two hooks write it, both in `tests/sandbox_site/rmx_sandbox.py`:
   `install_from_env()` (every exec'd child runs it through `sitecustomize`) and an
   `os.register_at_fork(after_in_child=…)` callback, registered by `enter()` in the pytest
   process and by `install_from_env()` in every child (a daemon double-forks with no exec, so
   its final pid is only visible there). One `write` of one line under `O_APPEND`.
2. **At session finish** (the outermost session only), for every ledger pid that is still
   alive **and** whose process start time matches the ledger's:
   - print one line: `LEAKED PROCESS pid=<n> age=<s> spawned in <test id> argv=<…> root=<store
     root, when a pid file under the sandbox names it>`;
   - stop it: `daemon.stop_daemon(root)` when the root is known, else SIGTERM, a bounded wait,
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

### R6: families are derived {#r6}

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
2. runs tier (c), the family of `HEAD..MERGE_HEAD` ([[#r6]]), and `./scripts/lint-gmd.sh`;
3. fails on any failed test, any **errored** phase (teardown included), any SkipGate or reaper
   finding, and any non-zero exit of the lint gate;
4. writes `workflow/review-output/merge-gate-<merge head sha>/`, as [[#r2]] does.

`CLAUDE.md`'s git workflow and `#before-commit` list name this command. A dev-tree run carries
known failures today. The 0.83.0 release run had 14: bug-168 × 9, bug-170, bug-127 and
bug-196 × 2 (all T0's), and bug-231 (this task's). Until T0 closes its rows, the gate compares
by E line against the previous gate's `failures.jsonl`: a known row is recorded as seen, and a
new node id or a new E line fails the gate. {#r7-list}

### R8: the docs say what is true {#r8}

- `CLAUDE.md#development-commands` and `.claude/PROJECT_PROFILE.md#commands`: the tier commands,
  the family command and the merge gate, beside the plain full command. Suite size and time are
  quoted from the last `summary.txt`, with its date.
- `README.md` (bug-239): the hand-written "1361 tests" goes. The README names the command that
  prints the count and gives no number that nothing updates.
- `workflow/TDD_GOVERNANCE.md`: one paragraph: what a family is for and what it is not for.
- `workflow/test_mock_registry.md`: any new double.
{#r8-list}

`CLAUDE.md` and `.claude/PROJECT_PROFILE.md` are instruction files. Their edits are part of
what the user approves with this plan; the implementer makes exactly the edits named here and
quotes the diff in the summary. {#r8-instruction-note}

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
- **AC-3: `--compare` is exact.** Two fixture runs that differ only in a sandbox path, a pid and
  a duration compare equal. Two that differ in one E line, in one node id, or in one phase
  (`call` against `teardown`) compare unequal, and the output names the difference. {#ac-3}
- **AC-4: no new wall-clock bound.** The census passes on the tree and **fails** on synthetic
  sources holding: `assert time.monotonic() - t0 < 2.0`; `assert elapsed < 2.0` where `elapsed`
  came from a clock difference; `assert took < LIMIT`; `assert 0.5 < wall < 3.0`. It passes on
  `assert elapsed >= 1.0` and on `assert time.monotonic() - t0 < HANG_GUARD_S`. A stale allow
  entry fails it. bug-228's and bug-231's tests hold no entry in the list. {#ac-4}
- **AC-5: a leaked daemon fails the session, by name.** An inner pytest run (a child process)
  over a fixture test that starts a real daemon with `spawn_daemon_subprocess` and never stops
  it:
  - exits with pytest's "tests failed" status although its one test passed;
  - prints `LEAKED PROCESS` with the daemon's pid, the fixture test's id and the store root;
  - leaves no process: the outer test asserts the pid is gone and the pid file's socket does
    not answer.

  A second fixture's test stops its daemon properly: the inner run exits 0 and prints no
  `LEAKED` line. A third has a ledger line naming a live, unrelated process with a different
  start time: it is not signalled. A fourth is killed with SIGKILL mid-test; the next inner
  session's start prints `ORPHAN from a killed run` with the pid, stops it, and exits 0.
  {#ac-5}
- **AC-6: bug-228, bug-229, bug-231 and bug-239 are closed with evidence.** For 228 and 231:
  the replaced tests pass 20 of 20 while 4 shards of tier (b) run beside them (a load the old
  bound failed under; the old test's result under the same load is recorded first, as the
  reproducer, and if it does not fail in 20 the summary says so and the row closes on the
  mechanism test alone, with that stated). For 229: AC-5. Each row's status is written in 29.1's
  grammar with the fixing sha, after `git merge-base --is-ancestor <sha> master` succeeds. {#ac-6}
- **AC-7: at most 20 minutes.** Three consecutive `--tier all` runs at the final sha on the
  16-core dev machine, each started at a 1-minute load average ≤ 8.0:
  - each run's wall time for tiers (a) + (b) + (d), as the runner measures it, is ≤ 20:00;
  - each run's `failures.jsonl` compares equal ([[#ac-3]]) to the R0 serial baseline's, minus
    the records of the rows this task closes.

  A run that started above load 8.0 is labelled and does not count; it is not discarded from
  the summary. Tier (c)'s wall time is reported beside it. The before number is R0's serial run.
  {#ac-7}
- **AC-8: the family is computed and back-tested.** `--family` prints a reason for every file.
  For a synthetic change to one module, a test that imports it only through a `tests/` helper
  is in the family, and a child-process test is in the family of `cli`. The back-test table
  ([[#r6-bands]]) is in the summary with its percentage and the action its band names. {#ac-8}
- **AC-9: the merge gate refuses a clone and fails on a teardown error.** In a clone it exits 2
  and says why. On a fixture checkout whose family holds a test that passes and errors at
  teardown, it exits non-zero and names the test (bug-230's shape). {#ac-9}
- **AC-10: the plain command is unchanged.** `pytest -q -p no:cacheprovider` with no `-m`
  collects, before and after the task, the same node ids in the same order, apart from the ids
  this task adds, renames or splits (bug-228's and bug-231's tests, the new test files). The two
  `--collect-only -q` listings are diffed and every differing line is in the summary with its
  reason. No id disappears without one. {#ac-10}

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
  14. `--family` drops the `always` part (AC-8);
  15. the merge gate ignores teardown errors (AC-9).
- **All output to files.** Every run in this task goes through the runner or through
  `2>&1 | tee workflow/review-output/task-29.4/<name>.log`. The summary quotes, for each run,
  the exit code, the collected count, passed / failed / errors / skipped, the sha and the load.
{#test-strategy-list}

## Order of work {#order}

Four sub-tasks, each on its own branch from the `master` that holds the one before, each with
RED → GREEN → ch-bsd:

| Sub-task | Holds | Why this order |
|---|---|---|
| 29.4a | R0, R1, R2 (tiers, runner, `--compare`, the hang guard) | nothing else can be measured without it. No test's meaning changes |
| 29.4b | R4, R5 (reaper, roots) | shards multiply daemons; the reaper has to exist before shards become the normal way to run |
| 29.4c | R3 (bug-228, bug-231, the census, the replacements R0's band asks for) | uses 29.4a's shards as its load |
| 29.4d | R6, R7, R8 (families, merge gate, docs), then AC-7's three runs | the final numbers are taken last |
{#order-table}

## Files {#files}

| File | Change |
|---|---|
| `tests/tiering.py` | new: `tier_of`, the signal table, `DEVTREE_FILES`, `ALWAYS_FILES`, the serial group |
| `tests/timing.py` | new: `HANG_GUARD_S` and the wait-for-outcome helper |
| `tests/conftest.py` | tier markers; `failures.jsonl` records; reaper hooks at session start and finish |
| `tests/sandbox_site/rmx_sandbox.py` | the ledger (exec and fork), `owner.json`, `short_root`, the reaper |
| `scripts/ptest.sh`, `scripts/ptest.py` | the runner: tiers, shards, `--compare`, `--family`, `--merge-gate` |
| `tests/shard_weights.json`, `tests/wallclock_allow.json`, `tests/tmp_root_allow.json` | new: measured weights and the two shrinking lists |
| `tests/test_suite_tiers.py`, `tests/test_ptest_runner.py`, `tests/test_wallclock_census.py`, `tests/test_tmp_root_census.py`, `tests/test_daemon_reaper.py`, `tests/test_family_derivation.py` | new |
| `tests/fixtures/suite_health/` | new: the fixture suites for AC-2, AC-5, AC-9 |
| `tests/test_plan4_remedy.py`, `tests/test_task21_1_recall_skip.py` | bug-231, bug-228 |
| the 28 files that call `spawn_daemon_subprocess`; the files R0's band selects for [[#r3-scope]] | roots; bound replacements |
| `pyproject.toml` | `pytest-timeout` in `dev`; `[tool.pytest.ini_options]` |
| `CLAUDE.md`, `.claude/PROJECT_PROFILE.md`, `README.md`, `workflow/TDD_GOVERNANCE.md` | [[#r8]] |
| `workflow/bug_registry.md` | rows 228, 229, 231, 239 |
| `workflow/implementation_summaries/task-29.4-suite-health.md` | new: R0 tables, the class table, the back-test, AC-7's runs |
{#files-table}

`src/refmatrix/` changes only if [[#r3-classes]] class B needs a clock to be injectable where
the code now calls `time.monotonic()` directly. Each such change is listed in the summary with
the test that needs it, and it adds a parameter with the current behaviour as its default.
{#files-src-note}

## Out of scope {#out-of-scope}

- **T0's rows** ([[#t0-boundary]]).
- **Moving test files into directories.** A tier is a marker and a function. 357 renames would
  conflict with every branch and buy nothing the marker does not.
- **Replacing all 78 bounds.** [[#r3-scope]] says which. The rest are listed, tiered and owned.
- **The macOS user lane and the VM lane** (`scripts/test-lane-user.sh`, `test-lane-vm.sh`). They
  run the plain command, which stays valid.
- **bug-088 / bug-101** (live-socket reach), deferred by the user. Sharding multiplies that
  reach; the runner's summary records the touches-log line count per run so the multiplication
  is seen, and adds no mitigation.
- **A coverage gate, a formatter gate.**
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **plan-29 D10: shards are plain pytest processes over whole files; `pytest-xdist` is not
  added.**
  - **Why:** each process already has its own sandbox root, so file-level process shards are
    isolated with no new mechanism. A shard's log reads like today's logs, and a shard is
    reproduced by pasting its command. xdist distributes single tests across workers; the
    sandbox attributes a touch to a test by pid and by `PYTEST_CURRENT_TEST`, and module-level
    setup such as `h.mark_token(...)` runs per importing process. Whether that survives xdist is
    unknown, and finding out is a task of its own.
- **plan-29 D11: a tier is decided per file, by a function, with two short lists.**
  - **Why:** the lead asked for a mechanical rule with a test that each file lands in exactly
    one tier. An ordered rule gives "exactly one" by construction. The two lists (`devtree`,
    serial) hold what cannot be read from the source, each entry with its reason and its bug.
  - **Cost:** a file with one bound among 143 tests (`test_task25_1_recall_budget.py`) sits in
    tier (d) whole until that bound is replaced. [[#r3-scope]] replaces by duration, so such
    files go first.
- **plan-29 D12: a family is the direct importers, the named files and a fixed always-set.
  The import closure is not used.**
  - **Why:** measured, the closure is the suite. The direct rule is checked against history
    with bands fixed before the check ([[#r6-bands]]).
- **plan-29 D13: this session's leak fails this session; a killed run's orphan is stopped and
  reported, and does not fail the next run.**
  - **Why:** failing an unrelated run for an older run's leak teaches people to ignore the
    failure. It is still loud: a header line, a log file, a count.
- **plan-29 D14: no reruns, and one hang guard.**
  - **Why:** a rerun turns a load-dependent test into a slower load-dependent test and hides
    which one it was. The hang guard is not a speed check: it is one number, far above any
    real duration, whose only job is to turn a hang into a stack trace.
- **plan-29 D15: "normal load" is a 1-minute load average ≤ 8.0 at the start of a run on the
  16-core machine.**
  - **Why:** the 0.83.0 release run saw 5.6-7.6 with agents working; bug-231 failed at 12-20
    and also at 5.6-7.6. A target with no stated load cannot be failed.
{#decisions-list}
