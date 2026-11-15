---
gmd: "0.1"
id: impl-task-t0-3-load-flakes-wallclock
title: "T0.3 + 29.4c GREEN: load flakes explained, 37 wall-clock bounds replaced by outcome checks, the two censuses (bug-130, 190, 091, 228, 231, 269)"
tags: [implementation-summary, t0, t0-3, task-29.4, wallclock, census, flaky, bug-130, bug-190, bug-091, bug-228, bug-231, bug-269, bug-270]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-15
---

# T0.3 + 29.4c GREEN: load flakes and wall-clock bounds {#root}

rel: implements -> [[task-t0-suite-trust-sweep#t0-3]]
rel: implements -> [[task-29.4-suite-health#r3]]
rel: derives-from -> [[t0-3-red-report#contract]]
rel: derives-from -> [[t0-3-red-report#base-sweep]]

Plan-29 task 29.4, stage 2, branch `task-t0.3-load-flakes-wallclock` in
`/Volumes/littlebig/refmatrix-t03-green` (GREEN clone of the RED branch at `0276c71`; RED base
`c4b44d0`). Interpreter: the dev tree's `.venv-eval`, `PYTHONPATH=<clone>/src`; every run under
`/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`, logged to
`workflow/review-output/t0.3/green-*.log`. The R3 work changes only `tests/` (the replacements
and the contract modules) and `workflow/test_mock_registry.md`. The one `src/` change is
bug-269's fix (ruling L161, [[#bug269-fix]]): `src/refmatrix/subproc.py` and
`src/refmatrix/daemon.py`. RED's later commits (`cdc9c88` L159, `d81ed07` L160, `9270f58`
bug-269) are merged at `401e351`.

## What was built {#built}

- `tests/timing.py`: `HANG_GUARD_S = 60.0`; `wait_for(predicate, *, timeout, interval, what)`
  (returns the value; at the deadline `AssertionError` naming `what` and the elapsed seconds);
  `with_budget(command, seconds)` (swaps the ONE `--timeout <n>`, raises on zero or two);
  `record_transport(monkeypatch, module, name="call")` and
  `assert_one_deadline(calls, *, budget, root=None, what="")`, the class B replacement (the
  timeout and retries that reached `daemon.call`, and their sum against the budget).
- `tests/wallclock_census.py`: `find_bounds(source, relpath)` (an upper bound on a clock
  difference, a name assigned from one, or an elapsed-like name, any limit; key
  `relpath::function::unparsed assert`, an ordinal suffix for a repeat, no line number) and
  `run_census(tests_root, *, allow_path, specs_root, legacy_baseline=None)` (`.ok`, `.errors`,
  `.counts`, `.report()`). Exempt: lower bounds; `< HANG_GUARD_S` imported from `tests.timing`
  and never rebound (its value read from `tests/timing.py`, >= 60); `tests/fixtures/suite_health/`.
  `feature-bound` entries resolve `ac` by frontmatter id and anchor, quote a clause of that AC
  (entries per AC <= its number of time quantities), and set their knob (`env:` setenv / env
  mapping / subscript; `const:` setattr string or module form; `arg:` a literal keyword) to a
  literal <= `max_s` <= 2.0.
- `tests/wallclock_legacy_baseline.json`: the 78 keys at `c4b44d0`, pinned by
  `_BASELINE_SHA256` in the census module, so a new `legacy` entry needs an edit review sees.
- `tests/wallclock_allow.json`: 41 `legacy` entries (class A 4, B 37 across 39 functions; each
  with a note), 18 files.
- `tests/budget_outcome_census.py`: `violations(source, relpath)` and
  `run_census(tests_root, *, allow_path)`. Real-daemon reach is to a fixed point over the file's
  fixtures and helpers and the conftest fixtures above it; the control form is
  `tests.timing.with_budget(cmd, <literal or HANG_GUARD_S>)` (ruling L141); a `budget-outcome`
  entry needs a reason and is stale when its hit is gone. The two tables (`REAL_DAEMON_HELPERS`,
  `OUTCOME_FIELDS`) live in the module, since `tests/tiering.py` is stage 4's file.

{#built-list}

## R0.1: the cited sites at the base {#r0-1}

| Finding | At `c4b44d0` | Now |
|---|---|---|
| bug-130, `test_catalog_measure.py::test_rewrite_bytes_is_the_median_of_the_runs` indexes `rewrite_bytes_all` with no `failed` check | holds (`:323`) | `failed == 0` asserted first, message carries every failed store's error (R3.1) |
| bug-190, `test_rerank_budget_real_clients.py::test_a_cold_private_worker_is_skipped_without_spawning` `wall < 0.3 and spawns == 0` | holds (`:282`) | wall dropped (class C); L164 fix: no spawn on the caller's thread, client retired, every spawn's thread and stack in the message |
| bug-091, `test_watch.py::test_run_watcher_picks_up_new_file` one `wait(timeout=3.0)` after a 0.2 s sleep | holds (`:89-93`) | 30 s module deadline, re-written while polling (R3.3, L141) |
| bug-228, `test_task21_1_recall_skip.py::test_ac2b_live_daemon_recall_writes_one_ok_recall_row` | holds (`:195`) | see [[#bug228]] |
| bug-231, `test_plan4_remedy.py:129` `< 8.0` on `grace=10.0` | holds | class A under `HANG_GUARD_S` |
| `HANG_BOUND_S` assert, `test_bug212_r4_red.py:771` | holds | deleted (it repeated the kill bound); `HANG_BOUND_S` keeps its name (L141) |
| `eval/catalog_maint/measure_catalogs.py` (R3.1's harness route) | not touched: the one captured failure was bug-270, a test defect fixed by RED (`350fdfd`) | unchanged |

{#r0-1-table}

## Acceptance, by node and log {#acceptance}

### T0.3 AC-3.1: the five rows {#ac-3-1}

Base trials are RED's sweep ([[t0-3-red-report#base-sweep-table]]); the post-fix confirm
trial is one trial at the reproducer's level, per the lead's brief (not the 45-pass run).

| Row | Base, L3 / L5 / L8 (failures) | Band | E lines at base | Fix / outcome |
|---|---|---|---|---|
| bug-130 | 1/9, 1/9, 0/8 | not reproduced | `IndexError: tuple index out of range` captured as the store's error (bug-270), read as `KeyError: 'rewrite_bytes_all'` | R3.1 diagnostic only; bug-270 fixed by RED; row reads `deferred: diagnosed-loud` |
| bug-190 | 0/9, 0/9, 0/8 | not reproduced | none | test-side fix by ruling L164 (no band run, L164 (b)); [[#bug190]] |
| bug-091 | 0/9, 0/9, 0/8 | not reproduced | none | R3.3 deadline + R3.4 message; `deferred: diagnosed-loud` |
| bug-228 | 5/9 (L3) | reproducer, L3 | `AssertionError: {... 'outcome': 'skipped_budget', 'latency_ms': 5018 ...}` | [[#bug228]] |
| bug-231 | 6/9 (L3), 9/9, 3/8 | reproducer, L3 (L157 (2)) | `assert (733208.75… - 733200.72…) < 8.0` once; `assert False is True` (graceful_stop False at 10.0 s) the rest = bug-269 | class A replacement; confirm trial pass ([[#confirm]]) |

{#ac-3-1-table}

### T0.3 R3.1-R3.4 and the RED diagnostics nodes {#r3-nodes}

`workflow/review-output/t0.3/green-edited-a.log` (at the pre-commit tree, `0276c71` + working
changes): exit 1, 182 collected, 181 passed / 1 failed (`test_plan4_remedy_r2.py::
test_stop_daemon_signals_first_when_ping_fails`, my first ordering check; fixed, see
[[#verify]]). In it, all four `test_t03_flake_diagnostics.py` nodes passed, each by reading
the forced child's own `E` lines: bug-130's carries the store's error, not the KeyError (the
child's line, quoted in `green-new-nodes-1.log` where the node still failed on my docstring:
`AssertionError: bug-130: 1 store(s) failed to measure (exit 1): m: step unexpected:
RuntimeError: t03-forced-store-error: the catalog rewrite failed`); bug-190's names the stack
through `_t03_forced_spawn`; bug-091's gives `elapsed` >= the forced 4.0 s deadline and the
watcher thread's state. `test_r3_3_bug091_the_delivery_deadline_is_a_named_constant_of_at_least_
30s` passed (`WATCHER_DELIVERY_DEADLINE_S = 30.0`, read at call time).

### 29.4 AC-4, AC-11 and the R3 scope nodes {#ac-4-11}

Final: `green-bug269-fix.log` (the tree committed as `e8277d4`; see [[#verify]]) has `test_wallclock_census.py` and
`test_budget_outcome_census.py` all passing after RED's L159 (`cdc9c88`) and L160 (`d81ed07`)
commits were merged. History: `green-new-nodes-1.log`, exit 1, 85 collected, 80 passed / 5 failed.
The census nodes that pass carry every must-fail case and the tree nodes
`test_the_tree_passes_the_wallclock_census`, `test_the_legacy_list_starts_at_the_r0_count_and_
only_shrinks` (legacy 41 <= 77), `test_r3_scope_the_four_heaviest_tier_d_files_hold_no_entry`,
`test_r3_scope_no_class_c_or_d_legacy_entry_remains`, `test_r3_scope_tier_d_projected_within_
its_band` (18 files, 337.98 s <= 360). The five failures:

- `test_ac4_a_listed_bound_passes`, `test_ac4_fixture_suite_health_is_exempt_by_path_and_nothing_
  else_is`: `FileNotFoundError: ... /ok/tests` from the test's own `_tree` (`root.mkdir()` with no
  `parents=True` under `tmp_path / "ok"`): a RED defect, fixed by RED at `d81ed07` (L160).
- `test_bug228_and_bug231_tests_hold_no_entry`: its filter (`"graceful_stop" in key` for any
  `test_plan4_remedy.py` entry) also matched the sibling class B bound of
  `test_graceful_stop_signals_first_then_waits_the_grace`, which is not bug-231: narrowed by RED
  at `d81ed07` (L160); the sibling keeps its legacy entry.
- `test_the_tree_passes_the_budget_outcome_census` (bug-228, see [[#bug228]]) and the bug-130
  diagnostic (a docstring of mine quoted the KeyError text; reworded, passing in
  `green-verify-1.log`).

### 29.4 AC-6: bug-228 and bug-231 {#ac-6}

The mechanism tests `test_t03_outcome_mechanisms.py` (bug-231's poll count k = 4 under
`HANG_GUARD_S`; bug-228's generated command carries `--timeout 5` and `with_budget` swaps that
one token) pass in `green-new-nodes-1.log`. Neither row's test holds a wall-clock entry.

## The 78 sites {#sites}

Classified per 29.4 `#r3-classes`. 37 replaced (A 2, B 16, C 18, D 1): the four heaviest
tier-(d) files (18 sites), every class C and D site, bug-231, and bug-212's duplicate hang
bound. 41 stay as `legacy` (A 4, B 37). The remainder row in 29.1's grammar is the lead's to
allocate: "41 legacy wall-clock bounds (A 4 / B 37) in 18 files stay in tier (d), 338.0 s
serial; scheduled for replacement with class B mechanism checks as their files are next
touched". The class B budgets asserted for the scope files were read first from the transport
calls the base tests made (`green-measure-scope-transport.log`, exit 0, 22 passed; per-call
records in `green-measure-scope-transport.jsonl`). Each call is listed twice in that file, an
artifact of the scratch plugin: the in-test recorder sees one per call, since
`assert_one_deadline`'s sum (for example 5.0 + 4.97 s against 10 s on the read twins) passes in
`green-edited-b.log` and would fail at double.

{#sites-lead}

The lead's guard (every replacement keeps or strengthens what the test proved): each row
gives the site at the base sha, the old bound, and the outcome check that now stands for it.
Where a row says "stays asserted" or names an existing assertion, that assertion was already
in the test and is the outcome the bound was a proxy for; it is kept verbatim, and nothing
else in the test was removed. ch-bsd: those rows (learn_broker D, the slow-private and
cold-private rerank rows, task25_1, task3_7_r4, bug-212) are the ones to check for weakening.

{#sites-guard}

| # | Site at `c4b44d0` | Test | Old bound | Class | New outcome check, or why it stays |
|---|---|---|---|---|---|
| 1 | `test_bug112_duckdb_reopen.py:347` | `test_stale_reader_mid_statement_is_interrupted_and_the_writer_proceeds` | `took < 10.0` | A | stays (legacy): the write open must not wait out a 50e9-row statement; the outcome (interrupted, values) is asserted too |
| 2 | `test_bug112_duckdb_reopen.py:584` | `test_stale_writer_mid_statement_is_interrupted_and_the_reopen_proceeds` | `took < 10.0` | A | stays (legacy): the reopen must not wait out the stale writer's statement |
| 3 | `test_bug115_liveness_under_load.py:230` | `test_call_does_not_resend_a_request_the_daemon_already_has` | `took < 0.6` | B | stays (legacy): a 0.3 s timeout with retries=2 gave up within ~one timeout (no resend; conns==1 is asserted) |
| 4 | `test_bug129_hub_pidfile.py:345` | `test_a_daemon_that_cannot_start_fails_fast_with_its_reason` | `_t.monotonic() - t0 < 15.0` | B | stays (legacy): a dead launcher is not polled for the 30 s readiness window |
| 5 | `test_bug212_r4_red.py:771` | `test_a_hanging_git_raises_the_check_error_within_the_timeout` | `time.monotonic() - t0 < HANG_BOUND_S` | A | **replaced**: deleted: it repeated the HANG_BOUND_S kill bound; `r is None` fails the test at the bound (HANG_BOUND_S keeps its name, L141) |
| 6 | `test_daemon_liveness.py:46` | `test_ping_absent_socket_short_circuits` | `time.time() - t0 < 0.2` | C | **replaced**: no connect attempt and no backoff sleep are made (recorders on socket.socket / time.sleep) |
| 7 | `test_daemon_shutdown.py:64` | `test_drain_pool_returns_quickly_when_workers_finish` | `elapsed < 1.0` | C | **replaced**: workers held on a test-owned event; the drain is seen waiting, then returns once released under a timeout 10x the hang guard |
| 8 | `test_daemon_shutdown.py:45` | `test_drain_pool_returns_within_timeout_when_worker_hangs` | `elapsed < 1.0` | B | stays (legacy): the drain gives up within its 0.4 s timeout |
| 9 | `test_daemon_shutdown_drain.py:66` | `test_a_silent_client_does_not_pin_a_dispatcher_past_shutdown` | `elapsed < 3.0` | A | stays (legacy): a handler lets go of a silent socket on shutdown instead of its 30 s read |
| 10 | `test_ingest_async.py:60` | `test_ingest_path_start_returns_job_then_completes` | `elapsed < 1.0` | C | **replaced**: the job body is held on a test-owned event; the start op answers and the job reads `running` while it is held |
| 11 | `test_learn_broker_bounded.py:145` | `test_the_default_path_queues_instead_of_calling_the_daemon` | `elapsed < 0.5` | D | **replaced**: deleted (a latency number); the mechanism stays asserted: no daemon call, one queued line |
| 12 | `test_learn_broker_bounded.py:73` | `test_the_learn_broker_is_bounded_well_under_the_old_wall` | `elapsed < 5.0` | B | stays (legacy): the learn broker against a deaf daemon is bounded by its budget |
| 13 | `test_plan2_remedy.py:381` | `test_daemon_status_takes_a_probe_budget` | `_time.monotonic() - t0 < 1.2` | B | stays (legacy): daemon_status(retries=0) costs one probe |
| 14 | `test_plan2_remedy.py:440` | `test_detach_is_bounded_when_the_daemon_answers_ping_but_holds_the_store` | `elapsed < 4.0` | B | stays (legacy): the 1 s detach budget on a held store |
| 15 | `test_plan2_remedy.py:351` | `test_detach_on_a_silent_daemon_costs_one_probe_plus_the_budget` | `abs(float(m.group(1)) - elapsed) < 0.6` | B | stays (legacy): one probe + the 1 s detach budget; the reported wait matches |
| 16 | `test_plan2_remedy.py:347` | `test_detach_on_a_silent_daemon_costs_one_probe_plus_the_budget` | `elapsed < 3.0` | B | stays (legacy): one probe + the 1 s detach budget; the reported wait matches |
| 17 | `test_plan2_remedy.py:600` | `test_detach_path_has_one_deadline_and_reports_the_wait` | `elapsed < 2.5` | B | stays (legacy): probe + partition_list + ingest_gmd_start under one 1 s budget; the reported wait matches |
| 18 | `test_plan2_remedy.py:602` | `test_detach_path_has_one_deadline_and_reports_the_wait` | `m and abs(float(m.group(1)) - elapsed) < 0.6` | B | stays (legacy): probe + partition_list + ingest_gmd_start under one 1 s budget; the reported wait matches |
| 19 | `test_plan2_remedy.py:542` | `test_recall_hook_modes_are_bounded_and_degrade_to_empty` | `elapsed < 1.6` | B | stays (legacy): the recall hook's 1 s budget + 0.6 |
| 20 | `test_plan2_remedy.py:287` | `test_stop_promote_bounds_subject_filing_and_is_loud` | `_time.monotonic() - t0 < 3.0` | B | stays (legacy): --timeout 0.5 across the promote's calls (timeouts and retries also asserted) |
| 21 | `test_plan2_remedy.py:495` | `test_stop_promote_never_exceeds_its_timeout_across_calls` | `elapsed < 1.2` | B | stays (legacy): the 0.5 s promote budget is one deadline across calls |
| 22 | `test_plan2_remedy.py:310` | `test_stop_promote_says_busy_not_absent_on_a_silent_daemon` | `elapsed < 2.5` | B | stays (legacy): --timeout 0.5 on a silent daemon |
| 23 | `test_plan2_remedy.py:583` | `test_verb_recall_timeout_is_a_deadline_across_calls` | `_time.monotonic() - t0 < 1.5` | B | stays (legacy): the recall verb's 0.5 s timeout is one deadline |
| 24 | `test_plan2_remedy_r6.py:127` | `test_global_leg_on_a_held_global_store_is_bounded_and_named` | `elapsed < 1.6` | B | stays (legacy): the 1 s budget with a held global store |
| 25 | `test_plan2_remedy_r6.py:346` | `test_precompact_recall_is_bounded_and_hook_env_is_hook_mode` | `elapsed < 1.6` | B | stays (legacy): the PreCompact recall's 1 s budget in hook mode |
| 26 | `test_plan2_remedy_r6.py:69` | `test_recall_hook_wall_is_within_budget_on_a_held_writer` | `elapsed < 1.6` | B | stays (legacy): the recall hook's 1 s budget on a held writer |
| 27 | `test_plan2_remedy_r6.py:176` | `test_replica_path_is_bounded_when_the_shared_worker_stalls` | `elapsed < 2.6` | B | stays (legacy): the 2 s budget with a stalled shared worker |
| 28 | `test_plan2_remedy_r6.py:244` | `test_rerank_is_skipped_and_said_when_the_budget_is_short` | `time.monotonic() - t0 < 1.0` | B | stays (legacy): rerank skipped with 0.8 s left (rr.calls == 0 also asserted) |
| 29 | `test_plan2_remedy_r7.py:180` | `test_cli_partition_probe_reads_the_replica_under_a_held_writer` | `time.monotonic() - t0 < 0.8` | C | **replaced**: the held daemon was asked nothing but ping while the test held the writer |
| 30 | `test_plan2_remedy_r7.py:225` | `test_session_start_hook_answers_from_the_replica_under_a_held_writer` | `elapsed < 2.5` | C | **replaced**: ROWS returned while the writer is held (a probe that ate the budget prints []) |
| 31 | `test_plan2_remedy_r7.py:206` | `test_verb_memory_partition_falls_back_to_the_daemon_without_a_replica` | `time.monotonic() - t0 < 3.0` | B | stays (legacy): the 1 s partition budget without a replica |
| 32 | `test_plan2_remedy_r7.py:195` | `test_verb_memory_partition_reads_the_replica_under_a_held_writer` | `time.monotonic() - t0 < 0.8` | C | **replaced**: the held daemon was asked nothing but ping while the test held the writer |
| 33 | `test_plan3_remedy_r4.py:109` | `test_mcp_recall_default_timeout_is_bounded_on_a_held_writer` | `time.monotonic() - t0 < 36.0` | B | **replaced**: assert_one_deadline(30.0) over the held daemon's calls |
| 34 | `test_plan3_remedy_r4.py:121` | `test_memory_get_cli_reads_the_replica_within_the_budget_on_a_held_writer` | `elapsed < 16.0` | B | **replaced**: assert_one_deadline(MEMORY_READ_BUDGET_S) |
| 35 | `test_plan3_remedy_r4.py:101` | `test_memory_get_verb_is_bounded_on_a_held_writer` | `time.monotonic() - t0 < 16.0` | B | **replaced**: record_transport + assert_one_deadline(MEMORY_READ_BUDGET_S): one attempt, timeouts inside one deadline |
| 36 | `test_plan3_remedy_r4.py:184` | `test_memory_partition_raises_busy_on_a_held_writer_without_a_replica` | `time.monotonic() - t0 < 16.0` | B | **replaced**: assert_one_deadline(PARTITION_PROBE_CAP_S = 10.0) |
| 37 | `test_plan3_remedy_r4.py:196` | `test_memory_partition_reads_the_replica_under_a_held_writer` | `time.monotonic() - t0 < 1.0` | C | **replaced**: the held daemon was asked nothing but ping |
| 38 | `test_plan3_remedy_r4.py:132` | `test_memory_recall_recent_cli_reads_the_replica_within_the_budget` | `elapsed < 12.0` | B | **replaced**: assert_one_deadline(5.0) for `--timeout 5` |
| 39 | `test_plan3_remedy_r4.py:147` | `test_promote_digest_is_typed_busy_on_a_held_writer` | `elapsed < 36.0` | B | **replaced**: assert_one_deadline(30.0): the digest write is one 30 s attempt |
| 40 | `test_plan3_remedy_r5.py:173` | `test_federated_locate_names_a_straggler_past_the_fan_out_deadline` | `elapsed < 2.5` | B | **replaced**: the straggler is held on a test-owned event; the fan-out returns while it is still held |
| 41 | `test_plan3_remedy_r5.py:184` | `test_federated_locate_on_a_held_writer_with_a_replica_skips_nothing` | `time.monotonic() - t0 < 10.0` | C | **replaced**: the held daemon was asked nothing but ping |
| 42 | `test_plan3_remedy_r5.py:139` | `test_federated_query_reports_a_held_store_as_skipped_within_the_bound` | `elapsed < 25.0` | B | **replaced**: assert_one_deadline(search.QUERY_OP_TIMEOUT_S): one `query` |
| 43 | `test_plan3_remedy_r5.py:153` | `test_federated_where_reports_the_stalled_memory_leg` | `elapsed < 12.0` | B | **replaced**: assert_one_deadline(search.WHERE_MEMORY_OP_S) |
| 44 | `test_plan3_remedy_r5.py:74` | `test_list_and_search_twins_reach_the_replica_within_the_budget_on_a_held_writer` | `elapsed < 16.0` | B | **replaced**: assert_one_deadline(MEMORY_READ_BUDGET_S) |
| 45 | `test_plan3_remedy_r5.py:114` | `test_read_twins_on_a_held_writer_without_a_replica_never_say_reading_the_replica` | `elapsed < 36.0` | B | **replaced**: assert_one_deadline(read budget, or the recall's --timeout): probe + read share one deadline |
| 46 | `test_plan3_remedy_r6.py:269` | `test_federated_where_names_pool_stragglers` | `elapsed < 4.0` | B | stays (legacy): the 0.5 s where fan-out deadline does not wait a 5 s straggler |
| 47 | `test_plan3_remedy_r6.py:127` | `test_memory_get_degree_on_a_held_writer_degrades_by_name` | `elapsed < 36.0` | B | stays (legacy): the read budget on a held writer (was 10.1 s + a NameError) |
| 48 | `test_plan3_remedy_r6.py:143` | `test_promote_on_a_held_writer_says_busy_within_the_budget` | `elapsed < 36.0` | B | stays (legacy): promote within the read budget (was 180.2 s) |
| 49 | `test_plan3_remedy_r6.py:172` | `test_promote_verb_read_is_single_attempt_under_the_action_budget` | `elapsed < 20.0` | B | stays (legacy): one attempt under the action budget (was 90.2 s) |
| 50 | `test_plan3_remedy_r7.py:190` | `test_promote_is_bounded_on_the_global_write_too` | `elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0` | B | stays (legacy): MEMORY_READ_BUDGET_S + 3 on the global write |
| 51 | `test_plan3_remedy_r7.py:216` | `test_promote_subtracts_its_partition_probe_from_the_budget` | `elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0` | B | stays (legacy): the partition probe is subtracted from MEMORY_READ_BUDGET_S |
| 52 | `test_plan4_remedy.py:93` | `test_adoption_never_kills_a_busy_predecessor` | `time.monotonic() - t0 < 8.0` | B | stays (legacy): adoption grace 1 s + stop_daemon's 2 s SIGTERM wait |
| 53 | `test_plan4_remedy.py:129` | `test_graceful_stop_on_a_live_daemon_returns_quickly` | `time.monotonic() - t0 < 8.0` | A | **replaced**: bug-231: grace=HANG_GUARD_S; asserts True and the pid gone; elapsed + rmxd.log tail in the message only |
| 54 | `test_plan4_remedy.py:120` | `test_graceful_stop_signals_first_then_waits_the_grace` | `ok is False and 0.9 < elapsed < 3.0` | B | stays (legacy): a 1 s grace on a stopped daemon is waited, then given up (lower half 0.9 is the wait) |
| 55 | `test_plan4_remedy_r2.py:264` | `test_foreground_start_refuses_a_busy_daemon_without_reaping_it` | `time.monotonic() - t0 < 4.0` | B | stays (legacy): the busy refusal costs its probe budget |
| 56 | `test_plan4_remedy_r2.py:239` | `test_stop_daemon_signals_first_when_ping_fails` | `ok is True and elapsed < 1.5` | C | **replaced**: SIGTERM is the first event, before any poll of the grace (recorders on os.kill / is_alive) |
| 57 | `test_plan4_remedy_r3.py:255` | `test_await_shutdown_returns_at_once_without_a_marker` | `time.monotonic() - t0 < 0.3` | C | **replaced**: no poll-loop sleep, and the call returns while the test-owned process is alive |
| 58 | `test_plan4_remedy_r3.py:400` | `test_stop_daemon_keeps_the_ping_discovered_pid_after_a_failed_grace` | `time.monotonic() - t0 < 10.0` | B | stays (legacy): a 1 s stop grace on a pid that ignores SIGTERM |
| 59 | `test_read_path_partition_and_budget.py:254` | `test_a_busy_worker_costs_at_most_the_budget` | `time.time() - t0 < 1.0` | B | stays (legacy): a 0.5 s rerank budget against a 3 s busy worker |
| 60 | `test_rerank_budget_real_clients.py:242` | `test_a_busy_private_worker_is_skipped_not_waited_on` | `wall < 1.2` | B | stays (legacy): a 0.8 s budget against a busy private worker |
| 61 | `test_rerank_budget_real_clients.py:220` | `test_a_cold_hub_worker_is_skipped_not_loaded_inside_the_budget` | `wall < 0.5` | C | **replaced**: the cold load is held by the test; budget 10x the hang guard; the call returns `cold` while held |
| 62 | `test_rerank_budget_real_clients.py:282` | `test_a_cold_private_worker_is_skipped_without_spawning` | `wall < 0.3 and stub.spawns() == 0` | C | **replaced**: bug-190 (L164): no spawn on the caller's thread (each spawn recorded with its thread), client retired at the end; message carries every spawn's thread and stack |
| 63 | `test_rerank_budget_real_clients.py:269` | `test_a_slow_private_rerank_finishes_and_keeps_the_worker` | `out2 == 'scored' and wall2 < 0.6` | C | **replaced**: deleted wall2 bound; the single load (`loads() == 1`) it stood for stays asserted |
| 64 | `test_rerank_budget_real_clients.py:836` | `test_a_warming_worker_is_skipped_at_once` | `'warming' in out and wall < 0.2` | C | **replaced**: the warm thread's load is held; a far-budget call returns `warming` while held |
| 65 | `test_rerank_budget_real_clients.py:300` | `test_an_evicted_private_worker_reads_as_cold` | `wall < 0.3 and stub.loads() == 1` | C | **replaced**: a respawn's load is held by the test; budget 10x the hang guard; returns `cold` with the worker still cold |
| 66 | `test_rerank_budget_real_clients.py:172` | `test_the_daemons_own_unbudgeted_rerank_does_not_hold_a_budgeted_view` | `wall < 1.2` | B | stays (legacy): a 0.8 s view does not wait behind the client lock |
| 67 | `test_rerank_budget_real_clients.py:586` | `test_the_daemons_reranker_never_loads_a_cold_private_model` | `wall < 0.5` | C | **replaced**: the load is held; `_reranker()` returns under the hang guard with the model not loaded |
| 68 | `test_rerank_budget_real_clients.py:955` | `test_the_header_refill_has_its_own_bound` | `wall < 1.5` | B | stays (legacy): REFILL_TIMEOUT_S (0.3) bounds a wedged header refill |
| 69 | `test_rerank_budget_real_clients.py:195` | `test_the_queue_estimate_is_answered_while_the_worker_is_busy` | `wall < 0.6` | C | **replaced**: the other rerank is held on the worker by the test; the estimate answers `queued` while it is held |
| 70 | `test_rerank_budget_real_clients.py:403` | `test_the_socket_gets_what_is_left_after_the_header_not_the_whole_budget` | `wall < 1.2` | B | stays (legacy): a 0.5 s header on a 1.0 s budget leaves 0.5 s |
| 71 | `test_subproc_workers.py:189` | `test_timeout_kills_the_worker` | `time.time() - t0 < 20` | A | stays (legacy): a 1 s worker timeout does not hang the caller (20 s guard) |
| 72 | `test_task25_1_recall_budget.py:735` | `test_ac4c_hook_mode_no_daemon_no_worker_exits_0_silent_and_counted` | `took < 5.0` | B | **replaced**: deleted; the only leg that could spend the offline hook's budget, a model import, is asserted absent |
| 73 | `test_task3_5_r8_remedy.py:213` | `test_promote_says_not_running_when_the_global_daemon_cannot_start` | `elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0` | B | stays (legacy): MEMORY_READ_BUDGET_S + 3 when the global daemon cannot start |
| 74 | `test_task3_6_r9_remedy.py:543` | `test_a_held_real_global_daemon_is_busy_and_never_spawned_over` | `elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0` | B | **replaced**: assert_one_deadline(MEMORY_READ_BUDGET_S); the global status probe is one attempt; no global write |
| 75 | `test_task3_6_r9_remedy.py:565` | `test_promote_cannot_start_a_real_overlong_global_root_within_budget` | `elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0` | B | **replaced**: the readiness window given to ensure_global_daemon is <= MEMORY_READ_BUDGET_S (MD: 30 s default) |
| 76 | `test_task3_6_r9_remedy.py:511` | `test_promote_with_a_slow_launcher_stays_inside_its_budget` | `elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0` | B | **replaced**: ensure/spawn readiness windows and the launcher timeout are <= MEMORY_READ_BUDGET_S |
| 77 | `test_task3_6_r9_remedy.py:494` | `test_spawn_holds_one_deadline_for_launcher_and_readiness` | `elapsed < 3.0 + 2.0` | B | **replaced**: the launcher's subprocess timeout is <= the one 3 s deadline, and the error says the launcher was killed at it |
| 78 | `test_task3_7_remedy_r4.py:192` | `test_two_concurrent_calls_behind_a_mute_hub_finish_within_the_request_path_bound` | `hub.connections == before and took < 1.0` | C | **replaced**: deleted `took < 1.0`; `hub.connections == before` (no re-probe) stays |

{#sites-table}

## bug-190: what the passing trials show {#bug190}

The harness's capture recorded a spawn in 22 of the 26 base trials, every one with the same
stack: `_warm <- info <- call <- _call_once <- _ensure <- _spawn`, the background warm the cold
skip starts by design (r11 #b-1), in trials where the test PASSED. The test reads the stub's
`spawns` file right after `wc.close()`; `close()` does not retire the client, so the warm thread
can spawn after it, and the read races the stub recording its pid. That is a test-side race on
the evidence, not reproduced as a failure (0/26). **Fixed test-side by ruling L164** (commit
`f4262e8`): each spawn is recorded with its thread and stack, the assertion is "no spawn on the
caller's thread" (the budgeted call itself), and the client ends with `wc.retire()`, so the
designed background warm can neither race the check nor leave a stub process behind. The forced
RED child (`_t03_forced_spawn` spawns on the caller's thread) still fails, naming that frame.
Registry-row text for the lead: "the test raced the cold skip's designed background warm (22/26
passing trials spawned from `_warm`); fixed test-side at `f4262e8`: no spawn on the caller's
thread, client retired; the assertion's old `spawns == 0` read was the race".

{#bug190-body}

## bug-228 {#bug228}

**Leg breakdown (before any fix):** RED's, from the first failing trial (L3 trial 5),
[[t0-3-red-report#base-sweep-bug228-table]]: SandboxDaemon boot 1.26 s (outside the budget);
the hook 5.50 s; the embed worker spawned 05:14:34 and `embedder warm in 9.1s` at 05:14:43; the
`memory_recall` op waited on the embedder through the budget's expiry and never ran. More than
90% of the overrun was before the recall op, so ruling L157 (1) builds the readiness branch.

**Built (`b9d15fa`; ruling L159 confirms option 1).** The live test runs the hook only after
`SandboxDaemon.wait_models_warm()` (bug-184's signal: the warm-up thread's own terminal
`rmxd.log` line per role), on the real 5 s budget.

**Deviation, ruled L159.** 29.4 `#r3-budget-census` names two control forms (`with_budget`,
the knob forms; L141 kept only `with_budget` and reasoned entries). The readiness wait fits
neither, and `test_bug228_and_bug231_tests_hold_no_entry` forbids an entry, so the census gains
a third form: `READINESS_CALLS = {"wait_models_warm"}` in `tests/budget_outcome_census.py`,
one table entry beside `with_budget`.

**How the census tells before from after, and direct from hidden**
(`_waits_ready_before_the_run`): it collects every `ast.Call` in the test function whose callee
name (the attribute name, or the bare name) is in `READINESS_CALLS`, and every call whose name is
in `RUN_CALLS = {"run_hook", "run_cmd"}`, and accepts only when both exist and the smallest
line number of a readiness call is smaller than the smallest line number of a run call. A
readiness call after the hook has a larger line number, so it fails. A call hidden in a helper
(`_ready(d)` whose body calls `wait_models_warm`) is a call named `_ready`, not in the table, so
it fails too: only the test function's own syntax tree is read for this form. RED's L159 nodes
(`cdc9c88`: two pass cases, the after-the-hook and the helper must-fails) and the earlier
must-fails (the frozen base copy, `str.replace`, `with_budget(cmd, budget)`) all pass in
`green-bug269-fix.log`.

**Product row (for the lead's id):** "live recall over its 5 s budget at load 3: the embedder's
cold load (5.6-9.1 s from daemon start) spent the budget; the recall op waited and never ran"
(RED's text), `deferred: ...; review <date>` unless a task takes it.

{#bug228-body}

## bug-269: diagnosis {#bug269}

**Measured mechanism.** A daemon's shutdown waits out its startup model warm-up.
`serve_forever`'s `finally` runs `_close_workers()` first; it calls `WorkerClient.retire(timeout=
2.0)` for embed then rerank, and `retire` takes the worker's `_lock`, which the startup warm
thread (`_start_embedder_warmup`) holds through each cold load (`info()` loads the model under
the lock). `retire`'s `timeout` bounds only the close after the lock is taken, and this wait is
outside `_StopDeadline`. A stop issued during warm-up costs the rest of the embed load plus the
whole rerank load, in series.

Evidence: an A/B probe run once from a throwaway copy in `tests/` (deleted after; its source,
the log-capture plugin and the data are kept as text in `workflow/review-output/t0.3/bug269-probe/`;
run log `green-r9-fix-and-b269-probe.log`, exit 0, 8 passed) and one L3 harness trial with the
daemon's log captured (`harness/diag-bug269-l3/`, `green-diag-bug269-l3.log`):

| Run | Stop issued | Stop wall | rmxd.log |
|---|---|---|---|
| quiet, stop right after spawn (3) | models warming | 5.54 / 5.48 / 5.02 s | `worker[embed] closed` and `worker[rerank] closed` each in the same or the next second as its `... warm in 2.4-2.6s` line |
| quiet, stop after both `warm in` lines (3) | models warm | 1.88 / 1.89 / 1.92 s | closes 1 s apart, no wait |
| L3 trial at `83c2711` with the log captured | warming | 5.36 s | embed warm 10:52:56, closed :57; rerank warm :58, closed :59; stopped :59 |

{#bug269-table}

**The over-grace window.** In the base sweep the stop op went out about 1 s after the spawn
(warming), and graceful_stop gave up at 10.0 s with `stop_op: sent`; the SIGTERM that followed
still took 0.8-13.0 s. In the same window bug-228's captures show the embedder alone taking
9.1 s (L3 trial 5, 05:14:43) and 5.6 s (trial 6), so the two serial loads exceeded the 10 s
grace; after 07:40 the stops took 5.7-6.0 s, the quiet figure. What made model loads slow in
05:14-07:20 was not measured (start-of-trial load averages do not separate the groups).

**Product row (for the lead's id/status).** "A daemon stopped during its startup model warm-up
waits for both cold loads before it exits: `_close_workers` -> `WorkerClient.retire()` blocks on
the worker lock the warm thread holds, outside `_StopDeadline` (measured: 5.0-5.5 s vs 1.9 s
warm, quiet; > 10 s when the loads were slow)". Diagnosis accepted, ruling L161, which put the
fix in scope.

{#bug269-body}

### bug-269: the fix (L161) {#bug269-fix}

Choice: **acquire the lock with the retire timeout, then abandon the holder.**
`subproc.WorkerClient.retire(timeout, *, abandon_in_flight=False)`:

- default: unchanged (take the lock, then retire and close). Adoption (`_maybe_adopt_shared`,
  `recall`'s embed swap) keeps it, because an in-flight op there (an ingest's embedding batch)
  must finish against the worker it started with;
- `abandon_in_flight=True`: wait for the lock at most `timeout`; on success retire and close as
  before. Past it, set `_retired` FIRST, then SIGKILL the model process and wait for it (a
  still-alive pid after the wait is logged, not swallowed). The holder's `select` sees EOF, its
  `call` closes and tries to respawn, and `_ensure` refuses ("retired ... not respawning"), so
  the holder fails with `WorkerError` instead of holding the stop.

`daemon.py`: `_close_workers` (shutdown only) passes `abandon_in_flight=True` with its existing
2.0 s timeout, so each worker costs at most 2.0 s plus the kill, independent of how long the
load would have taken. The abandoned warm thread is then stopped from doing more harm:
`_start_embedder_warmup` starts no reranker load once `_stop_began()`, and `Daemon._embedder`'s
fallback hook raises instead of letting `recall.shared_embedder` load the model in-process into
a stopping daemon (`shared_embedder` still logs its "falling back" warning line first; the next
line is the warm-up's `embedder warmup failed: RuntimeError('daemon stopping: no in-process
embedder fallback')`). `_stop_began()` reads `_shutdown_event` with `getattr`, because unit tests
assemble a Daemon without `__init__` and drive the warm-up alone
(`test_the_startup_warmup_really_loads`); `__init__` always sets it.

An earlier draft also made `_model_client` refuse after the stop and took `_worker_lock` in
`_close_workers`. Both were dropped before commit: the refusal routed `_embedder` into the
in-process fallback, and the lock broke a unit test whose Daemon has no `_worker_lock`.
What remains is the narrow race the code already had: a reranker client created in the instant
between the warm thread's `_stop_began()` check and `_close_workers` reading the attribute.

Not charged to `_StopDeadline`: the worker stage is bounded by its own 2.0 s lock wait plus the
kill instead (the bound in the Self-audit, Q4).

**RED proven at the pre-fix tree.** With `401e351`'s `subproc.py` and `daemon.py` checked out
(then restored, `__pycache__` cleared), the node fails on its own E line:
`AssertionError: bug-269: the stop waited out the warm-up: the embed worker's load was released
(after the 20 s hold) before the daemon exited (rc=0)` (`green-bug269-red-at-prefix-401e351.log`,
1 failed); that daemon's log stops at 12:07:58 after `embedder warm in 22.4s`
(`bug269-evidence/prefix-rmxd.log`). After the fix the stop takes 12:08:31 to 12:08:33 and the log
shows each guard firing (`bug269-evidence/postfix-rmxd.log`, quoted under Q1 below).

Result: `tests/test_bug269_stop_during_warmup.py::test_bug269_a_stop_during_warmup_does_not_wait_
out_the_warmup` (RED `9270f58`: a 20 s held embed load) passes in `green-bug269-fix.log` (exit 0,
155 passed), with the retire tests of `test_rerank_budget_real_clients.py` (a retired client
never respawns or warms; shutdown retires; adoption retires), `test_daemon_shutdown*.py`,
`test_stop_deadline.py`, `test_daemon_dense_ops.py`, `test_task3_7_remedy_r4.py` and
`test_plan4_remedy.py`. red-t02's bug-267 guards are not on this branch.

{#bug269-fix-body}

## Confirm trials {#confirm}

One trial per reproduced row, `until-target`, under `caffeinate -i`, the lane lock per trial.

| Row | Level | Sha | Outcome | Awake | Held | Notes |
|---|---|---|---|---|---|---|
| bug-231 | 3 | `83c2711` | pass (stop 5.37 s, grace 60) | 76.9 s | 76.9 s | load average 5.0 at the start; 1 leaked load-process daemon swept by the harness; `harness/confirm-bug231-l3/` |
| bug-228 | 3 | `b9d15fa` | pass (boot 0.41 s, warm wait, hook 0.74 s) | 41.6 s | 41.6 s | load average 4.2 at the start, below the base sweep's 9-18; `harness/confirm-bug228-l3/` |
| bug-231, after the bug-269 fix (L164 (b)) | 3 | `f4262e8` | pass (stop 3.01 s, grace 60) | 42.3 s | 42.3 s | load average 6.6 at the start; `harness/confirm-bug231-l3-after-bug269/` |

{#confirm-table}

An earlier bug-231 trial at the uncommitted tree (pass, 5.34 s, 41.4 s) was discarded so the
recorded trial names a committed sha.

## Verify set {#verify}

**The final set (run 2).** bug-269's fix changes `src/refmatrix/subproc.py` and
`src/refmatrix/daemon.py`, so the set is: every `tests/test_*.py` importing either, found with
`grep -lE 'from refmatrix(\.daemon| import .*\bdaemon\b)|import refmatrix\.daemon|from
refmatrix(\.subproc| import .*\bsubproc\b)|import refmatrix\.subproc' tests/test_*.py` (152
files); plus the six new T0.3/29.4c files, the bug-269 RED file, every test file this branch
edited, and every importer of an edited test module (found per module with
`grep -lE "from tests(\.| import )<module>\b|from tests\.<module> import"`:
`test_bug212_r5/r6/r7_red`, `test_plan2_remedy_r6`, `test_plan3_remedy_r6/_r7`,
`test_task4_5_r4_remedy`, `test_task4_6_r5_remedy`, `test_task3_7_remedy_r5/_r6`). The union is
159 files, listed in `workflow/review-output/t0.3/green-verify-2-files.txt`. No full suite.

| Run | Sha | Exit | Collected | Passed / failed / skipped | Log |
|---|---|---|---|---|---|
| verify 2 (final set) | `e8277d4` | 0 | 2,640 | 2,640 / 0 / 0 | `green-verify-2.log` (43:30) |
| bug-269 RED node + stop/retire/census files | tree of `e8277d4` | 0 | 155 | 155 / 0 / 0 | `green-bug269-fix.log` |
| verify 1 (all but `test_task21_1_recall_skip.py`) | `83c2711` | 1 | 718 | 714 / 4 / 0 | `green-verify-1.log` |
| bug-228 file + budget census + mechanisms | `b9d15fa` | 0 | 25 | 25 / 0 / 0 | `green-bug228-provisional.log` |
| bug-269 RED node at the pre-fix src (`401e351`) | `401e351` src on `e8277d4` tests | 1 | 1 | 0 / 1 / 0 | `green-bug269-red-at-prefix-401e351.log` |
| bug-190 (L164) file + every RED node (bug-269, flake diagnostics, censuses, mechanisms, timing) | `f4262e8` | 0 | 108 | 108 / 0 / 0 | `green-bug190-l164-and-red-nodes.log` |

Verify 2 was run on the src fix itself; the only later code change is the bug-190 test
(`f4262e8`, no `src/`), re-run in the last row with every RED node, so the 159-file set was not
run a third time.

{#verify-table}

Verify 2 has no failure. Verify 1's four failures, by E line, all closed since (none of these
nodes exists in `release-0.84.0-full.log`, whose 13 failures are in `test_brief_real_daemon`,
`test_repo_hooks_in_sync`, `test_search_hooks`, `test_task21_1_agent_usage_report`, none in
this set):

- `test_wallclock_census.py::test_ac4_a_listed_bound_passes` and
  `::test_ac4_fixture_suite_health_is_exempt_by_path_and_nothing_else_is`: `FileNotFoundError:
  [Errno 2] No such file or directory: '.../ok/tests'` (and `'.../a/tests'`): RED's helper, fixed
  at `d81ed07` (L160).
- `test_wallclock_census.py::test_bug228_and_bug231_tests_hold_no_entry`: `AssertionError:
  ['test_plan4_remedy.py::test_graceful_stop_signals_first_then_waits_the_grace::ok is False and
  0.9 < elapsed < 3.0']`: RED's filter, narrowed at `d81ed07` (L160).
- `test_budget_outcome_census.py::test_the_tree_passes_the_budget_outcome_census`:
  `AssertionError: ['test_task21_1_recall_skip.py::test_ac2b_live_daemon_recall_writes_one_ok_
  recall_row: asserts an outcome a real-time ...']`: closed by the L159 form (`b9d15fa`).

The pre-existing `PytestUnhandledThreadExceptionWarning` (BrokenPipe in `_RawHub`) of
`test_a_header_that_eats_the_budget_sends_no_rerank` is also in the release log (its line 474).


## Mock registry {#mocks}

Nine rows added to `workflow/test_mock_registry.md#registry` (`T0.3 + 29.4c GREEN ...`): the
transport and budget recorders, the stub's held load / held rerank, the bug-190 spawn-stack
recorder, the held ingest body, the signal-first recorders, the await-shutdown sleep recorder,
the absent-socket recorders, and the held locate straggler.

## Not done, flagged {#flags}

- Mutations are the reviewer's (brief). AC-3.2's M3.1-M3.4 and 29.4's census mutations map to
  nodes in [[t0-3-red-report#mutation-table]].
- No fix-proof bands of any length (L164 (b); Q42 is with the user). The proof is one confirm
  trial per reproduced row, bug-231's re-run after the bug-269 fix.
- Registry rows 130, 190, 091, 228, 231, 269 are not edited here: their text and status are the
  lead's at the merge (AC-6 needs the merged sha).

{#flags-list}

## Self-audit {#self-audit}

For the bug-269 `src/` fix and the T0.3 test changes (ruling L166), against the eight questions
of `workflow/SELF_AUDIT.md` on dev master (not yet on this branch, so not linked).

1 **real**: the RED node runs a real `rmx daemon start --no-detach` child (`SandboxDaemon`) and
sends the real `stop` op (`daemon.call`); the daemon's own log after the fix
(`bug269-evidence/postfix-rmxd.log`): `12:08:30 worker[embed] spawned` → `12:08:33 worker[embed]
retire: the lock is still held after 2.0s (a call or the warm-up's load in flight); abandoning
it, killing pid=81122` → `died on op=info (EOFError('worker closed')); respawning` → `subprocess
embedder unavailable (WorkerError('embed worker retired ... not respawning'))` → `embedder warmup
failed: RuntimeError('daemon stopping: no in-process embedder fallback')` → `reranker warmup
skipped: the daemon is stopping` → `12:08:33 daemon stopped`. Pre-fix, the same node: stopped at
12:07:58 after `embedder warm in 22.4s` (`prefix-rmxd.log`). Through the hub's path:
`hub.graceful_stop` on a spawned daemon at L3 took 3.01 s (confirm trial at `f4262e8`; 5.37 s
before the fix).
{#sa-1}

2 **wiring**: `test_bug269_stop_during_warmup.py::test_bug269_a_stop_during_warmup_does_not_wait_
out_the_warmup` enters through the daemon's `stop` op over its socket; nothing in the daemon or
`WorkerClient` is patched (the hold is a preload in the embed worker process). bug-190's test
drives the real `RemoteReranker.with_budget` over a real `WorkerClient` and stub process; the
recorder calls the real `_spawn`. The T0.3 tests replaced in [[#sites]] keep their entry points
(CLI via `CliRunner`, verbs, daemon ops, real daemons).
{#sa-2}

3 **census**: `grep -n 'retire(' src/refmatrix/*.py` and the `getattr(w, "retire", w.close)`
form: `daemon.py:1174` `_close_workers` (shutdown; passes `abandon_in_flight=True`),
`daemon.py:1046` `_maybe_adopt_shared` and `recall.py:644` the embed swap (adoption; default,
waits, so an in-flight ingest batch finishes: deliberate). `_stop_began()`: `daemon.py:938`
(`_embedder` fallback) and `:1250` (warm-up's reranker step). Left: the hub's shared clients
(`modelsrv`) close without `retire` and hold no warm lock in the daemon; `_fast_exit`
(`os._exit(2)` on a lost writer) skips `_close_workers` entirely, unchanged; the narrow race in
[[#bug269-fix]] (a reranker client made between `_stop_began()` and `_close_workers` reading the
attribute) is pre-existing and stays.
{#sa-3}

4 **bound**, stop op to exit. Caller (`daemon.graceful_stop`): `ping` 0.5 s, retries 0; `call
stop` 2.0 s, retries 0; then polls the pid for `grace`. Daemon: `_op_stop` sets `_stop`; the
accept loop wakes within `srv.settimeout(1.0)`; `shutdown.started` touch; `_StopDeadline(
stop_grace_s())` = 45 s − 2 s margin starts here. `_close_workers`, per private worker: lock wait
≤ 2.0 s, then either `close(2.0)` (EOF wait 2.0 + terminate wait 2.0 + kill wait 2.0) or SIGKILL
+ wait ≤ 2.0 s: ≤ 8 s per worker, ≤ 16 s for two (before: the remaining cold loads, unbounded;
measured 22.4 s here). Then watcher join `budget(3.0)`, three pool drains `budget(10)` each,
flush/repair/replica joins `budget(3.0)` each, `_final_flush` capped by what is left, store close
`budget(5.0)`: every one of these asks the same deadline, so they shrink by what the workers
spent. The worker stage itself is not charged to the deadline, so the worst case is max(16 s +
5 s store close, 43 s) = 43 s at the default grace. No `daemon.call` with default retries is on
the path.
{#sa-4}

5 **busy**: worker busy (a held cold load) → the lock wait times out at 2.0 s, the process is
killed, the holder fails with `WorkerError` (the RED node; log above). Worker idle → the lock is
taken at once and the old close runs (`test_shutdown_retires_the_workers`). Worker down while a
call holds the lock → the branch logs `retired while a call held the lock past 2.0s; no live
process to stop` and returns; no test reaches it (named, not covered). Daemon down: not on this
path (a stop with no daemon is `graceful_stop`'s `skipped: no daemon`, unchanged, seen in every
confirm trial's second stop). A busy ADOPTION swap still waits for the in-flight op (default).
{#sa-5}

6 **guard**: (a) the abandon branch fires on "lock still held after `timeout`", the state a
warm-up's cold load produces; reached by `_close_workers` at a stop during warm-up; test: the
bug-269 node, which holds the load in the worker process without patching the lock or the
client. (b) `_stop_began()` in the warm-up and (c) the `_embedder` fallback refusal fire on
`_shutdown_event` set by `serve_forever`'s `finally`; both reached in the same node (their log
lines above). (d) the "no live process" branch and (e) the post-SIGKILL "still alive" log are
not reached by any test. bug-190's guard (a spawn on the caller's thread) fires on the forced
RED child (`_t03_forced_spawn`), `test_r3_4_bug190_a_spawn_on_the_skip_path_names_its_stack`.
{#sa-6}

7 **loud**: forced bug-269 at the pre-fix tree → pytest exit 1, `E AssertionError: bug-269: the
stop waited out the warm-up ...` (`green-bug269-red-at-prefix-401e351.log`). An abandoned call is
loud to its caller (`WorkerError: embed worker retired ... not respawning`) and in `rmxd.log`
(the `retire: ... abandoning it, killing pid=` line). No `except: pass` added:
`git diff 401e351 -- src/ | grep -E '^\+.*(except|raise)'` lists one handler, `except
subprocess.TimeoutExpired:` (it logs the pid still alive after SIGKILL), and one `raise
RuntimeError("daemon stopping: no in-process embedder fallback")`.
{#sa-7}

8 **handoff**: bug-269's and bug-190's registry rows (text above, ids/status the lead's at the
merge); the remainder row for the 41 legacy bounds (text in [[#sites]]); the untested branches
in Q5/Q6 (d)(e) and the pre-existing race in Q3 are named here, not filed. Fix-proof bands: none,
by L164 (b) / Q42.
{#sa-8}
