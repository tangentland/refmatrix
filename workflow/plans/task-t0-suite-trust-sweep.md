---
gmd: "0.1"
id: task-t0-suite-trust-sweep
title: "Task T0: the suite-trust sweep: nine instrument bugs and the plan-6/7/8/15 closure gates (W2-a, W2-b, W2-c, W1-e)"
tags: [task, t0, tests, instrument, skipgate, flaky, plan-6, plan-7, plan-8, plan-15, plan-29, task-29.4, bug-215, bug-170, bug-168, bug-155, bug-127, bug-130, bug-190, bug-091, bug-196, bug-228, bug-229, bug-231, bug-253]
metadata:
  node_type: task
  status: approved
  created: 2026-11-13
  updated: 2026-11-15
---

# Task T0: suite-trust sweep {#root}

> Plan: the consolidated queue, track **T0 Instrument trust** ([[plan-review-2026-11-13#p1]],
> [[plan-review-2026-11-13#queue-body]]). Spec gap G5 ([[plan-review-2026-11-13#spec-gaps]]).
> **Since 2026-11-14 T0 is the body of [[task-29.4-suite-health]]**
> ([[task-29.4-suite-health#fold]]). It runs inside plan-29, in 29.4's stages, with the ten
> amendments of [[#amends-29-4]]. It no longer runs as queue item 2 beside 26.5.
> Status: **Approved** (2026-11-13) by the lead on the user's pattern (the d9co route,
> [[plan-review-2026-11-13#goal-horizon]]) after ch-bsd r3 came back MEH-only; the MEH is folded
> ([[#decision-approved]]). The lead's rulings on the first draft's choices and on each review
> round are in [[#rulings]], [[#rev-r1]], [[#rev-r2]] and [[#rev-r3]]. Revised 2026-11-15 for
> freshness and the 29.4 fold ([[#rev-note-fresh]]), and again after its two reviews
> ([[#rev-note-fresh-2]], ruling L122; [[#rev-note-fresh-3]], ruling L123).
> Depends on: what 29.4 depends on ([[task-29.4-suite-health#root]]), and 29.4's stage 0, which
> is done ([[task-29.4-r0-durations]]). Queue item 1 is on `master`: bug-212 (`cc061f4`),
> bug-216 (`7aed8df`), 25.1 rev 7 (`d44e359`, `d1be40a`). Every T0 branch starts from the
> `master` sha that holds the stage before it ([[#amend-2]], [[#amend-3]]).
> Closes: bug-215, 170, 168, 127, 130, 190, 091 and 196 ([[#ruling-o1]]), and bug-155's
> residual ([[#amend-1]]). bug-228, bug-231 and bug-229 are closed by 29.4's text, on T0.3's
> harness and on T0.2's branch ([[#amend-4]], [[#amend-5]]).
> It also closes the recorded closure gates of plans 6, 7, 8 and 15 (D-Q6).
> User gates: none of T0's own. No step opens a live store, starts a fleet daemon, or needs a
> hook install window ([[#rules]] R0.7). But T0 can be **held** by one: a hook-drift stop at R7.4
> ([[#r7-4]]) is cleared only by a G31 install window, which is user-gated. A gate-drift stop
> (master's GMD gate red) is cleared by whoever owns the failing file.

rel: part-of -> [[task-29.4-suite-health#fold]]
rel: depends-on -> [[task-29.4-r0-durations]]
rel: depends-on -> [[orchestration]]
rel: derives-from -> [[plan-review-fable-2026-11-14-queue#b3]]
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

In a littlebig clone with a symlinked `.venv-eval` every run exits 1 on a skip the gate cannot
place (bug-215). On 2026-11-13 the repo-scope GMD gate failed in every clone on about 1,080
dangling ids, for two reasons (bug-155, [[#t0-1-bug155-cause]]); both were fixed the next day and
a residual is left ([[#amend-1]]). Three tests fail only under load (bug-130,
190, 091). Readers have learned to diff E lines by hand and call the rest "pre-existing". That is
the habit this task removes. {#why-instrument}

**Re-read on 2026-11-15.** The picture has moved, and it has not got cleaner:
- The 0.84.0 release suite in the dev tree (`workflow/review-output/release-0.84.0-full.log`; the
  directory is git-ignored and that log is not committed) ended **13 failed, 5,028 passed**:
  bug-168 9, bug-170 1, bug-127 1, bug-196 2. bug-155's test passes there since `988e96d` and
  `44d1a34`. The 0.83.0 suite had a fourteenth failure, bug-231 (9.02 s against 8.0).
- A clone with no `.venv-eval` sees a different set. 29.4's stage-0 run at `4c6a0c6` exited 1
  with 4 failed and 127 errors: bug-196's two, and 129 nodes of one new cause, bug-253
  ([[task-29.4-r0-durations#digest]]). Its 19 skips were all pinned.

So no checkout runs clean today, and the two kinds of checkout do not fail the same tests.
{#why-now}

Four legacy plans cannot close for the same reason. Each carries a recorded "may NOT flip" gate
that the 2026-10-19 fold made a wave item. Neither a decision nor a host has moved them since
(Ce-9 in [[pop-2026-11-13-contra-e]]). D-Q6 keeps the gates and
schedules them here:
- W2-a, plan-6 ch-bsd r1 at `e0b7df6`;
- W2-b, plan-8 ch-bsd r5;
- W2-c, the plan-7 task 7.4 dense/fused re-run;
- W1-e, the plan-15 clean suite plus r13 #s-1/#m-1/#m-2. {#why-gates}

## Amendments from task 29.4 (2026-11-15) {#amends-29-4}

T0 was approved on 2026-11-13, before plan-29 existed. [[task-29.4-suite-health#fold-deltas]]
lists ten changes to its text. Each one is a subsection here, with an edge to what it amends, and
each is also written in place at the site it names, marked with a link back to its subsection.
The text at the site is what a sub-task builds from. T0's requirements, ACs and mutations are
otherwise built as written. {#amends-29-4-lead}

rel: derives-from -> [[task-29.4-suite-health#fold-deltas]]

### A1 (row 1): T0.1 becomes T0.1' {#amend-1}

R1.3 shipped verbatim (`988e96d`) and is dropped as a requirement. R1.4 shipped as bash in
`scripts/lint-gmd.sh` (`44d1a34`) that tests only that the own-slug directory exists, so an empty
`memory/` defeats the fallback. R1.4 becomes: converge the shipped fallback onto one resolver,
with the populated-directory check and canonicalisation. AC-1.5's RED is the empty-directory
case, and M1.3 and M1.4 are restated against it. The bug-155 row gains the residual
([[#rev-note-fresh-bug155]]). Round 2 (ruling L122) adds what the review found live: a clone
of a clone. The resolver walks the origin chain, and AC-1.5 has a second RED for it
([[#rev-note-fresh-2]]).

rel: amends -> [[#r1-3]]
rel: amends -> [[#r1-4]]
rel: amends -> [[#ac-1-5]]
rel: amends -> [[#t0-1-mutations]]
rel: derives-from -> [[plan-review-fable-2026-11-14-queue#st-8]]

### A2 (row 2): plan-29 runs first, and 26.5 is not in flight {#amend-2}

The header's "Depends on queue item 1" and "in parallel with 26.5" are replaced. plan-29 runs
first (ruling L104, [[plan-review-2026-11-13#lead]]), T0 runs inside it as 29.4's body, and 26.5
does not run during this task.

rel: amends -> [[#root]]
rel: amends -> [[#merge-265]]

### A3 (row 3): the merge order is 29.4's stages {#amend-3}

T0.2 ∥ T0.3 ∥ T0.4 ∥ T0.6 ∥ T0.8 becomes the stages of [[task-29.4-suite-health#fold-stages]]:
T0.4 → T0.5 run after stage 2, not beside it.

rel: amends -> [[#scope]]
rel: amends -> [[#merge-order]]
rel: derives-from -> [[plan-review-fable-2026-11-14-queue#b3]]

### A4 (row 4): bug-228 and bug-231 join T0.3's harness {#amend-4}

T0.3 covers bug-130, 190 and 091, plus bug-228 and bug-231 on the same harness with the same
bands ([[#t0-3-bands]]). What is built for the two is 29.4's text
([[task-29.4-suite-health#r3]]).

rel: amends -> [[#t0-3]]
rel: derives-from -> [[plan-review-fable-2026-11-14-queue#b3]]

### A5 (row 5): bug-229's reaper and root rule join T0.2 {#amend-5}

T0.2 covers bug-170, 168 and 127, plus bug-229 through [[task-29.4-suite-health#r4]] and
[[task-29.4-suite-health#r5]], on one branch with 29.4b.

rel: amends -> [[#t0-2]]
rel: derives-from -> [[plan-review-fable-2026-11-14-queue#b3]]

### A6 (row 6): `open / diagnosed-loud` is written in 29.1's grammar {#amend-6}

Wherever T0 sets the status `open / diagnosed-loud` ([[#t0-3-attempts]], [[#t0-3-band-none]],
[[#r3-1]], and the places that read it: [[#r7-6]], [[#done]]), the row reads
`deferred: diagnosed-loud, <trial counts>; review <date>`.

rel: amends -> [[#t0-3-attempts]]
rel: amends -> [[#t0-3-band-none]]
rel: amends -> [[#r3-1]]
rel: derives-from -> [[task-29.1-registry-triage#r1-other-writers]]

### A7 (row 7): the clean runs go through 29.4's runner {#amend-7}

R7.4 and R7.5 named one `pytest -rA --junitxml` process of about 45 minutes. They become
`scripts/ptest.sh --tier all`, in the main tree (run tier (c) included) and in the clone twin.
"Clean" keeps T0's definition word for word. Row 7 also asked for `-rA` and one junit file per
shard. The runner has no such flags, and ruling L122 adds none: per-node results are read from
the runner's `outcomes.jsonl` ([[task-29.4-suite-health#r2-outcomes]]), and row 7 is reworded
to say so.

rel: amends -> [[#r7-4]]
rel: amends -> [[#r7-5]]
rel: derives-from -> [[task-29.4-suite-health#ac-7]]

### A8 (row 8): the four plan-7 deferral rows get no phantom owner {#amend-8}

R7.8 re-owned four plan-7 deferral rows to "plan-20 evals". Plan-20's three tasks hold none of
them. The owner becomes "no host plan; backlog (L33)".

rel: amends -> [[#r7-8]]
rel: amends -> [[#ac-6-3]]
rel: derives-from -> [[plan-review-fable-2026-11-14-queue#dup-2]]

### A9 (row 9): ruling O7's re-run is the only re-run {#amend-9}

Ruling O7's "immediate isolated re-run" is unchanged. It is the only re-run 29.4 allows
([[task-29.4-suite-health#decisions]], plan-29 D14): the runner has no retry flag.

rel: amends -> [[#ruling-o7]]

### A10 (row 10): R0.1 to R0.8 bind 29.4's additions too {#amend-10}

The rules of [[#rules]] apply to everything 29.4 adds, as they do to T0's sub-tasks
([[task-29.4-suite-health#r10]]).

rel: amends -> [[#rules]]
rel: derives-from -> [[plan-review-fable-2026-11-14-queue#ord-6]]

## Scope and order {#scope}

| sub-task | closes | branch | stage ([[task-29.4-suite-health#fold-stages]]) |
|---|---|---|---|
| [[#t0-1]] **T0.1'** Skip gate and checkout identity | bug-215, bug-155's residual ([[#amend-1]]) | `task-t0.1-skip-gate-memdir` | 1 |
| [[#t0-2]] Dev-tree-only tests stop reading the real HOME and cwd ancestry | bug-170, bug-168, bug-127; with 29.4b on the same branch: bug-229 ([[#amend-5]]), and bug-253 by L121 and L122, which retires the 18 venv pins ([[#t0-2-bug253]]) | `task-t0.2-dev-tree-test-isolation` | 2 |
| [[#t0-3]] Load-dependent flakes | bug-130, bug-190, bug-091; with 29.4c on the same branch: bug-228, bug-231 ([[#amend-4]]) | `task-t0.3-load-flakes` | 2 |
| [[#t0-8]] bug-196: the cli.log recall leg split per channel | bug-196 ([[#ruling-o1]]) | `task-t0.8-bug196-recall-channels` | 2 |
| [[#t0-6]] W2-c: the plan-7 dense/fused re-run | task 7.4's missing rows; REPORT.md completed | `task-t0.6-plan7-dense-rerun` | lane: any time after stage 1; long-running |
| [[#t0-4]] W2-a: the plan-6 remedy | plan-6 r1 #b-1, #b-2, #s-1, #s-2, #s-3, #m-1..#m-5; todo G7/G8 | `task-t0.4-plan6-remedy` | 3, first |
| [[#t0-5]] W2-b: the plan-8 remedy | plan-8 r5 #b-2, #b-3, #s-4, #m-10; #s-9 and #s-6's 8.3 half confirmed closed | `task-t0.5-plan8-remedy` | 3, after T0.4 (both edit `cli.py`; T0.4's registry lint lands first) |
| [[#t0-7]] W1-e: plan-15 r13 remedy + the clean full suite | plan-15 r13 #s-1, #m-1, #m-2; the clean-suite gate for plans 15, and the trust proof for T0 | `task-t0.7-plan15-close-clean-suite` (with 29.4d) | 5, **last** |

The order is 29.4's ([[#amend-3]]; [[task-29.4-suite-health#order]]):
- **Stage 0** is the durations run, T0.3's R0. It is done ([[#t0-3-r0]]).
- **Stage 1, T0.1'**, goes first because until it lands, every symlinked-clone run exits 1 and no
  sub-task can quote a clean exit code.
- **Stage 2** is T0.2, T0.3 and T0.8. They are independent of each other. T0.2 and T0.3 each
  share a branch and a ch-bsd range with a part of 29.4 ([[task-29.4-suite-health#order-pairs]]).
- **T0.6 is a lane**: it builds no `src/` and may start any time after stage 1.
- **Stage 3** is T0.4, then T0.5, after stage 2. They delete dead code before 29.5 moves it.
- **Stage 4** is 29.4's runner and holds no T0 sub-task.
- **Stage 5, T0.7**, runs the closing suite through that runner, so it merges last.

Sub-tasks of one stage may be written in parallel littlebig clones (each in its own
`/Volumes/littlebig/refmatrix-t0-<n>`). Their test runs are not parallel: the machine runs one
test process at a time ([[orchestration#one-suite]]), and the lead orders them. T0.3's load
harness is several pytest processes by design; while it is up it is that one run.
{#scope-order}

## Rules for every sub-task {#rules}

- **R0.1 Re-verify before fixing.** Every finding cited here is 2 to 7 weeks old, and the code
  has moved: for example `store.py:717` was `:1159` when this spec was approved and is `:1372`
  at `f45b9a3`, and r13 #m-1's wording no longer greps. The line numbers in this spec were
  re-read on 2026-11-15 at `f45b9a3` ([[#rev-note-fresh]]); 29.5 will move them again.
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
- **R0.1 to R0.8 also bind what 29.4 adds** ([[#amend-10]]; [[task-29.4-suite-health#r10]]).
  {#r0-also-29-4}
- **The operating procedure binds every sub-task** ([[orchestration]], adopted 2026-11-15, after
  this spec). Two of its rules change how T0 runs:
  - no branch full suite ([[orchestration#task]] step 4). A sub-task verifies with its own
    files, their family and every test that imports a changed module. T0's full runs are stage
    0's, which is done, and T0.7's two (R7.4, R7.5), which run at a `master` sha;
  - one test run at a time on the machine ([[orchestration#one-suite]]).

  {#r0-orchestration}
- **Two branches edit files every test loads, so their verify set is named** (ch-bsd r1 M8;
  ruling L122). `tests/conftest.py` and `tests/sandbox_site/rmx_sandbox.py` are imported by the
  whole suite, so "every test that imports a changed module" would be a branch full suite, which
  the procedure forbids. The lead named the two sets: T0.1' in [[#t0-1-verify]], T0.2 + 29.4b in
  [[#t0-2-verify]]. Neither is the full suite; that stays the minor-release gate.
  {#r0-verify-sets}

## T0.1 Skip gate and checkout identity (bug-215, bug-155) {#t0-1}

**bug-215.** This sweep tracks it as one item. It is the defect the bug-212 notes call the
SkipGate UNPINNED skip (ch-bsd bug-212 r1 #m-4, carried as flag 8 of GREEN r2), and the plan
review's separate "SkipGate UNPINNED row" is the same defect (lead ruling, 2026-11-13). Closing
bug-215 closes it. {#t0-1-identity}

**bug-155 had two causes (probe 2026-11-13; second cause found by the r1 spec review). Both
have shipped fixes since; what T0.1' builds is the residual, below.**
1. **Namespace.** `tools/gmd/lint.py` `project_name()` takes the repo directory's basename as the
   id namespace when `.gmd/config.yml` has no `project:` key. The ADRs carry ids like
   `refmatrix/adr-0000-adr-overview`, so in any checkout not named `refmatrix`,
   `[[adr-0000-adr-overview]]` does not resolve. Probe (two `git archive` copies of `1cf3b9f`,
   main memory dir supplied): a dir named `refmatrix` 1 `dangling-doc`; `refmatrix-clone` 33;
   `refmatrix-clone` + `project: refmatrix` 1. The remaining 1 was `[[agent-brief-bsd-pop-r1]]`,
   fixed by the lead at `35e1e0d` ([[#ruling-o4]]).
2. **Memory dir.** A clone has no memory dir under its own slug. As probed on 2026-11-13,
   before `44d1a34`:
   - `scripts/lint-gmd.sh` added `$HOME/.claude/projects/<slug>/memory` only if it existed.
   - `test_the_repo_scope_is_clean_under_the_stricter_gate` copied that same slug's dir into a
     decoy HOME, and copied nothing when it was missing.
   - No `~/.claude/projects/-Volumes-littlebig-refmatrix*/memory` exists. Over the script's scope
     in this clone with no memory dir, lint gives 1,084 errors (1,079 `dangling-doc`): every
     memory-id ref dangles. `project: refmatrix` alone removes only 32 of them.

   The fix is [[#ruling-o6]]: fall back to the memory dir of the clone's **origin** path. Every
   littlebig clone's `origin` is `/Users/tholley/claude_tools/refmatrix`.

{#t0-1-bug155-cause}

**What shipped on 2026-11-14, and what is left (re-read at `f45b9a3`; [[#amend-1]]).**
- **Cause 1 is fixed.** `.gmd/config.yml` declares `project: refmatrix` (`988e96d`). That is
  R1.3, verbatim.
- **Cause 2 is fixed for the case it was reported in, an absent own-slug dir.**
  `scripts/lint-gmd.sh:49-64` falls back to the origin checkout's memory dir and says so on
  stderr (`44d1a34`, Q18 a). `tests/test_gmd_lint_requires_version.py:125-140` repeats the slug
  and origin logic in Python to fill its decoy home.
- **The residual has two cases.** Both copies look at one directory per checkout and follow the
  origin one hop only.
  1. **A clone of a clone (live today; ch-bsd r1 S1).** A clone whose origin is another clone
     reaches a slug with no memory dir, and the fallback stops there. The gate then prints
     `no memory dir for <clone> or its origin <clone>; memory-id refs will dangle` and exits 1
     on every memory id: 1,234 `dangling-doc` errors in the reviewer's own clone at `5b04e2d`
     ([[bsd-spec-t0-fresh-r1-5b04e2d]]). Of the 33 `refmatrix-*` clones on littlebig, 23 have
     the dev tree as origin, 8 have another clone, and 2 have none. Every review clone cut from
     an author's clone is of this kind.
  2. **An empty own-slug dir (not live today).** Both copies test only that the directory
     exists (the script's `-d` test, the test's `is_dir()`). An own-slug `memory/` that exists
     and is empty is taken as the memory dir, no fallback is tried, and every memory-id ref
     dangles. This is the case r2 s-1 named ([[#rev-r2]]). No
     `~/.claude/projects/-Volumes-littlebig-refmatrix*` directory exists on the dev machine
     (2026-11-15), so a test has to plant one, and it plants it in a decoy home.
- **The two copies also differ**, from each other and from R1.4. The script accepts only an
  absolute origin that holds a `.git` directory and keeps the logical path (`cd … && pwd`); the
  test `resolve()`s it. Neither takes a relative origin or a `<path>/.git` origin, and neither
  checks that the origin's dir is populated.

{#t0-1-residual}

**Two clone layouts, and bug-253 (2026-11-15; ruling L121, [[plan-review-2026-11-13#lead]]).**
Both layouts are in use on littlebig: a clone whose `.venv-eval` is a symlink to the main tree's,
and a clone with none, run with the main tree's interpreter and `PYTHONPATH=<clone>/src`.
- **bug-215 belongs to the symlinked layout.** `is_dir()` is true there, the pins are dropped,
  and every run exits 1 (AC-1.1).
- **In the no-venv layout the 19 pins hold** (stage 0: 19 skips, all pinned,
  [[task-29.4-r0-durations#run]]), and a different defect shows: **bug-253**. Six test files need
  `<checkout>/.venv-eval/bin/rmx` and `scripts/lint-gmd.sh` needs `…/bin/python`
  ([[#t0-2-bug253]] lists them). They **error or fail** when it is missing: 127 setup errors and
  2 failures in stage 0 ([[task-29.4-r0-durations#digest]]). Those are not skips. The allowed-skip set does not cover
  them and must not (R0.5).
- **Owner.** L121 gives bug-253's fix, and `lint-gmd.sh`'s dev-interpreter lookup with it, to
  the stage-2 branch ([[#t0-2-bug253]]), "or the next RED touching those files". T0.1' is the
  first branch after that ruling to edit `scripts/lint-gmd.sh`. It does not take the lookup:
  L122 keeps `DEVPY` with stage 2. T0.1's own ACs run where the script already reaches lint
  (the symlinked clone), and AC-1.4 runs only the seven pinned files.
- **Until bug-253's fix merges**, a no-venv clone run carries its E lines:
  `AssertionError: dev rmx missing at <clone>/.venv-eval/bin/rmx`, a `FileNotFoundError` on the
  same path, and `scripts/lint-gmd.sh did not run its checks (exit 2)`. They are bug-253,
  matched by E line (R0.2), not new findings. T0.1's new script-level test adds no other line
  to that list: it asserts that the gate ran before anything else, with that same message
  ([[#ac-1-5]]; ch-bsd r1 M1).
- **The 18 venv pins are stage-1 scope and are retired in stage 2** (ch-bsd r1 M5; ruling
  L122, ruled before stage 1 because T0.1' builds R1.1 first). bug-253's helper covers every
  file that looks up the dev `rmx`, the six venv-pinned files included. Once a pinned file uses
  the helper it no longer skips in a no-venv clone, and its pin goes in the same commit (R1.2:
  the pins follow the tests). So T0.1' builds R1.1's venv condition as written, AC-1.2 and
  AC-1.4 are met at stage 1 and stand as stage-1 evidence, and stage 2 then removes the 18
  pins and R1.1's venv half ([[#t0-2-bug253]]).

{#t0-1-bug253}

**The pinned skips and their actual reasons (read at `1cf3b9f`; re-read at `f45b9a3`,
unchanged).** `_CLONE_ONLY_SKIPS`
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
   The first condition lives until stage 2 retires the 18 pins it guards ([[#t0-1-bug253]]); the
   hooks condition stays. {#r1-1}
2. **R1.2 The gate matches the reason exactly.** Each pinned entry's value is the test's own
   `reason=` string, verbatim from [[#t0-1-skip-reasons]]. The two `_CLONE_*` description
   strings stop being match keys (they may stay as comments). `SkipGate` treats a skip as pinned
   only when its nodeid is allowed and its reason, after stripping pytest's `Skipped: ` prefix,
   is **equal** to the pinned value. A pinned nodeid that skips for any other reason is reported
   `SKIPPED-UNPINNED`, with both reasons. A test whose `reason=` text changes must update its
   pin in the same commit. {#r1-2}
3. **R1.3 (shipped; dropped as a requirement, [[#amend-1]]).** The GMD id namespace does not
   depend on the checkout's directory name: `.gmd/config.yml` declares `project: refmatrix` since
   `988e96d`, and `tools/gmd/lint.py` was not changed. T0.1' builds nothing for it. M1.3 keeps
   it pinned. {#r1-3}
4. **R1.4 One resolver replaces the shipped fallback ([[#ruling-o6]], r2 s-1/m-2;
   [[#amend-1]]).** The bash fallback in `scripts/lint-gmd.sh` (`44d1a34`; lines 49-64 at
   `f45b9a3`) and the copy of its logic in `tests/test_gmd_lint_requires_version.py` (lines
   125-140) are both removed. One resolver decides for both, with the populated-directory check
   and the canonicalisation that neither copy has ([[#t0-1-residual]]):
   - **One resolver.** A stdlib-only Python helper, `resolve_memdir(root, home)`, in a new
     `scripts/gmd_memdir.py`, takes the checkout root AND the home dir as explicit arguments and
     returns the chosen dir (or none) plus the one-line note to print. `scripts/lint-gmd.sh`
     calls it with its own `$HOME` and keeps no slug or origin logic of its own
     ([[#ac-1-7]]). It runs the helper under `python3`, as it runs the linter, and never under
     `$DEVPY`: the resolver must not depend on the dev venv, or it would inherit bug-253 (ch-bsd
     r1 M1). The repo-scope test imports it and calls it **in-process** with
     `RMX_SANDBOX_REAL_HOME` (a read-only existence check). No child process is ever given the
     real `HOME`.
   - **"Present" means populated.** The own-slug dir `<home>/.claude/projects/<own slug>/memory`
     counts only if it holds at least one `*.md` file. Claude Code creates an empty `memory/` for
     any session whose cwd was the checkout, so an empty dir is not a memory dir.
   - **Fallback, one origin at a time.** If the own-slug dir is absent or empty, the resolver
     reads the checkout's `git remote get-url origin` and canonicalises it before slugging:
     - a URL with a scheme or an scp-style `host:path` (`ssh://`, `https://`, `file://`,
       `git@…:`) is non-local, and the walk stops;
     - a relative path is resolved against the checkout it was read from;
     - the path is `resolve()`d (symlinks, `..`, trailing `/`), and a trailing `.git` component
       or suffix is stripped.

     The canonical path is slugged as today (`/` and `_` → `-`). If that path's memory dir holds
     at least one `*.md`, it is used for the lint scope and the parity `--memory-dir`.
   - **The walk follows local origins hop by hop** (ch-bsd r1 S1; ruling L122). A clone of a
     clone has an origin whose slug has no memory dir either. So when a local origin's dir is
     absent or empty, the resolver reads **that** checkout's origin and tries again. The walk
     stops at the first checkout whose slug has a populated dir, which is the one used. It also
     stops, with no dir, at:
     - a checkout with no origin, or a path that is not a git checkout;
     - a non-local origin;
     - a **cycle**: a canonical path already visited (two clones that name each other);
     - the **bound**: 5 origins followed from the checkout being linted.
   - **Loud, and the line names the chain.** Whenever the own-slug dir is not the one used, the
     script prints one stderr line. It names every checkout tried, in order, each with why it
     was passed over (`absent` or `empty`), and then either the dir used or why the walk
     stopped (`no origin`, `not a checkout`, `non-local origin`, `cycle`, `bound of 5`): for
     example
     `own memory dir <path> is empty; origin <path> absent; using origin <path>`. When no dir
     qualifies, the line also says that memory-id refs will surface as `dangling-doc`. The
     shipped lines (`lint-gmd: no memory dir for <root>; using its origin's …`) carry no reason
     word and at most one origin, and no test pins their wording at `f45b9a3`.
   - **The test copies what the resolver names.** It copies exactly that dir into its decoy HOME,
     under the slug of the checkout the resolver chose (the own slug, or the slug of the origin
     the walk stopped at). The child, running with the decoy HOME, walks the same origins, finds
     nothing at the slugs before it, and resolves the same content. {#r1-4}
5. **R1.5 Exit codes are part of every recorded run.** [[tdd-governance#rules]]
   (`workflow/TDD_GOVERNANCE.md`) gains one bullet: "A recorded run (RED, GREEN, suite) quotes the pytest exit code and
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
- **AC-1.5 (bug-155's residual, through the real script, in a clone; [[#amend-1]]).** Two REDs,
  one per case of [[#t0-1-residual]]. Both run the real `./scripts/lint-gmd.sh` on the checkout
  with a decoy `HOME`, and nothing is written to the real home. The clone has a symlinked
  `.venv-eval` (the script needs `<checkout>/.venv-eval/bin/python` to reach lint at all,
  [[#t0-1-bug253]]), is not named `refmatrix`, and its origin chain reaches a checkout with a
  populated memory dir within the bound: the main tree, directly or through other clones. (At
  approval this read "origin = the main tree"; ruling L122 relaxed it.)
  - **The gate ran, first** (ch-bsd r1 M1). Before any other assertion, every test that runs
    the script asserts that the gate ran, with the message of `assert_gate_ran_clean`'s first
    clause (`scripts/lint-gmd.sh did not run its checks (exit <n>) …`). In a no-venv clone
    before stage 2 the E line is then bug-253's own, already listed in [[#t0-1-bug253]].
  - **Case 1, a clone of a clone.** `test_the_repo_scope_is_clean_under_the_stricter_gate` is
    **RED at base** in a clone whose origin is another clone: stderr holds
    `no memory dir for <clone> or its origin <clone>; memory-id refs will dangle`, the exit is
    1, and the E lines are the memory-id `dangling-doc` errors, which R0.2 quotes by count and
    first lines. After R1.4 it passes there, and the fallback line names both hops.
  - **Case 2, the empty own-slug directory.** A new test in
    `tests/test_lint_gmd_memdir_fallback.py` gives the decoy an empty `memory/` under the
    checkout's own slug, and the populated dir the resolver names for this checkout (read
    through `RMX_SANDBOX_REAL_HOME`, as the repo-scope test reads it) under that checkout's slug.
    **RED at base:** the shipped script takes no fallback, because its `-d` test is satisfied by
    the empty dir; it exits 1 on the memory-id `dangling-doc` errors, and stderr carries no
    fallback line. The new test needs the resolver to build its decoy, so as a pytest node it
    fails at base on the missing module, like AC-1.6's cases. Its stated-reason RED is
    recorded in two parts (ch-bsd r2 M1; ruling L123):
    - **The base run.** The RED author runs the shipped script, the real `scripts/lint-gmd.sh`,
      at T0.1's base in a symlinked clone, against the same decoy. The log (R0.3) quotes the
      exit code and both E lines (R0.2). It is corroborated by ch-bsd's r1 probes at `5b04e2d`,
      which used a copy of the script with `DEVPY` re-pointed and are not this record.
    - **The node's own RED is a mutation RED.** After GREEN the node is run under M1.6. It
      goes red on its own assertions: no fallback line, and the memory-id `dangling-doc`
      count. The summary quotes those E lines as this node's recorded RED for the intended
      reason. The lead accepts a mutation RED for this one node (L123): a stated-reason node at
      base would need a third copy of the slug logic, which is what R1.4 removes.
  - **After R1.4**, in both cases, `./scripts/lint-gmd.sh` prints the fallback stderr line (with
    `empty` in case 2, with the chain in case 1), and its error count and E lines **equal the
    main tree's at the same sha**. The tests pass when the main tree's gate exits 0 at that sha,
    which is the same precondition R7.4 states. Dev master's gate was green at `35e1e0d`
    ([[#ruling-o4]]), red again on two forward-linked anchors, and green at `b816a08`. If the
    main tree is red at the T0.1 base, equality is still asserted, the failing E lines are
    reported as gate drift, and they are not T0.1's.
  - **The absent case with a direct origin is a characterization check, not a RED.** In a clone
    whose origin is the main tree, the repo-scope test passes at base, through the shipped
    fallback, and passes after R1.4, through the resolver.
  - **In a checkout with no usable origin** (the main tree: its origin is not a local path) the
    new test asserts the other branch, which is AC-1.6's non-local case through the script: the
    "no memory dir" line, and exit 1 on `dangling-doc`. It does not skip (R0.5).
  - Any other E line is a new finding, not an assumed residue.

  {#ac-1-5}
- **AC-1.6 (the resolver's cases).** A unit test of `resolve_memdir` with a tmp home and fixture
  checkouts covers:
  - own-slug dir holding ≥ 1 `*.md`: own dir chosen, no fallback line;
  - own-slug dir **empty** (exists, no `*.md`): falls back to the origin's dir, and the line says
    `empty`;
  - own-slug dir absent, origin local with a populated dir: fallback taken, and the line says
    `absent`;
  - origin given as a relative path, as a path with a trailing `/`, and as `<path>/.git`: all
    resolve to the same canonical origin and slug;
  - origin non-local (`git@host:repo`, `https://…`, `file://…`): no fallback, the "no memory dir"
    line, and through the script the memory-id refs surface as `dangling-doc` (exit 1);
  - **chained** (ch-bsd r1 S1): checkout → clone A → clone B, where only B's slug has a
    populated dir. B's dir is chosen, and the line names A as `absent` and B as used. The same
    with A's dir present and empty: the line says `empty` for A;
  - **cycle**: clone A's origin is clone B and B's is A, and neither slug has a populated dir.
    The resolver returns no dir, the line says `cycle`, and the call returns (it does not
    loop). The test runs with the bound intact and under a wall deadline (R0.4), so a broken
    guard fails on the message and a broken guard plus a broken bound fails on the deadline
    (ch-bsd r2 M2);
  - **bound**: a chain of 6 local origins where only the sixth has a populated dir. No dir is
    chosen and the line says `bound of 5`. With the populated dir at the fifth, it is chosen.

  {#ac-1-6}
- **AC-1.7 (one copy; static; ch-bsd r1 M2).** A test reads `scripts/lint-gmd.sh` as text and
  asserts three things: it invokes `scripts/gmd_memdir.py`; it holds no slug derivation (no
  `tr '/_'` and no other rewrite of a path into a slug); and it reads no origin (no
  `remote.origin.url`, no `remote get-url`). RED at base: the shipped block has both. This is
  the check AC-1.5 and AC-1.6 cannot make: a second, correct implementation in bash would pass
  both while the convergence had failed ([[feedback_converge_repeated_shapes]]). {#ac-1-7}
- **Mutations (each FAILS):**
  - M1.1: restore the single `is_dir()` switch (AC-1.1 and AC-1.2 red);
  - M1.2: match by nodeid only, or by substring (AC-1.3 red);
  - M1.3 (restated, [[#amend-1]]): delete `project:` from `.gmd/config.yml`, the shipped R1.3.
    In the clone, AC-1.5's empty-directory run goes red on the namespace `dangling-doc` errors,
    which R0.2 quotes by count. The mutation now pins a shipped fix; it is not T0.1's own RED;
  - M1.4 (restated, [[#amend-1]]): drop the origin fallback from the resolver. AC-1.5's
    empty-directory run goes red with the memory-id errors and the "no memory dir" line, and so
    does the absent-case repo-scope test;
  - M1.5: silence the fallback's stderr line (AC-1.6 red);
  - M1.6: treat an existing own-slug dir as present whatever it holds (AC-1.6's empty case
    red, and AC-1.5 case 2's node red with no fallback line and the memory-id `dangling-doc`
    count; that run is the node's recorded RED, [[#ac-1-5]]);
  - M1.7: skip origin canonicalisation (AC-1.6's relative and `.git` cases red);
  - M1.8 (ch-bsd r1 M2): put the slug derivation back into `scripts/lint-gmd.sh`, beside a
    working resolver call (AC-1.7 red; AC-1.5 and AC-1.6 stay green, which is the point);
  - M1.9 (ch-bsd r1 S1): follow one hop only (AC-1.6's chained case red, and AC-1.5's case 1);
  - M1.10 (ch-bsd r1 S1): drop the visited-path guard (AC-1.6's cycle case red: with the bound
    intact the walk ends on `bound of 5`, so the `cycle` assertion fails; it never hangs,
    R0.4);
  - M1.11 (ch-bsd r2 M2; ruling L123): drop the bound, or raise it (AC-1.6's bound case red:
    the sixth origin's dir is chosen).
  {#t0-1-mutations}

### Files {#t0-1-files}

`tests/conftest.py`, `tests/sandbox_site/rmx_sandbox.py` (`SkipGate`), a new
`tests/test_t0_skip_gate.py`, the seven test files in [[#t0-1-skip-reasons]] (only if a
`reason=` must change; the pins follow the tests, not the reverse),
`scripts/lint-gmd.sh` (the fallback block only; the `DEVPY` lookup is bug-253's,
[[#t0-1-bug253]]), a new `scripts/gmd_memdir.py`, `tests/test_gmd_lint_requires_version.py`,
a new `tests/test_lint_gmd_memdir_fallback.py`, `workflow/TDD_GOVERNANCE.md`,
`workflow/bug_registry.md` (rows bug-215, bug-155; the lead writes them). `.gmd/config.yml` is
no longer edited: R1.3 shipped, and only mutation M1.3 touches the file, and restores it. The
summary is `workflow/implementation_summaries/task-t0.1-skip-gate-memdir.md`.

### Verify set {#t0-1-verify}

Named by the lead (ruling L122; ch-bsd r1 M8), because conftest and `SkipGate` load in every
test and a branch full suite is not run ([[#r0-verify-sets]]):
- the seven pinned files of [[#t0-1-skip-reasons]];
- `tests/test_t0_skip_gate.py` and `tests/test_lint_gmd_memdir_fallback.py`;
- every `tests/test_gmd_lint*.py` and every `tests/test_*sandbox*.py` (at `f45b9a3`:
  `test_gmd_lint_requires_version.py`, and the seven `test_sandbox_*.py` files);
- every file a grep for `ALLOWED_SKIPS|SkipGate|lint-gmd|gmd_memdir` lists under `tests/`. At
  `f45b9a3` those are, beside files already named: `test_bug179_anchor_parity.py`,
  `test_bug216_rev4.py`, `test_bug216_scope_parity.py`, `test_bug230_repo_scope_gate.py` and
  `test_plan7_10_remedy_r4.py`. R0 re-runs the grep at the branch base and the summary lists
  what it found.

It is run in the clone layouts the ACs name: the symlinked clone for AC-1.1 and AC-1.5, a
no-venv clone for AC-1.4. Each run quotes its exit code (R0.3). {#t0-1-verify-body}

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

**Added by 29.4 (stage 2; [[#amend-5]]).** T0.2 shares its branch and its ch-bsd range with
29.4b, which closes bug-229: the reaper that fails the session ([[task-29.4-suite-health#r4]])
and the rule that test roots live under the sandbox root ([[task-29.4-suite-health#r5]]). Their
requirements, acceptance and mutations are 29.4's ([[task-29.4-suite-health#ac-5]]). Both parts
edit `tests/conftest.py` and `tests/sandbox_site/rmx_sandbox.py`, which is why they are one
branch ([[task-29.4-suite-health#order-pairs]]). T0.2's own requirements R2.1 to R2.3 stay about
bug-170, 168 and 127. {#t0-2-reaper}

**bug-253 lands here (ruling L121, contradiction 1; [[plan-review-2026-11-13#lead]]).** Stage 0
showed that a clone with no `.venv-eval` errors in 127 tests and fails 2 more for one cause
([[#t0-1-bug253]]). L121 fixes it at the root and not with a new run-tier signal, and names the
owner: this stage-2 branch (T0.2 + 29.4b), or the next RED that touches those files.
- **What is owned.** The fix is the bug-253 row's own text: the fixtures resolve the dev `rmx`
  from the bin directory of `sys.executable`, with the checkout's `src` on `PYTHONPATH` for the
  child, through one helper the files share. `scripts/lint-gmd.sh`'s dev-interpreter lookup
  (`DEVPY`, line 23 at `f45b9a3`) is in the same bug and has the same owner (L122: it stays
  here, not with T0.1').
- **The helper covers every file that looks up the dev `rmx`** (ch-bsd r1 M5; ruling L122), so
  that one definition of "the dev rmx" is left, not two. At `f45b9a3` eleven files name it;
  the helper covers them, and `test_bug241_r3_l114.py` through its import;
  `test_repo_hooks_in_sync.py` keeps its hooks pin (ch-bsd r2 M3; ruling L123). The eleven,
  under `tests/`:
  - five that error or fail in a no-venv clone: `test_bug240_ingest_file_arg.py:33`,
    `test_bug240_ingest_file_arg_mcp.py:38`, `test_bug241_r2_l112.py:46`,
    `test_bug241_rule_docs_reingest.py:46`, `test_scanorder_r2_l120.py:57` (`DEV_BIN`);
  - six that skip there, holding the 18 venv pins: `test_brief_real_daemon.py:23`,
    `test_grep_argv_order_e2e.py:48`, `test_grep_count_rows_e2e.py:27`,
    `test_grep_evidence_verified.py:39`, `test_grep_learning_replay.py:66`,
    `test_grep_no_flag_bundle.py:65`.

  `test_bug241_r3_l114.py` does not name the path; it errors through the fixtures it imports
  from `test_bug241_r2_l112`. `test_repo_hooks_in_sync.py`, the seventh pinned file, never
  looks up the dev `rmx`, so the helper does not apply to it. Eight more files mention
  `.venv-eval` without a lookup (conftest, three symlink fixtures, four docstrings or
  comments). R0 re-runs the grep at the branch base and the summary lists what it found.
- **Stage 2 retires the 18 venv pins and R1.1's venv half.** A pinned file that uses the
  helper no longer skips for a missing checkout venv, so its `skipif` and its pin go in the
  same commit (R1.2: the pins follow the tests). When all six are done:
  - `_CLONE_ONLY_SKIPS` holds one entry, the hooks test, under R1.1's hooks condition;
  - R1.1's venv condition guards nothing and is deleted, and AC-1.2's layouts assert the
    hooks-only set;
  - `test_the_tool_itself_is_the_one_that_scrambles` keeps a skip for a missing `rg` only. It
    is not pinned, so a machine without `rg` fails the session there, which is correct;
  - AC-1.4's 19 pinned skips stand as stage-1 evidence and are not re-asserted.

  The stage-2 summary quotes a run of the seven pinned files of [[#t0-1-skip-reasons]] in a
  no-venv clone: no error from a missing dev `rmx`, and one skip, the hooks pin, reported as
  pinned.
- **Afterwards** the five errored files have real durations for the first time. Stage 0's
  weights understate them ([[task-29.4-r0-durations#weights-gaps]]), and L121 asks for the
  re-weighting after this fix.

{#t0-2-bug253}

### Requirements {#t0-2-requirements}

1. **R2.1 bug-170: the hooks test renders with the real home, read-only.**
   `tests/test_repo_hooks_in_sync.py::test_installed_hooks_match_generated` renders the generator
   with a home equal to the real `HOME`, captured before the 23.0 sandbox redirect. It does
   this with no `src/` change (ch-bsd r1 M6; ruling L122): `hooks.check(project_root)` takes no
   home parameter (`hooks.py:737`) and gets none. The test restores `HOME` for that one render,
   and where only the hooks dir matters it uses `RMX_CLAUDE_HOOKS_DIR`, which
   `search_hooks.hooks_dir()` already reads (`search_hooks.py:399-402`).

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

- **AC-2.1 (bug-170).** With `RMX_CLAUDE_HOOKS_DIR` pointed at a tmp copy of the installed
  hooks dir with one script byte changed, the comparison reports `script … differs`. This proves
  the test looks at real content. In the main tree (T0.7), the test passes under [[#r7-4]]'s hook precondition: the
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

On the same branch, not by this spec's requirements: 29.4b's files
([[task-29.4-suite-health#files]]: conftest, `rmx_sandbox.py`, `tests/test_daemon_reaper.py`,
`tests/test_tmp_root_census.py`, the 28 files that call `spawn_daemon_subprocess`), and
bug-253's ([[#t0-2-bug253]]: the eleven test files that name the dev bin, `test_bug241_r3_l114.py`
through its import, their shared helper, the 18 pins and R1.1's
venv condition in `tests/conftest.py`, `tests/test_t0_skip_gate.py` for AC-1.2's layouts, and
the `DEVPY` lookup in `scripts/lint-gmd.sh`). {#t0-2-files-shared}

### Verify set {#t0-2-verify}

Named by the lead (ruling L122; ch-bsd r1 M8), because conftest, the sandbox and the reaper
load in every test and a branch full suite is not run ([[#r0-verify-sets]]):
- T0.2's own files, the eleven files that name the dev bin, and `test_bug241_r3_l114.py`
  ([[#t0-2-bug253]]);
- every file stage 0's tier rule puts in run tier (b): 126 files, 2,065 s serial
  ([[task-29.4-r0-durations#tiers]]);
- the sandbox tests (every `tests/test_*sandbox*.py`) and the reaper tests
  (`tests/test_daemon_reaper.py`, `tests/test_tmp_root_census.py`).

It is one run at a time, like any other ([[orchestration#one-suite]]). It is not the full
suite: run tiers (a) and (d) are not in it. {#t0-2-verify-body}

## T0.3 Load-dependent flakes (bug-130, bug-190, bug-091) {#t0-3}

All three pass alone and fail under suite load, and none is root-caused. A flake fix with no
reproducer cannot be told apart from luck. So the bands below are fixed before any fix is
written ([[feedback_go_no_go_ranges_not_predrop]]). {#t0-3-lead}

**Two more rows (stage 2; [[#amend-4]]).** bug-228 and bug-231 fail under load in the same way,
and they run on this harness with these bands. What is built for them is 29.4's text
([[task-29.4-suite-health#r3-bug228]], [[task-29.4-suite-health#r3-bug231]]); 29.4c, which holds
it, shares T0.3's branch and ch-bsd range ([[task-29.4-suite-health#order-pairs]]). T0.3's own
requirements R3.1 to R3.4 and mutations M3.1 to M3.4 stay about bug-130, 190 and 091. AC-3.1's
record is kept for all five rows ([[task-29.4-suite-health#ac-6]]), and the trial bounds of
[[#t0-3-bound]] apply to each of the five. {#t0-3-two-more}

**The bug-228 leg breakdown comes from this harness (ruling L121, contradiction 3;
[[plan-review-2026-11-13#lead]]).** [[task-29.4-suite-health#r3-bug228]] asks R0 to measure one
failing bug-228 run and say which leg spent the time. Stage 0 had no failing run: bug-228 passed
(call 5.28 s), and so did bug-231 (5.21 s against 8.0)
([[task-29.4-r0-durations#digest-bug228-231]]). So the measurement is taken from bug-228's base
trials here. The first failing trial is the run that is broken down by leg, and the breakdown
goes in the summary before any fix is written. If no trial fails at any level, there is no
failing run to break down. Then the "otherwise" branch of
[[task-29.4-suite-health#r3-bug228]] is built, the split, which does not depend on where the
time went, and the product row records "not reproduced in N trials at levels 3/5/8" (ch-bsd r1
M7; ruling L122; the sentence is in 29.4). {#t0-3-bug228-legs}

### The load harness and bands (pre-registered) {#t0-3-bands}

- **R0 builds the harness's list. Done, as 29.4's stage 0** ([[task-29.4-suite-health#r0]]).
  No committed full-suite log carried durations (the 0.82.0 log has none). So the first step
  was one full-suite run in a clone with `--durations=0` (every setup, call and teardown phase),
  logged per R0.3. It ran on 2026-11-14 at `4c6a0c6` in `/Volumes/littlebig/refmatrix-r0`:
  `workflow/review-output/task-29.4/r0-serial.log`, exit 1, 5,041 collected, 4,891 passed / 4
  failed / 127 errors / 19 skipped, all 19 pinned ([[task-29.4-r0-durations#run]]). The phases
  are summed by file, and the 25 files with the largest totals, each with its total, are
  [[task-29.4-r0-durations#top25]]. That is the harness's list, written before trial 1, and it
  does not change afterwards. T0.3 does not run the suite again for it.
  - The re-weighting L121 asks for after bug-253 feeds `tests/shard_weights.json` for 29.4's
    runner. It does not reopen this list. None of the five files stage 0 understated is among
    the 25.
  - Every file a trial's cap needs has a stage-0 weight: the 25, and the five target files
    (`test_catalog_measure.py` 35.68 s, `test_rerank_budget_real_clients.py` 45.35 s,
    `test_watch.py` 3.28 s, `test_plan4_remedy.py` 37.25 s, `test_task21_1_recall_skip.py`
    8.71 s; `tests/shard_weights.json`).

  {#t0-3-r0}
- **Harness.** The target test runs in the clone while 3 concurrent `pytest` processes run those
  files. Each process is sandboxed as usual. One harness run gives one trial. {#t0-3-harness}
- **Per-trial wall cap.** Every trial runs under a cap derived from R0: `max(3 × T, 300 s)`, where
  `T` is the R0 summed duration of the files that trial's processes run (the target's file
  included). Hitting the cap counts as a **failure**, recorded as `hang`, with `ps -o
  pid,etime,time,command` and `lsof -p <pid>` of every still-running process taken before it is
  killed.

  **A trial's outcome is the TARGET test's own** (r3 m-1):
  - pass or fail is the target test's result, with its E line;
  - a cap hit counts as the row's failure (`hang`) only if the target test had **not** finished,
    as the `ps` record shows. A hang counted this way counts toward the reproducer in the base
    trials and fails a fix attempt, like any failure;
  - if the target test finished and only a background load process hung, the trial is **void**.
    It is recorded (with the `ps`/`lsof` record), it is not counted, and it is re-run;
  - at most 3 voids per load level. A fourth void at that level stops the level: it is reported
    as **noisy** in the summary, with all its trial records, and the row stays at its prior status
    (no reproducer is declared from that level, and a fix attempt run there neither passes nor
    fails). {#t0-3-cap}
- **Reproducer found:** ≥ 3 failures in 10 trials at base, each with the row's E line. If fewer
  than 3 fail, raise the load to 5 and then 8 concurrent processes. The first level that reaches
  3 out of 10 is the reproducer. {#t0-3-band-found}
- **Fix proven:** **45 consecutive passes** on the same harness at the same level. A 3/10
  reproducer's 95% Clopper-Pearson lower bound on the failure rate is 0.067. At that rate,
  0.933^45 ≈ 0.044 < 0.05, so 45 straight passes is unlikely by luck even at the weakest rate
  the reproducer admits. Any failure in the 45, a hang included, means that fix attempt did not
  hold. {#t0-3-band-fixed}
- **At most two fix attempts.** Each attempt gets its own fresh run of 45. If the first attempt
  fails, one second attempt is allowed. If the second also fails, T0.3 keeps only R3.4's
  diagnostic for that test, reverts the rest of both attempts (the revert commit names them), and
  sets the row to `deferred: diagnosed-loud, <both runs' counts>; review <date>`, in 29.1's
  grammar ([[#amend-6]]; [[task-29.1-registry-triage#r1-other-writers]]). No third attempt is
  made inside T0. {#t0-3-attempts}
- **Not reproduced:** fewer than 3 failures in 10 at every level. The test gains only R3.4's
  diagnostic. The row reads `deferred: diagnosed-loud, <trial counts>; review <date>`
  ([[#amend-6]]). It does not count as closed. In T0.7's suite it is handled by
  [[#ruling-o7]]. {#t0-3-band-none}
- **Bounded by count and by time.** Per bug, at most 30 base trials (3 levels × 10) and 90
  post-fix trials (2 attempts × 45), plus the one shared R0 durations run, each trial under its
  wall cap. The summary records each trial's wall time and outcome (pass, fail, hang).
  {#t0-3-bound}
- **Live-socket exposure.** Concurrent suites multiply the suite's reach to live rmx sockets
  (bug-088, deferred by the user). T0.3 adds no mitigation. It records the conftest live-socket
  recorder's count for the R0 run and for one trial at each load level, so the multiplication is
  measured, not assumed. Stage 0's summary carries no such count, but the run's recorder log
  exists: `/Volumes/littlebig/refmatrix-r0/workflow/review-output/live-socket-touches.log`, 41
  lines, written inside the stage-0 run (ch-bsd r1; ruling L122). That is the R0 count. T0.3's
  summary quotes it, with the file's line count re-read on the day. {#t0-3-sockets}

### Requirements {#t0-3-requirements}

1. **R3.1 bug-130.** `tests/test_catalog_measure.py::test_rewrite_bytes_is_the_median_of_the_runs`
   asserts `failed == 0` before it indexes `rewrite_bytes_all`. The assertion message carries the
   failed store's captured error, so a failure is never reported as a bare `KeyError`. The
   reproducer's captured error decides the fix:
   - a harness defect in `eval/catalog_maint/measure_catalogs.py` is fixed there, under the
     45-pass band;
   - a product defect gets its own registry row with the error. Its fix is NOT absorbed into T0
     ([[#ruling-o5]]). bug-130's row then reads
     `deferred: diagnosed-loud, <trial counts>; review <date>` ([[#amend-6]]), linked to the new
     row, so a firing in T0.7's suite is handled by [[#ruling-o7]]. {#r3-1}
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
  of 10 with E lines (hangs marked), each fix attempt's run of 45, and the outcome (fixed, or
  `diagnosed-loud` after two failed attempts with the revert commit), or the `not reproduced`
  band with all the counts. {#ac-3-1}
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

On the same branch, not by this spec's requirements: 29.4c's files
([[task-29.4-suite-health#files]]: `tests/timing.py`, `tests/test_plan4_remedy.py`,
`tests/test_task21_1_recall_skip.py`, the wall-clock census and its allow list, and the files
[[task-29.4-suite-health#r3-scope]] selects). {#t0-3-files-shared}

## T0.4 W2-a: the plan-6 remedy {#t0-4}

Source: [[bsd-plan6-deferrals-docs-benchmark-r1-e0b7df6]] (DIRTY, "may NOT flip"). T0.4 is
stage 3 ([[#amend-3]]): it starts from the `master` that holds stage 2. R0
(2026-11-13, at `1cf3b9f`) found what follows. Every row was re-read on 2026-11-15 at `f45b9a3`
and still holds; the line numbers are that sha's:
- `duckdb_view.py`, both of its tests and `RMX_READ_VIA_DUCKDB` are still present
  (`store.py:1368-1376`; the `_read()` branch is `:2517-2531`, the close is `:2546-2552`);
- `wrapper_paths()` is still present (`search_hooks.py:405`; `render_scripts(wrappers=)` is
  `:418`, and `hooks.py:617` still records `wrappers=`);
- the session-ingest "Phase A" docstring (`session_ingest.py:3-5`), `vectors.py:14` "for now" and
  `cli.py:6199` "for now" are still present;
- the `_op_embed` cancel return still drops `degraded` (`daemon.py:6277`);
- "Called after the SQLite commit" is still present (`store.py:1454`);
- `BANNED` is still guarded by `len(BANNED) >= 4` (`tests/test_deferrals_clean.py:70`);
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
5. **R4.5 #s-3 and todo G7: phrase families, not literals.** Of the three sites, T0.4 fixes
   one and allow-lists two ([[#r4-5-derive-hold]]):
   - `cli.py`'s `-v` docstring says "refused, falls back to rg";
   - the landed claim in `session_ingest.py` (line 5, "later phases") and `vectors.py`'s "for
     now" (line 14) are **not edited here**. Each gets an allow-list entry.

   Then widen `test_deferrals_clean.py` from five literals to phrase families: `for now`,
   `in v1`, `later phase(s)`, `eventually`, `when needed`, `not yet`, and `TODO` with no plan
   id. It keeps an explicit allow-list of reviewed exceptions, each with a reason. The meta-test
   asserts the phrase set, not `len(BANNED)`. G7's five named docstrings (`ingest_gmd`, `store`,
   `duckdb_view`, `embedder`, `sync`) are re-checked, and the todo row is updated. {#r4-5}

   **The two pass-module lines are allow-listed, not edited (ruling L122; ch-bsd r1 S2).**
   `session_ingest.py` (pass `sessions`) and `vectors.py` (pass `embed`) are derive pass
   modules (`_DERIVE_PASS_MODULES`, `store.py:889`).
   - **Why not here.** The pass hash reads raw bytes (`store.py:1047-1090`), so a docstring
     edit to either file flips its pass on every fleet store.
     [[task-29.4-suite-health#files-src-note]] forbids it, and
     [[task-29.4-suite-health#ac-15]] checks that the seven pass modules are byte-identical from
     29.4's base to stage 5.
   - **The entries.** `test_deferrals_clean.py`'s allow-list gains exactly two:
     `src/refmatrix/session_ingest.py`, line 5, phrase `later phases`; and
     `src/refmatrix/vectors.py`, line 14, phrase `for now`. Each carries the reason ("derive
     pass module: the edit is made by 29.2's R7 release") and its owner,
     [[task-29.2-mypy-gate#ac-29]].
   - **Each entry is self-expiring.** The guard fails when an entry's line no longer holds its
     phrase, naming the entry. So the release that fixes the docstring must delete the entry in
     the same commit, and an entry cannot outlive what it excuses.
   - **Who makes the edits.** 29.2's R7 makes the derive hash ignore docstrings. Its release
     makes both edits and deletes both entries; that is an AC there, not a note here
     ([[task-29.2-mypy-gate#ac-29]]).
   - **Nothing else is held.** A scan of the seven pass modules for the phrase families and
     `TODO` at `f45b9a3` finds only these two lines, so G7's re-check of the `ingest_gmd` and
     `embedder` docstrings has no edit to make. If R0 finds one at the branch base, it is
     raised to the lead, not made.
   - **Plan-6.** The lead accepts that #s-3 closes with these two named, owned exceptions
     ([[#ac-4-close]]).

   {#r4-5-derive-hold}
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
  and the guard goes red. M4.5c (ruling L122): the guard is run on a tmp copy of the tree in
  which `vectors.py` line 14 no longer holds `for now`, with the allow-list unchanged, and it
  goes red naming the stale entry; no pass module in the checkout is edited for it. M4.5d: an
  allow-list entry for a pass module other than the two named in [[#r4-5-derive-hold]] makes
  the meta-test go red. It allows at most those two, so 29.2's deletion of both keeps it green
  ([[task-29.2-mypy-gate#ac-29]] then allows none). M4.6 drops `degraded` from the cancel return, and a test of that return
  goes red. M4.4 (if R4.4 adds its test): the `memory_partition` warning is not logged, and that
  test goes red. M4.8 (if R4.8 adds its check): drop a module from the required list, and the
  unimportable-module test goes red. {#ac-4-4}
- **AC-4.5.** The summary carries R0's per-finding table, covering #b-1, #b-2, #s-1, #s-2, #s-3,
  #m-1 to #m-5, G7 and G8. Every row is `holds → fixed by <commit>` or `closed by <evidence>`.
  #s-3 has one more form for its two pass-module lines: `allow-listed, owned by 29.2 AC-29`.
  {#ac-4-5}
- **Plan-6 closes** when the T0.4 ch-bsd round is CLEAN, as its `#execution` requires
  ([[plan-6-deferrals-docs-benchmark#execution]]). The two allow-listed lines of
  [[#r4-5-derive-hold]] do not hold it open: the lead accepted them as named, owned exceptions
  (ruling L122). {#ac-4-close}

### Files {#t0-4-files}

- Deleted: `src/refmatrix/duckdb_view.py`, `tests/test_duckdb_read_routing.py`,
  `tests/test_duckdb_parity.py`.
- Modified source: `src/refmatrix/store.py` (R4.1, R4.7; in no pass's set),
  `src/refmatrix/search_hooks.py`, `src/refmatrix/hooks.py`, `src/refmatrix/daemon.py`
  (`_op_embed`), `src/refmatrix/cli.py`.
- **Not modified:** `src/refmatrix/session_ingest.py` and `src/refmatrix/vectors.py`, nor any
  other derive pass module ([[#r4-5-derive-hold]]).
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
#s-6 (9.2/9.3) and #m-11 are plan-9's, and they closed with 21.1 (Ce-8). T0.5 is stage 3, after
T0.4 ([[#amend-3]]). R0 at `1cf3b9f` found what follows; every row was re-read on 2026-11-15 at
`f45b9a3` and still holds, at the same lines:
- `brief.parse_gmd` and the dead `_parse_evidence(…, ids_by_name)` are still present
  (`brief.py:654`, `:683`);
- 8.3's summary now exists (W1-d), so #s-6's plan-8 half is closed;
- #s-9 is closed by `a170ce9` (26.6 r1 remedy): it rewrote
  `tests/test_plan7_10_remedy_r4.py`'s test onto a real throwaway store, and the file's
  `monkeypatch.setattr` calls now target only `telemetry` and `verbs`. R0 confirms;
- r5's `_fake_plan()` helper does not exist in `tests/` (no match at `1cf3b9f`, none at
  `f45b9a3`);
- (2026-11-15) the `memory` verb carries `plan=` and `compile_scope=` and no `compile`
  (`verbs.py:2163-2186`), and the CLI still builds the plan itself behind `--compile`
  (`cli.py:13839`). R5.3 is unbuilt.

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
The persisted store is at `/Volumes/littlebig/longmemeval/.refmatrix` (present 2026-11-13 and
2026-11-15). It was built by 0.69.1. T0.6 is a lane in 29.4's order: it builds no `src/` and may
start any time after stage 1 ([[#amend-3]]). {#t0-6-lead}

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
4. **R6.4 Every number carries its provenance** ([[task-7.4-plan-7-longmemeval#requirements]],
   [[plan-7-longmemeval#execution]]):
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
  ch-bsd round is CLEAN and its four deferral rows carry the owner "no host plan; backlog (L33)"
  ([[#amend-8]]), an edit T0.7 makes ([[#r7-8]]). {#ac-6-3}
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

All three were re-read on 2026-11-15 at `f45b9a3` and hold at the same lines. Two registry
facts for R7.3's R0 to confirm: bug-095 is a row for the adoption leak and names `4fb5000`, and
the mock registry's `_FakePrivate` row reads graduated (2026-10-07). T0.7 is stage 5, on one
branch with 29.4d, and its two runs go through 29.4's runner ([[#amend-7]]).

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
   T0.8 and T0.7's own merge, and with them every stage of 29.4 up to stage 5
   ([[task-29.4-suite-health#ac-7]]). Preconditions:
   - **GMD gate green.** `./scripts/lint-gmd.sh` exits 0 at the run sha, in the main tree, before
     the run. If it does not, the failing E lines are reported to the lead as **gate drift** (a
     file that is not T0's, such as a report forward-linking an unmerged anchor), and R7.4 does not
     start until the gate is green. It is never filed as bug-155;
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
   - the lead is told before the run starts that the main tree is under a suite run, and for
     how long, so no one writes those paths during it. The length is the runner's: 17.3 min is
     projected for run tiers (a), (b) and (d) at 8 shards ([[task-29.4-r0-durations#bands]]),
     run tier (c) comes on top, and stage 4's first sharded run gives the measured number;
   - no branch switch: the main tree is shared ([[feedback_shared_tree_no_branch_switch]]).

   **Command ([[#amend-7]]).** `scripts/ptest.sh --tier all --name t0-clean-suite-<sha>`,
   29.4's runner ([[task-29.4-suite-health#r2]]), with no flag it does not already have. In the
   main tree it runs run tier (c) as well. The run is the directory
   `workflow/review-output/t0-clean-suite-<sha>/`: one log per shard, `failures.jsonl`,
   `outcomes.jsonl`, and `summary.txt` with each shard's command, exit code and counts, the sha
   and the load average. `outcomes.jsonl` holds one record per test node and phase
   ([[task-29.4-suite-health#r2-outcomes]]), and it is where AC-7.4 reads a `passed` node. This
   replaces the single `pytest -rA --junitxml … | tee` process, and its echoed exit code, that
   this requirement named at approval.

   **Clean** means all of:
   - pytest exit code 0;
   - 0 failed and 0 errors;
   - no SkipGate line;
   - collected = passed + pinned skips (0 in the main tree).

   Through the runner, "exit code 0" is every shard's and the runner's own, and the counts are
   the totals in `summary.txt`. 29.4 adds one line to the list for its own acceptance: no reaper
   line ([[task-29.4-suite-health#ac-7]]).

   The run directory is committed (`workflow/review-output/` is git-ignored, so it is added
   with `git add -f`). [[#ruling-o7]] is the only exception to "exit 0" ([[#r7-6]]). {#r7-4}
5. **R7.5 The clone twin (T0's trust proof; [[#amend-7]]).** The same sha runs the same
   command in a littlebig clone, as `--name t0-clean-twin-<sha>`. It exits 0 (or meets
   [[#ruling-o7]]), and its only skips are the pinned clone-only set, each reported as pinned.
   Its GMD gate takes R1.4's origin fallback (the stderr line is in the log), and
   `./scripts/lint-gmd.sh`'s error count in the clone **equals the main tree's** at the same sha.
   A clone is where every branch run and review round happens, so it is the checkout bug-215 and
   bug-155 failed in.
   - **The runner does not run run tier (c) in a clone**, and says so
     ([[task-29.4-suite-health#r2]], [[task-29.4-suite-health#ac-7]]). The files that carried
     bug-215 and bug-155 are tier (c) by 29.4's rule ([[task-29.4-suite-health#r1]]). Left
     there, the twin would show neither a pinned skip nor the repo-scope gate test.
   - **So the twin has a second run** (ch-bsd r1 M4; ruling L122). After the runner, the same
     clone runs eight files directly: `pytest -rA <files>`, with the seven files of
     [[#t0-1-skip-reasons]] and `tests/test_gmd_lint_requires_version.py`, whatever run tier
     each has by then. Its log is kept beside the twin run's, with its exit code and its counts
     quoted (R0.3). It exits 0. Its only skips are the pinned set at that sha, each reported as
     pinned: after stage 2 that is the hooks pin alone ([[#t0-2-bug253]]). The repo-scope gate
     test passes in it, and its fallback line is in the log.
   - The runner has no `--files` form at this stage and gets none for this; the second run is
     plain pytest. It starts after the runner run has ended ([[orchestration#one-suite]]).

   {#r7-5}
6. **R7.6 A failure in R7.4 or R7.5 does not get explained away.** Every failing E line is matched
   to a row by E line (R0.2).
   - **A `diagnosed-loud` flake ([[#ruling-o7]]).** The gate still passes if EVERY failure in the
     run matches a T0.3 row whose status is `deferred: diagnosed-loud, …` ([[#amend-6]]; the two
     rows of [[#amend-4]] count as T0.3 rows), and each of those nodeids
     passes on an immediate isolated re-run (`pytest <nodeid>` alone, same sha, same tree,
     logged). The summary records each such nodeid with both outcomes, and the row's band counts
     gain the firing. This is the only re-run 29.4 allows; its runner has no retry flag
     ([[#amend-9]]).
   - **A match to any other T0 row** means that sub-task's fix did not hold. It reopens and takes
     the O5 path below.
   - **Anything else**, including a `diagnosed-loud` nodeid that fails its isolated re-run, a
     hook-drift or gate-drift failure ([[#r7-4]]), or a failure with no matching row, is handled per
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
   - owner "plan 7" → "no host plan; backlog (L33)" ([[#amend-8]]: plan-20's three tasks hold
     none of them, so "plan-20 evals" would be a phantom owner) on "LongMemEval Layer B (answer
     model + LLM judge)", "`longmemeval_m` variant (500 sessions/question)", "CLI candidate-set
     prefilter for recall (`ann_search(candidate_ids=...)` has no flag)", and "Re-measure
     big-store query latency on a SETTLED store";
   - owner "plan 8" → "T3, held with the frozen 19.2 (D-Q3 hold; [[#ruling-o3]])" on
     "Answer-usefulness as the retrieval-miss signal (vs `cardinality == 0`)" and "`brief/stale`
     detector".

   R0 first re-reads the registry at the branch base. If another branch has already made either
   edit, it is recorded as done, not repeated. At `f45b9a3` all six rows are present under these
   titles, and still name "plan 7" or "plan 8". {#r7-8}

### Acceptance {#t0-7-acceptance}

- **AC-7.1.** Mutations L6 (`_start_embedder_warmup` calls `self._reranker()` without
  `load=True`) and L1 (the refill bound is dropped) each go **red**. At base both survive, and
  r13's table is the RED record. {#ac-7-1}
- **AC-7.2.** The R7.2 wording test covers every cause branch R0 found. The R7.3 registry rows
  exist. Mutation M7.2: revert one cause's wording to the old single message, and the test goes
  red. {#ac-7-2}
- **AC-7.3.** The committed R7.4 run (its `summary.txt`) shows exit 0 for every shard, with the
  collected count equal to passed. The committed R7.5 run shows exit 0 for every shard, with
  only pinned skips, and its eight-file run shows exit 0 with only pinned skips. The summary
  quotes all three exit codes and counts. {#ac-7-3}
- **AC-7.4.** At least one previously failing test from each of bug-170, 168 and 127 has a
  `call` record with outcome `passed` in the R7.4 run's `outcomes.jsonl`
  ([[task-29.4-suite-health#r2-outcomes]]; ch-bsd r1 S2, ruling L122: one source, and no `-rA`
  or junit flag on the runner). The summary quotes the three records. This is T0.2's main-tree
  proof. {#ac-7-4}
- **AC-7.5.** After R7.8, none of the six deferral rows names "plan 7" or "plan 8" as its owner.
  {#ac-7-5}

### Files {#t0-7-files}

`tests/test_rerank_budget_real_clients.py`, `src/refmatrix/daemon.py` (only R7.2's wording),
`workflow/bug_registry.md`, `workflow/test_mock_registry.md`, `workflow/deferral_registry.md`
(R7.8), the run directories `workflow/review-output/t0-clean-suite-<sha>/` and
`workflow/review-output/t0-clean-twin-<sha>/` (the twin's holds the eight-file run's log), and
the plan
frontmatter and body status lines for plans 6, 7, 8 and 15. The summaries are
`workflow/implementation_summaries/task-t0.7-plan15-close-clean-suite.md` and
`workflow/implementation_summaries/task-t0-suite-trust-sweep.md` (the T0 roll-up: each sub-task,
its rows, its exit codes).

## T0.8 bug-196: the cli.log recall leg is split per channel {#t0-8}

Added by [[#ruling-o1]]: without it R7.4 cannot be clean. In the 0.82.0 release suite (main tree)
both RED tests failed: `test_ac6_frozen_fixture_prints_the_exact_counts` (the report prints
`cli.log: memory recall commands=244`, and no line holds the fixture's 34 agent recalls) and
`test_ac6_cli_log_recalls_are_split_per_channel` (`assert []` from its `chan('prompt_recall', 5)`
lookup). The bug-196 row names the cause and the fix. Both tests still fail, on the same E
line, in the 0.84.0 release suite and in 29.4's stage-0 clone run
([[task-29.4-r0-durations#digest]]). T0.8 is stage 2 ([[#amend-3]]). {#t0-8-lead}

rel: derives-from -> [[bug_registry]] {bug: "bug-196"}

### Requirements {#t0-8-requirements}

1. **R8.1 One line per channel.** `telemetry.agent_usage_report`'s cli.log leg counts each
   `memory recall` end row under its channel. The channel comes from
   `recall_channel(session_start=, stdin_json=, recent=, invocation=source)`
   (`telemetry.py:1313` at `f45b9a3`; `agent_usage_report` is `:1866`), fed from the row's argv
   flag names (they survive redaction) and its
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

The order is 29.4's stages ([[#amend-3]]; [[task-29.4-suite-health#fold-stages]],
[[task-29.4-suite-health#order]]):

stage 0 (the durations run; done) → stage 1 **T0.1'** → stage 2 T0.2 (+ 29.4b) ∥ T0.3 (+ 29.4c)
∥ T0.8 → stage 3 T0.4 → T0.5 → stage 4 (29.4a, the runner; no T0 sub-task) → stage 5 **T0.7**
(+ 29.4d; last; R7.4 runs on the sha after its merge). T0.6 is a lane, any time after stage 1.
Each sub-task merges `--no-ff` from its own branch, cut from the `master` that holds the stage
before.

At approval the order was: queue item 1 (bug-212, bug-216, 25.1 rev 7) → T0.1 → T0.2 ∥ T0.3 ∥
T0.4 ∥ T0.6 ∥ T0.8 → T0.5 (after T0.4) → T0.7. Queue item 1 has merged. {#merge-order-body}

- **Interim bug-127.** Once T0.1 merges, a symlinked clone no longer skips
  `test_brief_real_daemon.py`, so every symlinked-clone full run between T0.1's merge and T0.2's
  fails `test_an_unknown_class_fails_loudly_through_the_daemon` on bug-127's `Conflicting lock`
  E line. That failure is bug-127, matched by E line (R0.2), not a new finding. {#merge-interim-127}
- **Interim bug-253.** A no-venv clone run carries bug-253's E lines until the stage-2 branch
  merges its fix ([[#t0-1-bug253]]). {#merge-interim-253}
- **26.5 is not in flight ([[#amend-2]]).** At approval T0 ran alongside 26.5 (queue item 2),
  and this paragraph ordered their merges in `cli.py`, `verbs.py` and `mcp.py`. plan-29 now runs
  first (ruling L104, [[plan-review-2026-11-13#lead]]), and 26.5 does not run during 29.4. So
  T0.4 and T0.5 meet no 26.5 merge, and R7.4's `master` holds none. What they must leave quiet
  instead is 29.5's ground: they land in stage 3, before the module split.
  {#merge-265}
- **Release.** T0 needs no hook install window (R0.7). T0.5 changes an MCP tool, so it rides the
  next release with a `/mcp` reconnect. 29.4 has one release point, after stage 5
  ([[task-29.4-suite-health#r10]]). {#merge-release}

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

The ch-bsd spec review of `1cf3b9f..7e67551` (DIRTY 1B/6S/9M, persisted as
`workflow/bullshit/2026-11-13-2305-spec-t0-r1-7e67551.md`) and the lead's rulings on it, folded:

rel: derives-from -> [[bsd-spec-t0-7e67551]]


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

## Revision round r2 (2026-11-13) {#rev-r2}

The ch-bsd spec review r2 of `7e67551..772803a` (DIRTY 0B/2S/4M; all 16 r1 findings closed, the
19-pin count confirmed; persisted as `workflow/bullshit/2026-11-13-2335-spec-t0-r2-772803a.md`)
and the lead's rulings, all as recommended, folded:

rel: derives-from -> [[bsd-spec-t0-r2-772803a]]


| finding | resolution | where |
|---|---|---|
| s-1 an empty auto-created own-slug memory dir defeats the fallback | own-slug dir counts only with ≥ 1 `*.md`; empty → origin fallback, with the stderr line; AC case + mutation M1.6; AC-1.6's second case corrected | [[#r1-4]], [[#ac-1-6]], [[#t0-1-mutations]] |
| s-2 no branch for a failed fix; no trial timeout | at most 2 fix attempts × 45 per bug, then keep only the diagnostic, revert the rest, `diagnosed-loud`; per-trial cap `max(3 × T, 300 s)` from R0, a timeout is a failure recorded as `hang` | [[#t0-3-cap]], [[#t0-3-attempts]], [[#t0-3-bound]], [[#ac-3-1]] |
| m-1 `--durations=25` is phases, not files | `--durations=0`, summed by file, top 25 | [[#t0-3-r0]] |
| m-2 resolver vs the real HOME; origin canonicalisation | in-process `resolve_memdir(root, home)` in `scripts/gmd_memdir.py`; origin resolved, trailing `.git` stripped, schemes and scp-style non-local; mutation M1.7 | [[#r1-4]], [[#ac-1-6]], [[#t0-1-files]] |
| m-3 "User gates: none" vs a hook-drift stop | header names the G31 install window that clears a hook-drift stop | [[#root]] |
| m-4 no GMD-gate precondition | R7.4 precondition: `./scripts/lint-gmd.sh` exits 0, else gate drift (never bug-155); AC-1.5 relies on it | [[#r7-4]], [[#ac-1-5]], [[#r7-6]] |

{#rev-r2-body}

## Revision round r3 (2026-11-13) {#rev-r3}

The ch-bsd spec review r3 (confirm-lite) of `772803a..efe618c` came back MEH-only (0B/0S/1M),
persisted as `workflow/bullshit/2026-11-13-2340-spec-t0-r3-efe618c.md`. Its one MEH, folded as
the lead ruled:

rel: derives-from -> [[bsd-spec-t0-r3-efe618c]]

| finding | resolution | where |
|---|---|---|
| m-1 a background-process hang is charged to the row | a trial's outcome is the target test's own; a cap hit is the row's `hang` only if the target had not finished; a background-only hang voids the trial (recorded, re-run), at most 3 voids per load level, then the level is reported noisy and the row keeps its prior status | [[#t0-3-cap]] |

{#rev-r3-body}

## Revision note (2026-11-15, freshness + 29.4 fold) {#rev-note-fresh}

This revision makes the approved spec ready to merge to `master`. It was approved on
2026-11-13 on branch `spec-wave-t0` (`fa1227d`) and never merged; plan-29 and task 29.4 were
written after it. Two things were done: the ten rows of [[task-29.4-suite-health#fold-deltas]]
were applied ([[#amends-29-4]]), and every file, function, line, test name and sha the spec cites
was re-read at `master` `f45b9a3` (the code under the merge of `spec-wave-t0` with `master`). No
test was run for it, and no `src/` or test file was edited. No requirement was added; what a
gap would need is listed as a proposal ([[#rev-note-fresh-proposals]]). {#rev-note-fresh-lead}

rel: derives-from -> [[task-29.4-suite-health#fold-deltas]]
rel: derives-from -> [[task-29.4-r0-durations]]
rel: derives-from -> [[plan-review-2026-11-13#lead]] {ruling: "L121"}
rel: depends-on -> [[orchestration#planning]]

### The ten rows of 29.4's fold {#rev-note-fresh-fold}

| row | what changed in T0 | where |
|---|---|---|
| 1 | T0.1 is T0.1'. R1.3 marked shipped (`988e96d`) and dropped. R1.4 is now the convergence of the shipped bash fallback (`44d1a34`) and the test's copy of it onto one resolver. AC-1.5's RED is the empty own-slug `memory/` run; the absent case is a characterization check. M1.3 and M1.4 restated. `.gmd/config.yml` leaves the files list. The residual and both layouts of clone are written down | [[#amend-1]], [[#t0-1-residual]], [[#r1-3]], [[#r1-4]], [[#ac-1-5]], [[#t0-1-mutations]], [[#t0-1-files]] |
| 2 | Header: T0 is 29.4's body inside plan-29; queue item 1 is merged (shas named); 26.5 is not in flight | [[#amend-2]], [[#root]], [[#merge-265]] |
| 3 | Scope table and merge order follow 29.4's stages: T0.4 → T0.5 are stage 3, after stage 2 | [[#amend-3]], [[#scope]], [[#scope-order]], [[#merge-order-body]] |
| 4 | bug-228 and bug-231 are two more rows on T0.3's harness and bands; what is built for them stays 29.4's text | [[#amend-4]], [[#t0-3-two-more]], [[#t0-3-files-shared]] |
| 5 | bug-229's reaper and root rule share T0.2's branch (29.4b) | [[#amend-5]], [[#t0-2-reaper]], [[#t0-2-files-shared]] |
| 6 | `open / diagnosed-loud` reads `deferred: diagnosed-loud, <trial counts>; review <date>` at the three sites that set it and the two that read it | [[#amend-6]], [[#t0-3-attempts]], [[#t0-3-band-none]], [[#r3-1]], [[#r7-6]], [[#done]] |
| 7 | R7.4 and R7.5 run `scripts/ptest.sh --tier all`; `-rA` and a junit file per shard; a run is a directory; "clean" keeps its four lines unchanged | [[#amend-7]], [[#r7-4]], [[#r7-5]], [[#ac-7-3]], [[#ac-7-4]], [[#t0-7-files]] |
| 8 | The four plan-7 deferral rows go to "no host plan; backlog (L33)" | [[#amend-8]], [[#r7-8]], [[#ac-6-3]] |
| 9 | Ruling O7's re-run is unchanged and is named as the only re-run 29.4 allows | [[#amend-9]], [[#r7-6]] |
| 10 | R0.1 to R0.8 bind 29.4's additions | [[#amend-10]], [[#r0-also-29-4]] |

{#rev-note-fresh-fold-table}

### Freshness: what was re-read, and what moved {#rev-note-fresh-cites}

Everything not listed here was re-read and holds as written: the 19 pins and the eight skip
reasons of [[#t0-1-skip-reasons]], `conftest.py:286`, every test name, every sha, the six
deferral-row titles, the plan and task-spec paths, and the three ch-bsd spec reports.

| cited | at `f45b9a3` | change |
|---|---|---|
| "every clone run exits 1" (bug-215) | true only for a clone with a symlinked `.venv-eval`; both layouts are in use | [[#why-instrument]], [[#t0-1-bug253]] |
| the gate fails in a clone on about 1,080 dangling ids (bug-155) | fixed for the absent case by `988e96d` and `44d1a34`; residual: the empty dir, and two copies of the logic | [[#why-instrument]], [[#t0-1-residual]] |
| 0.82.0 suite: 14 failed | 0.84.0: 13 failed, 5,028 passed (bug-168 9, 170 1, 127 1, 196 2); stage 0 in a no-venv clone: 4 failed, 127 errors | new [[#why-now]] |
| `store.py:717` "is now `:1159`" (R0.1's example) | `:1372` | [[#r0-1]] |
| `store.py:1155-1159` (`RMX_READ_VIA_DUCKDB`) | `store.py:1368-1376`; `_read()` at `:2517-2531` | [[#t0-4-lead]] |
| `cli.py:6028` "for now" | `cli.py:6199` | [[#t0-4-lead]] |
| `daemon.py:6149` (the `_op_embed` cancel return) | `daemon.py:6277` | [[#t0-4-lead]] |
| `store.py:1241` ("Called after the SQLite commit") | `store.py:1454` | [[#t0-4-lead]] |
| `telemetry.py:1246` (`recall_channel`) | `telemetry.py:1313` | [[#r8-1]] |
| T0.3's R0 durations run "is T0.3's first step" | done as 29.4 stage 0 at `4c6a0c6`; the 25-file list is [[task-29.4-r0-durations#top25]] | [[#t0-3-r0]] |
| R7.5 "this is where releases run" | releases gate on merged `master` in the dev tree ([[orchestration#release]]); a clone is where branch runs and reviews happen | [[#r7-5]] |
| the R7.4 log "committed as `workflow/review-output/t0/…`" | `workflow/review-output/` is git-ignored; a run directory is added with `git add -f` | [[#r7-4]] |
| `workflow/TDD_GOVERNANCE.md` `#rules`; task 7.4 `#requirements`; plan-7 `#execution`; `contra-e.md` (code spans) | links | [[#r1-5]], [[#r6-4]], [[#why-gates]] |
| T0.5's R0 list | holds at the same lines; one fact added: the verb has `plan=` and `compile_scope=`, no `compile` | [[#t0-5-lead]] |
| T0.7's R0 list | holds at the same lines; bug-095 and the graduated `_FakePrivate` row named for R7.3's R0 | [[#t0-7-lead]] |

{#rev-note-fresh-cites-table}

### Owners from ruling L121 {#rev-note-fresh-owners}

| L121 | owner | written at |
|---|---|---|
| contradiction 1: bug-253's fixture fix, and `lint-gmd.sh`'s dev-interpreter lookup | the stage-2 branch (T0.2 + 29.4b), or the next RED touching those files | [[#t0-2-bug253]]; what it means for T0.1', which edits `lint-gmd.sh` first: [[#t0-1-bug253]] |
| contradiction 3: no failing bug-228 run in stage 0 | T0.3's harness gives the leg breakdown | [[#t0-3-bug228-legs]] |
| re-weight after bug-253 | after the stage-2 fix; for the runner's weights, not T0.3's list | [[#t0-2-bug253]], [[#t0-3-r0]] |
| contradictions 2, 4, 5 and 6 | stage 4 (29.4a): not T0's | none |

{#rev-note-fresh-owners-table}

### Where the documents disagreed, and what was chosen {#rev-note-fresh-choices}

Ruling L122 let choices 1 to 5 stand and ruled on 6 ([[#rev-note-fresh-2]]). R7.5 has since
gained the second run that choice 5 lacked.

1. **T0.1' and `lint-gmd.sh`'s interpreter lookup.** L121's "or the next RED touching those
   files" would make T0.1' the owner, because it is the first branch to edit that script. Chosen:
   the lookup stays with stage 2 unless the lead moves it, and T0.1's ACs name the
   symlinked-venv clone, where the script reaches lint. {#choice-1}
2. **`diagnosed-loud` for bug-130's product route.** 29.4's row 6 names `#r3-1` and gives
   `deferred: diagnosed-loud, …`. 29.1 also offers `scheduled → <target>` when T0.3 opens a
   product row. Chosen: row 6, because ruling O7 matches a failing node to a row by the words
   `diagnosed-loud`, and R3.1 relies on that. The new product row takes its own status in 29.1's
   grammar. {#choice-2}
3. **The 25-file list.** T0 freezes it before trial 1. L121 asks for a re-weighting after
   bug-253. Chosen: the list stays frozen as stage 0 measured it; the re-weighting is for
   `tests/shard_weights.json`. {#choice-3}
4. **Parallel sub-tasks.** T0 let sub-tasks run in parallel clones, and T0.3's harness starts 3
   to 8 pytest processes. The operating procedure allows one test run at a time. Chosen: the
   procedure. Sub-tasks are written in parallel and run one at a time; the harness counts as the
   one run while it is up. {#choice-4}
5. **The clone twin.** T0's R7.5 has the pinned skips reported in the twin run. 29.4's runner
   does not run run tier (c) in a clone, and the seven pinned files are tier (c). Chosen: 29.4's
   runner, as row 7 says; R7.5 states that the pinned set may be empty there (P5 below).
   {#choice-5}
6. **Pass modules.** Not chosen: T0.4's R4.5 and 29.4's derive-file rule cannot both be built.
   The site is marked held ([[#r4-5-derive-hold]]), and the proposal is P1. {#choice-6}

### The bug-155 row: proposed text {#rev-note-fresh-bug155}

The lead writes registry rows. Proposed addition to the row's fix cell:

> RESIDUAL, two cases (queue review `#st-8`; ch-bsd T0 fresh r1 S1; T0.1', 29.4 stage 1). The
> shipped fallback (`scripts/lint-gmd.sh:49-64`) and the test's copy of it
> (`tests/test_gmd_lint_requires_version.py:125-140`) look at one directory per checkout and
> follow the origin one hop. (1) LIVE: a clone whose origin is another clone. The origin's slug
> has no memory dir either, the gate prints `lint-gmd: no memory dir for <clone> or its origin
> <clone>; memory-id refs will dangle` and exits 1 on every memory id: 1,234 `dangling-doc` in
> `/Volumes/littlebig/refmatrix-bsdt0-r1` at `5b04e2d` (`bsdt0-r1-chained-origin-probe.log`).
> 8 of the 33 `refmatrix-*` clones have another clone as origin, and so does every review
> clone cut from an author's clone. (2) NOT LIVE on 2026-11-15: an own-slug `memory/` that
> exists and holds no `*.md` (Claude Code creates one for a session whose cwd is the checkout)
> is used as the memory dir, no fallback is taken, and every memory-id ref dangles; no
> `~/.claude/projects/-Volumes-littlebig-refmatrix*` exists yet. The two copies also differ on
> the origin: the script keeps `cd && pwd`, the test `resolve()`s; neither takes a relative or
> `<path>/.git` origin; neither checks that the origin's dir is populated. Fix: T0.1' R1.4, one
> stdlib resolver `resolve_memdir(root, home)` in `scripts/gmd_memdir.py`, run under `python3`,
> used by the script and by the test: populated check on every dir, the origin canonicalised,
> local origins walked hop by hop (bound 5, cycle guard), and the chain with each reason
> (`absent` or `empty`) on stderr. RED: AC-1.5 case 1 (the repo-scope test in a clone of a
> clone) and case 2 (the empty-directory run).

Proposed status cell, in 29.1's grammar:
`scheduled → task-t0-suite-trust-sweep (T0); causes 1 and 2 fixed 988e96d + 44d1a34, residual: clone of a clone (live), empty own-slug memory dir`.
Tags gain `residual`. `Seen` goes from 4 to 5: the reviewer's clone reproduced the symptom on
2026-11-15. (Rewritten in round 2, ruling L122, to name both cases.)
{#rev-note-fresh-bug155-status}

### Proposals for the lead {#rev-note-fresh-proposals}

As written on 2026-11-15, before the review: none of these was in the spec's requirements, and
each needed a ruling. **All eight were ruled in L122 and are folded** ([[#rev-note-fresh-2]]):
P1 accepted with two conditions, P2 replaced by a static AC, P5's command corrected, the rest
as proposed. The text below is kept as the record of what was asked.

- **P1 (blocks stage 3): R4.5 against 29.4's derive-file rule.** `session_ingest.py` and
  `vectors.py` are pass modules ([[#r4-5-derive-hold]]). Proposed, by the rule 29.4 already
  applies to a clock in a derive file: T0.4 leaves both docstrings alone, lists the two lines in
  `test_deferrals_clean.py`'s allow-list with the reason "pass module; routed to 29.2 R7's
  release", and 29.2's release, whose hash ignores docstrings, makes the two edits and removes
  the entries. Plan-6's #s-3 would then close on the widened guard plus two named exceptions,
  which the lead has to accept or refuse. R4.7's one-line `store.py` docstring edit and R4.1's
  "stale mentions" in `store.py` are outside 29.4's stated exception too, but `store.py` is in
  no pass's set, so they flip nothing; the exception's wording could name them. {#p1}
- **P2: a bypass mutation for the convergence.** R1.4 is now "two copies become one". No
  mutation checks that the script stays on the resolver. Proposed M1.8: `scripts/lint-gmd.sh`
  goes back to its own `-d` test and bash fallback; AC-1.5's empty-directory run goes red with
  no fallback line ([[feedback_converge_repeated_shapes]]). {#p2}
- **P3: bug-228 with no failing trial.** [[task-29.4-suite-health#r3-bug228]] picks its branch
  from a failing run's leg breakdown. If T0.3's 30 base trials never fail, neither branch is
  selected. Proposed: the not-reproduced band applies, and the "otherwise" branch (split the
  test) is built, since it does not depend on where the time went. {#p3}
- **P4: the R0-run live-socket count.** [[#t0-3-sockets]] asks for the recorder's count for the
  R0 run. Stage 0's summary has none. Proposed: accept the per-level counts alone and say so in
  T0.3's summary, or read the count from the stage-0 clone's
  `workflow/review-output/live-socket-touches.log` if it is still there. {#p4}
- **P5: the clone twin proves less than R7.5 meant.** With run tier (c) not run in a clone, the
  twin run shows no pinned skip and does not run the repo-scope lint test
  ([[#choice-5]]). Proposed: the twin also runs the eight tier-(c) files named in R7.5 directly
  (`scripts/ptest.sh --files …`), so the stage-5 clone evidence still includes the pins and the
  gate test. {#p5}
- **P6: `-rA` and the per-shard junit file have one source.** Row 7 is the only text that asks
  for them; [[task-29.4-suite-health#r2]] names no flag and no AC for them. AC-7.4 depends on
  them. Proposed: 29.4a's R2 says the runner passes both to every shard, with a line in its
  runner test; or AC-7.4 reads `outcomes.jsonl`, which R2 already writes. {#p6}
- **P7: bug-253's helper and the seven pinned files.** The seven files of
  [[#t0-1-skip-reasons]] look up the same `<checkout>/.venv-eval/bin/rmx`, and skip where the
  six bug-253 files error. If bug-253's helper is used there too, those 18 tests run in a
  no-venv clone and their pins go (R1.2: the pins follow the tests). The row names five files
  only. {#p7}
- **P8: AC-2.1's `home=` route.** `hooks.check(project_root)` has no `home` parameter at
  `f45b9a3`, and T0.2's files list holds no `src/` file. The route through
  `RMX_CLAUDE_HOOKS_DIR`, or restoring `HOME` for the one render, needs none. Proposed: say so,
  or add `src/refmatrix/hooks.py` to T0.2's files. {#p8}

### Lint run for this revision {#rev-note-fresh-lint}

`./scripts/lint-gmd.sh` does not run in the revision's clone: it has no `.venv-eval`, and the
script exits 2 (bug-253). Run by hand, over the script's own scope with the origin's memory dir,
which is what the shipped fallback would pass: `python3 tools/gmd/lint.py CLAUDE.md docs/
workflow/ eval/ .claude/PROJECT_PROFILE.md <origin memory dir>`, and the anchor-parity step with
the main tree's interpreter and `PYTHONPATH=<clone>/src`. Both exited 0: lint 0 errors; parity
0 divergent docs, 0 parse failures, 0 docs outside the ingest scope. The same lint exited 0 at
the merged base before the revision. {#rev-note-fresh-lint-body}

## Revision note 2 (2026-11-15, ch-bsd confirm-lite r1; ruling L122) {#rev-note-fresh-2}

ch-bsd's confirm-lite r1 of the freshness revision (`549c56e..5b04e2d`) came back DIRTY 10
(0B/2S/8M), persisted as `workflow/bullshit/2026-11-15-0918-spec-t0-fresh-r1-5b04e2d.md`. The
lead ruled that all ten fold (L122, [[plan-review-2026-11-13#lead]]). No test was run and no
`src/` or test file was edited for this round. {#rev-note-fresh-2-lead}

rel: derives-from -> [[bsd-spec-t0-fresh-r1-5b04e2d]]
rel: derives-from -> [[plan-review-2026-11-13#lead]] {ruling: "L122"}

| finding | resolution | where |
|---|---|---|
| S1 a clone of a clone still fails the gate | the resolver walks local origins hop by hop; it stops at the first populated slug, or with no dir at a missing or non-local origin, a cycle, or the bound of 5; the loud line names the chain; chained, cycle and bound cases; M1.9 (one hop only) and M1.10 (no cycle guard); AC-1.5's "origin = the main tree" relaxed and split in two REDs; the residual and the proposed bug-155 text name both cases | [[#t0-1-residual]], [[#r1-4]], [[#ac-1-5]], [[#ac-1-6]], [[#t0-1-mutations]], [[#rev-note-fresh-bug155]] |
| S2 / P1 the hand-off to 29.2 had no AC there | T0.4 allow-lists `session_ingest.py:5` and `vectors.py:14`; each entry fails once its line no longer holds the phrase (M4.5c), and no third pass-module entry is allowed (M4.5d); 29.2 gains AC-29 and a paragraph under R7; the hold is lifted; plan-6 #s-3 closes with the two exceptions | [[#r4-5]], [[#r4-5-derive-hold]], [[#ac-4-4]], [[#ac-4-5]], [[#ac-4-close]], [[#t0-4-files]], [[task-29.2-mypy-gate#ac-29]] |
| S2 / P6 `-rA` and junit had one source | AC-7.4 reads `outcomes.jsonl`; R7.4's command asks the runner for no new flag; row 7 in 29.4 and [[#amend-7]] reworded | [[#ac-7-4]], [[#r7-4]], [[#amend-7]], [[task-29.4-suite-health#fold-deltas]] |
| M1 an unlisted E line in a no-venv clone | every test that runs the script asserts "the gate ran" first, with `assert_gate_ran_clean`'s first-clause message; `gmd_memdir.py` runs under `python3`, never `$DEVPY` | [[#ac-1-5]], [[#r1-4]], [[#t0-1-bug253]] |
| M2 / P2 nothing checked that two copies became one | new static AC-1.7; M1.8 puts the slug derivation back into the script and must turn it red | [[#ac-1-7]], [[#t0-1-mutations]] |
| M3 29.4's exception was narrower than T0.4's `store.py` edits | the exception names R4.1 and R4.7 | [[task-29.4-suite-health#files-src-note]], [[#t0-4-files]] |
| M4 / P5 the proposed command used a flag that does not exist | the twin has a second run: `pytest -rA` over the eight files, exit code and counts quoted; no `--files` | [[#r7-5]], [[#ac-7-3]] |
| M5 / P7 two definitions of "the dev rmx" | bug-253's helper covers every file that names the dev bin (eleven: [[#rev-note-fresh-3]] corrects this round's "twelve"); stage 2 retires the 18 venv pins and R1.1's venv half; AC-1.4 stands as stage-1 evidence | [[#t0-2-bug253]], [[#t0-1-bug253]], [[#r1-1]], [[#t0-2-files-shared]] |
| M6 / P8 AC-2.1 assumed a `home=` parameter | R2.1 and AC-2.1 use the routes that need no `src/` change | [[#r2-1]], [[#ac-2-1]] |
| M7 / P3 bug-228's branch if it never fails | one sentence in 29.4: build the "otherwise" split; the product row records "not reproduced in N trials at levels 3/5/8" | [[task-29.4-suite-health#r3-bug228]], [[#t0-3-bug228-legs]] |
| M8 no verify set for the branches that edit conftest | the two sets the lead named | [[#r0-verify-sets]], [[#t0-1-verify]], [[#t0-2-verify]] |
| P4 the R0 live-socket count | the stage-0 clone's recorder log, 41 lines, is the R0 count | [[#t0-3-sockets]] |

{#rev-note-fresh-2-table}

**Also, as the lead asked.** [[task-29.1-registry-triage#r1-other-writers]] no longer says T0 is
"not yet on `master`", and its files row for T0 points at [[#amend-6]]. The one `T0#t0-3-r0`
code span in [[task-29.4-r0-durations]] is a link. {#rev-note-fresh-2-also}

**Three things in this round are the author's, not the ruling's**, and the next review should
look at them. {#rev-note-fresh-2-own}
1. **AC-1.5 case 2 is RED at base in two different ways.** As a pytest node it fails on the
   missing resolver, which it needs to build its decoy without a third copy of the logic. The
   RED for the stated reason is a logged run of the shipped script against the same decoy.
   Case 1 has no such gap: it is an existing test, RED at base in a clone of a clone.
2. **Two mutations beyond the ruling:** M1.10 (no cycle guard) for the cycle case, and M4.5d
   (no pass-module entry other than the two), so that the allow-list cannot grow quietly. A **bound** case
   was added to AC-1.6 beside the chained and cycle cases.
3. **The eight-file run takes the eight files "whatever run tier each has by then".** After
   stage 2 retires their pins, six of the seven formerly pinned files leave run tier (c) by
   29.4's derivation, and the runner then runs them in a clone anyway. The list is kept fixed
   so the twin's evidence does not depend on that.

**Lint for this round.** Same commands as [[#rev-note-fresh-lint]]: both exited 0 (lint 0
errors; parity 0 divergent docs). {#rev-note-fresh-2-lint}

## Revision note 3 (2026-11-15, ch-bsd confirm-lite r2; ruling L123) {#rev-note-fresh-3}

ch-bsd's confirm-lite r2 of round 2 (`f34b40c..f6b32e2`) came back MEH-only (0B/0S/4M), GO,
persisted as `workflow/bullshit/2026-11-15-0939-spec-t0-fresh-r2-f6b32e2.md`. The lead ruled
that the four MEHs fold before the merge and that it checks the fold itself (L123,
[[plan-review-2026-11-13#lead]]). AC-29's third bullet in 29.2 stays. No test was run and no
`src/` or test file was edited. {#rev-note-fresh-3-lead}

rel: derives-from -> [[bsd-spec-t0-fresh-r2-f6b32e2]]
rel: derives-from -> [[plan-review-2026-11-13#lead]] {ruling: "L123"}

| finding | resolution | where |
|---|---|---|
| M1 AC-1.5 case 2's node has no stated-reason RED of its own | M1.6 also names that node; its run under M1.6 after GREEN is its recorded RED, a mutation RED the lead accepts for this one node; the RED author re-takes the shipped-script run at T0.1's base with the real script in a symlinked clone, exit code quoted; the bsd r1 probes are "corroborated by" | [[#ac-1-5]], [[#t0-1-mutations]] |
| M2 the bound had no mutation | M1.11 (drop or raise the bound) turns AC-1.6's bound case red; the cycle test runs with the bound intact and a wall deadline; M1.10's wording says why it fails and does not hang | [[#ac-1-6]], [[#t0-1-mutations]] |
| M3 "twelve files" was wrong | eleven files name the dev bin and are listed with their lines; `test_bug241_r3_l114.py` is covered through its import; `test_repo_hooks_in_sync.py` keeps its hooks pin; the 18 venv pins sit in six files, not seven | [[#t0-2-bug253]], [[#t0-1-bug253]], [[#t0-2-files-shared]], [[#t0-2-verify]] |
| M4 29.4 still routed class-B clock edits to 29.2 with no receiving AC | the routing commit also adds the receiving AC to 29.2, or the edit is not routed | [[task-29.4-suite-health#files-src-note]] |

{#rev-note-fresh-3-table}

**Lint for this round.** Same commands as [[#rev-note-fresh-lint]]: both exited 0 (lint 0
errors; parity 0 divergent docs). {#rev-note-fresh-3-lint}

## Decision {#decision}

| date | decision | by | basis |
|---|---|---|---|
| 2026-11-13 | `metadata.status: approved` | the lead | Approved by the lead on the user's pattern (d9co route) after ch-bsd r3 MEH-only, `bsd-spec-t0-r3-efe618c`, MEH folded ([[#rev-r3]]) |
| 2026-11-15 | `approved` stands; the text is revised for freshness and the 29.4 fold ([[#rev-note-fresh]]) | ch-architect, on the lead's brief | [[task-29.4-suite-health#fold-deltas]], ruling L121. A ch-bsd confirm-lite on the revision's diff comes before the merge; P1 to P8 are open for the lead |
| 2026-11-15 | round 2: ch-bsd confirm-lite r1 (DIRTY 10, 0B/2S/8M) folded whole ([[#rev-note-fresh-2]]); P1 to P8 ruled | the lead (ruling L122); text by ch-architect | [[bsd-spec-t0-fresh-r1-5b04e2d]]. A confirm-lite r2 comes before the merge |
| 2026-11-15 | round 3: ch-bsd confirm-lite r2 was MEH-only GO; its four MEHs folded ([[#rev-note-fresh-3]]) | the lead (ruling L123); text by ch-architect | [[bsd-spec-t0-fresh-r2-f6b32e2]]. The lead checks this fold itself; no third review round |

{#decision-approved}

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
  only) `deferred: diagnosed-loud, <trial counts>; review <date>` ([[#amend-6]]). Row 155's
  `fixed` covers its residual ([[#amend-1]]).
- R7.4 and R7.5 are committed and meet the gate: exit 0, or the [[#ruling-o7]] flake clause
  with each re-run recorded.
- Plans 6, 7, 8 and 15 are `completed` in frontmatter and body, or still `in-progress` with the
  named reason that holds each (a ch-bsd round not yet CLEAN, an unmet deferral owner, or an O5
  stop).
- Every sub-task's ch-bsd round is CLEAN, or MEH-only where its plan allows.
- GMD lint shows 0 errors on every touched `.md`.
- Each branch is merged `--no-ff` to `master`.
- This spec's frontmatter flips to `completed` in stage 5's closing commit, with 29.4's
  ([[task-29.4-suite-health#ac-14]]).
