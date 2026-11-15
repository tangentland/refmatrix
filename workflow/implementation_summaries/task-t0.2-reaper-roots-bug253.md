---
gmd: "0.1"
id: impl-task-t0-2-reaper-roots-bug253
title: "T0.2 + 29.4b GREEN: the spawn ledger and the reaper (bug-229), test roots under the sandbox, the dev-rmx helper (bug-253), bug-170/168/127"
tags: [implementation-summary, t0, task-29.4, reaper, sandbox, bug-229, bug-253, bug-170, bug-168, bug-127]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-15
---

# T0.2 + 29.4b GREEN: reaper, test roots, dev-rmx helper {#root}

rel: implements -> [[task-t0-suite-trust-sweep#t0-2]]
rel: implements -> [[task-29.4-suite-health#r4]]
rel: implements -> [[task-29.4-suite-health#r5]]
rel: implements -> [[task-29.4-suite-health#ac-5]]
rel: implements -> [[task-t0-suite-trust-sweep#t0-2-bug253]]
rel: derives-from -> [[t02-red-report]]

Plan-29 task 29.4, stage 2 (T0.2 + 29.4b). Branch `task-t0.2-reaper-roots-bug253` in
`/Volumes/littlebig/refmatrix-t02-green` (symlinked `.venv-eval`). RED tip `860fce8`. GREEN code
commit `78489af`. Rulings followed: L142, L146 (and L121, L122, L123 through the spec). No
`src/` file changed. No test assertion was edited; the edits to test files are the ones the RED
report's `#green-work` assigns to GREEN (lookups, env, skip conditions, roots, two helper
bodies). Mutations are the reviewer's and are not recorded here.

## What changed {#changes}

### The spawn ledger, the reaper and the sweep: `tests/sandbox_site/rmx_sandbox.py` {#changes-sandbox}

- Process identity is (pid, start time), read with `proc_info(pid) -> dict | None`
  (`start`, `ppid`, `state`): darwin `sysctl(KERN_PROC_PID)` through `ctypes`, linux
  `/proc/<pid>/stat`, any other platform raises. The `kinfo_proc` offsets (start 0, `p_stat` 36,
  `p_pid` 40, `e_ppid` 560) were probed on this host with a running, a SIGSTOPped and a zombie
  process. `process_table() -> dict` reads every process (`KERN_PROC_ALL`, about 2 ms).
- **R4.1, the ledger.** `ledger_write(how)` appends one JSON line to
  `<sandbox root>/children.jsonl` with one `os.write` under `O_APPEND`. The fields are `pid`,
  `ppid`, `start`, `argv` (`sys.orig_argv`), `cwd`, `root` (`REFMATRIX_ROOT`), `test`
  (`PYTEST_CURRENT_TEST` without its phase), `how` (`exec` or `fork`) and `t`. Two writers:
  - `install_from_env()` writes the exec'd child's line;
  - an `os.register_at_fork(after_in_child=…)` callback writes each fork's line. It is
    registered once per process, by `install_from_env()` in every child and by `enter()` in
    the pytest process.

  A cwd that has vanished is recorded as `cwd_error`. A line that cannot be written is said on
  the child's stderr.
- **R4.3, `owner.json`.** `enter()` writes `owner.json` atomically: `pid`, `start`, `argv`,
  `cwd` and `created`.
- **R5, test roots.** `short_root(prefix) -> str` is a `mkdtemp` under `<sandbox root>/t/`.
  `sandbox_root() -> Path` raises when there is no sandbox; it never falls back to `/tmp`.
- **`stop_process(pid, start, root, emit, protected=None) -> bool`**, each step printed:
  1. SIGCONT for a stopped process.
  2. `daemon.stop_daemon(root, timeout=20)` only when the ledger gives a root AND that root's
     `rmxd.pid` names THIS pid (R4.2 read with L142 (2): a ledger root alone does not make a
     pid that root's daemon).
  3. SIGTERM, a 5 s wait, SIGKILL, a 2 s wait.

  It never signals its own pid or an ancestor (`_ancestors()`, L142). It never signals a pid
  whose start time no longer matches.
- **`reap_ledger(ledger, label, emit, grace=0.0, descendants=False) -> dict`** is the one body
  behind both the finish reaper and the sweep. It reads one record per pid. A live pid with a
  different start time is printed as `reused` and never signalled. A line with no start time
  is printed and counted, never signalled. A survivor is printed
  `<label> pid=<n> age=<s> spawned in <test> argv=<…> root=<root | unknown (cwd=…)>` and then
  stopped. `descendants=True` (the finish reaper only) also takes every live descendant of the
  session that has no ledger line after a 2 s wait for a late line.
- **`sweep_orphans(ledger_path, emit=None, label=…) -> dict`** is R4.9.
  **`sweep_killed_runs(emit) -> dict`** is R4.3. It lists only `/tmp/rmx-*/owner.json`. A dead
  owner's survivors are stopped and printed `ORPHAN from a killed run: …`. The root is then
  removed, or KEPT and said so if anything survived.
- **R4.4.** `live_store_roots(root) -> list` lists store roots under the sandbox whose
  `rmxd.pid` names a live process.
- **R4.7.** `register_spawn(pid_or_daemon, root, why) -> None` (positional). Each entry is keyed
  to the node whose teardown finalizes the registering fixture: the nearest pytest
  `SubRequest` on the stack, else the current test. The entry is checked by
  `due_spawns(nodeid, live_nodes) -> list` and `check_spawn(e, emit) -> str | None` (a 10 s
  grace for a stop in flight). `check_spawn` stops what it finds.
- **R4.6.** `track_inprocess(obj, root)` and `set_inprocess_ops(serving, stop)` keep a
  `WeakKeyDictionary` registry. `inprocess_leaks(emit) -> list` reads it.
- **`reap_session(repo, emit) -> int`** runs at the outermost session's finish, in this order:
  1. the R4.4 count (printed when n ≥ 1), taken before anything is stopped;
  2. in-process daemons;
  3. registered spawns not yet checked;
  4. the ledger plus live descendants, after a 3 s grace.

  It returns the number of findings. `failure_record(nodeid, phase, e_line)` writes
  `$RMX_FAILURES_OUT` when that variable is set. `leak_log(repo, lines)` appends to
  `workflow/review-output/leaked-processes.log`. `claim_session(config) -> bool` makes the
  outermost session the one that reaps.

### conftest: the hooks and the retired pins {#changes-conftest}

`tests/conftest.py`:
- **`Daemon.__init__` is wrapped** (`_track_daemon_instances`) to record each instance and do
  nothing else. `_serve_thread(d)` finds a running `serve_forever` frame for the instance.
- **`pytest_sessionstart`** claims the session and runs the sweep. `pytest_report_header`
  returns `rmx sandbox: <n> orphan process(es) swept from killed runs`.
- **`pytest_runtest_makereport`**, at teardown, checks the registered spawns that are due and
  fails that test by name.
- **`pytest_sessionfinish`** runs `reap_session` and sets `TESTS_FAILED` on any finding.
  `_emitter(config)` prints through the terminal reporter's `write_line`, so a line never
  shares the progress line.
- **The 18 venv pins and R1.1's venv condition are deleted.** `allowed_skips` decides the hooks
  pin only. MEH-5 ([[bsd-t01-r1-fff91a8#meh-5]]): the stage-2 comment at the old
  `:254` is gone with the pins, and the block now says what stage 2 did.

### The dev-rmx helper and the files that use it (bug-253) {#changes-devbin}

- **`tests/devbin.py` (new):** `dev_bin() -> Path` (`Path(sys.executable).parent`, not
  resolved), `dev_rmx() -> Path`, and `dev_env(env=None) -> dict`. `dev_env` returns a copy
  whose `PYTHONPATH` starts with this checkout's `src`.
- **The eleven files** take `RMX` (or `DEV_BIN`) from the helper, and their child envs from
  `dev_env()`. The five erroring files lose their own `"PYTHONPATH": str(REPO / "src")`. The six
  skipping files lose their venv `skipif`s:
  - `test_the_tool_itself_is_the_one_that_scrambles` keeps `skipif(not HAS_RG, reason="needs
    rg")`;
  - `test_grep_count_rows_e2e.py` keeps `skipif(not Path(GREP).exists(), reason="/usr/bin/grep
    missing")`.

  Neither reason names `rmx`, and neither is pinned.
- **`eval/production/grep_learning_replay.py`** (L142 (1)) loads `tests/devbin.py` by path:
  `RMX = _DEVBIN.dev_rmx()`, and `_env` starts from `_DEVBIN.dev_env(os.environ)`. `main()`
  exits naming the path when no dev `rmx` sits beside the interpreter.
- **`scripts/lint-gmd.sh`** (L142 (3)): `DEVPY="${RMX_DEV_PYTHON:-$ROOT/.venv-eval/bin/python}"`.
  A set but missing `RMX_DEV_PYTHON` exits 2 and names it. Unset, the behaviour is as before.
  MEH-5: the resolver comment (the old `:53-54`) now says what is true. A no-venv clone that
  names its interpreter reaches the resolver line; `test_lint_gmd_memdir_fallback`'s real-script
  node shows it in the no-venv leg ([[#verify]]).

### R5: roots moved onto `short_root` {#changes-r5}

- The 15 `spawn_daemon_subprocess` files that held `/tmp` roots (25 sites) now call
  `rmx_sandbox.short_root(prefix)`, and each imports `rmx_sandbox`.
- `tests/task3_7_helpers.py::short_root` also moved. Reason: `test_task3_7_curator.py`, one of
  the 28, spawns a real daemon on a root that helper makes. The census keys sites by file, so
  it did not name the helper.
- `tests/tmp_root_allow.json` lists the 73 sites left, each with a reason:
  - `rmx_sandbox.make_root` is the sandbox root itself (permanent);
  - six sites are in files that start daemons through the CLI;
  - the rest are non-spawn files.

### bug-170 and bug-168 helper bodies {#changes-t02}

- `installed_hooks_diff` sets `HOME` to `RMX_SANDBOX_REAL_HOME` and `RMX_CLAUDE_HOOKS_DIR` to
  `hooks_dir` for one `hooks.check`, then restores both (R2.1; no `src/` change).
- `_rewrite` runs the rendered rewriter with `RMX_LEARN=on` (R2.2, L142 (5)).
- bug-127 needed nothing from GREEN (L146).

## Acceptance, node by node {#acceptance}

Logs are under `workflow/review-output/t0.2/`. The `own` log is `green-verify-own.log` at
`78489af`: 433 collected, 432 passed, 1 skipped (the pinned hooks test), exit 0.

| AC / requirement | node(s) | result | log |
|---|---|---|---|
| AC-5 leaked daemon, by name | `test_ac5_a_leaked_out_of_sandbox_daemon_fails_the_session_by_name` | pass | own |
| AC-5 clean daemon | `test_ac5_a_daemon_stopped_by_its_test_is_no_leak` | pass | own |
| AC-5 reused pid | `test_ac5_a_reused_pid_is_not_signalled_and_the_line_says_so` | pass | own |
| AC-5 killed run | `test_ac5_a_killed_runs_orphan_is_stopped_at_the_next_session_start` | pass | own |
| AC-5 in-process daemon | `test_ac5_an_in_process_daemon_left_serving_fails_the_session` | pass (reported, session failed; NOT stopped in-session, [[#gaps]] 1) | own |
| L142 own-pid | `test_l142_an_in_process_daemon_is_stopped_without_signalling_its_own_session` | pass | own |
| AC-5 SIGSTOPped | `test_ac5_a_sigstopped_daemon_is_continued_stopped_and_fails_the_session` | pass | own |
| AC-5 register_spawn | `…_its_fixture_does_not_stop_fails_its_own_test`, `…_its_fixture_stops_passes` | pass | own |
| R4 plain child | `test_r4_a_leaked_plain_child_is_stopped_even_though_its_ledger_names_a_root` | pass | own |
| R4.1 | `test_r4_an_exec_child_and_its_forked_grandchild_each_write_one_ledger_line`, `test_r4_a_fork_of_the_pytest_process_writes_a_ledger_line` | pass | own |
| R4.3 | `test_r4_enter_writes_owner_json_naming_this_process`, `test_r4_3_the_session_header_counts_the_orphans_the_start_swept` | pass | own |
| R4.4 | `test_r4_4_teardown_counts_the_sandbox_store_roots_with_a_live_pid_file` | pass | own |
| R4.9 | `test_r4_sweep_orphans_stops_the_live_survivors_of_a_ledger` | pass | own |
| R5 | `test_tmp_root_census.py` (16) | pass | own |
| bug-253 | `test_bug253_dev_bin.py` (29) | pass, both layouts | own, `green-verify-novenv.log` |
| bug-253 pins | `test_t0_skip_gate.py` (16) | pass, both layouts | own, novenv |
| bug-253 lint | `test_bug179_anchor_parity.py::test_bug253_*` (2), `test_gmd_lint_requires_version.py`, `test_lint_gmd_memdir_fallback.py` | pass, both layouts | own, novenv |
| AC-2.1 (bug-170) | `test_bug170_*` (3) | pass | own |
| AC-2.2 (bug-168) | the whole file from a cwd under a planted `.refmatrix/learn.off` | 27/27 pass, exit 0 | `green-ac2.2-search-hooks-under-learn-off.log` |
| AC-2.3 (bug-127) | `test_brief_real_daemon.py` (5) | pass, no `Conflicting lock` | own |
{#acceptance-table}

The main-tree halves are post-merge: AC-2.1's `test_installed_hooks_match_generated` and
AC-2.3 in the main tree are T0.7's run.

## Verify set (L122 M8, `#t0-2-verify`) {#verify}

Every run is at `78489af` and went through `/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`,
with `PYTHONPATH=<clone>/src`. No full suite was run.

| run | layout | collected | result | exit | log |
|---|---|---|---|---|---|
| own set: the reaper, the census, bug-253, the 7 sandbox files, T0.2's own, the eleven, `test_bug241_r3_l114.py`, the skip gate, the 3 lint files | symlinked clone | 433 | 432 passed, 1 skipped (the hooks pin, pinned) | 0 | `green-verify-own.log` |
| AC-2.2 recipe (`test_search_hooks.py` from a cwd under `.refmatrix/learn.off`) | symlinked clone | 27 | 27 passed | 0 | `green-ac2.2-search-hooks-under-learn-off.log` |
| tier (b), 126 files | symlinked clone | 2294 | 2292 passed, 2 failed, plus 1 reaper finding | 1 | `green-verify-tierb.log` |
| the eleven, `test_bug241_r3_l114.py`, `test_repo_hooks_in_sync.py` (the six formerly pinned + hooks), bug-253, the skip gate, the 3 lint files | no-venv clone `/Volumes/littlebig/refmatrix-t02-novenv` | 312 | 311 passed, 1 skipped (the hooks pin, pinned) | 0 | `green-verify-novenv.log` |
{#verify-table}

**How tier (b) was derived.** Stage 0's tier rule
(`workflow/measurements/plan-29-spec-census/tier_rule.py`'s `tier()`) was run unchanged at
`4c6a0c6` (the R0 sha) over:
- `git archive 4c6a0c6 tests`;
- `tier_signals.py`, fed `workflow/review-output/task-29.4/r0-collect.log`;
- `wallclock_census.py`.

It reproduces [[task-29.4-r0-durations#tiers-table]] exactly: daemon files=126 tests=2290. The
126 names are in `workflow/review-output/t0.2/green-verify-tierb-files.txt`, and all exist on
the branch. On the branch they collect 2294 tests.

**Failures, by E line, against `release-0.84.0-full.log`:**
- `tests/test_task21_1_agent_usage_report.py::test_ac6_frozen_fixture_prints_the_exact_counts`
  and `::test_ac6_cli_log_recalls_are_split_per_channel`:
  `AssertionError: agent usage · window 2026-09-23 .. 2026-10-07T11:06:35 (since inclusive,
  until exclusive)`. Both full E blocks (45 lines) are identical to the release log's, so this
  is pre-existing and not caused by this branch.
- **The reaper's finding (new, by design, open: [[#gaps]] 2):** `LEAKED PROCESS pid=80167
  age=1133s spawned in tests/test_models_offline.py::test_the_embedder_loads_without_a_network_call
  argv=… -c 'from multiprocessing.resource_tracker import main;main(123)'`. SIGTERM was ignored
  and SIGKILL was sent; the session failed. This is the stdlib's resource tracker, which the
  in-process embedder load starts.
- The 0.84.0 release failures of T0.2's own nodes (bug-170's hooks test, bug-168's 9 rewriter
  nodes, bug-127's brief node) are not in tier (b). In the own run they pass, or skip pinned
  (the hooks test in a clone).

**No-venv leg** ([[task-t0-suite-trust-sweep#t0-2-bug253]], the seven pinned files):
- no `dev rmx missing`, no `not found at`, and no `SKIPPED-UNPINNED` line;
- one skip, the hooks pin, reported as pinned (exit 0);
- the files that errored or failed at stage 0 (127 errors and 1 failure, `test_bug241_r3_l114.py`
  included) all pass.
{#verify-body}

## Gaps and choices for the lead {#gaps}

1. **R4 item 6, "stopped": not met (flagged to the lead).** `Daemon.serve_forever` ends every
   shutdown in `os._exit(0)` (`src/refmatrix/daemon.py`, the force-exit after "daemon
   stopped"). A stop through the weak registry therefore ends the pytest session with exit 0
   before its summary. The first build did that: the in-process case exited 0 with no summary
   (`green-wip-reaper-1.log`). The build now REPORTS the in-process daemon and FAILS the
   session, and does not stop it in-session; it ends with the process. A non-daemon serve
   thread would make interpreter shutdown wait on it. Fixing this needs a `src/` change (its
   own RED) or a ruling. The L142 node passes. Under mutation R4.6b it still fails either
   way: a stop by the pid file SIGTERMs the session, and a stop by `stop_daemon(root)` sends the
   stop op, which ends the session through `os._exit(0)` (exit 0, not 1). Not run here:
   mutations are the reviewer's.
2. **The resource tracker in tier (b)** ([[#verify-body]]): ruling requested. The options
   (a) stop the session's own stdlib helpers first, (b) a named exemption, (c) move the test
   are in the message to the lead.
3. **R4.2 `stop_daemon(root)`** is called only when the root's `rmxd.pid` names the ledger pid
   (RED `#not-followable` 2, L142 (2)). Otherwise the pid is signalled.
4. **Live descendants.** The finish reaper also takes the session's live descendants that
   have no ledger line. A child Popen'd in a test's last line can outrun its own sitecustomize:
   the plain-child case's session finished in 0.09 s, before its child wrote its line
   (`green-wip-reaper-2.log`). A descendant with no ledger line is reported as `spawned in <no
   ledger line: a live descendant of this session>`; its test is not guessed.
5. **`failures.jsonl`** is written only when `RMX_FAILURES_OUT` is set (R2's runner is not
   built yet). The durable record is `workflow/review-output/leaked-processes.log`, which gets
   orphans and leaks only, never zero counts. The R4.4 line prints only when n ≥ 1, which
   L146 allows. The R4.3 header line prints every session, and pytest's `-q` hides headers.
6. **`tests/test_grep_learning_replay.py`** imports `dev_rmx` but does not use it (`# noqa:
   F401`). `test_each_of_the_eleven_uses_the_helper` requires the import, and the file's only
   lookup was its venv skip, now gone. The harness is what uses the helper.
7. **`tests/task3_7_helpers.py::short_root`** moved as well ([[#changes-r5]]). Twelve
   task-3.7 files use it.
8. **Not done here:** `workflow/bug_registry.md` rows (170, 168, 127, 229, 253; the lead
   allocates and records); mutations (the reviewer's).
{#gaps-list}
