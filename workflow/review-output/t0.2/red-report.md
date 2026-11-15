---
gmd: "0.1"
id: t02-red-report
title: "T0.2 + 29.4b RED report: the reaper, test roots, bug-253's helper, bug-170/168/127"
tags: [review, tdd, red, plan-29, t0]
---

# T0.2 + 29.4b RED report {#root}

Branch `task-t0.2-reaper-roots-bug253` (the lead's name; the spec's `#t0-2` row says
`task-t0.2-dev-tree-test-isolation`), from `c4b44d0`, in `/Volumes/littlebig/refmatrix-t02`
(symlinked `.venv-eval`). The no-venv layout is `/Volumes/littlebig/refmatrix-t02-novenv`, a
clone of that clone. Every run is in `workflow/review-output/t0.2/`. Each run went through
`/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`, one file per run, with
`PYTHONPATH=<clone>/src` and the dev tree's `.venv-eval/bin/python`. No `src/`, `scripts/`,
conftest or sandbox code was changed. Base means src and test infrastructure at `c4b44d0` plus
these tests.

rel: specified-by -> [[task-t0-suite-trust-sweep#t0-2]]
rel: specified-by -> [[task-29.4-suite-health#r4]]
rel: specified-by -> [[task-29.4-suite-health#r5]]
rel: specified-by -> [[task-29.4-suite-health#ac-5]]

## Runs (R0.3) {#runs}

| log | sha | collected | result | exit |
|---|---|---|---|---|
| `base-red-daemon-reaper.log` | 63b97b0 | 13 | 12 failed, 1 passed | 1 |
| `base-red-tmp-root-census.log` | 503783b | 16 | 3 failed, 13 passed | 1 |
| `base-red-bug253-dev-bin.log` | 14c825c | 29 | 22 failed, 7 passed | 1 |
| `novenv-base-red-bug253-dev-bin.log` | 14c825c | 29 | 22 failed, 7 passed | 1 |
| `base-red-t0-skip-gate.log` | 63b97b0 | 16 | 6 failed, 10 passed | 1 |
| `novenv-base-red-t0-skip-gate.log` | 63b97b0 | 16 | 7 failed, 9 passed | 1 |
| `base-red-repo-hooks-in-sync.log` | 63b97b0 | 4 | 2 failed, 1 passed, 1 skipped (hooks pin) | 1 |
| `base-red-search-hooks.log` | 63b97b0 | 27 | 2 failed, 25 passed | 1 |
| `base-ac2.2-search-hooks-under-learn-off.log` | 63b97b0 | 27 | 11 failed, 16 passed | 1 |
| `base-red-brief-real-daemon.log` | 63b97b0 | 5 | 2 failed, 3 passed | 1 |
| `base-red-bug179-anchor-parity.log` | 63b97b0 | 47 | 2 failed, 45 passed | 1 |
| `novenv-base-bug179-anchor-parity.log` | 63b97b0 | 47 | 2 failed, 45 passed | 1 |
| `base-red-grep-learning-replay.log` | 63b97b0 | 5 | 1 failed, 4 passed | 1 |
| `base-gmd-lint-requires-version.log` | 63b97b0 | 9 | 9 passed | 0 |
| `novenv-base-gmd-lint-requires-version.log` | 63b97b0 | 9 | 1 failed, 8 passed | 1 |
| `base-lint-gmd-memdir-fallback.log` | 63b97b0 | 19 | 19 passed | 0 |
| `novenv-base-lint-gmd-memdir-fallback.log` | 63b97b0 | 19 | 1 failed, 18 passed | 1 |
| `novenv-base-test_<the 11 + r3_l114 + hooks>.log` (13 logs) | 63b97b0 | see [[#bug253-base]] | | |

Later commits changed nothing in the files those runs read, except: `14c825c` and `503783b`
changed the bug-253 scan and the census (both re-run, at the sha shown), and `503783b` added a
`DeprecationWarning` filter around one `os.fork()` in `test_daemon_reaper.py`. That filter is
not re-run.

## Nodes and their base E lines {#nodes}

**Intended** means the node fails at base for the reason it exists to pin.

### tests/test_daemon_reaper.py (new; 29.4 R4, AC-5) {#nodes-reaper}

Each AC-5 case is a child pytest over `tests/fixtures/suite_health/case_*.py`, copied into a
tmp checkout that carries this checkout's conftest and sandbox. The daemons are real.

| node | base E line | intended |
|---|---|---|
| `test_ac5_a_leaked_out_of_sandbox_daemon_fails_the_session_by_name` | `a daemon (pid 72986, root /private/tmp/shl-6q2d1cbm/proj/.refmatrix) outlived its test and the inner session exited 0, not 1: no reaper failed the session (bug-229)` | yes |
| `test_ac5_a_daemon_stopped_by_its_test_is_no_leak` | passes (no-false-positive guard) | n/a: guard |
| `test_ac5_a_reused_pid_is_not_signalled_and_the_line_says_so` | `the case could not point a ledger line at the unrelated pid: its own child wrote no line to <sandbox root>/children.jsonl (#r4 item 1)` | yes, on R4.1 (no ledger at base) |
| `test_ac5_a_killed_runs_orphan_is_stopped_at_the_next_session_start` | ``the next session's start printed no `ORPHAN from a killed run` line for pid 75140`` | yes |
| `test_ac5_an_in_process_daemon_left_serving_fails_the_session` | `an in-process daemon on /private/tmp/shi-k7bjf__7/proj/.refmatrix was left serving and the session exited 0` | yes |
| `test_ac5_a_sigstopped_daemon_is_continued_stopped_and_fails_the_session` | `a SIGSTOPped daemon (pid 75383) was left and the session exited 0` | yes |
| `test_r4_a_leaked_plain_child_is_stopped_even_though_its_ledger_names_a_root` | `an abandoned child (pid 75849) outlived its test and the session exited 0` | yes |
| `test_ac5_a_registered_spawn_its_fixture_does_not_stop_fails_its_own_test` | `the fixture could not register its daemon through rmx_sandbox.register_spawn(pid, root, why) (#r4 item 7), so the test errored at setup …` | yes (the API is missing) |
| `test_ac5_a_registered_spawn_its_fixture_stops_passes` | `the fixture could not register its daemon through rmx_sandbox.register_spawn(pid, root, why) (#r4 item 7)` | yes (the API is missing) |
| `test_r4_an_exec_child_and_its_forked_grandchild_each_write_one_ledger_line` | `expected exactly one ledger line for the exec'd child 76198 in /private/tmp/rmx-xcc0lhlz/children.jsonl, got 0: []` | yes |
| `test_r4_a_fork_of_the_pytest_process_writes_a_ledger_line` | `no single ledger line for pid 76200, forked from the pytest process (…/children.jsonl)` | yes |
| `test_r4_enter_writes_owner_json_naming_this_process` | `no /private/tmp/rmx-xcc0lhlz/owner.json: a killed run's sandbox cannot be told from a live one` | yes |
| `test_r4_sweep_orphans_stops_the_live_survivors_of_a_ledger` | `the child 76201 wrote no ledger line in …/children.jsonl` | yes, on R4.1 (precondition: the ledger); `sweep_orphans` is also missing |

### tests/test_tmp_root_census.py (new; 29.4 R5) {#nodes-census}

| node | base E line | intended |
|---|---|---|
| `test_the_tree_holds_no_tmp_root_outside_the_allow_list` | `no tests/tmp_root_allow.json: the tmp-root census has no list (task-29.4 #r5); 99 /tmp roots under tests/ are unlisted` | yes |
| `test_the_spawn_daemon_files_were_moved_onto_short_root` | `25 /tmp root(s) remain in the files that spawn daemons (15 of 28 files); they move to rmx_sandbox.short_root` | yes |
| `test_short_root_is_fresh_under_the_sandbox_and_short` | `rmx_sandbox has no short_root(prefix) (task-29.4 #r5)` | yes |
| 13 synthetic must-fail / must-pass cases | pass | n/a: they test the census's own logic, which is test code. They are its must-fail guard ([[feedback_clean_corpus_hides_a_dead_gate]]) |

### tests/test_bug253_dev_bin.py (new; `#t0-2-bug253`) {#nodes-bug253}

Both layouts give the same result (22 RED, 7 pass).

| node | base E line | intended |
|---|---|---|
| `test_the_dev_rmx_is_the_bin_dir_of_the_interpreter_running_the_suite` | `no tests/devbin.py: the dev rmx is still looked up by each file on its own (bug-253 …)` | yes |
| `test_dev_env_puts_this_checkouts_src_first_and_keeps_absolute_entries` | same | yes |
| `test_a_child_run_through_the_helper_runs_this_checkouts_code` | same | yes |
| `test_no_test_file_but_the_helper_looks_up_a_checkout_venv_bin` | lists exactly the eleven at their spec lines (brief:23, argv:48, count:27, evidence:39, replay:66, noflag:65, bug240:33, bug240_mcp:38, r2_l112:46, rule_docs:46, scanorder:57) plus `tests/conftest.py:310` (R1.1's venv condition) | yes |
| `test_each_of_the_eleven_uses_the_helper[×11]` | `tests/<f> does not import tests/devbin.py; it looked up the dev rmx itself` | yes |
| `test_the_six_no_longer_skip_on_a_missing_dev_rmx[×6]` | e.g. `tests/test_grep_argv_order_e2e.py still skips on the dev rmx: ['dev venv rmx not built', 'needs rmx + rg', …]` | yes |
| `test_the_conftest_pins_no_venv_skip_and_tests_no_checkout_venv` | `tests/conftest.py still carries the 18 venv pins` | yes |
| `test_the_lookup_scan_sees_each_spelling[×7]` | pass | n/a: the scan's must-fail guard |

### Edited nodes (stage 2 retires the venv pins) {#nodes-edited}

| node | base E line | intended |
|---|---|---|
| `test_t0_skip_gate.py::test_the_allowed_set_follows_each_skips_own_condition[no-venv, half-built-venv-dir, symlinked-venv-without-rmx, foreign-hooks-no-venv, no-hooks-file-no-venv]` | `layout venv=none hooks=self: allowed set differs.` (the 18 venv pins are present) | yes |
| `test_t0_skip_gate.py::test_every_pin_is_its_tests_own_reason_verbatim` | the allowed set is `{18 venv pins + hooks}`, expected `{hooks}` | yes |
| `test_t0_skip_gate.py::test_this_sessions_allowed_set_is_the_builder_on_this_checkout` | RED in the no-venv clone only: `ALLOWED_SKIPS for …-novenv (hooks owner: /Users/tholley/claude_tools/refmatrix) is {…venv pins…}`. It passes in the symlinked clone, as it should | yes |
| `test_grep_learning_replay.py::test_the_harness_uses_the_dev_venv_rmx_not_the_deployed_one` (rewritten; it pinned `parts[-3:] == (".venv-eval","bin","rmx")`) | `the harness's dev rmx is /Volumes/littlebig/refmatrix-t02/.venv-eval/bin/rmx, not the running interpreter's /Users/tholley/claude_tools/refmatrix/.venv-eval/bin/rmx` | yes. RED in clones; it passes in the main tree at base, see [[#not-followable]] item 1 |
| `test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate` (now passes `RMX_DEV_PYTHON=sys.executable`) | no-venv clone: `scripts/lint-gmd.sh did not run its checks (exit 2) … dev interpreter not found at /Volumes/littlebig/refmatrix-t02-novenv/.venv-eval/bin/python`. Symlinked clone: passes | yes: bug-253's stage-0 E line |
| `test_lint_gmd_memdir_fallback.py::test_an_empty_own_slug_memory_dir_falls_back_through_the_real_script` (same env addition) | no-venv: the same exit-2 E line. Symlinked: passes | yes. This also makes MEH-5's `lint-gmd.sh:53-54` comment testable |

### T0.2's own (bug-170, bug-168, bug-127) {#nodes-t02}

| node | base E line | intended |
|---|---|---|
| `test_repo_hooks_in_sync.py::test_bug170_the_comparison_renders_with_the_home_the_hooks_were_installed_with` | `hooks installed under the real home do not compare clean …`: `- SessionStart/…` (real home) / `+ SessionStart/…` (sandbox `/private/tmp/rmx-3h3dxj8i/h`), the two hook-path lines, and `- script grep-rewrite-guard.sh / rmxgrep-rewrite.py / grep-tool-teach.sh differs …` ×3 | yes: bug-170's 3 + 3 shape |
| `test_repo_hooks_in_sync.py::test_bug170_ac21_one_changed_script_byte_is_the_only_drift` (AC-2.1) | `expected exactly one drift line, for grep-rewrite-guard.sh; got:` the same 6 + 3 lines | yes |
| `test_repo_hooks_in_sync.py::test_bug170_the_comparison_restores_the_sandbox_and_writes_nothing` | passes (env restored, files unchanged) | n/a: guard against a fix that leaves `HOME` real for the rest of the session |
| `test_search_hooks.py::test_bug168_rewriting_does_not_depend_on_the_cwds_ancestry` | `AssertionError: ('grep -rn pat src/', '')` | yes: bug-168's main-tree E line, verbatim |
| `test_search_hooks.py::test_bug168_rewriting_does_not_depend_on_the_homes_learn_switch` | `AssertionError: ('grep -rn pat src/', '')` | yes |
| `test_search_hooks.py::test_bug168_the_rewriter_stands_down_under_a_planted_learn_off` | passes | n/a: R2.2's "the stand-down stays tested". M2.1 kills it |
| AC-2.2 recipe (`base-ac2.2-search-hooks-under-learn-off.log`: the whole file from a cwd whose ancestor holds `.refmatrix/learn.off`) | 11 failed: bug-168's 9 (`test_rewriter_catches_dodges[×8]`, `test_env_assignments_survive_in_place`, each `('<cmd>', '')`) and the 2 new ones | yes: the main-tree condition reproduced in a clone |
| `test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon` (existing, unchanged) | `_duckdb.IOException: IO Error: Could not set lock on file "/private/tmp/bd._6lwy9a1/.refmatrix/catalog.A.duckdb": Conflicting lock is held in …` | yes: AC-2.3's E line |
| `test_brief_real_daemon.py::test_bug127_no_test_opens_the_catalog_its_daemon_holds` | `tests open Store() on the catalog their own daemon holds (bug-127) …: ['test_an_unknown_class_fails_loudly_through_the_daemon:145']` | yes. In the no-venv clone at base it is `SKIPPED-UNPINNED` under the module's `dev rmx not built` mark, which GREEN removes |
| `test_bug179_anchor_parity.py::test_bug253_a_named_dev_interpreter_runs_the_gate_in_a_checkout_with_no_venv` | `the gate did not run with RMX_DEV_PYTHON=…/.venv-eval/bin/python and no .venv-eval (exit 2)` | yes |
| `test_bug179_anchor_parity.py::test_bug253_a_named_dev_interpreter_that_is_missing_exits_2_and_names_it` | `the gate did not name RMX_DEV_PYTHON=/tmp/b179…/no-such-python` | yes |

### bug-253's own RED, no-venv clone, unchanged files {#bug253-base}

This matches the bug row's counts exactly. The E line is
`AssertionError: dev rmx missing at /Volumes/littlebig/refmatrix-t02-novenv/.venv-eval/bin/rmx`:

| file | result | exit |
|---|---|---|
| `test_bug241_rule_docs_reingest.py` | 96 errors | 1 |
| `test_bug240_ingest_file_arg_mcp.py` | 10 errors | 1 |
| `test_bug241_r2_l112.py` | 9 errors | 1 |
| `test_bug240_ingest_file_arg.py` | 8 errors | 1 |
| `test_bug241_r3_l114.py` | 4 errors | 1 |
| `test_scanorder_r2_l120.py` | 1 failed (`FileNotFoundError: … .venv-eval/bin/rmx`), 13 passed | 1 |
| the six skip files | 18 pinned skips. Exit 0 except replay (my rewritten node fails) and brief (the new node is unpinned) | — |
| `test_repo_hooks_in_sync.py` | hooks pin skipped and pinned; the 2 new bug-170 nodes RED | 1 |

## Mutation-to-node map {#mutations}

These are predictions. GREEN's commit is what proves them.

| mutation | turns RED |
|---|---|
| 29.4 #9 no ledger after a fork | `test_ac5_a_leaked…` (the LEAKED line lacks the double-forked daemon's pid), `test_r4_an_exec_child_and_its_forked_grandchild…`, `test_r4_a_fork_of_the_pytest_process…` |
| #10 prints, does not stop | `test_ac5_a_leaked…` (`_gone_within`), `test_ac5_a_sigstopped…`, `test_r4_a_leaked_plain_child…` |
| #11 stops, does not fail the session | `test_ac5_a_leaked…`, `test_ac5_an_in_process…`, `test_ac5_a_sigstopped…`, `test_r4_a_leaked_plain_child…` (exit 0) |
| #12 no start-time check | `test_ac5_a_reused_pid…` (the `/bin/sleep` is signalled) |
| #13 no session-start sweep | `test_ac5_a_killed_runs_orphan…` |
| #16 the `Daemon.__init__` wrapper records nothing | `test_ac5_an_in_process…` |
| #17 the reaper skips a stopped process | `test_ac5_a_sigstopped…` (the pid survives) |
| #22 `root=` from a sandbox pid file only | `test_ac5_a_leaked…` (the root is under `/tmp`, outside the sandbox) |
| proposed R4.2b: a ledger root is treated as "this pid is that root's daemon" (no signal fallback) | `test_r4_a_leaked_plain_child…`, `test_r4_sweep_orphans…` |
| proposed R4.7: `register_spawn`'s teardown check is dropped | `test_ac5_a_registered_spawn_its_fixture_does_not_stop…` |
| proposed R5.1: `short_root` returns a `/tmp` mkdtemp | `test_short_root_is_fresh…` |
| proposed R5.2: move one spawn file's root back to `dir="/tmp"` | `test_the_tree_holds_no_tmp_root…`, `test_the_spawn_daemon_files_were_moved…` |
| M2.1 the rewriter ignores `learn.off` | `test_bug168_the_rewriter_stands_down_under_a_planted_learn_off` |
| M2.2 the hooks comparison skips the scripts | `test_bug170_ac21_one_changed_script_byte_is_the_only_drift` |
| M2.3 the library stops raising on an unknown class | the bug-127 node after GREEN's rewrite, which must keep `"bogus-class" in str(err)` ([[#green-work]]) |
| M2.4 re-add the direct `Store()` opener | `test_bug127_no_test_opens_the_catalog_its_daemon_holds` (static, so it does not depend on the lock contending), plus the lock E line in the node itself |
| proposed B1: `dev_bin()` resolves `sys.executable` (lands in the base interpreter's bin, which has no `rmx`) | `test_the_dev_rmx_is_the_bin_dir…` |
| proposed B2: `dev_env` drops the checkout `src` / puts it last | `test_dev_env_puts…`, `test_a_child_run_through_the_helper…` (in a clone the editable install's tree is imported) |
| proposed B3: one file looks up `.venv-eval/bin` again | `test_no_test_file_but_the_helper…` |
| proposed B4: re-add the venv pins / the venv condition | `test_t0_skip_gate` layouts, `test_the_conftest_pins_no_venv_skip…` |
| proposed B5: `lint-gmd.sh` ignores `RMX_DEV_PYTHON` | both `test_bug253_a_named_dev_interpreter…` nodes, and the repo-scope test in a no-venv clone |

## Mock registry {#mocks}

One row was added to `workflow/test_mock_registry.md`. It covers `signal.signal`, replaced inside
`case_inprocess_daemon.py` only by a wrapper that runs the real function on the main thread and
does nothing on other threads. Classification: external, permanent. Reason: `serve_forever` installs
SIGTERM/SIGINT handlers and cannot run off the main thread. The rest of the AC-5 fixtures are real
processes with no doubles. The bug-170 fixture sets `HOME` and `RMX_CLAUDE_HOOKS_DIR` with
`monkeypatch.setenv` around one render. bug-168 sets `HOME` and the cwd. Both are environment
inputs, not doubles.

## Stale citations reconciled (R0.1, at c4b44d0) {#reconciled}

- All eleven dev-bin lookups are at the lines the spec gives (`#t0-2-bug253`, read at `f45b9a3`).
  The scan finds no other lookup under `tests/` except `tests/conftest.py:310`, which is R1.1's
  venv condition.
- `hooks.check` is at `hooks.py:737`. `search_hooks.hooks_dir` is at `search_hooks.py:399-402`.
  `lint-gmd.sh` `DEVPY` is at line 23. The MEH-5 comments are at `tests/conftest.py:255-256` and
  `scripts/lint-gmd.sh:53-54`. All hold.
- There are 28 files that call `spawn_daemon_subprocess`. That holds. Only 15 of them hold a
  `/tmp` root (25 sites); the other 13 already use `tmp_path` or the sandbox.
- The census counts 99 `/tmp` mkdtemp sites under `tests/`. The store review said 96.
- bug-253's counts (127 errors and 1 failure) reproduce exactly in a no-venv clone of `c4b44d0`.

## Not followable as written, and interface choices for the lead {#not-followable}

1. **A twelfth dev-bin lookup outside `tests/`.** `eval/production/grep_learning_replay.py:66`
   has `RMX = REPO / ".venv-eval" / "bin" / "rmx"`, and the replay node's subprocesses run
   that path. Removing the node's skip (R1.2) without changing the harness makes the node fail
   in a no-venv clone on the same missing path. The file is not in `#t0-2-files-shared`. I
   rewrote `test_the_harness_uses_the_dev_venv_rmx_not_the_deployed_one` (it pinned the old
   path) to `glr.RMX == Path(sys.executable).parent / "rmx"`, and not under the deploy tree.
   GREEN needs leave to edit the eval harness.
2. **R4.2's "stop_daemon(root) when the ledger gives a root" stops nothing for most children.**
   The sandbox gives every child a per-test `REFMATRIX_ROOT`, so a root in the ledger does not
   mean the pid is that root's daemon. `test_r4_a_leaked_plain_child…` and
   `test_r4_sweep_orphans…` require the reaper to fall back to SIGTERM, wait, then SIGKILL for
   a pid still alive after `stop_daemon`. Item 6 has the same hazard: an in-process daemon's
   pid file is the inner pytest's own pid, so `stop_daemon` would end in SIGTERM to pytest.
3. **Interfaces the RED fixes, because the spec leaves them open:**
   - The ledger line is one JSON object per line, with the process id under `pid`. The other
     fields are checked by value only.
   - `owner.json` has `pid` plus at least one more field (the start time).
   - `register_spawn(pid, root, why)` takes positional arguments.
   - `tests/devbin.py` provides `dev_bin()`, `dev_rmx()` and `dev_env(env=None)`.
   - `tests/tmp_root_allow.json` is `{"entries": [{"key", "reason"}]}`, with key
     `file::scope::ast.unparse(call)` and duplicates for multiplicity.
   - The reaper's lines contain `LEAKED PROCESS pid=<n>`, the test's nodeid,
     `root=<path as recorded>`, `LEAKED IN-PROCESS DAEMON` and `ORPHAN from a killed run`. A
     reused pid gets a line with the pid and the word `reused`, and exit 0.
   - **`scripts/lint-gmd.sh` gets `RMX_DEV_PYTHON`.** A bash script has no `sys.executable`,
     so the caller names the dev interpreter. A set but missing interpreter gives exit 2 and
     names it. Unset, the script uses `.venv-eval/bin/python` as now, and
     `test_ac10_a_missing_dev_interpreter_exits_2_and_names_it` stands. The alternative is
     walking origins, as `gmd_memdir.py` does (bsd r1's remark). That needs no knob but is a
     second "find the canonical checkout" walk. The lead may prefer it; if so, the two
     `test_bug253_a_named_dev_interpreter…` nodes and the env additions change.
4. **Things the census and R5 read beyond the letter:**
   - The census also flags an absolute `prefix="/tmp/…"`. That is the same root spelled
     differently (`test_brief_real_daemon.py`'s `prefix="/tmp/bd."`).
   - `test_the_spawn_daemon_files_were_moved…` reads "the list starts with the sites left after
     the 28 files are moved" as: none of those files' sites remain.
5. **bug-168's HOME node narrows the fix.** R2.2 allows "pin `RMX_LEARN=on` *or* run from a
   tmp cwd outside `$HOME`". The HOME node (a planted `~/.refmatrix/learn.off`, which is a file
   outside the test's tmp root, per R2.2's first sentence) is passed only by the `RMX_LEARN`
   route or an equivalent. A cwd-only fix fails it. The lead may drop the node if the cwd
   route should stay open.
6. **Things not pinned by any node:**
   - R4.4 (the count of store roots with a live `rmxd.pid` at finish).
   - R4.3's "count in the session header". `leaked-processes.log` is pinned.
   - Neither has an AC, and their format is unspecified.
7. **Observed, not touched:** pid 35281, `.venv-eval/bin/rmx daemon start --no-watch`, started
   2026-11-14 19:28. Its parent is launchd, its cwd is the dev tree, and it serves
   `/private/tmp/b241.96tsufy2/proj/.refmatrix`. This is a live bug-229 case from a
   `test_bug241_*` run.

## What GREEN builds {#green-work}

All the changes below are test infrastructure or scripts. No `src/` change is needed.

- **`rmx_sandbox`:**
  - the ledger (exec through `install_from_env`, plus `register_at_fork` in `enter()` and
    `install_from_env()`);
  - `owner.json`;
  - `short_root`, `register_spawn` and `sweep_orphans`;
  - the session-start sweep and the finish reaper, with a signal fallback, SIGCONT, a
    start-time check, `failures.jsonl` and `leaked-processes.log`.
- **conftest:**
  - the weak `Daemon` registry;
  - the reaper hooks;
  - drop `_VENV_RMX_PINS` and R1.1's venv condition. Make MEH-5's `conftest.py:255-256` comment
    true or remove it.
- **`tests/devbin.py`**, with the eleven files converted to it. The six files lose their venv
  `skipif`s. `test_the_tool_itself_is_the_one_that_scrambles` keeps a `rg`-only skip, whose
  reason must not contain "rmx".
- **`eval/production/grep_learning_replay.py` `RMX`**, needs the lead's leave
  ([[#not-followable]] item 1).
- **`scripts/lint-gmd.sh` `RMX_DEV_PYTHON`.**
- **`tests/tmp_root_allow.json`**, with the 15 files' 25 roots moved to `short_root`.
- **The body of `installed_hooks_diff`** in `tests/test_repo_hooks_in_sync.py` (it holds
  `c4b44d0`'s shape, moved unchanged).
- **`_rewrite()`** in `tests/test_search_hooks.py`.
- **bug-127's test body:** reach `compile_briefs`' ValueError through the daemon op or verb
  path, keeping `"bogus-class"` in the asserted error. This is a test-body change; the lead
  decides whose hands it is in.
