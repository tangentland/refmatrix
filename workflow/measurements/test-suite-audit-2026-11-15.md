---
gmd: "0.1"
id: test-suite-audit-2026-11-15
title: "Test-suite audit 2026-11-15: not polluted; the time is real-timeout waits and fixture teardowns"
tags: [measurement, tests, suite, audit, p1]
metadata:
  node_type: measurement
  created: 2026-11-15
---

# Test-suite audit, 2026-11-15 {#root}

Static, read-only audit by the `test-audit` agent (ch-test-engineer) for POP row P1 (a)
(L165). Timings from `task-29.4/r0-serial.log` (3,255 s summed); failures from the 0.82.0,
0.83.0 and 0.84.0 release logs plus 57 `*full*.log` files. {#lead}

rel: evidence-for -> [[plan-of-plans#queue]]
rel: depends-on -> [[orchestration]]

## Verdict {#verdict}

The suite is not polluted. About 4,010 of 4,098 tests are behaviour tests; none patches the
function under test. About 20 tests are deletable (~6 s). The runtime is in tests that wait out
real product timeouts (~546 s), daemon-stop teardowns in fixtures (~358 s), and 350-doc ingest
jobs kept running only to observe a wait (~208 s). The top 25 files take 61% of the time.

## Classes {#classes}

| class | tests | files | seconds |
|---|---|---|---|
| behaviour | ~4,010 | ~355 | ~3,215 |
| source-text | 56 (48 guard a rule, 8 pin a detail) | 29 | 33.5 |
| round-duplicate | 2 confirmed, ~4 partial | 6 | 0.4 / ~60 |
| mock-heavy (6+ patches, all process boundaries) | 23 | 15 | 4.3 |
| waits on a real timeout | ~43 calls | ~15 | ~546 |
| teardowns ≥ 3 s | 70 | 23 | 358 |
| 350-doc ingest-job waits | 6 | 3 | ~208 |

## Always red in 0.82.0, 0.83.0 and 0.84.0 {#always-red}

13 tests: `test_search_hooks.py` 9 (bug-168), `test_task21_1_agent_usage_report.py` 2 (bug-156/196),
`test_brief_real_daemon.py` 1 (bug-127), `test_repo_hooks_in_sync.py` 1 (bug-170). A regression in
these files is invisible. T0.2 owns 11 of them and T0.8 (merged) the other 2.

## Delete or trim (high confidence) {#delete}

Source-text pins of an implementation detail:
1. `test_embed_phases_r10::test_the_cli_embed_loop_uses_the_verdict` (delete)
2. `test_embed_phases_r10::test_the_watch_flush_uses_the_sum` (delete; behaviour test beside it)
3. `test_plan4_remedy_r2::test_foreground_start_refuses_a_busy_daemon_without_reaping_it` (delete or call the helper)
4. `test_plan7_10_remedy_r4::test_this_guard_names_the_mechanism_it_replaces` (delete; cannot fail)
5. `test_plan5_remedy::test_sync_disk_is_a_thin_alias_of_the_bridge` lines 218-220 (trim)
6. `test_deferrals_clean::test_no_caller_passes_yield_args_to_sync` (delete; medium)
7. `test_task3_7_curator::test_enqueue_curator_writes_through_the_atomic_spool_writer` (delete; medium)
8. `test_task3_6_r9_remedy::test_the_outer_first_plant_kills_mutant_q5` `src.count(needle)==1` (trim; medium)

Confirmed duplicates: `test_plan2_remedy_r7::test_verb_memory_partition_reads_the_replica_under_a_held_writer`
(= `test_plan3_remedy_r4::test_memory_partition_reads_the_replica_under_a_held_writer`);
`test_mcp_memory_recall_routing::test_resolve_root_unknown_project_raises`
(= `test_task25_1_recall_budget::test_ac4e_r10_resolve_root_unknown_project_raises`).
Partial: the promote-on-a-held-writer trio in `test_plan3_remedy_r4`/`r6` (51 s) → one test with
three entry points.

## Make the waits cheap (medium confidence) {#speed}

| change | saves |
|---|---|
| test-sized budgets (env knob or constant), one test per budget kept at the real default; the verb read budget has no knob yet | ~450 s |
| fixtures stop test daemons with a short `RMX_DAEMON_SHUTDOWN_TIMEOUT_S` | ~250 s |
| 350-doc `_big_dir` → a small job held open by a gate | ~150 s |
| `test_modelsrv` probe timeout | ~40 s |
| `test_bug212_r4_red` git-timeout knob (and rename) | ~84 s |

Estimate: ~54 → ~40 min serial (release ~60 → ~45 min), before 29.4's sharded runner.

## Against the new test rules (L166, L167) {#vs-new-rules}

Lead's AST scan over 4,098 test functions (`scratchpad/betray.py`, `entry.py`), same day.

| rule | tests that break it | files | how counted |
|---|---|---|---|
| never fake daemon state by patching `ping` / `daemon.call` / `daemon_status` … | **208** | 66 | `monkeypatch.setattr` / `patch` targets (incl. fixtures the test takes) |
| … of those, tests ABOUT busy / down / timeout / held states (where L167 requires a real test daemon) | **49** | ~30 | same, name says busy, held, down, absent, timeout, budget, slow … |
| no per-round test files | 111 files (1,439 tests) | 111 | file names |
| test behaviour, not source text (detail pins) | 8 | 7 | the audit above |
| goes through a user entry point | 2,400 reach none | 297 | no CLI / verb / MCP / daemon op / hook call seen in the test or its fixtures |

The 2,400 overstates the breach: most are unit tests of pure functions (grep flag parsing, kwic,
STM), which the rule allows. L167 asks for at least one entry-point test per large change, and
the static scan cannot map tests to features. The 49 are the real breach: tests that claim to
prove busy/down behaviour against a patched value. The other 159 patch daemon calls as a process
boundary in tests about something else, which is allowed. {#vs-new-rules-reading}
