---
gmd: "0.1"
id: task-t0-suite-trust-sweep
title: "Task T0: the suite-trust sweep: eight instrument bugs, the SkipGate clone row, and the plan-6/7/8/15 closure gates (W2-a, W2-b, W2-c, W1-e)"
tags: [task, t0, tests, instrument, skipgate, flaky, plan-6, plan-7, plan-8, plan-15, bug-215, bug-170, bug-168, bug-155, bug-127, bug-130, bug-190, bug-091]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
---

# Task T0: suite-trust sweep {#root}

> Plan: the consolidated queue, track **T0 Instrument trust** ([[plan-review-2026-11-13#p1]]),
> queue item 2, run in parallel with 26.5 ([[plan-review-2026-11-13#queue-body]]). Spec gap G5
> ([[plan-review-2026-11-13#spec-gaps]]).
> Status: **Drafting.** It is approved only after a clean ch-bsd spec round (the d9co route,
> [[plan-review-2026-11-13#goal-horizon]]). [[#open-items]] lists five choices for the lead
> before then.
> Depends on: queue item 1 merged to `master` (bug-212, bug-216, 25.1 rev 7). Their branches
> edit `src/refmatrix/store.py` and `src/refmatrix/hooks.py`, which T0.4 also edits. Every T0
> branch starts from the `master` sha that holds those merges.
> Closes: bug-215 (it is also the SkipGate UNPINNED row), 170, 168, 155, 127, 130, 190 and 091.
> It also closes the recorded closure gates of plans 6, 7, 8 and 15 (D-Q6).
> User gates: none. No step opens a live store, starts a fleet daemon, or needs a hook install
> window ([[#rules]] R0.7).

rel: derives-from -> [[plan-review-2026-11-13#d-q6]]
rel: derives-from -> [[plan-review-2026-11-13#f8]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: part-of -> [[plan-review-2026-11-13#queue-body]]
rel: derives-from -> [[plan-review-2026-10-14#t11-folded-waves]]
rel: derives-from -> [[bug_registry]] {bugs: "bug-215, bug-170, bug-168, bug-155, bug-127, bug-130, bug-190, bug-091"}
rel: derives-from -> [[bsd-plan6-deferrals-docs-benchmark-r1-e0b7df6]]
rel: derives-from -> [[bsd-plan8-9-10-r5-e0b7df6]]
rel: derives-from -> [[bsd-r1-remedy-r13-dcf7115]]
rel: depends-on -> [[tdd-governance]]
rel: depends-on -> [[constitution]]
rel: reinforces -> [[feedback_compare_failures_by_error_not_name]]
rel: reinforces -> [[feedback_mutation_must_fail_not_hang]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]

## Why {#why}

Every review round pays for a test instrument it cannot trust. The 0.82.0 release suite
(`workflow/review-output/release-0.82.0-full.log`, main tree, sha in `release-0.82.0-full.sha`)
ended **14 failed, 4265 passed**. None of the 14 failures was a regression:

- bug-168: 9 failures (the rewriter stands down under the real `~/.refmatrix/learn.off`);
- bug-170: 1 (the hooks test renders under the sandbox HOME);
- bug-127: 1 (a DuckDB `Conflicting lock` held by the test's own daemon);
- bug-155's test: 1. Its E line that day was bug-211, which is now fixed;
- bug-196: 2 (see [[#open-items]] O1).

In a littlebig clone every run exits 1 on a skip the gate cannot place (bug-215), and the
repo-scope GMD gate fails on 32 dangling ids (bug-155). Three tests fail only under load (bug-130,
190, 091). Readers have learned to diff E lines by hand and call the rest "pre-existing". That is
the habit this task removes. {#why-instrument}

Four legacy plans cannot close for the same reason. Each carries a recorded "may NOT flip" gate
that the 2026-10-19 fold made a wave item. Neither a decision nor a host has moved them since
(contra-e Ce-9, `workflow/review-output/pop-2026-11-13/contra-e.md`). D-Q6 keeps the gates and
schedules them here:
- W2-a, plan-6 ch-bsd r1 at `e0b7df6`;
- W2-b, plan-8 ch-bsd r5;
- W2-c, the plan-7 task 7.4 dense/fused re-run;
- W1-e, the plan-15 clean suite plus r13 #s-1/#m-1/#m-2. {#why-gates}

## Scope and order {#scope}

| sub-task | closes | branch | merges |
|---|---|---|---|
| [[#t0-1]] Skip gate and checkout identity | bug-215 (= the SkipGate UNPINNED row, bug-212 r2 flag 8 / r1 #m-4), bug-155 | `task-t0.1-skip-gate-checkout-identity` | first |
| [[#t0-2]] Dev-tree-only tests stop reading the real HOME and cwd ancestry | bug-170, bug-168, bug-127 | `task-t0.2-dev-tree-test-isolation` | any order after T0.1 |
| [[#t0-3]] Load-dependent flakes | bug-130, bug-190, bug-091 | `task-t0.3-load-flakes` | any order after T0.1 |
| [[#t0-4]] W2-a: the plan-6 remedy | plan-6 r1 #b-1, #b-2, #s-1, #s-2, #s-3, #m-1..#m-5; todo G7/G8 | `task-t0.4-plan6-remedy` | any order after T0.1 |
| [[#t0-5]] W2-b: the plan-8 remedy | plan-8 r5 #b-2, #b-3, #s-4, #s-9, #m-10 (+ #s-6 check) | `task-t0.5-plan8-remedy` | after T0.4 (both edit `cli.py`; T0.4's registry lint lands first) |
| [[#t0-6]] W2-c: the plan-7 dense/fused re-run | task 7.4's missing rows; REPORT.md completed | `task-t0.6-plan7-dense-rerun` | any time after T0.1; long-running |
| [[#t0-7]] W1-e: plan-15 r13 remedy + the clean full suite | plan-15 r13 #s-1, #m-1, #m-2; the clean-suite gate for plans 15, and the trust proof for T0 | `task-t0.7-plan15-close-clean-suite` | **last** |

T0.1 goes first because until it lands, every clone run exits 1 and no sub-task can quote a
clean exit code. T0.2 to T0.6 are independent of each other, apart from the T0.4 → T0.5 order.
They may run in parallel littlebig clones (each in its own `/Volumes/littlebig/refmatrix-t0-<n>`).
T0.7 runs the closing suite, so it merges last. {#scope-order}

## Rules for every sub-task {#rules}

- **R0.1 Re-verify before fixing.** Every finding cited here is 2 to 7 weeks old, and the code
  has moved: for example `store.py:717` is now `:1159`, and r13 #m-1's wording no longer greps.
  Each sub-task opens with an R0 that re-reads every cited site at the branch's base sha. The
  result is a table in the implementation summary with one row per finding: `holds` (with the
  current `path:line`), `closed` (the commit or evidence that closed it), or `changed` (what it
  is now). A `closed` finding needs no code. A finding that has `changed` is fixed in its current
  shape, or, if the change alters what the fix must be, raised to the lead before any code is
  written. {#r0-1}
- **R0.2 Failures are compared by E line, not test name.** Any claim that a failure is
  "pre-existing" or "the same" quotes both E lines.
  [[feedback_compare_failures_by_error_not_name]]: in the 0.82.0 log, bug-155's test failed on
  bug-211's E line, not bug-155's. {#r0-2}
- **R0.3 Every run is a log, and every log states its result.** Output goes through
  `2>&1 | tee workflow/review-output/t0/<name>.log`. The implementation summary quotes, for each
  run: the pytest **exit code**, the collected count, `N passed / N failed / N skipped`, any
  SkipGate lines, and the sha. A summary that gives counts without an exit code does not meet
  this rule (bug-215's fix column). {#r0-3}
- **R0.4 RED first, and a mutation must FAIL, not hang.** New tests are RED at the base sha, with
  the failing E line recorded. Every named mutation fails within a bounded deadline, and each
  mutation is reverted in its own command ([[feedback_mutation_must_fail_not_hang]]). Commit
  before the mutation loop, and clear `__pycache__` after it. {#r0-4}
- **R0.5 No skip is added, and no test is weakened.** A test that cannot run in some checkout is
  pinned in `ALLOWED_SKIPS` with its reason ([[#t0-1]]). Nothing is added to `ALLOWED_SKIPS` to
  make a failure disappear. {#r0-5}
- **R0.6 Sandbox discipline.** Tests use throwaway stores under a short `mkdtemp()` root. Nothing
  opens `Store()` on a catalog that a live daemon holds. No dev-venv `rmx` runs against a live
  store. {#r0-6}
- **R0.7 No install window.** No T0 change may make `rmx install-hooks --check` report drift on an
  existing install. If one would, it stops and is raised as a G31 batching item. It is never
  shipped as a silent drift. {#r0-7}
- **R0.8 One ch-bsd round per sub-task range**, remedied and re-reviewed until CLEAN or MEH-only.
  This is the plans' own contract for T0.4 to T0.7 (CLEAN is required wherever a plan's
  `#execution` says CLEAN). {#r0-8}

## T0.1 Skip gate and checkout identity (bug-215, bug-155) {#t0-1}

**bug-215 = the SkipGate UNPINNED row.** The plan review lists "the SkipGate UNPINNED row" as a
separate item. Its source, flag 8 of the bug-212 GREEN r2 notes, reads "Unchanged from r1: … the
SkipGate UNPINNED skip (m-4)". The bug-212 summary first called it "no registry row yet". The
bug-215 row was then logged on master from ch-bsd bug-212 r1 #m-4. So these are one defect with
one fix, and closing bug-215 closes the flag. {#t0-1-identity}

**bug-155, root-caused while writing this spec (probe, 2026-11-13).** Two `git archive` copies of
`1cf3b9f` were made: one in a dir named `refmatrix`, one in a dir named `refmatrix-clone`, each
with an empty `.git/`. The repo-scope lint ran over the same scope and the main memory dir:
- `refmatrix`: 1 `dangling-doc`;
- `refmatrix-clone`: 33 `dangling-doc`;
- `refmatrix-clone` plus `project: refmatrix` in `.gmd/config.yml`: 1.

The cause is `tools/gmd/lint.py` `project_name()`. With no `project:` key it takes the repo
directory's basename as the id namespace. The ADRs carry ids like `refmatrix/adr-0000-adr-overview`.
So in any checkout not named `refmatrix`, `[[adr-0000-adr-overview]]` does not resolve. The
remaining 1, in both copies, is `[[agent-brief-bsd-pop-r1]]`, which [[#open-items]] O4 covers.
{#t0-1-bug155-cause}

### Requirements {#t0-1-requirements}

1. **R1.1 The allowed-skip set follows each skip's condition, not one directory test.**
   `tests/conftest.py` builds `ALLOWED_SKIPS` per entry:
   - a `_CLONE_NO_VENV` entry is allowed only when `<checkout>/.venv-eval/bin/rmx` does not exist;
   - a `_CLONE_HOOKS` entry is allowed only when the installed hooks belong to another checkout,
     decided the way the test itself decides it.

   A `.venv-eval` that is a symlink resolving outside the checkout satisfies neither condition by
   itself. Today one `(_REPO / ".venv-eval").is_dir()` test switches the whole set (`conftest.py:286`).
   {#r1-1}
2. **R1.2 The gate matches the reason too.** `SkipGate` treats a skip as pinned only when its
   nodeid is allowed and its reason contains the pinned reason string. A pinned test that skips
   for some other reason is reported `SKIPPED-UNPINNED`, with both reasons. {#r1-2}
3. **R1.3 The GMD id namespace does not depend on the checkout's directory name.**
   `.gmd/config.yml` declares `project: refmatrix`. `./scripts/lint-gmd.sh` and
   `test_the_repo_scope_is_clean_under_the_stricter_gate` then give the same result in a checkout
   named `refmatrix` and in one named anything else. `tools/gmd/lint.py` is not changed: the config
   key already exists for this purpose (`project_name()` docstring). {#r1-3}
4. **R1.4 Exit codes in summaries.** The implementation summary template line is added
   (`workflow/templates/task-spec.md` `#done` example, or wherever the template names the
   summary): "quote the pytest exit code and the collected count for every run". This is the
   second half of bug-215's fix column. {#r1-4}

### Acceptance {#t0-1-acceptance}

- **AC-1.1 (RED at base, clone).** In a littlebig clone with a symlinked `.venv-eval`, a run that
  reaches `test_installed_hooks_match_generated` exits **1**, with
  `SKIPPED-UNPINNED tests/test_repo_hooks_in_sync.py::test_installed_hooks_match_generated`. After
  the fix the same command exits **0**, and the skip is reported as pinned. The log carries both
  exit codes. {#ac-1-1}
- **AC-1.2 (unit, both conditions).** A `pytester` (or direct) test of the allowed-set builder
  covers four checkout layouts and asserts the exact allowed set for each:
  - no venv;
  - a real venv;
  - a symlinked venv;
  - a foreign hooks install. {#ac-1-2}
- **AC-1.3 (reason match).** A pinned nodeid that skips with a different reason fails the session,
  and the output names both reasons. {#ac-1-3}
- **AC-1.4 (bug-155, clone).** In the T0.1 clone (not named `refmatrix`),
  `test_the_repo_scope_is_clean_under_the_stricter_gate` is RED at base. Its E line lists the 32
  ADR / architecture-index `dangling-doc` errors, which R0.2 quotes. It is green after R1.3, as
  long as O4's two lead-owned errors are fixed on the base. If they are not, the remaining E lines
  are exactly those, quoted by E line. `./scripts/lint-gmd.sh` exits 0 under the same condition.
  {#ac-1-4}
- **Mutations (each FAILS):**
  - M1.1: restore the single `is_dir()` switch (AC-1.1 and AC-1.2 red);
  - M1.2: drop the reason check (AC-1.3 red);
  - M1.3: delete `project:` from `.gmd/config.yml` (AC-1.4 red with the 32 errors). {#t0-1-mutations}

### Files {#t0-1-files}

`tests/conftest.py`, `tests/sandbox_site/rmx_sandbox.py` (`SkipGate`), a new
`tests/test_t0_skip_gate.py`, `.gmd/config.yml`, `workflow/templates/task-spec.md`,
`workflow/bug_registry.md` (rows bug-215, bug-155),
`workflow/implementation_summaries/task-t0.1-skip-gate-checkout-identity.md`.

## T0.2 Dev-tree-only tests stop reading the real HOME and cwd ancestry (bug-170, bug-168, bug-127) {#t0-2}

These three fail in the main tree and skip in clones. That is why no release suite run in a
clone saw them (bug-170's row calls it "the same blind spot as bug-168"). They are proven
post-merge, in the main tree, by T0.7's run. Pre-merge, each AC below names how the clone
reproduces the main-tree condition. {#t0-2-lead}

### Requirements {#t0-2-requirements}

1. **R2.1 bug-170: the hooks test renders with the real home, read-only.**
   `tests/test_repo_hooks_in_sync.py::test_installed_hooks_match_generated` renders the generator
   with an explicit home equal to the real `HOME`, captured before the 23.0 sandbox redirect. It
   can do this through `hooks_mod.check` with an explicit home, or by restoring `HOME` for that
   one render.

   It reads, and never writes, outside the sandbox. The 23.0 touches-log shows no write outside
   the sandbox root. It still compares all three user-global scripts and the SessionStart memory
   dir, so the comparison it makes is not narrowed. {#r2-1}
2. **R2.2 bug-168: the rewriter tests measure rewriting, not the ambient learn switch.**
   `tests/test_search_hooks.py`'s `_rewrite()` produces a result that depends on no file outside
   the test's tmp root. Today the rendered rewriter's `_learning_off(cwd)` walks up from the cwd
   to the user's `~/.refmatrix/learn.off`, which has been present since 2026-10-15. The fix can
   pin `RMX_LEARN=on` or run from a tmp cwd outside `$HOME`. Either way, the stand-down stays
   tested: a new test plants `learn.off` in an ancestor of a tmp cwd and asserts that the
   rewriter emits nothing. {#r2-2}
3. **R2.3 bug-127: the real-daemon brief test never opens `Store()` under its own daemon.**
   `tests/test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon`
   reaches the library's raise through the daemon op path, which is the way MCP reaches it. It
   does not open `Store()` on the catalog its daemon holds. R0 confirms that the second opener is
   the test itself. The 0.82.0 E line is `Could not set lock … Conflicting lock is held in …
   (PID <the test's daemon>)`. If R0 finds a different opener, that opener is the fix. {#r2-3}

### Acceptance {#t0-2-acceptance}

- **AC-2.1 (bug-170).** With `home=` pointed at a tmp copy of the installed hooks dir with one
  script byte changed, the comparison reports `script … differs`. This proves the test looks at
  real content. With the real home in the main tree (T0.7), the test passes after `rmx
  install-hooks --check` reads in sync. The sandbox touches-log for the test shows no write
  outside the sandbox. {#ac-2-1}
- **AC-2.2 (bug-168).** In the clone, run the rewriter tests with a tmp cwd whose ancestor holds
  `.refmatrix/learn.off`. At base this reproduces the main-tree E line
  `AssertionError: ('grep -rn pat src/', '')`. After the fix, 24/24 pass. The new stand-down test
  passes. {#ac-2-2}
- **AC-2.3 (bug-127).** The test passes in a checkout with a `.venv-eval` of its own (the main
  tree, inside T0.7's run, or a clone that has one). No `Conflicting lock` appears in the log.
  {#ac-2-3}
- **Mutations (each FAILS):**
  - M2.1: the rewriter ignores `learn.off` (stand-down test red);
  - M2.2: the hooks comparison skips the scripts (AC-2.1's byte-change case goes green, so the
    test is red);
  - M2.3: the library stops raising on an unknown class (bug-127 test red). {#t0-2-mutations}

### Files {#t0-2-files}

`tests/test_repo_hooks_in_sync.py`, `tests/test_search_hooks.py`,
`tests/test_brief_real_daemon.py`, `workflow/test_mock_registry.md` (any new double),
`workflow/bug_registry.md` (rows 170, 168, 127),
`workflow/implementation_summaries/task-t0.2-dev-tree-test-isolation.md`.

## T0.3 Load-dependent flakes (bug-130, bug-190, bug-091) {#t0-3}

All three pass alone and fail under suite load, and none is root-caused. A flake fix with no
reproducer cannot be told apart from luck. So the bands below are fixed before any fix is
written ([[feedback_go_no_go_ranges_not_predrop]]). {#t0-3-lead}

### The load harness and bands (pre-registered) {#t0-3-bands}

- **Harness.** The target test runs in a clone while 3 concurrent `pytest` processes run the
  heaviest test files. "Heaviest" means the top files by `--durations` in the newest full-suite
  log on master, named in the summary. Each process is sandboxed as usual. One harness run gives
  one trial. {#t0-3-harness}
- **Reproducer found:** ≥ 3 failures in 10 trials at base, each with the row's E line. If fewer
  than 3 fail, raise the load to 5 and then 8 concurrent processes. The first level that reaches
  3 out of 10 is the reproducer. {#t0-3-band-found}
- **Fix proven:** 20 passes out of 20 on the same harness at the same level. At an unchanged 30%
  failure rate, 20 out of 20 passes happens by chance with p ≈ 0.0008. {#t0-3-band-fixed}
- **Not reproduced:** fewer than 3 failures in 10 at every level. The test gains only R3.4's
  diagnostic. The row stays `open` with status `diagnosed-loud`, with the trial counts. It does
  not count as closed, and T0.7's suite is its only further evidence. {#t0-3-band-none}

### Requirements {#t0-3-requirements}

1. **R3.1 bug-130.** `tests/test_catalog_measure.py::test_rewrite_bytes_is_the_median_of_the_runs`
   asserts `failed == 0` before it indexes `rewrite_bytes_all`. The assertion message carries the
   failed store's captured error, so a failure is never reported as a bare `KeyError`. The
   reproducer's captured error decides the fix:
   - a harness defect in `eval/catalog_maint/measure_catalogs.py` is fixed there;
   - a product defect gets its own registry row with the error. Its fix is NOT absorbed into T0,
     and T0.7 records it under [[#open-items]] O5. {#r3-1}
2. **R3.2 bug-190.** For
   `tests/test_rerank_budget_real_clients.py::test_a_cold_private_worker_is_skipped_without_spawning`,
   the reproducer records the stack of every spawn. The route follows that evidence:
   - the cold precondition is not established under load (test-side): the test waits on a
     readiness signal, as bug-184's fix `37c487f` does, not on a count;
   - a budget path spawns when it should skip (product-side): a RED test for that path, then a
     `src/` fix. {#r3-2}
3. **R3.3 bug-091.** `tests/test_watch.py::test_run_watcher_picks_up_new_file` polls until a
   deadline of at least 30 s, not one 3 s `wait`. That way it measures that the event is
   delivered, not how fast. The deadline is a named constant and bounds the test. {#r3-3}
4. **R3.4 Every flake failure explains itself.** Whatever the band, each of the three tests' failure
   messages names the observed cause: the store's error, the spawn stack, or the elapsed time
   with the watcher's state. {#r3-4}

### Acceptance {#t0-3-acceptance}

- **AC-3.1.** For each bug, the summary records: the reproducer level, the base failure count out
  of 10 with E lines, and the post-fix count out of 20, or the `not reproduced` band with all the
  counts. {#ac-3-1}
- **AC-3.2.** Mutations (each FAILS, within its deadline, never hangs):
  - M3.1: the bug-130 test indexes before its `failed` check (red on a forced failed store);
  - M3.2: the bug-190 skip path spawns (red);
  - M3.3: the watcher is never started (red at the R3.3 deadline). {#ac-3-2}

### Files {#t0-3-files}

`tests/test_catalog_measure.py`, `eval/catalog_maint/measure_catalogs.py` (only if R3.1 routes
there), `tests/test_rerank_budget_real_clients.py`, `src/refmatrix/` (only if R3.2 routes
product-side; the path is named in the summary), `tests/test_watch.py`,
`workflow/bug_registry.md` (rows 130, 190, 091; any new row R3.1 opens),
`workflow/implementation_summaries/task-t0.3-load-flakes.md`.

## T0.4 W2-a: the plan-6 remedy {#t0-4}

Source: [[bsd-plan6-deferrals-docs-benchmark-r1-e0b7df6]] (DIRTY, "may NOT flip"). R0
(2026-11-13, at `1cf3b9f`) found:
- `duckdb_view.py`, both of its tests and `RMX_READ_VIA_DUCKDB` are still present
  (`store.py:1155-1159`);
- `wrapper_paths()` is still present (`search_hooks.py:405`);
- the session-ingest "Phase A" docstring, `vectors.py:14` "for now" and `cli.py:6028` "for now"
  are still present;
- the `_op_embed` cancel return still drops `degraded` (`daemon.py:6149`);
- "Called after the SQLite commit" is still present (`store.py:1241`);
- `BANNED` is still guarded by `len(BANNED) >= 4`;
- #m-3 is closed: the test loops over all four figures;
- #s-2 is closed: task-6.4's summary exists, landed by W1-d `c40006b`. R0 checks its content;
- #m-1 is closed: `855940f` and W1-d;
- #m-5 is partly closed: the conftest checkout guard plus SkipGate. R4.8 below.

The implementer re-takes this table at the branch base (R0.1). {#t0-4-lead}

### Requirements {#t0-4-requirements}

1. **R4.1 #b-1: execute plan-6 Q1 as decided.** The decision is "Delete"
   ([[plan-6-deferrals-docs-benchmark#q1]], unamended). R0 re-checks the three facts r1 found
   false:
   - `RMX_READ_VIA_DUCKDB` has no production setter: none in the repo, `~/Library/LaunchAgents/`,
     or `.claude/hooks/hooks.env`;
   - the facade mounts SQLite only;
   - no production read reaches it.

   If all three still hold, delete:
   - `src/refmatrix/duckdb_view.py`;
   - the `_read_via_duckdb` / `_duck_view` / `_read_conn` state and the `_read()` branch in
     `store.py`;
   - `tests/test_duckdb_read_routing.py` and `tests/test_duckdb_parity.py`. R0 confirms that both
     test only the facade;
   - the stale mentions.

   If any fact has changed, stop and raise it to the lead. Q1 is a recorded decision, and the
   implementer does not re-decide it. The task-6.1 "Correction to this spec" paragraph gains a
   superseded note citing this task. {#r4-1}
2. **R4.2 #b-2: the mock registry is guarded, not swept.** First, register the six files r1 names
   and any found since. Then add a test, in the shape of `test_deferrals_clean.py`. It scans
   `tests/` for external-boundary patch targets:
   - `os.*`, `sys.stdin`, `socket.*`, `shutil.which`, `subprocess.*`;
   - `time.time` / `monotonic`, launchd.

   It asserts that each matching file has a `workflow/test_mock_registry.md` row. Its first run
   registers every file it finds, and that includes plan-8 r5 #s-9's file ([[#t0-5]]). {#r4-2}
3. **R4.3 #s-1: drop the dead wrapper plumbing.** Delete the `render_scripts(wrappers=)`
   parameter, the `wrappers=` value in `hooks.py`'s `record_flags`, and `wrapper_paths()` (once
   no caller is left). `search_hooks.py`'s module docstring is rewritten to describe runtime
   resolution, with bug-008. R0.7 applies: an existing install whose `.claude/rmx-hooks.json`
   still carries `wrappers` must read in sync under `--check`. {#r4-3}
4. **R4.4 #s-2.** R0 confirms that task-6.4's summary records the change, the run and the
   mutation that r1 asked for. If it records no test for the `memory_partition` warning branch,
   add one: an answered-error `partition_list` logs the `warning` naming root, error and the
   fallback partition. {#r4-4}
5. **R4.5 #s-3 and todo G7: phrase families, not literals.** Fix the three sites (or their
   current equivalents):
   - delete the landed claims in `session_ingest.py`;
   - `cli.py`'s `-v` docstring says "refused, falls back to rg";
   - `vectors.py` names a task or makes no promise.

   Then widen `test_deferrals_clean.py` from five literals to phrase families: `for now`,
   `in v1`, `later phase(s)`, `eventually`, `when needed`, `not yet`, and `TODO` with no plan
   id. It keeps an explicit allow-list of reviewed exceptions, each with a reason. The meta-test
   asserts the phrase set, not `len(BANNED)`. G7's five named docstrings (`ingest_gmd`, `store`,
   `duckdb_view`, `embedder`, `sync`) are re-checked, and the todo row is updated. {#r4-5}
6. **R4.6 #m-2.** `_op_embed`'s shutdown-cancel return carries `"degraded": degraded`, as the
   `skipped_empty` return already does. {#r4-6}
7. **R4.7 #m-4.** `store._log_event` says "after the catalog commit". {#r4-7}
8. **R4.8 #m-5: a degraded interpreter cannot read green.** R0 probes a run whose `PYTHONPATH` is
   assigned (`PYTHONPATH=<clone>/src`, not prepended) over a selection that reaches `lance`.
   - If the session fails loudly (the conftest guard, an import error, or SkipGate on an
     `importorskip`), #m-5 is closed by the 23.0 / SkipGate work, with the log as evidence.
   - If the session is green with a lower collected count, conftest gains a required-import check
     (the modules the suite cannot run without) that fails the session by name. {#r4-8}
9. **R4.9 todo G8.** R0 re-checks the two G8 claims ("README 0.961 has no committed artifact";
   "ARCHITECTURE.md lists 24/80 commands") against 6.2/6.3's output. A claim that still holds is
   fixed: regenerate from the CLI tree that 6.2 generates. The todo row is then updated. {#r4-9}

### Acceptance {#t0-4-acceptance}

- **AC-4.1.** After R4.1: `rmx grep -rn RMX_READ_VIA_DUCKDB src tests` is empty and the suite
  collects with no import error. R0's three-fact table is in the summary. {#ac-4-1}
- **AC-4.2.** The registry guard is RED at base, listing at least the six r1 files, and green
  after. Mutation M4.2: add `monkeypatch.setattr(os, "link", …)` to a tmp test file in the
  scanned set, and the guard goes red, naming that file. {#ac-4-2}
- **AC-4.3.** `rmx install-hooks --check` reads in sync for a fixture install carrying the old
  `wrappers` key. A rendered rewriter is byte-identical before and after R4.3. {#ac-4-3}
- **AC-4.4.** Mutations: M4.5a replaces one phrase family with `ZZZ-never-matches`, and the
  meta-test goes red, because it compares the set. M4.5b appends `# for now` to a `src/` file,
  and the guard goes red. M4.6 drops `degraded` from the cancel return, and a test of that return
  goes red. {#ac-4-4}
- **AC-4.5.** The summary carries R0's per-finding table, covering #b-1, #b-2, #s-1, #s-2, #s-3,
  #m-1 to #m-5, G7 and G8. Every row is `holds → fixed by <commit>` or `closed by <evidence>`.
  {#ac-4-5}
- **Plan-6 closes** when the T0.4 ch-bsd round is CLEAN, as its `#execution` requires
  ([[plan-6-deferrals-docs-benchmark#execution]]). {#ac-4-close}

### Files {#t0-4-files}

- Deleted: `src/refmatrix/duckdb_view.py`, `tests/test_duckdb_read_routing.py`,
  `tests/test_duckdb_parity.py`.
- Modified source: `src/refmatrix/store.py`, `src/refmatrix/search_hooks.py`,
  `src/refmatrix/hooks.py`, `src/refmatrix/daemon.py` (`_op_embed`),
  `src/refmatrix/session_ingest.py`, `src/refmatrix/cli.py`, `src/refmatrix/vectors.py`.
- Tests: `tests/test_deferrals_clean.py`, a new `tests/test_mock_registry_coverage.py`, and
  `tests/conftest.py` (only if R4.8 routes there).
- Docs and registries: `workflow/test_mock_registry.md`,
  `workflow/plans/plan-6-deferrals-docs-benchmark-tasks/task-6.1-plan-6-deferrals-docs-benchmark.md`
  (the superseded note), `docs/architecture/todo.md` (G7, G8), `docs/ARCHITECTURE.md` (if G8
  holds).
- `workflow/implementation_summaries/task-t0.4-plan6-remedy.md`.

## T0.5 W2-b: the plan-8 remedy {#t0-5}

Source: [[bsd-plan8-9-10-r5-e0b7df6]], whose verdict on plan-8 is "NO" for #b-2 and #b-3: those
are its own `#execution` and `#proposed-approach` gates. #b-1 is plan-10's (T3, not here). #s-5,
#s-6 (9.2/9.3) and #m-11 are plan-9's, and they closed with 21.1 (Ce-8). R0 at `1cf3b9f`
found:
- `brief.parse_gmd` and the dead `_parse_evidence(…, ids_by_name)` are still present
  (`brief.py:654`, `:683`);
- 8.3's summary now exists (W1-d), so #s-6's plan-8 half is closed.

{#t0-5-lead}

### Requirements {#t0-5-requirements}

1. **R5.1 #b-2: `corroborated` is reached through the wiring.** The `test_brief_detectors`
   `store` fixture builds a compile plan (`_fake_plan()` already exists in
   `tests/test_plan7_10_remedy_r4.py`) and passes `plan=` to `compile_briefs`. The
   "every class" test then asserts all four classes, `corroborated` and `singleton` included.
   {#r5-1}
2. **R5.2 #b-3: the second direction is either built or deleted, as [[#open-items]] O2 ratifies.**
   - **(a) delete:** remove `parse_gmd` and `_parse_evidence`. Amend
     [[plan-8-derived-coverage-notes#proposed-approach]] to claim one direction, with a dated
     note citing this task.
   - **(b) expose:** `rmx memory brief --from <doc>` as a verb action, with an MCP parameter and a
     parity row, plus an `--out` path so the index really is "on disk".

   Either way, `names=` / `ids_by_name` is dropped. {#r5-2}
3. **R5.3 #s-4: `brief` is verb-first.** The compile plan is built inside the verb or op when the
   caller asks for compile-backed classes. The way it asks is the implementer's choice: an action
   or a `do_compile` flag. The CLI `--compile` becomes a pass-through, and an MCP caller reaches
   all four detectors without building a plan by hand. The verb parity test pairs the new
   parameter. {#r5-3}
4. **R5.4 #s-9.** The four doubles in `tests/test_plan7_10_remedy_r4.py:177-184` have registry
   rows, or [[#t0-4]]'s guard already registered them; R0 checks which. The `cli._store`
   replacement's row says, in `Why kept`, that the test cannot see a writer opened by
   `memory compile --apply`. {#r5-4}
5. **R5.5 #m-10.** `tests/test_brief_surfaces.py` increments `compared` only where an assertion
   runs. `classes` is compared as a declared shape difference (the `SHAPE_DIFFERENCES` mechanism
   in `test_verb_parity.py`). {#r5-5}
6. **R5.6 The plan-8 deferral rows have a live owner before plan-8 closes.**
   `workflow/deferral_registry.md` rows 43 (answer-usefulness) and 44 (`brief/stale`) say
   "Owner: plan 8". Their host in the 2026-10-19 fold was W3-b, built on 19.2/21.1 usage records,
   and D-Q3 froze 19.2. Plan-8 flips only after those rows carry the owner [[#open-items]] O3
   names. T0 does not edit the deferral registry, which spec-t56 owns in this wave. {#r5-6}

### Acceptance {#t0-5-acceptance}

- **AC-5.1.** Mutations C1 to C4 from r5, re-run on the remedied tests: replace each detector's
  call in `compile_briefs` with an empty result. Each goes **red**. At base, C1 is green: that is
  the RED record. {#ac-5-1}
- **AC-5.2.** Through the MCP surface, on a throwaway store with a seeded memory set,
  `rmx_memory` brief returns `corroborated` and `singleton` with no `classes_not_run` entry for
  either. At base it returns both under `classes_not_run`. {#ac-5-2}
- **AC-5.3.** O2 (a): `rmx grep -rn "parse_gmd" src/refmatrix/brief.py` is empty, and plan-8's
  note is in place. O2 (b): a round-trip test through the CLI and MCP recovers every brief with
  its evidence ids from a rendered index. {#ac-5-3}
- **AC-5.4.** M7 from r5 (CLI `--class` defaults to `("contradicted",)`) turns the parity gate
  red. {#ac-5-4}
- **AC-5.5.** The verb parity test is green. Because the MCP tool changes, a deploy and `/mcp`
  reconnect are noted in the summary's release line. {#ac-5-5}
- **Plan-8 closes** when the T0.5 ch-bsd round is CLEAN and R5.6 holds
  ([[plan-8-derived-coverage-notes#execution]]). {#ac-5-close}

### Files {#t0-5-files}

- Source: `src/refmatrix/brief.py`, `src/refmatrix/verbs.py`, `src/refmatrix/cli.py`,
  `src/refmatrix/mcp.py`.
- Tests: `tests/test_brief_detectors.py`, `tests/test_brief_surfaces.py`,
  `tests/test_verb_parity.py` (pairing).
- Docs and registries: `workflow/test_mock_registry.md`,
  `workflow/plans/plan-8-derived-coverage-notes.md` (O2 a's note), and `docs/` CLI reference if
  O2 b adds a flag.
- `workflow/implementation_summaries/task-t0.5-plan8-remedy.md`.

## T0.6 W2-c: the plan-7 dense/fused re-run {#t0-6}

Task 7.4 shipped the symbolic rows only (`status: complete (symbolic only; dense blocked on
bug-030)`). bug-030 was fixed in `464485d` (2026-09-16). Nothing has shown that the embed now
completes on the LongMemEval store. [[longmemeval-report#embed]] still says the re-run is W2-c.
The persisted store is at `/Volumes/littlebig/longmemeval/.refmatrix` (present 2026-11-13). It
was built by 0.69.1. {#t0-6-lead}

### Requirements {#t0-6-requirements}

1. **R6.1 The production path, the deployed build.** The run uses the deploy `rmx` (`~/bin/rmx`,
   which `rmx version -v` proves) through `eval/production/longmemeval/ingest.py --skip init
   --skip ingest-gmd`, then `run.py`, with `REFMATRIX_ROOT` pinned to the eval store
   (`paths.rmx_env`). No adapter and no dev-venv `rmx` are used
   ([[feedback_measure_the_path_users_run]]). Models load cache-only. {#r6-1}
2. **R6.2 The store opens or is rebuilt, and the run says which.** R0 opens the 0.69.1 store with
   the deploy build, read-only first (`rmx status`).
   - If it opens and migrates cleanly, the embed resumes on it.
   - If it does not, the store is rebuilt from `corpus/` with the harness (the 4h23m ingest).

   REPORT.md's setup table records which path was taken and the build's version. {#r6-2}
3. **R6.3 Same knobs as the symbolic rows.** `recall`, `recall-fuse`, `recall-rr` and
   `recall-fuse-rr` run on the same 120 questions (20 per type, seed 42), at `--depth 50` and
   `--at 1,5,10,20`, in both modes, with ceilings printed. A dense row is labelled saturated
   exactly as the symbolic rows are when it hits its ceiling ([[longmemeval-report#next]] item 1:
   the depth-200 re-run is not part of W2-c). {#r6-3}
4. **R6.4 Every number carries its provenance** (task 7.4 `#requirements`, plan-7 `#execution`):
   the harness command, corpus size, scoring mode, rmx version and date. If the dense rows'
   version differs from the symbolic rows' 0.69.1, the table says so. [[#open-items]] O3 decides
   whether the symbolic rows are re-taken on the same build. {#r6-4}
5. **R6.5 Artifacts and citations.** Results JSON goes under
   `eval/production/longmemeval/results/`. README and `docs/PERFORMANCE.md` cite the committed
   path. `tests/test_eval_artifact_cited.py` covers every new figure it cites, compared over the
   full table and not one row (plan-6 r1 #m-3's lesson). REPORT.md's `#embed` section becomes the
   result. Its `#next` item 4 is closed. {#r6-5}
6. **R6.6 A failure is a result.** If the embed fails again, its error, timing and the worker
   state go in REPORT.md and a registry row. The dense rows stay absent, and plan-7 does not
   close. {#r6-6}

### Acceptance {#t0-6-acceptance}

- **AC-6.1.** REPORT.md's `#restricted` and `#union` tables hold all four dense/fused methods,
  each with a ceiling column. The setup table names the build, the store path taken (R6.2) and
  the embed wall time. {#ac-6-1}
- **AC-6.2.** `tests/test_eval_artifact_cited.py` is RED before the results are committed (README
  or PERFORMANCE cites a figure with no artifact) and green after. Mutation M6.1: edit one cited
  dense figure in README, and the test goes red. {#ac-6-2}
- **AC-6.3.** task-7.4's frontmatter status drops "(symbolic only …)". Plan-7 closes when the T0.6
  ch-bsd round is CLEAN and its deferral rows 40, 41, 42 and 46 carry the plan-20-evals owner
  that L33 assigns (the lead's G26). {#ac-6-3}

### Files {#t0-6-files}

`eval/production/longmemeval/REPORT.md`, `eval/production/longmemeval/results/*.json`,
`README.md`, `docs/PERFORMANCE.md`, `tests/test_eval_artifact_cited.py`,
`workflow/plans/plan-7-longmemeval-tasks/task-7.4-plan-7-longmemeval.md`,
`workflow/implementation_summaries/task-t0.6-plan7-dense-rerun.md`. The data stays on
`/Volumes/littlebig/longmemeval`, off every watched tree ([[feedback_generated_data_off_watched_tree]]).

## T0.7 W1-e: the plan-15 r13 remedy and the clean full suite {#t0-7}

Source: [[bsd-r1-remedy-r13-dcf7115]] (DIRTY 3: 1 SKETCHY, 2 MEH), plus plan-15's own gate: it
"returns to `completed` only after a full suite whose log describes the committed tree"
([[plan-15-derive-impact-tracking#root]]). R0 at `1cf3b9f` found:
- `test_the_startup_warmup_really_loads` still calls the helper (`tests/test_rerank_budget_real_clients.py:839`);
- `REFILL_TIMEOUT_S` is still present (`subproc.py:153`, `:435`);
- r13 #m-1's warning text no longer greps.

{#t0-7-lead}

### Requirements {#t0-7-requirements}

1. **R7.1 r13 #s-1: pin the route, not the helper.** A test drives `_start_embedder_warmup` on a
   `Daemon` with a stub-argv private worker (rerank enabled, `RMX_NO_EMBED_WARMUP` unset,
   `_embedder` stubbed). It asserts that the "reranker warm" log fires only once
   `wc.info(nowait=True)` is populated. A second test pins the refill bound: its stub's `info`
   sleeps longer than a patched `REFILL_TIMEOUT_S` and shorter than the op timeout. {#r7-1}
2. **R7.2 r13 #m-1.** R0 finds the writer-branch warning's current text and the branches that
   reach it: newer partition, no snapshot at boot, or snapshot open failed. Each cause is worded
   as itself, or `_read_with_fallback` passes the reason out. If the branch no longer exists, it
   is closed with the commit that removed it. {#r7-2}
3. **R7.3 r13 #m-2.** R0 checks the registries.
   - **Bug registry:** a row for the unbudgeted adoption leak, fixed in `4fb5000`, if none exists.
   - **Mock registry:** the `_FakePrivate` row graduates, or says why not. The
     `rerank_available` fake is registered for its file. {#r7-3}
4. **R7.4 The clean full suite (plan-15's gate).** This is one run of the full suite, in the
   **main tree** (`~/claude_tools/refmatrix`) at a committed `master` sha that holds T0.1 to T0.6
   and T0.7's own merge. Preconditions:
   - `git status --porcelain` lists nothing under `src/ tests/ docs/ workflow/ eval/ CLAUDE.md
     .claude/PROJECT_PROFILE.md`, both at start and at end;
   - HEAD is unchanged across the run;
   - the lead is told before the run starts that the main tree is under a suite run (for about
     45 min);
   - no branch switch: the main tree is shared ([[feedback_shared_tree_no_branch_switch]]).

   **Clean** means all of:
   - pytest exit code 0;
   - 0 failed and 0 errors;
   - no SkipGate line;
   - collected = passed + pinned skips (0 in the main tree).

   The log and a `.sha` file are committed as `workflow/review-output/t0/clean-suite-<sha>.{log,sha}`.
   {#r7-4}
5. **R7.5 The clone twin (T0's trust proof).** The same sha runs the full suite in a littlebig
   clone. It exits 0, and its only skips are the pinned clone-only set, each reported as pinned.
   This is where releases run, so it is the run bug-215 and bug-155 were invisible to. {#r7-5}
6. **R7.6 A failure in R7.4 or R7.5 does not get explained away.** Every failing E line is matched
   to a row by E line (R0.2).
   - A match to an open T0 row means that sub-task's fix did not hold: it reopens.
   - A failure with no matching row is logged as a new row, and the run stops there. The
     handling is [[#open-items]] O5.

   R7.4 is re-run only after the cause is fixed. {#r7-6}
7. **R7.7 Plan closures.** Plan-15 flips to `completed` when R7.4 is clean and the T0.7 ch-bsd round
   is CLEAN or MEH-only. Plans 6, 7 and 8 flip per [[#ac-4-close]], [[#ac-6-3]] and
   [[#ac-5-close]]. Each flip edits the plan's frontmatter and its body status line, which must
   agree (Cc-9, CD-9). {#r7-7}

### Acceptance {#t0-7-acceptance}

- **AC-7.1.** Mutations L6 (`_start_embedder_warmup` calls `self._reranker()` without
  `load=True`) and L1 (the refill bound is dropped) each go **red**. At base both survive, and
  r13's table is the RED record. {#ac-7-1}
- **AC-7.2.** The R7.2 wording test covers every cause branch R0 found. The R7.3 registry rows
  exist. {#ac-7-2}
- **AC-7.3.** The committed R7.4 log shows exit 0, with the collected count equal to passed. The
  committed R7.5 log shows exit 0, with only pinned skips. The summary quotes both exit codes and
  both counts. {#ac-7-3}
- **AC-7.4.** At least one previously failing test from each of bug-170, 168 and 127 appears as
  `PASSED` in the R7.4 log. This is T0.2's main-tree proof, read by nodeid from a
  `-rA`-style report or the junit XML. {#ac-7-4}

### Files {#t0-7-files}

`tests/test_rerank_budget_real_clients.py`, `src/refmatrix/daemon.py` (only R7.2's wording),
`workflow/bug_registry.md`, `workflow/test_mock_registry.md`,
`workflow/review-output/t0/clean-suite-<sha>.{log,sha}`, the clone-twin log, and the plan
frontmatter and body status lines for plans 6, 7, 8 and 15. The summaries are
`workflow/implementation_summaries/task-t0.7-plan15-close-clean-suite.md` and
`workflow/implementation_summaries/task-t0-suite-trust-sweep.md` (the T0 roll-up: each sub-task,
its rows, its exit codes).

## Merge order {#merge-order}

queue item 1 (bug-212, bug-216, 25.1 rev 7) → **T0.1** → T0.2 ∥ T0.3 ∥ T0.4 ∥ T0.6 → T0.5
(after T0.4) → **T0.7** (last; R7.4 runs on the sha after its merge). T0 runs alongside 26.5,
and 26.5's merges may land between T0 merges. R7.4 runs on whatever `master` holds at that point
and is clean only if 26.5's tests are too. Each sub-task merges `--no-ff` from its own branch. T0
needs no hook install window (R0.7). T0.5 changes an MCP tool, so it rides the next release with
a `/mcp` reconnect. {#merge-order-body}

## Open items for the lead (no D-Q or L-row settles them) {#open-items}

- **O1: bug-196 blocks R7.4.** Its two RED tests (`test_ac6_frozen_fixture_prints_the_exact_counts`
  and `test_ac6_cli_log_recalls_are_split_per_channel`) failed in the 0.82.0 release suite. L8 puts
  bug-196 on the T3 backlog, outside the goal, so W1-e's "clean full suite" cannot pass inside the
  goal. Options:
  - **(a) bug-196 joins T0 as T0.8** (recommended). It is a `src/` fix in `telemetry.py`
    `agent_usage_report`, with its RED tests already committed and the fix named in its row.
  - (b) W1-e moves to the backlog with bug-196, and plan-15 stays `in-progress`.
  - (c) R7.4 admits bug-196's two E lines as named exceptions. This contradicts "clean" and
    CLAUDE.md `#system-dependent-tests`.

  {#o1}
- **O2: plan-8 #b-3, delete or expose `brief.parse_gmd`.**
  - **(a) delete** (recommended). This is plan-6 Q1's recorded rule for code no production path
    reaches ("an env-flag facade nobody sets is a second path"). Plan-8 records no consumer of
    the reverse direction.
  - (b) expose it as `rmx memory brief --from <doc>`, with `--out`.

  {#o2}
- **O3: the owner of plan-8's deferral rows 43 and 44 (and whether T0.6 re-takes the symbolic
  rows).**
  - Rows 43/44: **(a) re-own them to T3, held with 19.2 under D-Q3** (recommended: their
    dependency is 19.2/21.1 usage records). (b) Plan-8 stays `in-progress` until W3-b. Either
    way, spec-t56 or the lead edits the registry, not T0.
  - T0.6's symbolic rows: **(a) re-take `context` and `scan` on the same build in the same run**
    (recommended: one build per table, and the symbolic re-run is cheap next to the embed).
    (b) Keep the 0.69.1 rows, labelled by version.

  {#o3}
- **O4: master fails its own repo-scope GMD gate today (lead-owned files).** At `1cf3b9f` the
  lint over the gate's scope gives:
  - 5 `no-gmd-version` errors: `workflow/review-output/pop-2026-11-13/contra-{a..e}.md` have no
    frontmatter;
  - 1 `dangling-doc` error, `[[agent-brief-bsd-pop-r1]]` in
    `workflow/bullshit/2026-11-13-2215-pop-review-r1-c56782f.md`. The target brief
    `workflow/agents/bsd-pop-r1.md` exists only untracked in the main tree.

  `test_the_repo_scope_is_clean_under_the_stricter_gate` fails on these at any checkout of
  master. Recommended: the lead fixes them in G27 bookkeeping (frontmatter or a `not-gmd`
  opt-out line on the five; commit the brief) before T0.1's AC-1.4 runs. {#o4}
- **O5: a failure R7.4 finds that no T0 row owns.** P5 rule 2 sends a new bug to its owning
  task's track. P5 rule 4 makes any queue insertion a user decision.
  - **(a) Recommended:** log the row, stop T0's closure there (plan-15 stays `in-progress`), and
    raise it to the lead. The goal continues with its other items.
  - (b) Fold the fix into T0 without a spec. The goal cannot do this unattended
    (CLAUDE.md `#plans-pre-written`).

  {#o5}
- **Also for the lead (not a choice):** bug-170's fix column also proposes a standing rule: "the
  release gate runs the dev-tree-only tests in the owning checkout". T0 meets it once, through
  R7.4. The standing rule has no home document, since there is no release checklist in
  `workflow/`. Recommended: one line in the POP release section during the P1 rewrite. {#o-release-rule}

## Q8 note {#q8-b}

No T0 line changes under Q8 a, b or c. T0 touches no ingest scope, no bridge and no save-state
path. Lint scope (T0.1) is not ingest scope. One effect under Q8 b: save-states would leave the
store, so live `brief` counts would shift. No T0 acceptance criterion asserts a live count.
{#q8-b-body}

## Definition of done {#done}

- Every sub-task has: R0's table, its RED run, its GREEN run, and its mutations, each run quoted
  with its exit code (R0.3). Every sub-task has its own implementation summary, named in its Files
  section, and the roll-up `workflow/implementation_summaries/task-t0-suite-trust-sweep.md`
  exists.
- Rows 215, 170, 168, 155, 127, 130, 190 and 091 read `fixed <sha>` with evidence, or (T0.3 only)
  `open / diagnosed-loud` with the band counts.
- R7.4 and R7.5 are committed and clean.
- Plans 6, 7, 8 and 15 are `completed` in frontmatter and body, or still `in-progress` with the
  named open item that holds each.
- Every sub-task's ch-bsd round is CLEAN, or MEH-only where its plan allows.
- GMD lint shows 0 errors on every touched `.md`.
- Each branch is merged `--no-ff` to `master`.
