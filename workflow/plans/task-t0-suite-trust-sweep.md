---
gmd: "0.1"
id: task-t0-suite-trust-sweep
title: "Task T0: the suite-trust sweep: nine instrument bugs and the plan-6/7/8/15 closure gates (W2-a, W2-b, W2-c, W1-e)"
tags: [task, t0, tests, instrument, skipgate, flaky, plan-6, plan-7, plan-8, plan-15, bug-215, bug-170, bug-168, bug-155, bug-127, bug-130, bug-190, bug-091, bug-196]
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
> [[plan-review-2026-11-13#goal-horizon]]). The lead ruled on the five choices the first draft
> raised, and on the r1 spec review's findings; [[#rulings]] and [[#rev-r1]] record them.
> Depends on: queue item 1 merged to `master` (bug-212, bug-216, 25.1 rev 7). Their branches
> edit `src/refmatrix/store.py` and `src/refmatrix/hooks.py`, which T0.4 also edits. Every T0
> branch starts from the `master` sha that holds those merges.
> Closes: bug-215, 170, 168, 155, 127, 130, 190, 091 and 196 ([[#ruling-o1]]).
> It also closes the recorded closure gates of plans 6, 7, 8 and 15 (D-Q6).
> User gates: none. No step opens a live store, starts a fleet daemon, or needs a hook install
> window ([[#rules]] R0.7).

rel: derives-from -> [[plan-review-2026-11-13#d-q6]]
rel: derives-from -> [[plan-review-2026-11-13#f8]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: part-of -> [[plan-review-2026-11-13#queue-body]]
rel: derives-from -> [[plan-review-2026-10-14#t11-folded-waves]]
rel: derives-from -> [[bug_registry]] {bugs: "bug-215, bug-170, bug-168, bug-155, bug-127, bug-130, bug-190, bug-091, bug-196"}
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
- bug-196: 2 (now [[#t0-8]], per [[#ruling-o1]]).

In a littlebig clone every run exits 1 on a skip the gate cannot place (bug-215), and the
repo-scope GMD gate fails on about 1,080 dangling ids, for two reasons (bug-155,
[[#t0-1-bug155-cause]]). Three tests fail only under load (bug-130,
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
| [[#t0-1]] Skip gate and checkout identity | bug-215, bug-155 | `task-t0.1-skip-gate-checkout-identity` | first |
| [[#t0-2]] Dev-tree-only tests stop reading the real HOME and cwd ancestry | bug-170, bug-168, bug-127 | `task-t0.2-dev-tree-test-isolation` | any order after T0.1 |
| [[#t0-3]] Load-dependent flakes | bug-130, bug-190, bug-091 | `task-t0.3-load-flakes` | any order after T0.1 |
| [[#t0-4]] W2-a: the plan-6 remedy | plan-6 r1 #b-1, #b-2, #s-1, #s-2, #s-3, #m-1..#m-5; todo G7/G8 | `task-t0.4-plan6-remedy` | any order after T0.1 |
| [[#t0-5]] W2-b: the plan-8 remedy | plan-8 r5 #b-2, #b-3, #s-4, #m-10; #s-9 and #s-6's 8.3 half confirmed closed | `task-t0.5-plan8-remedy` | after T0.4 (both edit `cli.py`; T0.4's registry lint lands first) |
| [[#t0-6]] W2-c: the plan-7 dense/fused re-run | task 7.4's missing rows; REPORT.md completed | `task-t0.6-plan7-dense-rerun` | any time after T0.1; long-running |
| [[#t0-8]] bug-196: the cli.log recall leg split per channel | bug-196 ([[#ruling-o1]]) | `task-t0.8-bug196-recall-channels` | any order after T0.1 |
| [[#t0-7]] W1-e: plan-15 r13 remedy + the clean full suite | plan-15 r13 #s-1, #m-1, #m-2; the clean-suite gate for plans 15, and the trust proof for T0 | `task-t0.7-plan15-close-clean-suite` | **last** |

T0.1 goes first because until it lands, every clone run exits 1 and no sub-task can quote a
clean exit code. T0.2 to T0.6 and T0.8 are independent of each other, apart from the T0.4 → T0.5
order.
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

**bug-215.** This sweep tracks it as one item. It is the defect the bug-212 notes call the
SkipGate UNPINNED skip (ch-bsd bug-212 r1 #m-4, carried as flag 8 of GREEN r2), and the plan
review's separate "SkipGate UNPINNED row" is the same defect (lead ruling, 2026-11-13). Closing
bug-215 closes it. {#t0-1-identity}

**bug-155 has two causes (probe 2026-11-13; second cause found by the r1 spec review).**
1. **Namespace.** `tools/gmd/lint.py` `project_name()` takes the repo directory's basename as the
   id namespace when `.gmd/config.yml` has no `project:` key. The ADRs carry ids like
   `refmatrix/adr-0000-adr-overview`, so in any checkout not named `refmatrix`,
   `[[adr-0000-adr-overview]]` does not resolve. Probe (two `git archive` copies of `1cf3b9f`,
   main memory dir supplied): a dir named `refmatrix` 1 `dangling-doc`; `refmatrix-clone` 33;
   `refmatrix-clone` + `project: refmatrix` 1. The remaining 1 was `[[agent-brief-bsd-pop-r1]]`,
   fixed by the lead at `35e1e0d` ([[#ruling-o4]]).
2. **Memory dir.** A clone has no memory dir under its own slug.
   - `scripts/lint-gmd.sh` adds `$HOME/.claude/projects/<slug>/memory` only if it exists.
   - `test_the_repo_scope_is_clean_under_the_stricter_gate` copies that same slug's dir into a
     decoy HOME, and copies nothing when it is missing.
   - No `~/.claude/projects/-Volumes-littlebig-refmatrix*/memory` exists. Over the script's scope
     in this clone with no memory dir, lint gives 1,084 errors (1,079 `dangling-doc`): every
     memory-id ref dangles. `project: refmatrix` alone removes only 32 of them.

   The fix is [[#ruling-o6]]: fall back to the memory dir of the clone's **origin** path. Every
   littlebig clone's `origin` is `/Users/tholley/claude_tools/refmatrix`.

{#t0-1-bug155-cause}

**The pinned skips and their actual reasons (read at `1cf3b9f`).** `_CLONE_ONLY_SKIPS`
(`tests/conftest.py`) pins 19 nodeids: 18 under `_CLONE_NO_VENV` and 1 under `_CLONE_HOOKS`. The
pinned strings ("clone-only: the dev venv rmx (<checkout>/.venv-eval/bin/rmx) is not built",
"clone-only: the installed hooks belong to another checkout of this commit") match none of the
reasons the tests actually skip with. Those are:

| file | pinned nodeids | the test's own `reason=` (and its condition) |
|---|---|---|
| `tests/test_brief_real_daemon.py` | 4 (module `pytestmark`) | `"dev rmx not built"` (`not RMX.exists()`) |
| `tests/test_grep_argv_order_e2e.py` | 3 | `"dev venv rmx not built"` (`not RMX.exists()`) |
| `tests/test_grep_argv_order_e2e.py` | 1 (`test_the_tool_itself_is_the_one_that_scrambles`) | `"needs rmx + rg"` (`not (RMX.exists() and HAS_RG)`) |
| `tests/test_grep_count_rows_e2e.py` | 7 (module `pytestmark`) | `"dev venv rmx or /usr/bin/grep missing"` |
| `tests/test_grep_evidence_verified.py` | 1 | `"dev venv rmx not built"` |
| `tests/test_grep_learning_replay.py` | 1 | `"needs the dev venv's rmx console script"` |
| `tests/test_grep_no_flag_bundle.py` | 1 | `"dev venv rmx not built"` |
| `tests/test_repo_hooks_in_sync.py` | 1 | `"hooks belong to another checkout of this commit"` (`_OWNER != REPO`); its other skip, `"not an rmx-hooks-managed checkout"`, is NOT pinned |

{#t0-1-skip-reasons}

### Requirements {#t0-1-requirements}

1. **R1.1 The allowed-skip set follows each skip's condition, not one directory test.**
   `tests/conftest.py` builds `ALLOWED_SKIPS` per entry:
   - the 18 dev-venv entries are allowed only when `<checkout>/.venv-eval/bin/rmx` does not exist;
   - the hooks entry is allowed only when the installed hooks belong to another checkout,
     decided the way the test itself decides it (`_OWNER is not None and _OWNER != REPO`).

   A `.venv-eval` that is a symlink resolving outside the checkout satisfies neither condition by
   itself. Today one `(_REPO / ".venv-eval").is_dir()` test switches the whole set (`conftest.py:286`).
   {#r1-1}
2. **R1.2 The gate matches the reason exactly.** Each pinned entry's value is the test's own
   `reason=` string, verbatim from [[#t0-1-skip-reasons]]. The two `_CLONE_*` description
   strings stop being match keys (they may stay as comments). `SkipGate` treats a skip as pinned
   only when its nodeid is allowed and its reason, after stripping pytest's `Skipped: ` prefix,
   is **equal** to the pinned value. A pinned nodeid that skips for any other reason is reported
   `SKIPPED-UNPINNED`, with both reasons. A test whose `reason=` text changes must update its
   pin in the same commit. {#r1-2}
3. **R1.3 The GMD id namespace does not depend on the checkout's directory name.**
   `.gmd/config.yml` declares `project: refmatrix`. `tools/gmd/lint.py` is not changed: the config
   key already exists for this purpose (`project_name()` docstring). {#r1-3}
4. **R1.4 A clone lints against its origin's memory dir ([[#ruling-o6]]).**
   - `scripts/lint-gmd.sh` resolves the memory dir as today, from the checkout's own slug. If that
     dir does not exist, it reads `git remote get-url origin`. If that is a local directory, it
     uses that path's slug (`tr '/_' '--'`, as now). If that dir exists, it adds it to the lint
     scope and to the parity `--memory-dir`.
   - Whenever the fallback is taken, the script prints one line to **stderr** naming the
     checkout's own slug, the origin path, and the memory dir used.
   - If neither dir exists (no origin, a non-local origin, or no dir under the origin's slug),
     it prints one stderr line saying so and that memory-id refs will surface as `dangling-doc`.
   - The resolution lives in ONE place that both the script and the test use (a
     `--print-memdir` mode of the script, or a helper both call). The test copies exactly the
     dir the resolver names into its decoy HOME, under the slug the resolver will look up there.
     It never hands the child the real `HOME`. {#r1-4}
5. **R1.5 Exit codes are part of every recorded run.** `workflow/TDD_GOVERNANCE.md`
   `#rules` gains one bullet: "A recorded run (RED, GREEN, suite) quotes the pytest exit code and
   the collected count; counts without the exit code are not a record." This is the second half
   of bug-215's fix column. {#r1-5}

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
  and the output names both reasons. A pinned nodeid that skips with its exact reason (with the
  `Skipped: ` prefix pytest adds) passes. {#ac-1-3}
- **AC-1.4 (no-venv clone pins all 19).** In a clone with NO `.venv-eval`, a run of the seven
  files in [[#t0-1-skip-reasons]] exits **0**, with 19 skips, every one reported pinned and none
  `SKIPPED-UNPINNED`. (In the main tree, `test_the_tool_itself_is_the_one_that_scrambles` would
  also skip if `rg` were missing; there its venv condition is false, so that skip stays unpinned
  and fails the session, which is correct.) {#ac-1-4}
- **AC-1.5 (bug-155, clone).** In the T0.1 clone (not named `refmatrix`, no memory dir under its
  own slug, origin = the main tree):
  - `test_the_repo_scope_is_clean_under_the_stricter_gate` is RED at base. Its E line holds the
    32 namespace errors plus the memory-id `dangling-doc` errors (about 1,046), which R0.2 quotes
    by count and first lines.
  - After R1.3 and R1.4, `./scripts/lint-gmd.sh` prints the fallback stderr line, and its error
    count **equals the main tree's at the same sha**. The base holds `35e1e0d`, where the
    main-tree gate is green ([[#ruling-o4]]), so both are 0 and the test passes.
  - Any other E line is a new finding, not an assumed residue.

  {#ac-1-5}
- **AC-1.6 (fallback is loud and bounded).** In a fixture checkout whose origin is not a local
  path, the script prints the "no memory dir" stderr line, and the memory-id refs surface as
  `dangling-doc` (exit 1). In a fixture whose own slug has a memory dir, no fallback line is
  printed. {#ac-1-6}
- **Mutations (each FAILS):**
  - M1.1: restore the single `is_dir()` switch (AC-1.1 and AC-1.2 red);
  - M1.2: match by nodeid only, or by substring (AC-1.3 red);
  - M1.3: delete `project:` from `.gmd/config.yml` (AC-1.5 red with the 32 namespace errors);
  - M1.4: drop the origin fallback (AC-1.5 red with the memory-id errors);
  - M1.5: silence the fallback's stderr line (AC-1.6 red). {#t0-1-mutations}

### Files {#t0-1-files}

`tests/conftest.py`, `tests/sandbox_site/rmx_sandbox.py` (`SkipGate`), a new
`tests/test_t0_skip_gate.py`, the seven test files in [[#t0-1-skip-reasons]] (only if a
`reason=` must change; the pins follow the tests, not the reverse), `.gmd/config.yml`,
`scripts/lint-gmd.sh`, `tests/test_gmd_lint_requires_version.py`, a new
`tests/test_lint_gmd_memdir_fallback.py`, `workflow/TDD_GOVERNANCE.md`,
`workflow/bug_registry.md` (rows bug-215, bug-155),
`workflow/implementation_summaries/task-t0.1-skip-gate-checkout-identity.md`.

## T0.2 Dev-tree-only tests stop reading the real HOME and cwd ancestry (bug-170, bug-168, bug-127) {#t0-2}

These three fail in the main tree, and each behaves differently in a clone:
- bug-170's test skips in a clone (the hooks belong to the main checkout);
- bug-168's rewriter tests **pass** in a clone, which has no `$HOME` ancestor (24/24, bug-168 row);
- bug-127's test **runs and fails** in a clone with a symlinked `.venv-eval` (2/2 runs, bug-168
  row), and skips only in a clone without one.

That is why no release suite run in a clone saw all three (bug-170's row: "the same blind spot
as bug-168"). After T0.1 merges, every symlinked-clone full run hits bug-127 until T0.2 merges
([[#merge-order]]). They are proven post-merge, in the main tree, by T0.7's run. Pre-merge, each
AC below names how the clone reproduces the main-tree condition. {#t0-2-lead}

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
  real content. In the main tree (T0.7), the test passes under [[#r7-4]]'s hook precondition: the
  deployed `rmx install-hooks --check` reads in sync, which proves the installed hooks match the
  DEPLOYED build's render. The test itself then proves the installed hooks also match this
  checkout's render. The sandbox touches-log for the test shows no write outside the sandbox.
  {#ac-2-1}
- **AC-2.2 (bug-168).** In the clone, run the rewriter tests with a tmp cwd whose ancestor holds
  `.refmatrix/learn.off`. At base this reproduces the main-tree E line
  `AssertionError: ('grep -rn pat src/', '')`. After the fix, 24/24 pass. The new stand-down test
  passes. {#ac-2-2}
- **AC-2.3 (bug-127).** In the T0.2 clone with a symlinked `.venv-eval`, the test is RED at base
  with the `Conflicting lock` E line and passes after the fix. It passes again in the main tree
  inside T0.7's run. No `Conflicting lock` appears in either log. {#ac-2-3}
- **Mutations (each FAILS):**
  - M2.1: the rewriter ignores `learn.off` (stand-down test red);
  - M2.2: the hooks comparison skips the scripts (AC-2.1's byte-change case goes green, so the
    test is red);
  - M2.3: the library stops raising on an unknown class (bug-127 test red);
  - M2.4: re-add the direct `Store()` opener while the daemon runs (`Conflicting lock` returns,
    bug-127 test red). {#t0-2-mutations}

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

- **R0 builds the harness.** No committed full-suite log carries durations (the 0.82.0 log has
  none). So T0.3's first step is one full-suite run in its clone with `--durations=25`, logged
  per R0.3. Its 25 slowest files, by summed duration, are written into the summary before trial 1
  and do not change afterwards. {#t0-3-r0}
- **Harness.** The target test runs in the clone while 3 concurrent `pytest` processes run those
  files. Each process is sandboxed as usual. One harness run gives one trial. {#t0-3-harness}
- **Reproducer found:** ≥ 3 failures in 10 trials at base, each with the row's E line. If fewer
  than 3 fail, raise the load to 5 and then 8 concurrent processes. The first level that reaches
  3 out of 10 is the reproducer. {#t0-3-band-found}
- **Fix proven:** **45 consecutive passes** on the same harness at the same level. A 3/10
  reproducer's 95% Clopper-Pearson lower bound on the failure rate is 0.067. At that rate,
  0.933^45 ≈ 0.044 < 0.05, so 45 straight passes is unlikely by luck even at the weakest rate
  the reproducer admits. Any failure in the 45 means the fix did not hold. {#t0-3-band-fixed}
- **Not reproduced:** fewer than 3 failures in 10 at every level. The test gains only R3.4's
  diagnostic. The row stays `open` with status `diagnosed-loud`, with the trial counts. It does
  not count as closed. In T0.7's suite it is handled by [[#ruling-o7]]. {#t0-3-band-none}
- **Bounded by count.** Per bug, at most 30 base trials (3 levels × 10) and 45 post-fix trials,
  plus the one R0 durations run. The summary records each trial's wall time. {#t0-3-bound}
- **Live-socket exposure.** Concurrent suites multiply the suite's reach to live rmx sockets
  (bug-088, deferred by the user). T0.3 adds no mitigation. It records the conftest live-socket
  recorder's count for the R0 run and for one trial at each load level, so the multiplication is
  measured, not assumed. {#t0-3-sockets}

### Requirements {#t0-3-requirements}

1. **R3.1 bug-130.** `tests/test_catalog_measure.py::test_rewrite_bytes_is_the_median_of_the_runs`
   asserts `failed == 0` before it indexes `rewrite_bytes_all`. The assertion message carries the
   failed store's captured error, so a failure is never reported as a bare `KeyError`. The
   reproducer's captured error decides the fix:
   - a harness defect in `eval/catalog_maint/measure_catalogs.py` is fixed there, under the
     45-pass band;
   - a product defect gets its own registry row with the error. Its fix is NOT absorbed into T0
     ([[#ruling-o5]]). bug-130's row then reads `open / diagnosed-loud`, linked to the new row,
     so a firing in T0.7's suite is handled by [[#ruling-o7]]. {#r3-1}
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
  of 10 with E lines, and the post-fix run of 45, or the `not reproduced` band with all the
  counts. {#ac-3-1}
- **AC-3.2.** Mutations (each FAILS, within its deadline, never hangs):
  - M3.1: the bug-130 test indexes before its `failed` check (red on a forced failed store);
  - M3.2: the bug-190 skip path spawns (red);
  - M3.3: the watcher is never started (red at the R3.3 deadline);
  - M3.4: each R3.4 message drops its cause (a test that forces each failure and reads the
    message goes red). {#ac-3-2}

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
   registers every file it finds. (plan-8 r5 #s-9's doubles are gone since `a170ce9`, [[#r5-4]].)
   {#r4-2}
3. **R4.3 #s-1: drop the dead wrapper plumbing.** Delete the `render_scripts(wrappers=)`
   parameter, the `wrappers=` value in `hooks.py`'s `record_flags`, and `wrapper_paths()` (once
   no caller is left). `search_hooks.py`'s module docstring is rewritten to describe runtime
   resolution, with bug-008. R0.7 applies: an existing install whose `.claude/rmx-hooks.json`
   still carries `wrappers` must read in sync under `--check`. {#r4-3}
4. **R4.4 #s-2.** R0 confirms that task-6.4's summary records the change, the run and the
   mutation that r1 asked for. If it records no test for the `memory_partition` warning branch,
   add one: an answered-error `partition_list` logs the `warning` naming root, error and the
   fallback partition (mutation M4.4). {#r4-4}
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
     (the modules the suite cannot run without) that fails the session by name, with a test that
     runs it with one module made unimportable (mutation M4.8). {#r4-8}
9. **R4.9 todo G8.** R0 re-checks the two G8 claims ("README 0.961 has no committed artifact";
   "ARCHITECTURE.md lists 24/80 commands") against 6.2/6.3's output. A claim that still holds is
   fixed: regenerate from the CLI tree that 6.2 generates. The todo row is then updated. {#r4-9}

### Acceptance {#t0-4-acceptance}

- **AC-4.1.** After R4.1: `rmx grep -rn RMX_READ_VIA_DUCKDB src tests` is empty and the suite
  collects with no import error. R0's three-fact table is in the summary. {#ac-4-1}
- **AC-4.2.** The registry guard is RED at base, listing at least the six r1 files, and green
  after. Mutation M4.2: add `monkeypatch.setattr(os, "link", …)` to a tmp test file in the
  scanned set, and the guard goes red, naming that file. {#ac-4-2}
- **AC-4.3.** `--check` (the dev code's `hooks.check`, on a fixture install in a tmp root, never
  the live install) reads in sync for a fixture install carrying the old `wrappers` key. A
  rendered rewriter is byte-identical before and after R4.3. Mutation M4.3: `check` treats the
  leftover `wrappers` key as drift, and AC-4.3 goes red. {#ac-4-3}
- **AC-4.4.** Mutations: M4.5a replaces one phrase family with `ZZZ-never-matches`, and the
  meta-test goes red, because it compares the set. M4.5b appends `# for now` to a `src/` file,
  and the guard goes red. M4.6 drops `degraded` from the cancel return, and a test of that return
  goes red. M4.4 (if R4.4 adds its test): the `memory_partition` warning is not logged, and that
  test goes red. M4.8 (if R4.8 adds its check): drop a module from the required list, and the
  unimportable-module test goes red. {#ac-4-4}
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
- 8.3's summary now exists (W1-d), so #s-6's plan-8 half is closed;
- #s-9 is closed by `a170ce9` (26.6 r1 remedy): it rewrote
  `tests/test_plan7_10_remedy_r4.py`'s test onto a real throwaway store, and the file's
  `monkeypatch.setattr` calls now target only `telemetry` and `verbs`. R0 confirms;
- r5's `_fake_plan()` helper does not exist in `tests/` (no match at `1cf3b9f`).

{#t0-5-lead}

### Requirements {#t0-5-requirements}

1. **R5.1 #b-2: `corroborated` is reached through the wiring.** The `test_brief_detectors`
   `store` fixture seeds a memory set that the real `consolidate.compile_memories` clusters, and
   builds the plan with that real function on the seeded store (no fake plan). It passes `plan=`
   to `compile_briefs`, and the "every class" test then asserts all four classes,
   `corroborated` and `singleton` included. {#r5-1}
2. **R5.2 #b-3: delete the second direction ([[#ruling-o2]]).** `brief.parse_gmd` and
   `_parse_evidence` (with `names=` / `ids_by_name`) have no production caller, so they go under
   plan-6 Q1's rule for code no production path reaches
   ([[plan-6-deferrals-docs-benchmark#q1]]). Their tests go with them. R0 confirms there is still
   no caller in `src/`, `scripts/`, `eval/` or the templates. `ingest_gmd.parse_gmd` is a different
   function and is untouched. [[plan-8-derived-coverage-notes#proposed-approach]] gains a dated
   note: the brief index is one-directional (store → GMD), citing this task. Task 8.3, whose
   whole deliverable was that round trip, gains the same superseded note on its spec (its
   `status: complete` stays, as history). A no-caller check pins the deletion ([[#ac-5-3]]).
   {#r5-2}
3. **R5.3 #s-4: `brief` is verb-first.** The `brief` verb gains `compile: bool = False`. When it
   is true, the verb (or its daemon op) builds the compile plan itself. The CLI `--compile` flag
   becomes a pass-through to that parameter, and the MCP `rmx_memory` brief action exposes the
   same `compile` parameter, so an MCP caller reaches all four detectors without building a plan
   by hand. The verb parity test pairs the new parameter, default for default. {#r5-3}
4. **R5.4 #s-9: closed by `a170ce9`.** R0 confirms the four doubles are gone from
   `tests/test_plan7_10_remedy_r4.py`, and that any registry row still naming them is updated to
   say so. No new row is written for doubles that no longer exist. Any double R0 finds instead is
   registered through [[#t0-4]]'s guard. {#r5-4}
5. **R5.5 #m-10.** `tests/test_brief_surfaces.py` increments `compared` only where an assertion
   runs. `classes` is compared as a declared shape difference (the `SHAPE_DIFFERENCES` mechanism
   in `test_verb_parity.py`). {#r5-5}
6. **R5.6 The plan-8 deferral rows have a live owner before plan-8 closes.** Two
   `workflow/deferral_registry.md` rows say "Owner: plan 8": "Answer-usefulness as the
   retrieval-miss signal (vs `cardinality == 0`)" and "`brief/stale` detector". Their host in the
   2026-10-19 fold was W3-b, built on 19.2/21.1 usage records, and D-Q3 froze 19.2. Per
   [[#ruling-o3]] both are re-owned to **T3, held with the frozen 19.2 under the D-Q3 hold**
   ([[plan-review-2026-11-13#d-q3]]: frozen until the handhold experiment reports). T0.7 makes
   that registry edit ([[#r7-8]]); plan-8 flips only after it lands. {#r5-6}

### Acceptance {#t0-5-acceptance}

- **AC-5.1.** Mutations C1 to C4 from r5, re-run on the remedied tests: replace each detector's
  call in `compile_briefs` with an empty result. Each goes **red**. At base, C1 is green: that is
  the RED record. {#ac-5-1}
- **AC-5.2.** Through the MCP surface, on a throwaway store with a seeded memory set,
  `rmx_memory` brief returns `corroborated` and `singleton` with no `classes_not_run` entry for
  either. At base it returns both under `classes_not_run`. {#ac-5-2}
- **AC-5.3 (no-caller pin).** `parse_gmd` and `_parse_evidence` are absent from
  `src/refmatrix/brief.py`, and plan-8's note is in place. A test asserts that `brief` exports
  no function that `src/` never calls, scoped to `brief.py`'s public functions plus an explicit
  allow-list of entry points (each with a reason). Mutation M5.3: re-add a `parse_gmd` stub to
  `brief.py`, and the test goes red, naming it. {#ac-5-3}
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
- Tests (new): `tests/test_brief_no_dead_exports.py`.
- Docs and registries: `workflow/test_mock_registry.md` (only rows R5.4 touches),
  `workflow/plans/plan-8-derived-coverage-notes.md` (the one-direction note),
  `workflow/plans/plan-8-derived-coverage-notes-tasks/task-8.3-plan-8-derived-coverage-notes.md`
  (the superseded note).
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
2. **R6.2 Backed up first, then opened or rebuilt, and the run says which.**
   - **Backup.** Before anything writes to `/Volumes/littlebig/longmemeval/.refmatrix` (a
     migration, the embed, `memory compile`), R0 checks the volume's free space against the
     store's size, then copies the store to
     `/Volumes/littlebig/longmemeval-store-backup-<YYYY-MM-DD>/`, outside every watched tree. It
     records the path and size. If space is short, it stops and raises it to the lead. The backup
     is kept until T0.6's ch-bsd round closes.
   - **Open.** R0 opens the 0.69.1 store with the deploy build, read-only first (`rmx status`). If
     it opens and migrates cleanly, the embed resumes on it. If it does not, the store is rebuilt
     from `corpus/` with the harness (the 4h23m ingest).

   REPORT.md's setup table records which path was taken and the build's version. {#r6-2}
3. **R6.3 Same knobs as the symbolic rows.** `recall`, `recall-fuse`, `recall-rr` and
   `recall-fuse-rr` run on the same 120 questions (20 per type, seed 42), at `--depth 50` and
   `--at 1,5,10,20`, in both modes, with ceilings printed. A dense row is labelled saturated
   exactly as the symbolic rows are when it hits its ceiling ([[longmemeval-report#next]] item 1:
   the depth-200 re-run is not part of W2-c). {#r6-3}
4. **R6.4 Every number carries its provenance** (task 7.4 `#requirements`, plan-7 `#execution`):
   the harness command, corpus size, scoring mode, rmx version and date. Per [[#ruling-o3]] the
   symbolic rows (`context`, `scan`) are re-taken on the same build in the same run, so one table
   holds one build. The 0.69.1 rows move to a dated history section with their own provenance;
   they are not deleted. {#r6-4}
5. **R6.5 Artifacts and citations.** Results JSON goes under
   `eval/production/longmemeval/results/`. README and `docs/PERFORMANCE.md` cite the committed
   path. `tests/test_eval_artifact_cited.py` covers every new figure it cites, compared over the
   full table and not one row (plan-6 r1 #m-3's lesson). REPORT.md's `#embed` section becomes the
   result. Its `#next` item 4 is closed. {#r6-5}
6. **R6.6 A failure is a result.** If the embed fails again, its error, timing and the worker
   state go in REPORT.md and a registry row. The dense rows stay absent, and plan-7 does not
   close. {#r6-6}
7. **R6.7 What the run touches outside the eval store is stated, not assumed.** R0 records,
   before the embed starts:
   - whether the harness starts a daemon for the eval store, and how (a foreground or
     `rmx daemon` process, never a launchd plist installed for it). Any daemon it starts is
     stopped after the run, and the summary names its pid and lifetime;
   - whether the embed and rerank use the hub's shared workers (`models.sock`) or private ones,
     and the run's window, so the hours of shared-worker load are on record. The summary quotes
     `rmx hub status` before and after.

   No step installs, restarts or reconfigures a fleet daemon or the hub. {#r6-7}

### Acceptance {#t0-6-acceptance}

- **AC-6.1.** REPORT.md's `#restricted` and `#union` tables hold `context`, `scan` and all four
  dense/fused methods, every row from one build, each with a ceiling column. The setup table names
  that build, the store path taken (R6.2) and the embed wall time. The 0.69.1 symbolic rows sit
  in a dated history section with their original provenance. {#ac-6-1}
- **AC-6.2.** `tests/test_eval_artifact_cited.py` is RED before the results are committed (README
  or PERFORMANCE cites a figure with no artifact) and green after. Mutation M6.1: edit one cited
  dense figure in README, and the test goes red. {#ac-6-2}
- **AC-6.3.** task-7.4's frontmatter status drops "(symbolic only …)". Plan-7 closes when the T0.6
  ch-bsd round is CLEAN and its four deferral rows carry the plan-20-evals owner that L33 assigns,
  an edit T0.7 makes ([[#r7-8]]). {#ac-6-3}
- **AC-6.4.** The summary carries R6.2's backup path and size and R6.7's daemon and worker record.
  {#ac-6-4}

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
   **main tree** (`~/claude_tools/refmatrix`) at a committed `master` sha that holds T0.1 to T0.6,
   T0.8 and T0.7's own merge. Preconditions:
   - **Hooks in sync.** `rmx install-hooks --check` (the deployed build) reads clean before the
     run. A mismatch means the installed hooks drifted from the deployed render (a deploy or
     install window not yet done, G31). It is reported to the lead as **hook drift**, not as
     bug-170, and R7.4 does not start until it is resolved. If `--check` is clean but
     `test_installed_hooks_match_generated` still fails on a script or settings diff, the summary
     first lists the hook-generator changes (`src/refmatrix/hooks.py`, `search_hooks.py`,
     `templates/`, `.claude/settings.json`) between the deployed sha and the run's sha. A diff
     explained by those changes is hook drift too (the deploy lags master), not bug-170;
   - `git status --porcelain` lists nothing under `src/ tests/ docs/ workflow/ eval/ CLAUDE.md
     .claude/PROJECT_PROFILE.md`, both at start and at end. If the end check fails, or HEAD moved,
     the run is **void**: its log is kept as void, and the run is repeated;
   - HEAD is unchanged across the run;
   - the lead is told before the run starts that the main tree is under a suite run (for about
     45 min), so no one writes those paths during it;
   - no branch switch: the main tree is shared ([[feedback_shared_tree_no_branch_switch]]).

   **Command.** `.venv-eval/bin/python -m pytest -p no:cacheprovider -rA
   --junitxml=workflow/review-output/t0/clean-suite-<sha>.xml 2>&1 | tee
   workflow/review-output/t0/clean-suite-<sha>.log`, then `echo "exit ${PIPESTATUS[0]}"` into
   the log. `-rA` puts every PASSED nodeid in the log for AC-7.4.

   **Clean** means all of:
   - pytest exit code 0;
   - 0 failed and 0 errors;
   - no SkipGate line;
   - collected = passed + pinned skips (0 in the main tree).

   The log, the junit XML and a `.sha` file are committed as
   `workflow/review-output/t0/clean-suite-<sha>.{log,xml,sha}`. [[#ruling-o7]] is the only
   exception to "exit 0" ([[#r7-6]]). {#r7-4}
5. **R7.5 The clone twin (T0's trust proof).** The same sha runs the full suite in a littlebig
   clone, with the same command. It exits 0 (or meets [[#ruling-o7]]), and its only skips are the
   pinned clone-only set, each reported as pinned. Its GMD gate takes R1.4's origin fallback (the
   stderr line is in the log), and `./scripts/lint-gmd.sh`'s error count in the clone **equals the
   main tree's** at the same sha. This is where releases run, so it is the run bug-215 and bug-155
   were invisible to. {#r7-5}
6. **R7.6 A failure in R7.4 or R7.5 does not get explained away.** Every failing E line is matched
   to a row by E line (R0.2).
   - **A `diagnosed-loud` flake ([[#ruling-o7]]).** The gate still passes if EVERY failure in the
     run matches a T0.3 row whose status is `open / diagnosed-loud`, and each of those nodeids
     passes on an immediate isolated re-run (`pytest <nodeid>` alone, same sha, same tree,
     logged). The summary records each such nodeid with both outcomes, and the row's band counts
     gain the firing.
   - **A match to any other T0 row** means that sub-task's fix did not hold. It reopens and takes
     the O5 path below.
   - **Anything else**, including a `diagnosed-loud` nodeid that fails its isolated re-run, a
     hook-drift failure ([[#r7-4]]), or a failure with no matching row, is handled per
     [[#ruling-o5]]. It is logged as a row (or the existing row is updated), T0's closure stops
     there (plan-15 stays `in-progress`), and it is raised to the lead. The goal continues with
     its other items, and T0 does not fix it without a spec.

   After an O5 stop, R7.4 is re-run only once the cause is fixed. {#r7-6}
7. **R7.7 Plan closures.** Plan-15 flips to `completed` when R7.4 is clean and the T0.7 ch-bsd round
   is CLEAN or MEH-only. Plans 6, 7 and 8 flip per [[#ac-4-close]], [[#ac-6-3]] and
   [[#ac-5-close]]. Each flip edits the plan's frontmatter and its body status line, which must
   agree (Cc-9, CD-9). {#r7-7}
8. **R7.8 T0.7 owns the deferral-registry edits the flips need.** T0.7 edits
   `workflow/deferral_registry.md` itself, identifying rows by their title, not line number:
   - owner "plan 7" → "plan-20 evals (L33; W4-a)" on "LongMemEval Layer B (answer model + LLM
     judge)", "`longmemeval_m` variant (500 sessions/question)", "CLI candidate-set prefilter for
     recall (`ann_search(candidate_ids=...)` has no flag)", and "Re-measure big-store query
     latency on a SETTLED store";
   - owner "plan 8" → "T3, held with the frozen 19.2 (D-Q3 hold; [[#ruling-o3]])" on
     "Answer-usefulness as the retrieval-miss signal (vs `cardinality == 0`)" and "`brief/stale`
     detector".

   R0 first re-reads the registry at the branch base. If another branch has already made either
   edit, it is recorded as done, not repeated. {#r7-8}

### Acceptance {#t0-7-acceptance}

- **AC-7.1.** Mutations L6 (`_start_embedder_warmup` calls `self._reranker()` without
  `load=True`) and L1 (the refill bound is dropped) each go **red**. At base both survive, and
  r13's table is the RED record. {#ac-7-1}
- **AC-7.2.** The R7.2 wording test covers every cause branch R0 found. The R7.3 registry rows
  exist. Mutation M7.2: revert one cause's wording to the old single message, and the test goes
  red. {#ac-7-2}
- **AC-7.3.** The committed R7.4 log shows exit 0, with the collected count equal to passed. The
  committed R7.5 log shows exit 0, with only pinned skips. The summary quotes both exit codes and
  both counts. {#ac-7-3}
- **AC-7.4.** At least one previously failing test from each of bug-170, 168 and 127 appears as
  `PASSED` in the R7.4 log's `-rA` summary and in its junit XML. This is T0.2's main-tree proof.
  {#ac-7-4}
- **AC-7.5.** After R7.8, none of the six deferral rows names "plan 7" or "plan 8" as its owner.
  {#ac-7-5}

### Files {#t0-7-files}

`tests/test_rerank_budget_real_clients.py`, `src/refmatrix/daemon.py` (only R7.2's wording),
`workflow/bug_registry.md`, `workflow/test_mock_registry.md`, `workflow/deferral_registry.md`
(R7.8), `workflow/review-output/t0/clean-suite-<sha>.{log,xml,sha}`, the clone-twin log and XML,
and the plan
frontmatter and body status lines for plans 6, 7, 8 and 15. The summaries are
`workflow/implementation_summaries/task-t0.7-plan15-close-clean-suite.md` and
`workflow/implementation_summaries/task-t0-suite-trust-sweep.md` (the T0 roll-up: each sub-task,
its rows, its exit codes).

## T0.8 bug-196: the cli.log recall leg is split per channel {#t0-8}

Added by [[#ruling-o1]]: without it R7.4 cannot be clean. In the 0.82.0 release suite (main tree)
both RED tests failed: `test_ac6_frozen_fixture_prints_the_exact_counts` (the report prints
`cli.log: memory recall commands=244`, and no line holds the fixture's 34 agent recalls) and
`test_ac6_cli_log_recalls_are_split_per_channel` (`assert []` from its `chan('prompt_recall', 5)`
lookup). The bug-196 row names the cause and the fix. {#t0-8-lead}

rel: derives-from -> [[bug_registry]] {bug: "bug-196"}

### Requirements {#t0-8-requirements}

1. **R8.1 One line per channel.** `telemetry.agent_usage_report`'s cli.log leg counts each
   `memory recall` end row under its channel. The channel comes from
   `recall_channel(session_start=, stdin_json=, recent=, invocation=source)`
   (`telemetry.py:1246`), fed from the row's argv flag names (they survive redaction) and its
   `source`. It replaces the single total. This applies 21.1 R7's per-invocation, per-R11-channel
   rule to the cli.log leg as well as to `kind=recall` query.log rows. {#r8-1}
2. **R8.2 No double count.** When a store has both 21.1 `kind=recall` query.log rows and cli.log
   end rows for the same calls, each call is counted once. R0 records which key pairs the two
   (the bug-196 row warns of this). {#r8-2}
3. **R8.3 Tests are already RED.** The two AC-6 tests named above are the RED record. They are
   not edited to pass. Any new test for R8.2 is RED first. {#r8-3}

### Acceptance {#t0-8-acceptance}

- **AC-8.1.** Both AC-6 tests pass. On the frozen fixture the report prints one line per channel:
  201 `prompt_recall`, 6 `session_start`, 3 `precompact`, 34 agent `recall` (the row's
  breakdown), and they sum to the old 244. {#ac-8-1}
- **AC-8.2.** A fixture holding the same calls as cli.log rows and as `kind=recall` rows counts
  each call once. {#ac-8-2}
- **Mutations (each FAILS):** M8.1: every cli.log recall falls to one channel (AC-8.1 red); M8.2:
  both legs count the same call (AC-8.2 red). {#t0-8-mutations}

### Files {#t0-8-files}

`src/refmatrix/telemetry.py`, `tests/test_task21_1_agent_usage_report.py` (only a new R8.2
test), `workflow/bug_registry.md` (row 196),
`workflow/implementation_summaries/task-t0.8-bug196-recall-channels.md`.

## Merge order {#merge-order}

queue item 1 (bug-212, bug-216, 25.1 rev 7) → **T0.1** → T0.2 ∥ T0.3 ∥ T0.4 ∥ T0.6 ∥ T0.8 →
T0.5 (after T0.4) → **T0.7** (last; R7.4 runs on the sha after its merge). Each sub-task merges
`--no-ff` from its own branch. {#merge-order-body}

- **Interim bug-127.** Once T0.1 merges, a symlinked clone no longer skips
  `test_brief_real_daemon.py`, so every symlinked-clone full run between T0.1's merge and T0.2's
  fails `test_an_unknown_class_fails_loudly_through_the_daemon` on bug-127's `Conflicting lock`
  E line. That failure is bug-127, matched by E line (R0.2), not a new finding. {#merge-interim-127}
- **26.5 in parallel.** T0 runs alongside 26.5 (queue item 2). T0.4 and T0.5 touch `cli.py`,
  `verbs.py` and `mcp.py` (T0.5 also the verb-parity pairing), and so does 26.5. The order does
  not change: whichever of them merges later rebases on the earlier one and re-runs its own
  tests and `test_verb_parity` before its merge. 26.5's merges may land between T0 merges. R7.4
  runs on whatever `master` holds at that point and is clean only if 26.5's tests are too.
  {#merge-265}
- **Release.** T0 needs no hook install window (R0.7). T0.5 changes an MCP tool, so it rides the
  next release with a `/mcp` reconnect. {#merge-release}

## Lead rulings, 2026-11-13 {#rulings}

The first draft raised five choices that no D-Q or L-row settled. The lead ruled on all five, on
the user's pattern (correct first, no dead code, nothing parked without a host), and they are
folded into the sections each one names. {#rulings-lead}

- **O1 → (a).** bug-196 joins T0 as [[#t0-8]], so W1-e's clean-suite gate (R7.4) can be met.
  Its RED tests are the two AC-6 tests named in the bug-196 row. {#ruling-o1}
- **O2 → (a).** `brief.parse_gmd` is deleted under plan-6 Q1's rule for code with no production
  caller, and the deletion is pinned with a no-caller check ([[#r5-2]], [[#ac-5-3]]).
  {#ruling-o2}
- **O3 → (a), both halves.** Plan-8's two deferral rows ("Answer-usefulness as the retrieval-miss
  signal" and "`brief/stale` detector") are re-owned to T3, held with the
  frozen 19.2 under the D-Q3 hold ([[#r5-6]]). T0.6 re-takes the symbolic rows on the same build
  for one comparable table ([[#r6-4]], [[#ac-6-1]]). {#ruling-o3}
- **O4: fixed by the lead** on dev master at `35e1e0d`: frontmatter on the pop-2026-11-13
  reports, the bsd-pop-r1 brief committed, `./scripts/lint-gmd.sh` exit 0. T0.1's AC-1.5 assumes
  a green master gate in the main tree ([[#ac-1-5]]). {#ruling-o4}
- **O5 → (a).** A failure that no T0 row owns is logged, stops T0's closure, and is raised to the
  lead ([[#r7-6]], [[#r3-1]]). {#ruling-o5}
- **O6 (r1 B-1) → origin fallback.** bug-155's second cause: a clone has no memory dir under its
  own slug. `scripts/lint-gmd.sh` and the repo-scope test fall back to the memory dir of the
  clone's ORIGIN path (`git remote get-url origin` → that path's slug) when the clone's own slug
  has none, and say so loudly on stderr. AC-1.5 and R7.5 assert that the clone's error count
  equals the main tree's ([[#r1-4]], [[#ac-1-5]], [[#r7-5]]). {#ruling-o6}
- **O7 (r1 s-3) → the flake clause.** The clean-suite gate (R7.4, R7.5) passes only when its exit
  is 0, OR every failure is a T0.3 `diagnosed-loud` flake row that passes on an immediate
  isolated re-run, recorded with its nodeid and both outcomes. Any other failure takes the O5 path
  ([[#r7-6]]). {#ruling-o7}

## Revision round r1 (2026-11-13) {#rev-r1}

The ch-bsd spec review of `1cf3b9f..7e67551` (`bsd-spec-t0-7e67551`, DIRTY 1B/6S/9M; persisted by
the lead) and the lead's rulings on it, folded:

| finding | resolution | where |
|---|---|---|
| B-1 bug-155 half-diagnosed | second cause recorded; origin-path memdir fallback, loud on stderr; clone count = main-tree count | [[#t0-1-bug155-cause]], [[#r1-4]], [[#ac-1-5]], [[#ac-1-6]], [[#r7-5]], [[#ruling-o6]] |
| s-1 reason match unpins all skips | the tests' actual reasons quoted (19 pins, not 18); pins = exact reasons, equality after stripping `Skipped: `; the seven files in Files; a no-venv clone pins all 19 | [[#t0-1-skip-reasons]], [[#r1-2]], [[#ac-1-4]], [[#t0-1-files]] |
| s-2 bands and harness | fixed = 45 consecutive passes (0.933^45 < 0.05 at the 3/10 reproducer's 95% lower bound); reproducer stays ≥ 3/10; R0 generates the `--durations` log; trials bounded by count | [[#t0-3-bands]] |
| s-3 diagnosed-loud flake in R7.4 | the O7 flake clause; bug-130's product route reads `diagnosed-loud` | [[#r7-6]], [[#r3-1]], [[#ruling-o7]] |
| s-4 hooks test depends on deploy | R7.4 precondition: deployed `install-hooks --check` clean; a mismatch is hook drift, not bug-170 | [[#r7-4]], [[#ac-2-1]] |
| s-5 registry edits had no actor | T0.7 owns the edits, rows cited by title | [[#r7-8]], [[#ac-7-5]], [[#r5-6]], [[#ac-6-3]] |
| s-6 stale facts | `_fake_plan()` removed (the plan comes from the real `compile_memories`); #s-9 closed by `a170ce9` | [[#t0-5-lead]], [[#r5-1]], [[#r5-4]] |
| m-1 T0.2 clone behaviour | corrected per test; interim bug-127 noted | [[#t0-2-lead]], [[#ac-2-3]], [[#merge-interim-127]] |
| m-2 report format, dirty end | `-rA` + `--junitxml` named; a dirty end voids the run | [[#r7-4]], [[#ac-7-4]] |
| m-3 the exit-code rule had no target section | it goes into `TDD_GOVERNANCE.md#rules` (now R1.5) | [[#r1-5]] |
| m-4 unnamed mutations | M2.4, M3.4, M4.3, M4.4, M4.8, M7.2 added | [[#t0-2-mutations]], [[#ac-3-2]], [[#ac-4-3]], [[#ac-4-4]], [[#ac-7-2]] |
| m-5 MCP parameter shape | `compile: bool = False` on the `brief` verb, mirrored by CLI `--compile` and the MCP brief action | [[#r5-3]] |
| m-6 26.5 overlap | stated; the later merge rebases on the earlier; no order change | [[#merge-265]] |
| m-7 task-8.3 note | task-8.3 gains the superseded note | [[#r5-2]], [[#t0-5-files]] |
| m-8 T0.6 daemon, backup; T0.3 sockets | backup before any write; daemon/worker use recorded; live-socket counts recorded | [[#r6-2]], [[#r6-7]], [[#ac-6-4]], [[#t0-3-sockets]] |
| m-9 rows by line number | rows cited by title | [[#r5-6]], [[#r7-8]] |

{#rev-r1-body}

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
- Rows 215, 170, 168, 155, 127, 130, 190, 091 and 196 read `fixed <sha>` with evidence, or (T0.3
  only) `open / diagnosed-loud` with the band counts.
- R7.4 and R7.5 are committed and meet the gate: exit 0, or the [[#ruling-o7]] flake clause
  with each re-run recorded.
- Plans 6, 7, 8 and 15 are `completed` in frontmatter and body, or still `in-progress` with the
  named reason that holds each (a ch-bsd round not yet CLEAN, an unmet deferral owner, or an O5
  stop).
- Every sub-task's ch-bsd round is CLEAN, or MEH-only where its plan allows.
- GMD lint shows 0 errors on every touched `.md`.
- Each branch is merged `--no-ff` to `master`.
