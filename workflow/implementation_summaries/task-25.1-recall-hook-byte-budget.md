---
gmd: "0.1"
id: task-25.1-recall-hook-byte-budget-summary
title: "Task 25.1 implementation summary (stub): RED tests for the recall hook byte budget (bug-164) and the MCP unknown-project error (bug-181)"
tags: [implementation-summary, plan-25, task-25.1, bug-164, bug-181, red, tests]
metadata:
  node_type: implementation-summary
  status: red
  created: 2026-11-11
  updated: 2026-11-11
---

# Task 25.1 implementation summary (stub, RED only) {#root}

rel: implements -> [[task-25.1-recall-hook-byte-budget]]
rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[hook-output-cap-probe]]
rel: derives-from -> [[task-25.1-recall-hook-byte-budget#acceptance]]

Branch `task-25.1-recall-hook-byte-budget` in `/Volumes/littlebig/refmatrix-plan25-1`, base
`f7c0d39`. Tests only: no `src/` change. RED commits `36bfaa7` (fixture), `71e7797` (tests,
support, routing inversion, mock-registry row), `e09454d` (AC-6 on both legs), `af3af4b` (AC-15
from spec rev 6). The R0 probe `d748196` and spec rev 6 `f4061aa` were committed to this branch by
the lead side during the run; the tests follow both. {#lead}

## RED run {#red}

`workflow/review-output/plan25/25.1-red.log`: **116 failed, 10 passed** in 101 s at `af3af4b`
(src = `f7c0d39`). The 10 passing: 7 untouched tests of `tests/test_mcp_memory_recall_routing.py`,
the fixture pre-check, and the two guards proved by mutation ([[#mutations]]). 0 sandbox
violations, 0 setup errors. Files: `tests/test_task25_1_recall_budget.py`,
`tests/task25_1_support.py`, `tests/fixtures/plan25/`, `tests/test_mcp_memory_recall_routing.py`.
{#red-run}

HEAD byte records on the fixture (the same numbers the RED lines print): per-prompt argv on the
question 18,865 B (5 rows; `savestate_fx01` first), on the ack 34,368 B; SessionStart argv
10,075 B (all 5 seeded subjects among 10 rows); PreCompact argv 67,098 B; scan-prompt alone
6,660 B and `scan_cmd` 8,545 B; `curator status` 1,885 B (30 queued paths > 120 chars);
`focus context --top 15` 3,300 B. AC-3 reach at HEAD: 0 distinct memories in what the model
receives (the 2 KB preview of a JSON list). {#red-head-bytes}

| test (in `test_task25_1_recall_budget.py` unless named) | AC | RED line at HEAD |
|---|---|---|
| `test_r1_hook_budget_table_names_every_channel_event_and_command`, `test_r1_non_rmx_reserve_is_per_event_and_covers_the_measured_hooks`, `test_r1_env_override_and_non_integer` | R1, AC-14 single-reserve mutation | `R1: refmatrix.hook_budget is not built` |
| `test_ac9_fit_blocks_whole_blocks_in_order_bytes_and_trailer[2000/4000/9000]`, `test_ac9_fit_blocks_everything_fits_has_no_trailer` | R0b, AC-9, AC-2 | `R0b: refmatrix.hook_budget.fit_blocks is not built` |
| `test_ac9_pack_hook_lines_first_whole_bodies_arithmetic_and_bytes[x3]`, `test_ac9_pack_curated_hook_else_first_sentence_and_scope_correct_fetch`, `test_ac9_pack_trailer_quotes_a_multiline_query`, `test_ac9_pack_loud_overflow_never_empty_never_over`, `test_ac10_pack_spans_are_utf8_byte_ranges`, `test_ac9_pack_prints_curated_hooks_from_load_hooks[path-keyed/id-keyed]` | AC-9, AC-2, AC-10, AC-11 (pack leg) | `R4: refmatrix.recall_pack is not built` |
| `test_ac1_ac4a_per_prompt_argv_within_prompt_recall_budget`, `test_ac1_ac4a_ack_prompt_within_budget` | AC-1, AC-4 (a) | `printed 18865 B` / `34368 B; ... budget('prompt_recall') does not exist` |
| `test_ac1_ac4a_session_start_argv_within_budget` | AC-1, AC-4 (a) | `printed 10075 B; ... budget('session_start')` |
| `test_ac1_ac4a_precompact_argv_within_budget_or_dropped` | AC-1, AC-4 (a) | `printed 67098 B; ... budget('precompact')` |
| `test_ac2_max_bytes_bounds_every_channel[channel x N]` (15) | AC-2 | `exit 2; Usage: rmx memory recall` / `rmx scan-prompt` / `rmx focus context` (no `--max-bytes`) |
| `test_ac3_reach_at_least_8_distinct_memories` | AC-3 | `the model receives 0 distinct memories ([]) from a 18865 B payload` |
| `test_ac4b_verb_reads_the_replica_with_a_shared_worker_and_no_daemon` | AC-4 (b) | `the verb raised VerbAbsentError: daemon not running ... with a replica and a live shared worker` |
| `test_ac4c_hook_mode_no_daemon_no_worker_exits_0_silent_and_counted` | AC-4 (c), d8 | `exit 1: Error: rmx memory recall needs the daemon up ...` |
| `test_ac4c_verb_hub_only_raises_the_r5_absent_error` | AC-4 (c) | `daemon not running for ...` (HEAD's words, not R5's) |
| `test_ac4e_mcp_cross_project_reads_the_named_stores_replica` | AC-4 (e) | `{"error": "daemon not running for .../fxb/.refmatrix"}` (B is resolved; the verb never reads its replica) |
| `test_ac4e_r10_resolve_root_unknown_project_raises` | AC-4 (e) R10 (1) | `project='charlie' names no store, yet _resolve_root returned .../alpha/.refmatrix (bug-181 silent fallback)` |
| `test_ac4e_r10_recall_tool_answers_iserror_without_cwd_rows` | R10 (2) | `{"error": "daemon not running for .../alpha/.refmatrix"}` (the cwd store was read) |
| `test_ac4e_r10_every_tool_refuses_an_unknown_project[<each of mcp.TOOLS>]` (40) | R10 (3) | per tool: the verb RAN against alpha (`hub not running`, `VerbArgsError: ... requires`, `isError: False` with alpha's data) |
| `test_ac4e_r10_memory_add_never_bootstraps_into_the_cwd_store` | R10 (3) | `{'isError': False, 'text': '{"id": 3}'}` (bootstrap write into alpha) |
| `test_r10_schema_says_registered_only` | #r10-schema | `target another project by name (any live store)` |
| `test_resolve_root_unknown_project_raises` (routing file; inverted from `..._falls_through`) | R10 (1) | `DID NOT RAISE VerbArgsError` |
| `test_ac4d_rows_parity_replica_on_and_off[replica-on/replica-first-0/no-worker]` | AC-4 (d) | `not a --pack payload (R3): 3979 B` / `18865 B` |
| `test_ac4f_interactive_recall_names_the_verbs_hits_including_a_doc` | AC-4 (f) | CLI `[..., fx_mem_06, fx_mem_16, ...]` != verb `[..., fx_mem_03, fx_mem_23, ...]` (two which-rows computations) |
| `test_ac4g_interactive_no_daemon_no_hub_uses_shared_embedder` | AC-4 (g) | `exit 1: Error: rmx memory recall needs the daemon up ...` |
| `test_ac4g_mcp_no_daemon_no_hub_uses_shared_embedder`, `test_ac7_mcp_embedder_policy_argument_is_dropped` | AC-4 (g), AC-7 | `{"error": "daemon not running ..."}` |
| `test_ac5_mistyped_savestate_not_named_on_the_packed_argv` | AC-5 | `not a --pack payload`; HEAD's JSON names `savestate_fx01` FIRST. Expected to stay RED until 26.4 merges (see [[#ambiguities]] a5) |
| `test_ac6_no_subject_rows_on_the_per_prompt_argv` | AC-6 | `AC-6 (replica leg): subjects named: ['subject_quasar_ledger_0', 'fx_dup_x', 'subject_quasar_ledger_1', 'gx_mem_9', 'subject_quasar_ledger_2']` |
| `test_ac6_include_subjects_brings_live_subjects_back_never_the_stale_one` | AC-6 | `exit 2` (no `--include-subjects`) |
| `test_ac6_session_start_argv_has_no_subject_and_no_stale_subject` | AC-6 | `['subject_quasar_ledger_4', 'fx_dup_x', 'subject_quasar_ledger_3', ...]` (stale subject named) |
| `test_ac6_verb_hides_subjects_and_the_stale_one_even_with_the_opt_in` | AC-6 | verb rows carry subjects |
| `test_ac7_cli_prints_the_verbs_text_byte_for_byte` | AC-7 | `pack=True returned no text: keys ['memories', 'mode', ...]` |
| `test_ac7_schema_has_pack_params_and_never_embedder_policy` | AC-7 | schema lacks `pack` / `max_bytes` / `include_subjects` |
| `test_ac8_env_unset_within_the_table`, `test_ac8_env_3000_caps_every_recall_argv`, `test_ac8_env_non_integer_fails_naming_the_variable` | AC-8 | `printed 18865 B`; `18865 B > 3000`; `RMX_HOOK_BUDGET_BYTES=abc exited 0` |
| `test_ac9_prompt_recall_is_pointers_only_and_arithmetic_holds`, `test_ac9_session_start_carries_bodies_after_all_hook_lines`, `test_ac10_delivered_events_slice_the_payload_by_bytes`, `test_ac11_the_packs_global_fetch_pointer_returns_the_global_row` | AC-9, AC-10, AC-11 | `not a --pack payload (R3)` |
| `test_ac11_memory_get_scope_global_returns_the_global_row` | AC-11, R6 | `exit 2: Usage: rmx memory get` (no `--scope`) |
| `test_ac12_scan_prompt_alone_within_its_budget`, `test_ac12_curator_status_alone_within_its_budget` | AC-12 | `printed 6660 B` / `1885 B; ... budget(...) does not exist` |
| `test_ac12_each_user_prompt_submit_command_within_its_command_budget` | AC-12 (A) | `R1 not built; 'rmx scan-prompt ...' printed 8545 B` |
| `test_ac12b_focus_context_within_its_budget`, `test_ac12b_each_session_start_command_within_its_budget` | AC-12b | `printed 3300 B`; `sess_cmd printed 1885 B` |
| `test_ac13_generator_emits_pack_raised_k_and_no_variable` | AC-13, R7 | `'rmx memory recall --stdin-json --k 5 --scope both --json --timeout 5'` lacks `--pack` |
| `test_ac15a..e_*` | AC-15 (a)-(e), R11 | `R11: expected ONE SessionStart entry running recall-state; got []` |
| `test_ac15f_max_bytes_is_a_recall_state_verb_parameter` | AC-15 (f) | schema `['memory_dir', 'project', 'root', 'session']` |

{#red-map}

Not RED by design (pass at HEAD): `test_ac2_fixture_density_precheck` (a fixture
PRE-CHECK, AC-2 / AC-10 admit the fixture only when it holds); the two guards below. {#red-not}

## Mutation proofs for the guards {#mutations}

Run against the committed tests (`71e7797`) with `src/` clean; each mutation restored with
`git checkout -- <file>` in its own command, `__pycache__` cleared after. {#mutations-method}

- `test_ac4h_legacy_memory_partition_replica_and_rpc_agree`: mutation = HEAD's
  `cli._replica_memory_recall` binds `_store_mod.default_partition_name(_root())` (the project
  partition) instead of `_resolve_partition()`. KILLED: `replica leg [] != rpc leg ['fx_mem_26',
  'fx_mem_20', 'fx_mem_24', 'fx_mem_21', 'fx_mem_22']`
  (`workflow/review-output/plan25/25.1-mutation-ac4h.log`). {#mut-ac4h}
- `test_ac4e_r10_no_project_and_explicit_root_are_unchanged` (R10 leg 4): mutation =
  `_resolve_root` ignores `root` (`if False and args.get("root")`). KILLED: resolved alpha, not
  bravo (`workflow/review-output/plan25/25.1-mutation-r10-leg4.log`). {#mut-leg4}

## Spec ambiguities and how they were resolved {#ambiguities}

- **a1 R0 landed mid-run (`d748196`): outcome (A) on both events.** The per-command assertions
  (AC-12, AC-12b) are written for (A) only; (B)/(C) event sums are not written because R0 says
  they do not bind. A command's budget is the SUM of its channels' budgets
  (`HOOK_COMMAND_CHANNELS`), which is ≤ R0's 9,000 B per command, so the tests stay on R1's
  constants as the spec requires. {#a1}
- **a2 rev 6 added `recall_state`** to `CHANNEL_BUDGET_BYTES`; R1's table test expects the eight
  names. {#a2}
- **a3 AC-4 (h) is a guard at HEAD, not RED.** The spec says HEAD's replica leg "binds the
  project partition (`cli.py:11394`) and returns none". At `f7c0d39` `_memory_intent` →
  `_apply_memory_partition_default` sets the override, so the replica leg already binds
  `memory-<p>`. With rerank on, the two legs differ (4 of 5 names shared) because they rerank in
  different processes over different pools (d7); the test pins `RMX_RERANK=0` on the daemon and
  the calling process so it compares partitions only, and is proved by mutation. {#a3}
- **a4 pack API details the spec leaves open:** `Packed.named` read as the list of named hit
  names and `Packed.more` as the trailer's N; `fit_blocks(trailer=)` taken as a callable of the
  dropped count; `Fitted.kept` / `dropped` accepted as counts or lists; the query-mode trailer
  uses the verb's mode name `dense`; a multi-line query collapses newline → space. `pack()` has
  no memdir argument, so "the row's path relative to the memdir" needs a field the spec does not
  name: the unit tests feed `metadata.source_path` and exercise the path-keyed case through
  `memory_index.load_hooks`. Since 26.1, `load_hooks` aliases every path key to its id, so the
  AC-14 mutation "the pack looking hooks up by id only" is EQUIVALENT on `load_hooks` output and
  cannot be killed through the verb: a spec finding for the next review. {#a4}
- **a5 AC-5 waits on 26.4.** At HEAD the bridge stores `savestate_fx01` as `project`, and it is
  HEAD's first hit. The test also asserts the verb's row list (what the pack is fed, R4) holds no
  save-state, so it stays RED after 25.1's GREEN until 26.4 merges, as the lead said. {#a5}
- **a6 AC-6 HEAD record.** On the daemon-RPC leg the `--scope both` merge left no subject in the
  project half (HEAD k 5 and GREEN k 12); HEAD's replica leg (a real worker) names
  `subject_quasar_ledger_0` first. The per-prompt test runs both legs, so its RED is AC-6's own.
  {#a6}
- **a7 AC-4 (c) "no modelsrv child, no sentence_transformers import".** Asserted as no
  `sentence_transformers` line in the hook's `PYTHONPROFILEIMPORTTIME` stderr, plus the 5 s hook
  budget (AC-14's "the hook overruns its 5 s budget"). A spawned private worker's stderr goes to
  DEVNULL, so the child itself is seen only through the overrun. {#a7}
- **a8 AC-10's fixed shape** (7 of 12 named, 3 bodied) is not forced on the integration path; the
  test asserts the contract (one delivered event per named hit, byte spans, null body fields,
  the global file) on the SessionStart argv, and the unit test covers byte spans with ≥ 3 `—`
  before every checked span. {#a8}
- **a9 AC-3's cap** is taken as 9,412 chars delivered whole and a 2,048 B preview (the lead's
  transcript evidence). R0 now says 10,000 UTF-16 units and a ≤ 2,000-unit preview; the AC-3
  bound (≥ 8) holds under either. {#a9}
- **a10 scan-prompt sizing.** The fixture pushes scan-prompt to 6,660 B at HEAD, not the
  spec's "> 10,000 B": `--max-tokens 2000` bounds it without the composite turn. RED holds
  against `budget("scan_prompt")` = 4,500 B. {#a10}
- **a11 AC-12b's `ingest-gmd --detach`** is not run: it would enqueue a re-ingest on the shared
  module daemon mid-module. {#a11}
- **a12 AC-15 (d) "counted"** names no recorder; the test asserts the missing daemon is SAID
  (stdout or stderr). AC-15 (e) runs through the generated entry, so at HEAD it is RED on the
  missing entry; whether HEAD's bare `rmx recall-state` already fails cleanly on an unreadable
  memdir was not measured. {#a12}
- **a13 not written:** AC-4 (i) (a guard; needs the "`shared_embedder` before the daemon"
  mutation at GREEN), AC-14's GREEN-time mutation run, and the before/after table
  (`workflow/measurements/plan-25-hook-bytes.md`). {#a13}

## Mock governance {#mocks}

No new mock. The fixtures use real daemons, a real `modelsrv.ModelServer` child, the real
bridge and the real registry; env redirections (`RMX_HOME`, `RMX_MODEL_SOCK`, `RMX_RERANK`,
`RMX_SESSION`) are inputs, and the R10 sweep's audit-hook connect counter is an observer with a
positive control. The routing file's PRE-EXISTING stubs (`daemon.call` / `daemon.ping` /
`discovery.discover_roots` / `discovery.store_name`) had no registry row; one was added
(`workflow/test_mock_registry.md`, last row), classified internal-active, graduating onto the
25.1 stores at GREEN. The registry's recent rows, including this one, sit below its
`#graduation-log` header: pre-existing layout drift, not fixed here. {#mocks-registry}
