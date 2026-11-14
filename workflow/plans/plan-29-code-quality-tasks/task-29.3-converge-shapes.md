---
gmd: "0.1"
id: task-29.3-converge-shapes
title: "Task 29.3: converge the repeated shapes — one helper and one census test per finding class (git runner, query term resolution, broad excepts, busy-is-not-absent, RPC bounds, caller remedies)"
tags: [task, plan-29, convergence, census, git, query, pql, exceptions, silent-failure, code-quality]
metadata:
  node_type: task
  status: pending
  plan: plan-29-code-quality
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 29.3: converge the repeated shapes {#root}

> Plan: [[plan-29-code-quality]] ([[plan-29-code-quality#t3]])
> Status: Pending
> Depends on: 29.4 (the healed suite) and 29.5 (the module split), per
> [[plan-29-code-quality#order]]. Its git and query slices land BEFORE [[task-29.2-mypy-gate]];
> the shared files are ordered in [[task-29.2-mypy-gate#seam]].
> Review input folded 2026-11-14: `plan-review-fable-2026-11-14-store#plan29-converge-candidates`,
> `plan-review-fable-2026-11-14-queue#p29-4`, `plan-review-fable-2026-11-14-queue#dup-2`
> ([[#fold]]). Open for the user: `plan-29 D4` ([[task-29.2-mypy-gate#d4]]).

rel: part-of -> [[plan-29-code-quality]]
rel: implements -> [[tdd-governance]]
rel: depends-on -> [[bug_registry#registry]]
rel: related-to -> [[task-29.2-mypy-gate]]
rel: realizes -> [[feedback_converge_repeated_shapes]]
rel: reinforces -> [[feedback_check_the_sibling_condition]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: derives-from -> [[bsd-pattern-sibling-render-path]]
rel: derives-from -> [[bsd-pattern-control-point-claim-without-census]]
rel: derives-from -> [[bsd-pattern-busy-is-not-absent]]
rel: derives-from -> [[bsd-pattern-partial-bound]]
rel: derives-from -> [[bsd-pattern-prereg-check-unrun-census]]

## What this task delivers {#summary}

For each finding class the review ledger has recorded more than twice: ONE helper that owns the
shape, every call site moved onto it, and a census test that fails when a new site bypasses it.
Eight slices, each on its own branch, in this order:

| slice | helper | closes |
|---|---|---|
| K | the census kit under `tests/census/`: bug-212's scanner, extracted | (used by every slice, and by later tasks) |
| a | `run_git` in a new module `refmatrix/gitrun.py` | bug-233; the bug-225 r3 rule in one place |
| b | one term resolver in the query engine; typed PQL arguments | bug-234, bug-236, bug-238; bug-237's `NOT` half |
| c | one classifier for broad `except` handlers | the plan's three counts; the unowned silent handlers; bug-096 |
| d | the typed daemon classifier, already in `verbs`, as the only route gate | the bare `ping` gates |
| e | one `Deadline`; explicit `timeout` and `retries` on every daemon call | the four `_left` copies |
| f | the tracked-catalog refusal takes the caller's remedy | bug-232 |
| g | one function for a daemon op's partition default | the 20 copies of one expression |

Slices a, b and c are the plan's "first three". Slices d to g are the other classes that qualify
under the plan's rule ([[#classes]]).

## The finding classes, counted {#classes}

**Method.** Sources at `f3709d2`: the eight `workflow/bullshit/*PATTERN*.md` documents, the 117
list items of `workflow/bullshit/IMPRESSIONS.md` (298 distinct `imp-` anchors with the folded ones),
and the 238 rows of [[bug_registry#registry]]. One sighting is one PATTERN table row, one
impression bullet, or one registry row that names the shape. A PATTERN document's own occurrence
count is used as given. Registry rows are found by their tag column. Classes with more than two
sightings: {#classes-method}

| id | class | sightings | where | helper | slice |
|---|---|---|---|---|---|
| G | a git call's failure is read as a harmless answer ("not found", "clean", "nothing to commit") | 7 | registry bug-212, bug-225, bug-233; [[bsd-impressions#imp-loud-read-silent-skip]], [[bsd-impressions#imp-exit-allowlist-needs-a-probe]], [[bsd-impressions#imp-mutate-the-extension]], [[bsd-impressions#imp-fail-closed-covers-every-call]] | `run_git` | a |
| Q | an input the evaluator does not understand gets an answer instead of an error | 5 | registry bug-234, bug-236, bug-238, bug-240; [[bsd-impressions#imp-refuse-the-old-spelling]] | the term resolver | b |
| X | a failure is swallowed with no count and no word | 30 | 25 registry rows tagged `silent-failure` (bug-040 … bug-240); [[bsd-impressions#imp-silent-memory]], [[bsd-impressions#imp-silent-pass-migrates]], [[bsd-impressions#imp-nonfatal-needs-its-report-pinned]], [[bsd-impressions#imp-quiet-branch-premise]], [[bsd-impressions#imp-handler-body-own-try-scope]] | the handler classifier | c |
| B | a busy daemon is read as an absent one | 8 | [[bsd-pattern-busy-is-not-absent#sites]] (6 sites in 4 plans); [[bsd-impressions#imp-busy-absent-call-tree]], [[bsd-impressions#imp-daemon-down-twin-untested]] | `verbs.require_daemon` (exists) | d |
| T | a bound stops one call short: a timeout or a retry count left at the library default | 12 | [[bsd-pattern-partial-bound#occurrences]] (5 runs); registry tag `timeout` (bug-030, bug-097, bug-116, bug-177, bug-182); [[bsd-impressions#imp-fleet-sum-timeouts]]; [[bsd-pattern-sibling-render-path#sightings]] row `#s-2` | `Deadline` | e |
| S | one check or message is shared by callers with different needs | 5 | registry bug-232 with [[bsd-impressions#imp-shared-check-caller-remedy]]; [[bsd-impressions#imp-test-the-advice-in-the-error]], [[bsd-impressions#imp-aim-the-guard-at-the-destination]], [[bsd-impressions#imp-ask-about-the-file-not-the-names]], [[bsd-impressions#imp-shared-probe-placement]] | the refusal's `remedy` parameter; rule [[#r0]] | f |
| C | "every X passes through here" is claimed with no census of X | 7 | [[bsd-pattern-control-point-claim-without-census]] (4 runs); [[bsd-impressions#imp-loudness-is-a-census]], [[bsd-impressions#imp-collision-column-census]], [[bsd-impressions#imp-scanner-needs-synthetic-positives]] | the census kit | K |
| R | a correct fix reaches one of its two outputs | 10 | [[bsd-pattern-sibling-render-path#sightings]] (7); [[bsd-impressions#imp-precedence-names-siblings]], [[bsd-impressions#imp-mirror-the-extension]]; registry bug-048 | none of its own | see below |
| P | an operation's partition is chosen in many places | 10 | registry tag `partition` (9 rows: bug-098, bug-105, bug-111, bug-128, bug-140, bug-145, bug-148, bug-153, bug-158); [[bsd-impressions#imp-scope-vs-every-table]] | one partition-default function (the expression only; plan-23 owns the binding contract) | g |
| V | a gate or guard that did not run, or cannot fire, reads as clean | 8 | [[bsd-pattern-guard-cannot-fire#sightings]] (4); registry bug-021, bug-068, bug-230; [[bsd-impressions#imp-gate-precondition-vacuous-pass]] | `assert_gate_ran_clean` (exists) | rule [[#r0]] |

**Classes that get no `src/` helper, and why.** {#classes-no-helper}

- R is what G, B, T and S look like from the review side. Its remedy is the inventory, and the
  census kit is the inventory made permanent.
- V is a rule for gates. Every census in this task follows it: it is proven to find a planted
  site before its silence counts ([[#r0]]).
- Three PATTERN documents describe how specs and tests are written, not a code shape:
  [[bsd-pattern-tests-prove-existence-not-wiring]] (3 runs),
  [[bsd-pattern-prereg-check-unrun-census]] (3 rounds),
  [[bsd-pattern-handoff-without-sibling-ac]] (5 runs). This spec applies them to itself: every
  count below names its script and commit, and every item it hands to 29.2 or 29.5 names the AC
  that receives it.
- Class P's binding contract (which partition a writer is bound to, and when) is plan-23's
  (the bug-105 row: "23.1 adopts the contract with AC-3d"). Slice g converges only the one
  expression that picks an op's default partition, and changes no behaviour.
- bug-240 (`rmx ingest <file>` ingests nothing, exit 0) is a sighting of class Q that the term
  resolver does not fix. `plan-review-fable-2026-11-14-queue#dup-2` puts it on the bug-241
  hotfix branch (0.83.1). If that release has not closed it when slice c starts, slice c does
  ([[#c-r6]]).
- **Numeric env knobs (bug-188)** are a candidate the queue review names for this task. The
  ledger has two sightings (the bug-188 row and [[bsd-impressions#imp-pin-the-run-end]]), which
  is not "more than twice", so it is not a slice here. Measured for whoever takes it:
  82 bare `float(…)` / `int(…)` reads of the environment in 20 modules outside `envknob`
  (`census/census_env_knobs.py`, log `census-env-knobs-f3709d2.log`), against 23 `env_float`
  calls. It stays with 29.1's triage.
- bug-201 (rich drops a literal `[daemon]`) is one site and one shape; not taken.

## Measured at `f3709d2` (before the 29.5 split) {#measured}

Scripts in `workflow/plans/plan-29-code-quality-tasks/census/`; logs in `workflow/review-output/`.
Each script's docstring is the exact rule it counts by. The task re-runs all of them at its
start commit and records the new numbers ([[plan-29-code-quality#baseline-rule]]).

| what | script → log | result |
|---|---|---|
| git call sites | `census_git_spawns.py` → `census-git-spawns-f3709d2.log` | 9 spawns in 6 modules (cli 4, handoff 1, store 1, sync 1, upgrade 1, verbs 1) + 3 git command lists handed to the shell helper `_ss_sh`; 3 wrappers with 13 callers (`upgrade._git` 8, `handoff._ss_git_run` 3, `store._run_git_check` 2). 2 spawns have no timeout; 1 raises a raw `CalledProcessError`; 3 sit under `except Exception` that returns empty |
| broad handlers | `census_broad_except.py` → `census-broad-except-f3709d2.log` | 401 (393 `Exception`, 8 `BaseException`, no bare `except:`): re-raised 29, surfaced 172, justified 8, silent 192 (174 with no comment, 18 with a comment not in the gate's form) |
| the same, memory-path modules | same | re-raised 1, surfaced 26, justified 0, silent 18 |
| handler detail | `census_broad_except_detail.py` → `census-broad-except-detail-f3709d2.log` | silent bodies: `pass` 69, assign a default 54, return a default 48, `continue` 13, other 8. 113 except lines already carry `# noqa: BLE001`, 104 of them with a reason |
| daemon liveness gates | `census_daemon_gates.py` → `census-daemon-gates-f3709d2.log` | 56 `ping(...)` calls inside a condition, in 7 modules (cli 39, daemon 10, hub 2, ui/server 2, discovery 1, scheduler 1, fingerprint 1); 25 calls to the typed classifiers |
| daemon RPC bounds | same | 66 calls with a constant op: 31 pass `timeout` and `retries`; 29 pass `timeout` only; 6 pass neither. `daemon.call` defaults to `retries=2`, so 35 calls can take 3 × their timeout |
| term resolution | read from `query.py` | 4 `resolve_concept_ids` sites (`_term_bitmap`, `_row`, `neighbors`, `co_occurrence`), each returning empty for an unresolved name; 6 `load_bitmap` sites that take a linkage name unchecked; 6 `QueryEngine(...)` constructions (cli 2, graphread 2, daemon 1, verbs 1) |
| deadline closures | `grep "def _left"` | 4 copies (cli 2, verbs 2) |
| partition default | `grep -c 'args.get("partition") or d._st()._partition_name'` | 20 copies in `daemon.py` |
| tracked-catalog refusal | `grep refuse_tracked_catalog_open(` | 4 callers: `_store_rw`, `compact`, `migrate-to-duckdb`, `verbs.local_write` |

**How good the handler rule is.** The classifier ran on all 401 handlers; it is a census, not a
sample. Its precision was then checked by hand with `census_broad_except_sample.py`: 8 random handlers
per class (seed 29) and 22 more silent ones (seed 7), 62 in all, with 0 found in the wrong class
(the samples are in `census-broad-except-sample-seed29-k8-f3709d2.log` and
`…-seed7-k22-f3709d2.log`). For `surfaced`, the one
loose leg is "the handler uses the bound exception name": 70 handlers are surfaced by that leg
alone; the detail log lists how each uses the name (57 pass it to a call, 11 return it, 2 only
assign it; both of those 2 were read and put it in the result). So the measured error is 0 of
62, and the upper bound on a 95% interval for the misclassified share is about 5%. The census
logs were produced by a previous agent's run and reproduce byte-for-byte. {#measured-precision}

## R0: rules every helper in this task follows {#r0}

These come from the ledger's record of how convergences fail.

1. **What differs by caller is a parameter with no default.** A timeout, a remedy text or an
   environment rule that encodes one caller's need is class S again.
2. **The helper's own promises are tested and mutated before the sites**
   ([[bsd-impressions#imp-convergence-tests-sites-not-helper]]).
3. **Each census has the five parts of the catalog-opener census** in
   `tests/test_bug212_r4_red.py`:
   - a "sees" test: the scanner finds known real sites;
   - a synthetic module with a positive and a negative for every family, aliases included
     ([[bsd-impressions#imp-scanner-needs-synthetic-positives]]);
   - no site outside the allowlist;
   - no allowlist entry the scanner no longer sees;
   - keyed on the guarded resource, not on one way of reaching it
     ([[bsd-impressions#imp-census-the-resource]]).
4. **One rule, one implementation.** The test and the report command import the same scanner
   from `tests/census/`. A count in a summary names the command and the commit.
5. **The predecessor is deleted** ([[bsd-impressions#imp-rewrite-orphans-predecessor]]). After a
   slice, no replaced wrapper is left with a test as its only caller.
6. **Where each caller calls the helper is checked**: which lock it holds, and whether it runs
   on a tick or inside a request ([[bsd-impressions#imp-shared-probe-placement]]).
7. **No behaviour change rides along.** A site whose behaviour must change gets its own AC and
   its own RED test. Everything else is pinned by a golden recorded at the start commit.

## Slice K: the census kit {#slice-k}

**The kit is bug-212's scanner, extracted; it is not a new AST walker**
(`plan-review-fable-2026-11-14-store#plan29-converge-candidates`). The catalog-opener census in
`tests/test_bug212_r4_red.py` already has the parts every census needs: alias handling
(`_store_aliases`, `_module_aliases`), a per-module scan that yields `module:qualname`, line and
family (`_scan_source`), the tree walk (`_census`), caller lookup (`_functions_calling`,
`_sites_calling`, `_calls_in`), the synthetic self-test, and "the allowlist names no dead site".

- **K-R1.** Those functions move to `tests/census/kit.py`, generalised only as far as a second
  family needs: a FAMILY is a name, a predicate over AST nodes, and (where the guarded thing is a
  resource) a text pattern for it. The walk uses `rglob`, so packages are covered.
- **K-R2.** `tests/test_bug212_r4_red.py` imports the kit and keeps its allowlists, its catalog
  pattern and its tests. Its census is RE-PROVEN after the move: its synthetic-module test passes,
  and a planted read-write `Store(` open in a temp copy of a module outside the allowlist fails
  `test_no_read_write_store_open_outside_the_allowlist`, naming the site.
- **K-R3.** Slices a to g each add one family module under `tests/census/`. None writes its own
  walk, alias resolution or allowlist checks.
- **K-R4.** `tests/census/report.py <family> [--list]` prints the tables the spec scripts print.
  The scripts under `workflow/plans/plan-29-code-quality-tasks/census/` are the measured
  prototypes: each family must reproduce its `f3709d2` numbers on a checkout of `f3709d2`
  before its rule is changed.
- **K-R5: the kit is built for the families that are waiting.** Named by the store review, and
  NOT built here: removal sites (22.6), CHECKPOINT and catalog holds (18.2, 18.3), out-of-daemon
  Lance reads (17.1), merge-table coverage (bug-124; 16.6, 23.1), the corpus predicate (16.1
  AC-5d), `_cli_read` (23.5 R7), the one writer installer (23.1). The kit's README lists them and
  shows the three things a new family supplies (predicate, allowlist with reasons, synthetic
  module). Those tasks add their family; this task does not.

Acceptance:

- **AC-K1:** for each family, the kit's count on `f3709d2` equals the committed log.
- **AC-K2 (the extraction changed nothing):** the bug-212 census reports the same
  `(site, line, family)` set before and after the move, recorded at the start commit.
- **AC-K3 (re-proven on its bypass):** K-R2's planted open fails the bug-212 test; and the
  mutation the ledger recorded ([[bsd-impressions#imp-scanner-needs-synthetic-positives]]:
  `_store_aliases` returning only `{"Store"}`) fails the synthetic-module test.
- **AC-K4:** the alias resolver has a synthetic module of its own; returning only the literal
  name fails it.
- **AC-K5:** no test file other than the kit defines an AST walk over `src/refmatrix` for a
  census (a census of the censuses: `ast.walk` with `rglob` in `tests/` outside `tests/census/`
  is allowlisted by file, with a reason).

## Slice a: one git runner {#slice-a}

### Requirements {#a-req}

**a-R1: the API.** `refmatrix/gitrun.py`, standard library only, importing nothing from
`refmatrix` (so `store`, `sync`, `handoff`, `upgrade` and `verbs` can all import it). {#a-r1}

- `run_git(repo, *args, timeout, strip_local_env=False)` runs `git -C <repo> <args>` and returns
  a result that unpacks as `(rc, out, err)`.
- `timeout` is keyword-only and has no default ([[#r0]] rule 1).
- It never uses `cwd=`. A missing directory is then git's own exit 128 with git's words.
- `out` and `err` are the raw text. Callers strip.
- `rc` is git's exit code. `rc is None` means git did not run, and the result's `why` field says
  which: `missing` (no `git` binary), `timeout` (the bound is named in `err`), or `oserror`. No
  caller parses `err` to find out. No other exception is caught.
- `strip_local_env=True` runs without the repository-local `GIT_*` variables (the list moves
  here from `store`), for a caller that must not let a hook's repository answer.

**a-R2: "not found" has one spelling.** The result has a property that is true only for
exit 1 with empty stderr: what a `--quiet` lookup prints for a miss (ruling L100,
[[plan-review-2026-11-13#lead]]). Its docstring says it is meaningful only for `--quiet`
lookups. Every other non-zero result, and every `rc is None`, is a failure. The failure sentence
(`_ss_git_failure` today) moves here unchanged, so the bug-225 texts stay byte-identical. {#a-r2}

**a-R3: "not a repository" has one spelling.** The rule "a failed `rev-parse` means not a
repository only when no `.git` exists at or above the directory" (bug-212 r4) moves here from
`store` and is used by both the tracked-catalog check and the handoff's non-git gate. {#a-r3}

**a-R4: every git call goes through it.** The 12 sites of [[#measured]]: {#a-r4}

| site (symbol) | today | after |
|---|---|---|
| `handoff._ss_git_run` and its 3 callers | the prototype of this helper | deleted; callers use `run_git`; behaviour identical |
| `handoff._ss_git_facts` (branch, head, dirty, session commits through `_ss_sh`) | any failure is `""`: a failed `git status` reads as a clean tree | a failure is collected and rendered wherever `trunk_error` is rendered (save-state doc, recall-state anomalies, CLI console, MCP result); a non-repository yields no git facts, by a-R3 |
| CLI `save-state --commit` (`git add`, `git commit` through `_ss_sh`) | a failed add or commit prints `(nothing to commit)` | "anything staged?" is asked first; nothing staged prints `(nothing to commit)`, exit 0; a failed add or commit is one `Error:` line with git's words and a non-zero exit |
| `store._run_git_check` (2 calls) | its own timeout rule; a raw `OSError` escapes | a thin adapter: `run_git(..., strip_local_env=True)`; `timeout` and `oserror` raise `TrackedCatalogCheckError`; `missing` answers `[]` as documented |
| `sync.changed_since` | its own spawn and `shutil.which` | `run_git`; the three typed errors and their texts unchanged |
| CLI `context --since` | no timeout; `check=True`: a bad ref is a raw `CalledProcessError` traceback | calls `sync.changed_since`; a bad ref is one `Error:` line, exit 1 |
| `upgrade._git` (8 callers) | no timeout | an adapter with a stated bound per call (table in the summary); `UpgradeError` texts unchanged |
| `verbs._timeline_git_leg` | its own spawn | `run_git`; the `warnings` texts unchanged |
| the STM capture: `_git_diff_summary`, `_git_commit_rationale`, `_git_added_comments` | `except Exception` returns empty; the repo is the hook's cwd | `run_git` in the resolved repository (a-R5) |

`hooks.py` has no Python git call: the generated shell hooks reach git through
`rmx sync --since`, which is `sync.changed_since`. The census covers `hooks.py` so a future
Python git call there is caught. The generated bash is outside a Python scan and is said to be.
{#a-r4-hooks}

**a-R5: the git milestone belongs to the right commit (bug-233).** {#a-r5}

- The repository comes from the command: `git -C <path> …` gives `<path>`; `cd <dir> && git …`
  gives `<dir>`; a command whose first segment is `git …` gives the hook's cwd. Anything else
  resolves to nothing.
- The diffstat is taken for the commit git itself named. For `commit`, `cherry-pick` and
  `revert`, git's output line `[<branch> <sha>] …` gives the sha, and the stat is
  `show --stat <sha>` in the resolved repository. With no such line, or no resolved repository,
  the event carries no stat. HEAD of the hook's cwd is never used as a stand-in.
- The label is the first output line in git's own form for that subcommand (a pinned table of
  forms). With none, the event text is `git <sub>` alone. A line of test output is never a
  label.
- The rationale and added-comment harvest use the same resolved repository and sha.
- A git call that fails here does not block the hook: the event is recorded without the stat,
  and the handler says why in the gate's form of [[#slice-c]].

**a-R7: git runs outside the store lock.** The daemon op `_op_sync_since` calls
`sync.sync_since`, which runs `changed_since`'s `git diff` while the op holds `_store_lock`
(`plan-review-fable-2026-11-14-store#plan29-converge-candidates`; rule 6 of [[#r0]]). After
this slice the changed-path list is resolved BEFORE the lock is taken and passed in. Every other
`run_git` caller's lock state is listed in the summary; none calls it under `_store_lock`. Task
16.4's git use, when it is built, goes through `run_git` and the census holds it to that. {#a-r7}

**a-R6: the census.** No git command list reaches `subprocess` or any other callable outside
`gitrun`. Families the scanner must find: a direct spawn; an aliased `subprocess` import; a list
bound to a name first; a list handed to a helper; a `shell=True` string that starts with `git `.
The allowlist is empty when the slice lands. {#a-r6}

### Acceptance {#a-ac}

- **AC-a1 (helper):** against a git shim on `PATH`, `run_git` returns each of: exit 0; exit 1
  with no stderr (the miss property is true); exit 1 with stderr (false); exit 128 (false); a
  hang past the bound (`rc is None`, `why == "timeout"`, within the bound plus a margin stated
  in the test); no binary (`why == "missing"`). Omitting `timeout` is a `TypeError`.
- **AC-a2 (env):** with `GIT_DIR` pointing at another repository, `strip_local_env=True` answers
  for the `-C` repository and the default does not.
- **AC-a3 (handoff facts):** with a shim whose `status` exits 128, the save-state document and
  the verb result carry the failure in git's words; "dirty" is not rendered as clean. RED at the
  start commit (it reads as clean).
- **AC-a4 (commit):** `save-state --commit` with a shim whose `commit` exits 1 with stderr exits
  non-zero and prints git's words; on a clean tree it prints `(nothing to commit)` and exits 0.
  RED at the start commit for the first half.
- **AC-a5 (`context --since`):** a ref git rejects gives one `Error:` line and exit 1, no
  traceback. RED at the start commit.
- **AC-a6 (bounds):** every `upgrade` git call passes a bound; a hanging shim ends in
  `UpgradeError` naming the call and the bound. RED at the start commit (it hangs; the test
  itself is bounded, so the red run is a failure, not a hang).
- **AC-a7 (bug-233), one test per shape from the registry row**, each in a real temp repository
  beside a different-content repository that is the hook's cwd:
  - `git -C <clone> commit …` → the stat equals `git -C <clone> show --stat <sha>`;
  - `cd <clone> && git commit …` → the same;
  - `pytest …; git checkout -- f` with test output first → the event text has no test-output
    line and no stat.
  All three are RED at the start commit.
- **AC-a8 (characterization):** the bug-225 and bug-212 suites pass unchanged; their texts are
  the goldens for a-R2 and a-R3.
- **AC-a9 (census):** the scanner finds all 12 sites on `f3709d2` (AC-K1), every family in the
  synthetic module, and nothing on the tree after the slice. A planted
  `subprocess.run(["git", "status"])` in a temp copy of any module fails the test and names the
  site.
- **AC-a10:** bug-233 is `fixed` with a sha reachable from `master`.
- **AC-a11 (lock placement):** in the sandbox, with a git shim that blocks until released, a
  `sync --since` through the daemon is in flight and a second op that needs `_store_lock`
  answers before the shim is released. RED at the start commit (the second op waits). The check
  is the order of the two events, not a duration.

### Mutations that must fail {#a-mut}

| mutation | must fail |
|---|---|
| the miss property is `rc != 0` | AC-a1, the bug-225 r3 tests |
| the miss property ignores stderr | AC-a1 |
| a timeout returns `rc = 1` with empty stderr | AC-a1, AC-a6 |
| `strip_local_env` ignored | AC-a2 |
| `_ss_git_facts` drops a failed read | AC-a3 |
| the commit failure branch prints `(nothing to commit)` | AC-a4 |
| the stat uses the hook's cwd | AC-a7 (first two) |
| the label takes the first output line | AC-a7 (third) |
| the scanner matches only `subprocess.run` | AC-a9 (synthetic) |
| `changed_since` called inside the lock again | AC-a11 |

## Slice b: query term resolution and PQL argument types {#slice-b}

### Requirements {#b-req}

**b-R1: one resolver.** The query engine has one place that turns a concept name into concept
ids and one that turns a linkage name into a known linkage. Every evaluation path uses them: the
DSL's bare term and `linkage:concept` term, `neighbors`, `co_occurrence`, and PQL's `Row` and
`Neighbors`. {#b-r1}

- A name that resolves to no concept, and a linkage name that is not a registered linkage after
  alias folding, are each RECORDED with their kind, the text as typed, and the term they came
  from. The evaluation continues with an empty set for that term, as today.
- A registered linkage with no rows yet is known, and is not recorded.
- The record belongs to one run of one expression and is returned with its result. It is not
  left on the engine for the next run to inherit.

**b-R2: the record reaches the caller (bug-234).** {#b-r2}

| surface | default | with strict terms |
|---|---|---|
| CLI `rmx query` (all three routes: replica, daemon, direct) | one stderr line per record: the kind, the text, the term; for a linkage, the known linkage names. The result is printed; exit 0 | flag `--strict-terms`: nothing on stdout; the same lines as `Error:`; exit 1 |
| daemon op `query` | the result carries `unresolved`, a list, always present, empty when clean | argument `strict_terms`: `ok: false` with the same text |
| verbs `rmx_query` and `rmx_matrix` `run`; their MCP tools | the result carries `unresolved` and one `warnings` entry per record | parameter `strict_terms`: a `VerbArgsError` |
| the cross-project search | each store's `unresolved` stays with that store's rows | not offered: a linkage one store lacks is normal there |

`--strict-terms` is a new flag. The existing `--strict` (exact name match) keeps its meaning.
{#b-r2-flag}

**b-R3: n-ary set functions (bug-236).** `Difference` and `Xor` fold every argument left to
right, as `Intersect` and `Union` do. A set function with no argument is a `PQL:` error, not a
raw `StopIteration` or `IndexError`. In the DSL, the `xor` evaluator branch and its mention in
the `Op` comment are removed: the parser cannot build it. The `diff` branch stays and gains a
parser path through b-R6. {#b-r3}

**b-R4: argument kinds (bug-238).** Each PQL function declares the kind of each argument, and a
wrong kind is a `ValueError` reading
`PQL: <Function> argument <n> must be a <kind>, got <kind> '<text>'`. {#b-r4}

| function | arguments |
|---|---|
| `Row` | name, name (exactly two) |
| `Neighbors` | name, then an optional integer |
| `Intersect`, `Union`, `Difference`, `Xor` | one or more bitmaps |
| `TopN` | a bitmap, then an optional integer |
| `Count` | a bitmap or a weighted list |

A bare identifier and a quoted string are both names. A top-level bare identifier is
a `PQL:` error naming it. This slice lands before 29.2's query work
([[task-29.2-mypy-gate#seam]]), so it defines the evaluator's value type (bitmap, weighted list,
count, name, integer) and 29.2 builds `run_pql`'s result union on it
([[task-29.2-mypy-gate#r4]], whose AC-7 holds the top-level case).

**b-R5: the census.** In the module that holds the query engine, `resolve_concept_ids`,
`resolve_concept_ids_many`, `load_bitmap` and `get_linkage_id` are called only inside the two
resolver functions and `topn` (which iterates registered linkages, known by construction). The
11 `resolve_concept_ids` calls in 8 other modules (context, scan, recall, graphread, …) resolve
prompt tokens, where a miss is the normal case; they are listed in the summary and not
converged. {#b-r5}

**b-R6: `A AND NOT B` is a difference (the `NOT` half of bug-237).** {#b-r6}

- The parser builds the `diff` op for `X AND NOT Y`, so no partition-wide id set is built for it.
- The universe is built only for a `NOT` that is not the right side of an `AND`, at most once
  per run.
- The universe comes from a public `Store` method (the row names `partition_entity_ids`), not
  from the store's private `_connect()`.
- Results are unchanged for every expression.
- bug-237's other half, `topn` loading every bitmap of every linkage, is NOT changed here: the
  row asks for a measurement on a real store first. The registry row is split so that this half
  can be closed: the `topn` cost gets its own row.

**b-R7: what this changes for measurements.** After b-R2 a query with a typo no longer looks like
a valid empty or over-full answer. Any frozen query set measured across this slice compares two
different things: G22's BEFORE and AFTER, and 21.2 / 21.4's sets, are both taken after this slice
is deployed (`plan-review-fable-2026-11-14-queue#p29-4`). This is a constraint on those tasks'
schedule; the summary repeats it. {#b-r7}

### Acceptance {#b-ac}

All RED at the start commit unless marked.

- **AC-b1:** in a throwaway store where `defines:x` matches and `mentions:x` matches, the query
  `defines:x AND NOT mentions:xx` (a typo) prints the same rows as `defines:x` AND names
  `mentions:xx` on stderr as an unresolved concept. With `--strict-terms`: exit 1, empty stdout.
- **AC-b2:** `defines:x AND NOT mention:x` (an unknown linkage) names `mention` and lists the
  known linkages. An alias of a known linkage is not named.
- **AC-b3:** a known linkage with no rows, and a concept that resolves but has no rows under
  that linkage, are not recorded (the two negatives; a mutation that records every empty term
  fails here).
- **AC-b4:** two runs on one engine: the second run's record does not contain the first's.
- **AC-b5:** the daemon op, the `rmx_query` verb, the `rmx_matrix` `run` action and the MCP tool
  each return `unresolved` for AC-b1's query (four tests, the daemon ones in the sandbox), and
  `unresolved: []` for a clean one.
- **AC-b6:** `Difference(a, b, c)` equals `a − b − c` and `Xor(a, b, c)` equals the fold, on
  fixture bitmaps where the third argument changes the answer. `Intersect()` is a `PQL:` error.
- **AC-b7:** each shape in the bug-238 row: `Count(foo)`, `Count("abcdef")`,
  `Intersect(foo, bar)`, `Xor(foo, bar)` → the `PQL:` error naming the function and the
  argument; `Row(mentions)` and `Row(a, b, c)` → the arity error; `Count(TopN(Row(mentions, x)))`
  still returns a count (characterization).
- **AC-b8 (characterization):** goldens recorded at the start commit for ten valid DSL and PQL
  expressions are equal after the change, apart from the added `unresolved` key.
- **AC-b9 (census):** on `f3709d2` the scanner finds the 4 + 6 sites of [[#measured]]; after the
  slice only the allowlisted functions call the store's resolution methods; a planted method
  that calls `self.s.resolve_concept_ids` directly fails the test.
- **AC-b10:** bug-234, bug-236 and bug-238 are `fixed` with shas reachable from `master`;
  bug-237 is split, its `NOT` half `fixed`, its `topn` half a new open row.
- **AC-b11 (b-R6):** with a store whose universe method counts its calls: `A AND NOT B` makes 0
  calls; `NOT A` makes 1; `NOT A OR NOT B` makes 1. The row sets equal those recorded at the
  start commit. No call to `_connect` remains in the query module. RED at the start commit for
  the first count (it is 1).

### Mutations that must fail {#b-mut}

| mutation | must fail |
|---|---|
| `neighbors` resolves directly again | AC-b9; a `Neighbors(typo)` case in AC-b1's file |
| the linkage check skips alias folding | AC-b2 |
| every empty term is recorded | AC-b3 |
| the record is kept on the engine | AC-b4 |
| the daemon op drops `unresolved` | AC-b5 |
| the CLI prints the warning on one route only | AC-b1, parametrized over the three routes |
| `Difference` stops at two arguments | AC-b6 |
| `Count` accepts a name | AC-b7 |
| `AND NOT` evaluated through the universe again | AC-b11 |
| the universe rebuilt per `NOT` | AC-b11 (third case) |

## Slice c: broad `except` handlers {#slice-c}

### Requirements {#c-req}

**c-R1: one classifier.** A handler is BROAD when it catches `Exception` or `BaseException`
(alone or in a tuple) or is a bare `except:`. Every broad handler in `src/refmatrix` is in
exactly one class, first match wins. The rule is the docstring of `census_broad_except.py`, word
for word: {#c-r1}

| class | rule |
|---|---|
| re-raised | the handler body, nested functions excluded, contains a `raise` |
| surfaced | the body uses the bound exception name; or adds to a failure counter (the target matches the script's `COUNTER` pattern; a plain `n += 1` does not count); or calls one of the script's `SURFACE_CALLS`, `print(..., file=…)`, `click.echo(..., err=True)`, a console print, or a `stderr.write` |
| justified | none of the above, and the `except` line carries `# noqa: BLE001 — <reason of at least three words>` |
| silent | none of the above |

**c-R2: unowned silent handlers end at zero.** Each of the 192 silent handlers ([[#measured]])
is either OWNED by another approved task (c-R2a) or moved into one of the three classes: {#c-r2}

- a handler around a release (`close`, `unlink`, `ROLLBACK`, a flush) is justified, and the
  reason names what is released;
- a handler that turns a lookup failure into a default is narrowed to the typed error the
  lookup raises, when that error is known (`Store.get_linkage_id` raises `KeyError`). Narrowing
  changes behaviour for every other exception, so each narrowed site gets a test;
- a handler on a sync, ingest, memory or hook path is surfaced: counted, and said where that
  path already says things;
- nothing else about the handler's control flow changes without a test.

**c-R2a: a site another approved spec owns is listed, not pulled in**
(`plan-review-fable-2026-11-14-queue#p29-4`). The test holds a list `module:qualname → owning
task id`. A silent handler on that list is allowed while its owner is open. {#c-r2a}

- Known at `f3709d2`: `Store.content_rank`'s reinforcement leg (bug-223, owned by bug-218's
  spec); `Store.rebuild_entities_indexes`' swallowed CHECKPOINT (bug-123, owned by 18.3 R8).
- Named by the store review as touched by T4-T6 specs, owner to be read from each spec when the
  list is written: the GMD fallback handler in `ingest`'s tree pass, `Scheduler._loop`,
  `Store.close` and `Store.transaction` (23.1 R1.6, R7).
- An entry must name a task whose spec file exists and which says it changes that handler. A
  site with no such owner is not listable: it is fixed here.
- An entry whose handler is no longer silent fails the test until it is removed, so the list
  cannot outlive its sites.
- bug-119's handler (`except json.JSONDecodeError: continue` in the log replay) is typed, so this
  census does not see it. It stays with 17.4 R6.

**c-R3: memory paths get no quiet justification.** In the memory-path modules (at `f3709d2`:
`ingest_gmd`, `handoff`, `recall`, `promote`, `memory_index`, `memory_layout`, `stm`, `embedder`,
`consolidate`, `brief`; after 29.5 also the CLI modules that hold the `memory`, `focus`,
`save-state`, `recall-state` and hook commands), a handler may be `justified` only if its
`module:qualname` is in a named list in the test, with the reason why the swallowed failure
cannot lose or hide a memory write or read. This is `CLAUDE.md#no-silent-failures` made
checkable. {#c-r3}

**c-R4: the ratchet, then the absolute rule.** The slice lands module group by module group,
memory-path modules first. From its first commit a per-module count of silent handlers is
recorded in `tests/census/broad_except_baseline.json`; the test fails when a module's count
rises (a NEW silent handler) and when it falls without the file being lowered. When the last
group lands the file is deleted and the test fails on ANY silent handler that is not on the
owned list of c-R2a. {#c-r4}

**c-R5: the three counts are recorded.** The summary has the table re-raised / surfaced /
justified / silent, per module, at the start commit and at the end, produced by
`tests/census/report.py broad-except`, and says how many of the 192 went to each class and how
many were narrowed. {#c-r5}

**c-R6: the two unowned registry rows of this class.** {#c-r6}

- bug-096: `rmx reingest` exits 1 when any step failed and names the failed steps on stderr.
- bug-240: only if the 0.83.1 hotfix has not closed it: a file argument to `rmx ingest` is
  refused with the `rmx sync -f <file>` remedy, or routed to the single-file sync; never
  `ingested 0 entities`, exit 0.

**c-R7: edits to the derive modules are batched.** A comment or a narrowed handler in `ingest.py`,
`ingest_gmd.py` or `session_ingest.py` changes `store.derive_code_hash` and flips every fleet
store to `behind_code` ([[task-29.2-mypy-gate#derive-hash]]). This slice's edits to those three
files (13 silent handlers at `f3709d2`: ingest 8, ingest_gmd 5) land in ONE commit group, in the
same release as 29.2's edits to them, and are covered by 29.2's AC-18 (equal graph digest). What
is done on live stores is `plan-29 D4` ([[task-29.2-mypy-gate#d4]]). {#c-r7}

### Acceptance {#c-ac}

- **AC-c1 (the scanner fires):** a synthetic module with one handler per class and per leg of the
  rule (a `raise` inside a nested function does not count; a plain `n += 1` does not count; a
  bare `# noqa: BLE001` with no reason is silent; a tuple containing `Exception` is broad; a
  typed `except OSError:` is not broad) is classified exactly.
- **AC-c2 (a new silent handler fails):** `except Exception:` + `pass` planted in a temp copy of
  any module fails the test and names `module:qualname` and the line. RED before the test
  exists; then green on the tree only through the ratchet.
- **AC-c3 (memory paths):** a `justified` handler planted in a memory-path module, absent from
  the named list, fails. The 18 silent handlers of those modules are gone.
- **AC-c4 (each narrowed site):** for every handler narrowed under c-R2, a test shows the typed
  error still yields the default and another exception now propagates.
- **AC-c5 (each surfaced site on a sync / ingest / memory / hook path):** a test drives the
  failure and asserts the count or the message; deleting the report line fails it
  ([[bsd-impressions#imp-nonfatal-needs-its-report-pinned]]).
- **AC-c6 (end state):** unowned silent is 0; `broad_except_baseline.json` does not exist; every
  entry of the owned list names an existing spec that names the handler; the summary carries the
  c-R5 table with the owned sites as their own column.
- **AC-c8 (owned list):** an entry with a task id whose spec file does not exist fails; an entry
  whose handler now re-raises fails as stale; a silent handler planted beside an owned one, in
  the same function, still fails.
- **AC-c9 (bug-096):** a `reingest` whose embed step fails (a stand-in step that raises) exits 1
  and names the step on stderr. RED at the start commit (exit 0).
- **AC-c7 (no regression):** the full suite is equal by E line before and after each group.

### Mutations that must fail {#c-mut}

| mutation | must fail |
|---|---|
| the scanner skips `BaseException` | AC-c1 |
| a `raise` in a nested function counts as re-raised | AC-c1 |
| any `noqa` counts as justified | AC-c1 |
| the ratchet compares the repo total, not per module | AC-c2, with one handler removed elsewhere |
| the memory-path list check removed | AC-c3 |
| a narrowed handler widened back | AC-c4 |
| a surfaced handler's report line removed | AC-c5 |
| the owned list accepts any task id string | AC-c8 |
| the owned list matches by module only | AC-c8 (third case) |
| `reingest` returns 0 after a failed step | AC-c9 |

## Slice d: busy is not absent {#slice-d}

- **d-R1.** Each of the 56 `ping` gates ([[#measured]]) is classified in the summary:
  DISPLAY (it reports liveness and its false branch opens nothing), INTERNAL (the daemon or the
  hub probing itself or a predecessor; plan-4 governs those), or ROUTE (its false branch opens
  the store in-process or tells the user no daemon runs).
- **d-R2.** Every ROUTE gate is replaced by the typed classifier: only an absent daemon reaches
  the in-process branch; a busy one is refused in the verb's words. The in-process branch takes
  its `Store` from the daemon-absent accessor of [[task-29.2-mypy-gate#r5]]; whichever task
  lands first creates it and the other adopts it. Known ROUTE gates from this spec's reading:
  `partition_add`, `partition_rename`, `import_`, `_subject_upsert`, `_subject_link`, and the
  CLI `query` command's daemon branch.
- **d-R3: the census.** A `ping(...)` inside a condition is allowed only at a `module:qualname`
  in the allowlist, which records its class. ROUTE is not an allowed class.
- **AC-d1:** the scanner finds the 56 on `f3709d2` and every family in a synthetic module
  (`if ping(…)`, `if not dm.ping(…)`, `x if ping(…) else y`, `bool(ping(…))`, `while`), and
  ignores a `ping` whose result is only returned or displayed.
- **AC-d2:** a planted `if daemon_mod.ping(root): … else: Store(root)` fails the test.
- **AC-d3:** for each converted ROUTE gate, a sandbox test with a daemon that holds its lock
  (alive, not answering in the gate's budget) shows a typed busy refusal and no in-process open.
  RED at the start commit for each.
- **Mutations:** the classifier call replaced by a bare `ping` (AC-d3, AC-d2); the allowlist
  check accepting class ROUTE (AC-d2).

## Slice e: bounds {#slice-e}

- **e-R1: one `Deadline`.** A small helper (a budget in seconds at construction; "seconds left,
  never below a floor"; "expired") replaces the four `_left` closures. Behaviour identical:
  goldens for each of the four paths against a silent test daemon, recorded at the start commit.
- **e-R2: every daemon call states its bounds.** Each of the 66 constant-op calls passes
  `timeout=` and `retries=` explicitly. For the 35 that rely on a default today the value
  written is the value in effect, so nothing changes at run time. A WRITE op found retrying
  (`retries` above 0 on an op that is not idempotent) is not changed here: it gets a registry
  row naming the op, because a re-sent write is a behaviour question
  ([[bsd-pattern-sibling-render-path#rule]] point 5).
- **e-R3: the census.** A daemon RPC call with a constant op and no explicit `timeout` or no
  explicit `retries` fails. A second leg: no function named `_left` that computes a remaining
  budget outside the helper.
- **AC-e1:** the scanner finds 66 / 35 / 6 on `f3709d2`, and both families in a synthetic module.
- **AC-e2:** a planted `daemon_mod.call(root, "ping", {})` fails the test.
- **AC-e3:** `Deadline` unit tests: left never negative; the floor; expiry; a clock passed in,
  no sleeping.
- **AC-e4 (characterization):** the four goldens are unchanged.
- **Mutations:** `Deadline` returning the full budget every time (AC-e4 against the silent
  daemon: the wall bound is exceeded, asserted on the number of calls made, not on seconds); the
  census ignoring `retries` (AC-e1).

## Slice f: the refusal carries its caller's remedy (bug-232) {#slice-f}

- **f-R1.** `refuse_tracked_catalog_open` takes a required keyword `remedy`. The fixed tail of
  today's message is removed from the function.
- **f-R2.** Each of the 4 callers passes its own: `_store_rw` and `verbs.local_write` keep
  today's text; `compact` names untracking only (no daemon runs compact); `migrate-to-duckdb
  --out` says to choose an untracked `--out` path or untrack that file.
- **f-R3.** The advice is a test case ([[bsd-impressions#imp-test-the-advice-in-the-error]]):
  for each caller, a test follows the remedy literally and the command then succeeds.
- **AC-f1:** each caller's refusal text is pinned; none contains another caller's remedy. RED
  at the start commit for `compact` and `migrate-to-duckdb`.
- **AC-f2:** f-R3's four tests.
- **AC-f3:** omitting `remedy` is a `TypeError`; the existing catalog-opener census still passes.
- **AC-f4:** bug-232 is `fixed` with a sha reachable from `master`.
- **Mutations:** a default `remedy` restored (AC-f3); `compact` passing `_store_rw`'s text
  (AC-f1).

**Overlap** (`plan-review-fable-2026-11-14-queue#dup-2`): `task-linked-readonly-store` R2 adds
another caller class to this same check, and its R1 rests on bug-125's path comparison. This
slice is the mechanism: the refusal has no text of its own after it. The linked-store task adds
its caller with its own `remedy` and its own row in AC-f1 and AC-f2; it does not add a second
message path. bug-125 is not taken here. Which task closes bug-232 is this slice ([[#k7]]),
because plan-29 runs first (L104); if the linked-store task is built first instead, it does
f-R1 to f-R3 and this slice is dropped. {#f-overlap}

## Slice g: one partition default for daemon ops {#slice-g}

- **g-R1.** The expression `args.get("partition") or d._st()._partition_name` appears 20 times in
  the daemon's op handlers. One function takes `(d, args)` and returns the name; every op calls
  it.
- **g-R2.** No behaviour changes. In particular, WHERE each op evaluates it (before or inside
  `_store_lock`) stays as it is; the summary lists that per op, because a default read outside
  the lock is a question for plan-23's binding contract, not for this slice
  (`plan-review-fable-2026-11-14-store#plan29-converge-candidates`).
- **g-R3: the census.** A read of `"partition"` from an op's `args` combined with a fallback to
  the store's partition name, outside the one function, fails. Families: the `or` form, a
  conditional expression, `args.get("partition", <store name>)`.
- **AC-g1:** the scanner finds the 20 on `f3709d2` and each family in a synthetic module.
- **AC-g2 (characterization):** for each of the 20 ops, a call with and without `partition`
  resolves to the same partition before and after (goldens at the start commit, against a
  throwaway two-partition store).
- **AC-g3:** a planted copy of the expression in a new op fails the test.
- **Mutations:** the function ignoring `args` (AC-g2); the scanner matching only the `or` form
  (AC-g1).

## Test strategy {#test-strategy}

- RED first by `@ch-test-engineer`, recorded per slice to `workflow/review-output/`; GREEN by
  `@ch-implementer`, who writes no tests ([[tdd-governance#pipeline]]). Characterization ACs are
  labelled and their goldens are recorded before the first edit.
- A RED test that passes at the start commit is not RED ([[feedback_red_test_must_fail_at_head]]):
  each AC above says whether it is.
- Daemon tests use the sandbox and a short temp root. No test opens a live store.
- The git tests reuse the shim pattern of `tests/test_bug225_handoff_trunk.py` (a fake `git` on
  `PATH` with modes), promoted to a shared fixture; it is an external-tool stand-in and is
  recorded in `workflow/test_mock_registry.md`. bug-233's tests use real temp repositories.
- Mutations run on a commit that holds the fix, each must fail and not hang, and `__pycache__`
  is cleared after the batch.
- After every slice: the full suite equal by E line, the generated CLI tree and verb parity
  unchanged, `./scripts/lint-gmd.sh` clean, and (once 29.2 has landed) `./scripts/check-types.sh`
  exit 0.

## Files {#files}

Names after the 29.5 split are resolved by symbol ([[#split]]).

| file | change |
|---|---|
| `tests/census/kit.py` (extracted from `tests/test_bug212_r4_red.py`), `tests/census/report.py`, `tests/census/README.md`, one family module per slice | create |
| `tests/test_bug212_r4_red.py` | import the kit; scanner functions removed from the file; tests and allowlists stay |
| the module that holds `_op_sync_since` and `sync.sync_since` | the changed-path list resolved before the lock (a-R7) |
| the module that holds the daemon op handlers | slice g |
| the module that holds the CLI `reingest` command | bug-096 (c-R6) |
| `src/refmatrix/gitrun.py` | create: `run_git`, the result type, the two rules |
| the modules that hold the 12 git sites (`handoff`, `store`, `sync`, `upgrade`, `verbs`, the CLI `save-state`, `context` and focus-hook modules) | adopt `run_git`; delete `_ss_git_run`, the git uses of `_ss_sh`, the four `shutil.which("git")` pre-checks |
| the module that holds `QueryEngine` and `_PQLEvaluator` | the resolver; the record; n-ary folds; argument kinds; dead branches removed |
| the modules that hold `_op_query`, the CLI `query` command, the `rmx_query` and `rmx_matrix` verbs, the MCP adapter | carry `unresolved`; `--strict-terms` |
| every module with a silent handler (31 modules at `f3709d2`) | slice c, by group |
| `tests/census/broad_except_baseline.json` | create in slice c's first commit; delete in its last |
| the CLI modules of the ROUTE gates | slice d |
| `src/refmatrix/deadline.py`; the modules of the 4 `_left` closures and the 35 calls | slice e |
| the module that holds `refuse_tracked_catalog_open` and its 4 callers | slice f |
| `tests/test_gitrun.py`, `tests/test_bug233_git_milestone_repo.py`, `tests/test_query_term_resolution.py`, `tests/test_pql_argument_kinds.py`, `tests/test_census_*.py`, `tests/test_deadline.py`, `tests/test_bug232_caller_remedy.py` | create |
| `docs/SYSTEM.md` (the query section: `unresolved`, `--strict-terms`); the generated CLI tree | update |
| `workflow/bug_registry.md`, `workflow/test_mock_registry.md` | the closed rows; the shim |
| `workflow/implementation_summaries/task-29.3-converge-shapes.md` | one section per slice, with the before / after census tables |

## Key decisions {#decisions}

None of these needs the user; each records the choice and why. The one open decision that
touches this task is `plan-29 D4` ([[task-29.2-mypy-gate#d4]]). A reviewer who disagrees with one
below raises it as a new `plan-29 D<n>` (D7 to D19 are taken by the 29.1 / 29.4 / 29.5 specs).

1. **`run_git` returns a result for "git did not run" instead of raising**. This is the
   contract ruling L96 and L100 tested (`_ss_git_run`), and its callers already print such a
   result. The `why` field is added so no caller reads the text to tell a timeout from a missing
   binary. {#k1}
2. **Unresolved terms warn by default and fail only under `--strict-terms`**, as the
   bug-234 row proposes. An unknown linkage is not made a hard error, because the cross-project
   search asks stores that legitimately lack a linkage another has. {#k2}
3. **`Difference` and `Xor` fold**, as `Intersect` and `Union` do. Refusing a third
   argument would be the other valid fix; folding matches the sibling functions. {#k3}
4. **Unowned silent handlers end at zero repo-wide, not only on memory paths**. The plan says
   every site ends in one of three classes. The ratchet holds the line while the groups land, and
   deleting it at the end makes the rule absolute. A site another approved spec owns is listed
   with that task's id and left to it. {#k4}
5. **Slice c adds no runtime "swallowed error" helper**. The 172 surfaced handlers report
   through what their process already has (the daemon log, CLI stderr, a verb's `warnings`); a
   new shared sink would be a feature ([[plan-29-code-quality#non-goals]]). The ONE thing
   converged is the rule. {#k5}
6. **Slices d and e change no behaviour except at ROUTE gates**. Making 35 retry counts
   explicit writes down today's values; choosing better ones is per-op work for the registry. {#k6}
7. **bug-232 is taken here**. It is the newest sighting of class S and a four-caller
   change. 29.1's triage row for bug-232 should name this task. The queue review would merge it
   into `task-linked-readonly-store`; that task becomes a fifth caller instead ([[#f-overlap]]).
   {#k7}
8. **The query slice takes bug-237's `NOT` half and not its `topn` half**. The `NOT` rewrite
   is the parser path that b-R3's `diff` branch needs, so doing it later would touch the same
   lines twice. `topn` waits for its measurement. {#k8}
9. **The kit is an extraction of bug-212's scanner**, and the bug-212 test file becomes its
   first user. Seven families from other tasks are waiting for it; none is built here. {#k9}
10. **The git and query slices land before 29.2's query and strict work**
    ([[task-29.2-mypy-gate#seam]]). {#k10}

## How this adapts to the 29.5 split {#split}

- Every site is a symbol. File names, line-free, are those of `f3709d2` and are for tracing.
- The census scripts and the kit find sites by walking `src/refmatrix` with `rglob`; allowlists
  are keyed `module:qualname`, written at the task's start commit from the kit's own output.
- The layout 29.5 produces: `refmatrix/cli/` (shared helpers in `cli/__init__.py`, commands in
  `cli/<group>_cmds.py`) and `store.py` plus `store_<concern>.py` mixin modules, with `Store`
  keeping its name and import path. A `module:qualname` key for a `Store` method then names the
  mixin class and its module; the kit resolves a method to the class that defines it.
- **First step of each slice:** run its report at the start commit and put the table in the
  summary. Counts should equal this spec's; a difference that moved code does not explain is a
  finding, reported before any edit.
- 29.5 re-keys the existing catalog-opener census (`tests/test_bug212_r4_red.py`) to the new
  module names and re-proves it on its synthetic bypass
  (`plan-review-fable-2026-11-14-queue#b1`, and its `#b2`). Slice K extracts the scanner from
  the re-keyed file and re-proves it again (AC-K3); slice f relies on that test.
- The memory-path module list of c-R3 is re-derived from 29.5's moved-symbol table
  ([[task-29.2-mypy-gate#needs-295]] asks 29.5 for it).

## Review findings folded on 2026-11-14 {#fold}

The review documents are `workflow/plan-review-fable-2026-11-14-queue.md` (master `3551894`) and
`workflow/plan-review-fable-2026-11-14-store.md` (master `ec3e0e8`). They landed on master after
this branch's base (`f3709d2`), so they are cited here as `doc-id#anchor` code spans; a wikilink
to a document this branch does not hold fails the repo lint. Turn them into wikilinks in the
merge commit. {#fold-cites}

| finding | change here |
|---|---|
| `plan-review-fable-2026-11-14-store#plan29-converge-candidates`: extract bug-212's scanner; do not write new AST walks | [[#slice-k]] rewritten as the extraction (K-R1 to K-R5, AC-K2, AC-K3, AC-K5); [[#k9]] |
| same: `run_git` for `_op_sync_since`, which runs git inside `_store_lock`; and for 16.4 | [[#a-r7]], AC-a11 |
| same: the partition default at 20 daemon sites | [[#slice-g]] |
| same: except-census hits those specs create or touch | [[#c-r2a]] |
| `plan-review-fable-2026-11-14-queue#p29-4`: the except census will flag sites approved specs own (bug-223, bug-123, bug-119); fix only the unowned (bug-096, bug-240) | [[#c-r2a]], [[#c-r6]], AC-c8, AC-c9 |
| same: bug-234's fix changes what G22 and 21.2 / 21.4 measure | [[#b-r7]] |
| same: not parallel on the query module; 29.3's query half first | [[task-29.2-mypy-gate#seam]], b-R4, [[#k10]] |
| `plan-review-fable-2026-11-14-queue#dup-2`: bug-232 and bug-125 overlap `task-linked-readonly-store`; bug-240 goes with bug-241 | [[#f-overlap]]; [[#c-r6]] makes bug-240 conditional |
| the queue review's `#dup-3` (29.1 input): bug-237, bug-096, bug-188, bug-201 | bug-237's `NOT` half in [[#b-r6]]; bug-096 in [[#c-r6]]; bug-188 and bug-201 not taken, with the measured count ([[#classes-no-helper]]) |
| 29.5's author: `derive_code_hash` hashes file content | [[#c-r7]]; `plan-29 D4` |

## Out of scope {#out-of-scope}

- bug-237's `topn` half (it needs a measurement first), bug-188 (env knobs) and bug-201: they
  stay in the registry under 29.1's triage ([[#classes-no-helper]]).
- The seven census families other tasks will add to the kit (K-R5).
- Silent handlers another approved spec owns (c-R2a).
- The 11 `resolve_concept_ids` call sites outside the query engine (b-R5).
- git run by the generated shell hooks.
- Better retry values for daemon calls (e-R2), and any change to `daemon.call`'s default.
- A shared runtime sink for swallowed errors ([[#k5]]).
- The partition-binding contract (plan-23), and the three process PATTERNs
  ([[#classes-no-helper]]).
- `rmx save-state --commit`'s use of `git add -A`
  ([[feedback_save_state_commit_adds_all]]): slice a changes how its failure is reported, not
  what it stages.
