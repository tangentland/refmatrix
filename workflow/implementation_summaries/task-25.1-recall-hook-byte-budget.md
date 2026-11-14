---
gmd: "0.1"
id: task-25.1-recall-hook-byte-budget-summary
title: "Task 25.1 implementation summary: RED tests and GREEN code for the recall hook byte budget (bug-164) and the MCP unknown-project error (bug-181)"
tags: [implementation-summary, plan-25, task-25.1, bug-164, bug-181, red, green, tests]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-11
  updated: 2026-11-13
---

# Task 25.1 implementation summary {#root}

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

## GREEN {#green}

rel: evidence-for -> [[task-25.1-recall-hook-byte-budget#acceptance]]
rel: depends-on -> [[plan-25-hook-bytes]]

`green-251` (2026-11-11) wrote the GREEN and left it uncommitted. `green-251b` resumed it on
2026-11-13, triaged it, fixed it, and committed it as `16ace00` on
`task-25.1-recall-hook-byte-budget`. That commit touches `src/refmatrix/` (two new modules and
seven changed ones), `.claude/settings.json` and `README.md`. No test was edited. {#green-lead}

### Signatures {#green-signatures}

- `hook_budget`: `CHANNEL_BUDGET_BYTES` has eight channels (`recall_state` included).
  `HOOK_COMMAND_CHANNELS`, `EVENT_SPLIT` and `NON_RMX_RESERVE_BYTES` are keyed per event
  (`UserPromptSubmit` 512, `SessionStart` 3,584). Also `MIN_USEFUL_RECALL_BYTES` and the functions
  `budget(channel) -> int`, `resolve(channel, max_bytes) -> int`, `env_override() -> int | None`,
  `nbytes(text) -> int`, `clip_utf8(text, max_bytes) -> str` and
  `fit_blocks(blocks, max_bytes, *, trailer) -> Fitted(text, kept, dropped, payload_bytes)`.
- `recall_pack.pack(rows, *, hooks, max_bytes, channel, query, mode, k_more, since=None,
  subject=None, global_hooks=None) -> Packed(text, spans, named, more, payload_bytes)`. Also
  `hook_for`, `hook_line`, `fetch_of`, `more_command`, `header_line` and `first_sentence`.
- `recall.replica_memory_recall(root, *, partition, query, k, kinds, fuse, rerank, left=None,
  warnings=None, embedder_policy="hub_only") -> {"hits", "fetch", "embedder"} | None`, plus
  `recall.replica_first_enabled()` and `recall.entity_row(s, eid, kinds)`.
- `verbs.memory_recall(..., include_subjects=False, ..., pack=False, max_bytes=None, timeout=30.0,
  **internal)`. `embedder_policy` and `channel` ride `**internal`.
- `verbs.recall_state(root, *, session=None, memory_dir=None, max_bytes=None)`.
- New in `verbs`: `VerbUnknownProjectError(VerbArgsError)`, `recall_patterns`,
  `is_stale_subject`, `recall_rows_filter`, `pack_recall`, `_dense_legs` and
  `_memory_get_global`.
- New in `handoff`: `recall_state_blocks(rep) -> list[str]` and
  `fit_recall_state(rep, max_bytes) -> (text, dropped)`.
- `mcp._resolve_root(args)` raises `VerbUnknownProjectError` when it is given a `project` it
  cannot resolve.
- New CLI flags: `memory recall --pack --max-bytes --include-subjects`,
  `memory get --scope {project,global}`, `scan-prompt --max-bytes`, `curator status --max-bytes`,
  `focus context --max-bytes` and `recall-state --max-bytes`.

### What green-251b changed in the uncommitted GREEN {#green-resume}

1. **A spent budget no longer throws away the project rows (a regression).** When the deadline
   is gone before the global leg runs on `scope=both`, the verb now keeps the project rows and
   adds "global rows omitted: …". On `scope=global` it still raises busy. Before this change the
   interactive and hook CLI, now routed through the verb, exited 1. The rule is the 2026-09-15
   live incident that `test_plan2_remedy_r6.py::test_budget_spent_before_the_global_leg_keeps_the_project_rows`
   pins.
2. **Output could run one byte over N (a regression).** `click.echo` adds a newline that the
   budget never counted. The pack's trailer now carries and counts its own newline, and the CLI
   writes the verb's text byte for byte (`nl=False`). scan-prompt, curator status and focus
   context now fit their output to `cap - 1`, which leaves room for the newline they print.
3. **The hook's degrade row is typed by the raw transport cause again (21.1 R4).**
   `_degrade_or_raise` now records the first non-verb exception in the cause chain, through
   `cli._raw_transport_cause`. The no-daemon refusal keeps that chain (`from e`). Without this,
   moving the dial into the verb turned a refused connect into
   `VerbAbsentError: memory recall needs …` and a mid-answer close into `skipped_budget`. Both
   are 21.1 `error`s. The d8 no-daemon case has no transport cause and is still recorded as
   `VerbAbsentError: memory recall needs the daemon up …` (AC-4 (c)).
4. **`RMX_RECALL_REPLICA_FIRST=0` now applies inside `recall.replica_memory_recall`.** R5 says
   the switch moves with the leg. Setting it turns off every replica step, including the
   no-daemon step, as it did at HEAD.
5. **The curator's kept-file notice now names the byte cap as a reason**, beside `--limit`.
   The `README.md` hooks table was regenerated with `scripts/gen-cli-tree.py`, running under the
   clone's `PYTHONPATH`.
{#green-resume-list}

### Runs {#green-runs}

| run | result | log |
|---|---|---|
| uncommitted GREEN, full suite (green-251, 2026-11-11) | 41 failed, 4360 passed, 1 skipped | `workflow/review-output/plan25/25.1-green-full-wip.log` |
| RED files plus the touched failing files, after fixes 1-2 | 11 failed, 161 passed | `workflow/review-output/plan25/25.1-green-b-red1.log` |
| family (75 files: hooks, recall, verbs, MCP, scan, focus, handoff, save-state, budget, rerank, curator, 21.1, plan-2/3 remedies), after fixes 1-5 | 34 failed, 1251 passed, 1 skipped | `workflow/review-output/plan25/25.1-green-b-family.log` |
| measurement probe (fixture, 3 runs, plus the a12 probe) | 2 passed | `workflow/review-output/plan25/25.1-green-b-probe.log` |
| mutations (38) | 37 killed, 1 survived (equivalent, a4) | `workflow/review-output/plan25/mutations/` |
| full suite at `16ace00` | **38 failed, 4363 passed, 1 skipped** (46 min). The 38 are AC-5, the 6 in [[#lead-judge]], 4 pre-existing and 27 contract changes ([[#green-triage-table]]). No regression is left | `workflow/review-output/plan25/25.1-green-full.log` |

{#green-runs-table}

### The RED files after GREEN {#green-red-files}

Over `tests/test_task25_1_recall_budget.py` and `tests/test_mcp_memory_recall_routing.py`,
7 tests still fail:

- **AC-5, as expected.** `test_ac5_mistyped_savestate_not_named_on_the_packed_argv` fails with
  `assert 'savestate_fx01' not in ['savestate_fx01', 'fx_dup_x', …]`. It waits on task 26.4
  (lead decision a5). No 26.4 code was written.
- **Six for the lead to judge (Amendment 2).** Each one is measured below
  ([[#lead-judge]]).

### The six non-AC-5 failures, for the lead to judge {#lead-judge}

All of these numbers come from the fixture probe at `16ace00`
([[plan-25-hook-bytes#session-start]]). None of the sandbox daemons set `RMX_RERANK`, so every
leg ran with the daemon's default rerank (on), served by the daemon RPC leg (the verb's
`warnings` say "recall leg: daemon RPC (the daemon's embedder and rerank default)"). Any
exception is said in its row.

| # | test | measured | reading |
|---|---|---|---|
| 1 | `test_ac9_pack_trailer_quotes_a_multiline_query` | 12 unit rows give 12 hook lines in 1,502 of 2,000 B. Nothing is dropped, so there is no trailer. With 20 rows: 14 named, and the trailer reads `+6 more: rmx memory recall 'line one of the question line two; rm -rf $HOME \`x\` pad …' --k 24`, collapsed to one line, at most 120 chars, and `shlex`-quoted | TEST fixture: 19.1 R3(d) prints a trailer only "when any retrieved hit was not named". 12 rows fit in 2,000 B, so the `more > 0` precondition never holds |
| 2 | `test_ac4f_interactive_recall_names_the_verbs_hits_including_a_doc` | verb, `kinds=[memory, doc]`, k=40: the first doc is at rank **33** with the daemon's default rerank and rank **32** with `rerank=False`. Doc distances are 0.52-0.57 against 0.29-0.35 for memories (green-251's probe). With `kinds=[doc]` alone the verb returns the 10 docs | FIXTURE (or PRODUCT): the `kind=doc` leg works, but no fixture doc can reach the top 8 under either rerank setting. The CLI and the verb name the same 8 hits, and that is the AC-4 (f) parity |
| 3 | `test_ac6_include_subjects_brings_live_subjects_back_never_the_stale_one` (argv) | the per-prompt argv with `--include-subjects` names 12 hits and none of them is a subject. The verb with k=40 and the daemon's default rerank puts the live subjects at ranks **32-35 of 36** | **PRODUCT finding:** the cross-encoder rerank, which is the production default, buries all 4 live subjects. `--include-subjects` then never shows a subject in a k=12 recall on this fixture |
| 4 | `test_ac6_verb_hides_subjects_and_the_stale_one_even_with_the_opt_in` (verb) | with `rerank=False` the same call puts the subjects at ranks **1-4**. The stale subject is never returned under either setting | as #3. The exclusion works, but the opt-in loses to the rerank |
| 5 | `test_ac9_session_start_carries_bodies_after_all_hook_lines` | 30 named hits, 0 trailer, 8,609 of 9,000 B. The hook lines take 5,961 B and leave 2,981 B. Three bodies fit, all GLOBAL rows: `fx_dup_x` at 126 B, and `gx_mem_9` and `gx_mem_8` at 1,214 B each. The smallest project body among the 30 is `fx_mem_12` at 4,934 B | SPEC tension: R3 puts every hook line before any body, and R7 sets SessionStart to `--k 30`. The 9,000 B budget then leaves no room for a fixture project body (2.0-8.7 KB). The test counts only `BODYMARK` bodies, and only project rows carry that marker, so it sees 0 |
| 6 | `test_ac10_delivered_events_slice_the_payload_by_bytes` | the event that fails is `fx_dup_x`, the GLOBAL duplicate. Its 126 B body was appended at byte 6,031, and its `body_offset_bytes` / `body_bytes` slice that body exactly | TEST detector: the test calls a hit "bodied" only when its body contains `BODYMARK`, so a real global body is treated as having no body. Its later global-file checks are never reached |

{#lead-judge-table}

### Triage of the non-25.1 failures, by E line {#green-triage}

The baseline is `release-0.82.0-full.log` in the dev repo (bug-127/168, bug-168 ×9, bug-170,
bug-196 ×2). The list is final: it is the full-suite run at `16ace00` ([[#green-runs]]). That
run had 31 non-25.1 failures: 4 pre-existing and 27 contract changes. The 3 regressions
listed as FIXED failed only in the uncommitted run. The bug-168 rewriter ×9 failures from
0.82.0 do not occur in this clone.

| test | E line at GREEN | class |
|---|---|---|
| `test_brief_real_daemon::test_an_unknown_class_fails_loudly_through_the_daemon` | `_duckdb.IOException: … Could not set lock on file …catalog.A.duckdb` | pre-existing; same E line as 0.82.0 |
| `test_task21_1_agent_usage_report::test_ac6_frozen_fixture_prints_the_exact_counts`, `::test_ac6_cli_log_recalls_are_split_per_channel` | `agent usage · window 2026-09-23 .. ` (counts) | pre-existing (bug-196 ×2); same E line |
| `test_gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate` | `docs/INDEX.md:31: error: [dangling-doc] [[adr-0000-adr-overview]] …` | pre-existing at this branch's base: GREEN edits no file under `docs/`. Its E line differs from 0.82.0's, whose errors were in a `workflow/bullshit` report |
| `test_docs_generated::test_hooks_table_section_equals_its_render`, `::test_check_mode_reports_drift_and_apply_fixes_it` | (README hooks table drift) | regression, FIXED: table regenerated |
| `test_plan2_remedy_r6::test_budget_spent_before_the_global_leg_keeps_the_project_rows` | `Error: recall not confirmed within 0.999603s …`, exit 1 | regression, FIXED ([[#green-resume-list]] item 1) |
| `test_bigop_nonblocking::test_replica_recall_env_kill_switch`, `::test_replica_recall_none_without_shared_workers`; `test_plan2_remedy_r6::test_rerank_is_skipped_and_said_when_the_budget_is_short`, `::test_rerank_timeout_is_said_not_swallowed`; `test_plan2_remedy_r7::test_json_recall_with_no_hits_prints_an_empty_list`, `::test_replica_recall_leg_sends_a_capped_pool_to_the_reranker`; `test_rerank_cost_budget::test_the_replica_recall_leg_skips_and_says_the_numbers`, `::test_the_replica_recall_leg_reranks_when_the_budget_covers_it`; `test_rerank_warning_routes::test_replica_recall_names_the_cause` | `ImportError` / `AttributeError: module 'refmatrix.cli' has no attribute '_replica_memory_recall'` | CONTRACT CHANGE, spec `#r5` (lines 209-214): "`_replica_memory_recall` moves to `recall.replica_memory_recall(root, *, partition, …)` … reads NO CLI global". The tests should target the moved leg with an explicit `root` / `partition` over `search.cached_replica` instead of `cli._reader_store` / `cli._resolve_partition`. The moved code keeps `RERANK_MIN_S`, `RERANK_PROBE_S`, `RERANK_DOC_CHARS` (re-exported from `cli`), the cause in `rr_why`, the A/B switch and the None returns |
| `test_rerank_warning_routes::test_cli_recall_daemon_branch_prints_the_warnings` | exit 1: `memory-partition probe failed (cannot dial the daemon … socket path is too long …)` | CONTRACT CHANGE, `#r5` (lines 296-297): the CLI "computes no rows of its own". The test patches `cli._memory_daemon_call`, which is no longer the recall transport; the verb dials through `verbs._call`. The behaviour it checks (daemon `warnings` reach stderr) is kept: `_dense_legs` extends `warnings` from the RPC and the CLI prints every warning |
| `test_plan3_remedy::test_verb_dense_rows_carry_the_annotation` | `['recall leg: daemon RPC (the daemon's embedder and rerank default)'] == []` | CONTRACT CHANGE, `#r5` (lines 250-251, 278; AC-4 (g)/(i)): "the verb's `warnings` name which leg and which embedder served" |
| `test_task21_1_used_events` (9: `test_ac11a` ×2, `test_ac11b` ×2, `test_ac11c`, `test_ac11d`, `test_ac11e`, `test_ac11f`, `test_r12`) and `test_task21_1_emitters::test_ac8_prompt_recall_retrieves_10_delivers_3_in_intuition`, `::test_ac10_global_hit_goes_to_the_global_file_project_hit_to_the_project_file` | `json.decoder.JSONDecodeError: Expecting value` on `'# rmx recall · prompt_recall · …'` | CONTRACT CHANGE, `#r7` (line 302): "the generator emits `--pack` in place of `--json` on the three recall commands". Their helpers `json.loads` the generated hook's stdout |
| `test_task21_1_recall_skip::test_ac2b_busy_daemon_skip_writes_one_skipped_budget_recall_row`, `::test_ac2b_non_budget_refused_connect_is_error`, `::test_ac2b_mid_answer_close_is_error_not_traceback` | `assert _stdout_is_empty_json('')` (the row's outcome and error assertions now pass) | CONTRACT CHANGE, `#r5` d8 (line 281: "prints NOTHING to stdout") and `#r7`. A `--pack` hook that degrades prints nothing, never `[]` |
| `test_task3_7_remedy_r1::test_cli_drain_that_printed_more_leaves_the_rest_in_the_spool`, `test_task3_7_remedy_r2_meh::test_drain_behind_an_oversized_head_file_reports_what_it_kept_on_stderr` | `'+5 more' in …`, but the line reads `+8 more path(s) not shown within 500 B` | CONTRACT CHANGE, `#r0b` (lines 152-155): "`rmx curator status` … fits its lines through `fit_blocks` to `budget("curator_status")`" (500 B). Drain safety holds: only the paths shown are drained, and the kept-file notice is still on stderr |

{#green-triage-table}

### Mutations {#green-mutations}

The method follows `#mutations-method`. The GREEN was committed first. Each mutation had a
single edit and its own log. The touched files were restored by `git checkout --` in a separate
subprocess, which also verified `git diff --quiet`, and `__pycache__` was cleared after every
mutation. The stated fix lines were grepped after the batch. The runner is a scratch script,
not committed. The logs are in `workflow/review-output/plan25/mutations/25.1-mut-<id>.log`.

| mutation (AC) | status | killed by (E line) |
|---|---|---|
| budget applied before the merge: the pack is given the project rows only (AC-4 a) | KILLED | `test_ac1_ac4a_per_prompt_argv…`: exit 1, because `_echo_pack` refuses spans for rows the payload does not carry |
| chars instead of bytes (AC-2) | KILLED | `test_ac9_fit_blocks…[2000]`: `3532 <= 2000` |
| bodies before hook lines (AC-9) | KILLED | `body of u_mem_00 precedes a hook line` |
| a cut body (AC-9) | KILLED | `body of u_mem_02 is cut` |
| missing trailer count (AC-9) | KILLED | `(15 + 0) == 20` |
| spans in characters (AC-10) | KILLED | `test_ac10_pack_spans_are_utf8_byte_ranges`: the hook-line slice is wrong |
| generator keeps `--json` (AC-13) | KILLED | `test_ac13`: `… --json --timeout 5` |
| `${RMX_HOOK_BUDGET_BYTES}` interpolated into the argv (AC-8, AC-13) | KILLED | `test_ac13`: the `$` is in the tail |
| `subject` exclusion dropped (AC-6) | KILLED | `AC-6 (replica leg): subjects named: ['subject_quasar_ledger_0', …]` |
| stale subject visible (AC-6) | KILLED | `test_ac6_session_start…`: `--include-subjects` names `subject_quasar_ledger_4` |
| a body counted as a second named hit (AC-9) | KILLED | `pk.named == list(p.named)` fails |
| `memory get --scope global` falls back to the project row (AC-11) | KILLED | `fx_dup_x id=205 mtype=project` |
| a `delivered` event for a trimmed hit (AC-10) | KILLED, but **not decidable** | same E line as GREEN (`body_offset_bytes` 6,031 on `fx_dup_x`). The fixture's SessionStart names 30 of 30, so no hit is trimmed |
| the packer calls a telemetry writer (AC-10), v1 | ineffective | the span records carry no `partition`, so `emit_recall_events` dropped them and the E line is unchanged |
| the packer calls a telemetry writer (AC-10), v2 (emits `recall_item` rows) | KILLED | `len({query_id, 'packer'}) == 1` fails: 2 query_ids |
| the CLI renders its own text, not the verb's (AC-7) | KILLED | `test_ac7` byte-for-byte |
| the verb skips the replica leg (AC-4 b) | KILLED | `VerbAbsentError: daemon not running for …/fxb/.refmatrix` |
| scan-prompt not fitted (AC-12) | KILLED | `printed 6660 B > budget('scan_prompt') = 4500 B` |
| curator status not fitted (AC-12) | KILLED | `printed 1885 B > … = 500 B` |
| the moved replica leg reads the CWD store (AC-4 e) | KILLED | `test_ac4e_mcp_cross_project…`: `set()` |
| the interactive path computes its own rows: the CLI passes `rerank=False` (AC-4 f) | KILLED | first assertion: CLI `[…, fx_mem_06, fx_mem_01, …]` != verb `[…, fx_mem_00, fx_mem_10, …]`. This E line differs from GREEN's doc-leg failure |
| the no-daemon hook exits 1 (AC-4 c) | KILLED | `AC-4 (c): exit 1` |
| a global hit's `delivered` event in the project file (AC-10) | KILLED, but **not decidable** | same E line as GREEN. AC-10 fails on `fx_dup_x`'s body before it reaches its scope check |
| hook mode embeds through `shared_embedder` (AC-4 c) | KILLED | `stdout not empty: b'# rmx recall · prompt_recall · 8 hits …'` |
| interactive / MCP kept hub-only (AC-4 g) | KILLED | `AC-4 (g): exit 1: … needs the daemon up …` |
| `shared_embedder` tried before the daemon RPC (AC-4 i) | KILLED, **indirectly** | there is no AC-4 (i) test (red-251 a13). Over both RED files, two tests fail that pass at GREEN: `test_ac4d_rows_parity…[no-worker]` and `test_ac7_cli_prints_the_verbs_text…`. Those parity tests see the in-process verb answer from a private-worker replica while the argv answers from the daemon |
| `embedder_policy` made a named verb parameter (AC-7) | KILLED | `'embedder_policy' not in {…schema…}` |
| the replica leg binds the project partition (AC-4 h) | KILLED | `replica leg [] != rpc leg ['fx_mem_26', …]` |
| the pack looks hooks up by id only (AC-9, r3 #m2) | **SURVIVED** | equivalent through `load_hooks`, which aliases path keys to ids (lead a4). A spec finding |
| focus context not fitted (AC-12b) | KILLED | `printed 3297 B > … = 1500 B` |
| one `NON_RMX_RESERVE_BYTES` for both events (AC-12b) | KILLED | `{'SessionStart': 512, 'UserPromptSubmit': 512}` |
| HEAD's silent `project` fallback restored (R10) | KILLED | `R10: project='charlie' names no store, yet _resolve_root returned …/alpha/.refmatrix` |
| AC-15: entry chained into another command (a) | KILLED | `test_ac15a` |
| AC-15: matcher drops `compact` (a) | KILLED | `test_ac15a` |
| AC-15: output not fitted (b, c) | KILLED | `test_ac15c`: 4,507 B > 700 (b passes: the full report fits 9,000) |
| AC-15: no `--max-bytes` in the generated argv (a, b, c) | KILLED | `test_ac15a` |
| AC-15: a traceback instead of one `Error:` line (e) | KILLED | `test_ac15e`: `Traceback` in stderr |
| AC-15: `max_bytes` not on the verb (f) | KILLED | `['memory_dir', 'project', 'root', 'session']` |

{#green-mutations-table}

### a12: a bare `rmx recall-state` on an unreadable memdir {#green-a12}

This was measured on a throwaway sandbox store, with no daemon and the memdir at mode 0.
`rmx recall-state`, `rmx recall-state --json` and `rmx recall-state --max-bytes 9000` each exit 1
with exactly ONE line on stderr: `Error: recall-state: the memory dir … is not readable`. None of
them prints a traceback, and stdout is 0 B. {#green-a12-result}

### Flags for the lead and the test engineer {#green-flags}

- **F1. `#r10-bus` is neither built nor tested.** It is the user's 2026-11-10 decision to split
  `rmx_bus_pub`'s `project` field into `about`. No RED test covers it, so it needs tests first.
  The R10 sweep already refuses an unknown `project=` on `rmx_bus_pub`.
- **F2. R11's last bullet is neither built nor tested.** It asks for recall-state to be counted
  as producer `recall_state` in `rmx telemetry --context`. R11 (d)'s "counted" is met as "said"
  (red-251 a12): the daemon block reads `daemon not running`.
- **F3. AC-4 (i) has no test.** Its mutation is killed only through AC-4 (d) and AC-7 parity.
  The "no `modelsrv` child, no `sentence_transformers`" assertions that the spec names are
  unwritten.
- **F4. Two AC-14 mutations are undecidable while AC-10 is RED** ([[#lead-judge-table]] #6):
  "a delivered event for a trimmed hit" and "a global hit's delivered event in the project
  file". The fixture's SessionStart pack also trims no hit, so the trimmed-hit leg needs a
  payload with a non-zero trailer.
- **F5. The hooks-by-id-only mutation survives** as an equivalent (lead a4: spec finding).
- **F6. The `recall leg: …` line is printed on every recall.** The spec wants it in the
  `warnings`. The CLI prints every warning to stderr as `# rmx: warning: …`, so every recall,
  hook included, now prints one informational line under a "warning" prefix. Hook stderr on
  exit 0 is not injected. The lead should decide whether the CLI should print it without the
  prefix.
- **F7. The mock-registry row for the routing file is not graduated.** `#mocks-registry` said
  that row (the `daemon.call` / `discover_roots` stubs) would graduate at GREEN. Graduating it
  means editing tests, which is test-engineer work, so it was not done here.
- **F8. Registry.** bug-164 and bug-181 close at merge (spec `#files-to-modify`), so the lead
  writes those rows. Fixes 1-3 in [[#green-resume-list]] were regressions inside the uncommitted
  GREEN and never reached `master`.
- **F9. 26.4 overlap.** No 26.4 code is here. AC-5 turns green only after the bridge types
  `savestate_*` as `session/recall-state`.
{#green-flags-list}

## RED rev 7 (red-251b, 2026-11-13) {#red-rev7}

rel: implements -> [[task-25.1-recall-hook-byte-budget#rev-round-7]]
rel: amends -> [[#red]]
rel: depends-on -> [[agent-brief-red-251b]]

`red-251b` applied the rev-7 decisions on the test side at `d68b71c` (GREEN `16ace00`). Tests
only: no `src/` change. Commit `1f9459a` holds the tests, the mock-registry update and the run
logs; this section and the mutation logs are the following docs commit. {#red-rev7-lead}

### Runs {#red-rev7-runs}

| run (at `d68b71c` src) | result | log |
|---|---|---|
| baseline: the two RED files before any edit | 7 failed, 119 passed (the GREEN's AC-5 + six) | `workflow/review-output/plan25/25.1-redb-baseline.log` |
| the 11 contract-updated files | 176 passed | `workflow/review-output/plan25/25.1-redb-contract1.log` |
| measurement probe (fixture; a scratch test, not committed) | 1 passed; the numbers quoted below | `workflow/review-output/plan25/25.1-redb-probe.log` |
| graduated routing file (F7) | 8 passed | `workflow/review-output/plan25/25.1-redb-routing.log` |
| every touched file (13) | **10 failed, 300 passed**: AC-5 + the new REDs, nothing else | `workflow/review-output/plan25/25.1-redb-touched-head.log` |
| mutations (8) | 8 killed | `workflow/review-output/plan25/mutations/25.1-redb-mut-*.log` |

{#red-rev7-runs-table}

### Change map {#red-rev7-map}

| rev-7 row | change (test side) | at HEAD |
|---|---|---|
| contract ×27 | `test_bigop_nonblocking` ×2, `test_plan2_remedy_r6` ×2, `test_plan2_remedy_r7` ×2, `test_rerank_cost_budget` ×2, `test_rerank_warning_routes` ×1: the replica leg is `recall.replica_memory_recall(root, partition=…)`; the store seam moved from `cli._reader_store` / `_resolve_partition` to `search.cached_replica`, and the leg embeds the query before its lock (a dim-4 stand-in). The rerank-budget, capped-pool, cause-naming and kill-switch assertions are unchanged | pass |
| contract | `test_rerank_warning_routes::test_cli_recall_daemon_branch_prints_the_warnings`: the verb dials (`verbs._call`), partition pinned; still asserts the daemon's warning reaches stderr, plus exit 0 and exactly one `memory_recall` | pass |
| contract | `test_plan2_remedy_r7::test_json_recall_with_no_hits_prints_an_empty_list`: the canned leg is `recall.replica_memory_recall` serving zero hits | pass |
| contract | `test_plan3_remedy::test_verb_dense_rows_carry_the_annotation`: `warnings == [the daemon-leg line]` (no degrade warning; the leg named, R5) | pass |
| contract ×11 | `test_task21_1_used_events` ×9, `test_task21_1_emitters` ×2: the generated hook prints `--pack`; named hits are read by ONE parser, `tests/task21_1_support.pack_rows` (scope from the fetch pointer); `task25_1_support.HOOK_LINE` aliases it | pass |
| contract ×3 | `test_task21_1_recall_skip`: a degraded `--pack` hook prints nothing (d8): `stdout == ""` (stricter than `[]`) | pass |
| contract ×2 | `test_task3_7_remedy_r1` / `_r2_meh`: the curator line is capped at 500 B; `+N more` with N ≥ 5 and shown + N = 15; the spool keeps what was not shown; the r2 control adds `--max-bytes 100000` so "everything shown" is reachable | pass |
| J1 | trailer test: 20 unit rows (measured at GREEN: 14 named, 6 trimmed) | pass |
| J2 | AC-4 (f): CLI `--json`, table and verb name the same hits for `-K memory,doc` AND `-K doc`; `-K doc` returns only `kind=doc` rows (the fixture's `quasar_design_*.md`). No rank claim | pass |
| J3/J4 | AC-6 argv + verb: still "live subjects named, stale never"; added: the opt-in's non-subject rows are a prefix of the default (reranked) run's; verb only: a pre-check that the rerank reorders the fixture (`rerank=False` differs), and each subject keeps its `rerank=False` index | RED (below) |
| J5 | AC-13 expects SessionStart `--k 12`; AC-9 counts named + trailer = 12 | RED (below) |
| J5 / J6 | AC-9 counts bodies as `## <name>` blocks after the hook lines, any scope (`Pack.body_blocks`), not `BODYMARK` | see [[#red-rev7-ambiguities]] a-j5 |
| J6 | AC-10: a body is identified by its span (`body_offset_bytes` / `body_bytes`): the slice sits right after `## <name>\n`, ends at a block boundary, names its row (a global body equals the global row's content), ≥ 3 `—` before it; null fields require no `## <name>` block | pass |
| F4 | new `test_ac10_trimmed_hits_get_no_delivered_event_and_global_hits_stay_global`: the SessionStart argv plus `--k 12 --max-bytes 2000` (measured: 9 of 12 named, `+3 more`, four global hits named, 1,875 B) | pass (guard) |
| F3 | new `test_ac4i_daemon_up_hub_down_daemon_serves_and_nothing_spawns`: CLI `--json` and MCP run in a child under an audit hook; no `embed_worker` spawn, no `sentence_transformers` / `torch` import; MCP `warnings` name the daemon leg | pass (guard, as the spec says) |
| F6 | new `test_f6_recall_leg_line_only_under_verbose_never_a_warning` | RED (below) |
| F2 | new `test_ac15g_recall_state_is_counted_as_producer_recall_state` | RED (below) |
| F1 | four new `test_r10_bus_pub_*` tests over a real bus (`_MiniHub` from `test_verbs_migrated`) | 3 RED, 1 guard (below) |
| F7 | `tests/test_mcp_memory_recall_routing.py`: the fake `daemon.call` and the `discover_roots` / `store_name` stubs are gone. Two real daemon-served stores (legacy `memory-<p>` and post-merge), embedded by the real model; dense-not-lexical proven by behaviour (a query that is a substring of no memory returns rows); the three `_resolve_root` tests use a real registry under a tmp `RMX_HOME`. Registry row marked GRADUATED, graduation-log entry added; the rows naming `cli._replica_memory_recall` / `cli._reader_store` now name the moved seams; a row added for `test_rerank_warning_routes` (its patches were unregistered) | pass |

{#red-rev7-map-table}

### The RED list for the implementer {#red-rev7-red-list}

E lines from `25.1-redb-touched-head.log` (src = `d68b71c`):

| test (`tests/test_task25_1_recall_budget.py`) | rev-7 row | E line at HEAD |
|---|---|---|
| `test_ac6_include_subjects_brings_live_subjects_back_never_the_stale_one` | J3 (#j3-subjects-exempt) | `AssertionError: ['savestate_fx01', 'fx_dup_x', 'fx_mem_00', 'gx_mem_9', …]`: no live subject named |
| `test_ac6_verb_hides_subjects_and_the_stale_one_even_with_the_opt_in` | J4 | `AssertionError: ['savestate_fx01', 'fx_mem_00', 'fx_mem_10', 'fx_mem_20', …]`: no live subject |
| `test_ac9_session_start_carries_bodies_after_all_hook_lines` | J5 | `AssertionError: (30, 0)` / `assert (30 + 0) == 12` |
| `test_ac13_generator_emits_pack_raised_k_and_no_variable` | J5 | `('SessionStart', 'rmx memory recall --session-start --k 30 --scope both --pack --timeout 10')` |
| `test_f6_recall_leg_line_only_under_verbose_never_a_warning` | F6 (#f6-leg-line) | `F6: a normal interactive recall printed the leg line: "# rmx: warning: recall leg: daemon RPC (the daemon's embedder and rerank default)\n"` |
| `test_ac15g_recall_state_is_counted_as_producer_recall_state` | F2 (R11) | `F2: no producer view in telemetry --context: ['by_command', 'counted', 'hook_budget', 'total_bytes', 'total_tokens_est', 'uncounted']` |
| `test_r10_bus_pub_about_tags_the_message_and_is_never_a_lookup` | F1 (#r10-bus) | `Failed: #r10-bus: verbs.bus_pub has no `about` parameter (… unexpected keyword argument 'about')` |
| `test_r10_bus_pub_project_is_the_transport_target_only` | F1 | `("#r10-bus: the transport target leaked into the message's project tag", {… 'from': 'bravo' …})` / `assert 'bravo' is None` |
| `test_r10_bus_pub_cli_about_option` | F1 | `Error: No such option: --about` (exit 2) |
| `test_ac5_mistyped_savestate_not_named_on_the_packed_argv` | a5 (waits on 26.4) | `assert 'savestate_fx01' not in ['savestate_fx01', 'fx_dup_x', …]` |

Guards that pass at HEAD: `test_r10_bus_pub_proj_channel_still_tags_its_project` (F1), the
unknown-`project` leg of `test_r10_bus_pub_project_is_the_transport_target_only` (R10, built),
F3 and F4. For the GREEN: SessionStart `--k 12` changes the generated config, so
`.claude/settings.json` / `.claude/rmx-hooks.json` and the README hooks table must be
regenerated (`test_repo_hooks_in_sync`, `test_docs_generated`); the bus verb's `about` needs its
CLI twin for verb parity. {#red-rev7-red-list-notes}

### Mutations on the new guards {#red-rev7-mutations}

Tests committed first (`1f9459a`); one mutation at a time by a scratch applier; each restored by
`git checkout -- <file>` in its own command; `__pycache__` cleared before each; every fix line
grepped back after the batch; `src/` clean at the end.

| mutation | guard | result (E line) |
|---|---|---|
| m1 `shared_embedder` tried before the daemon (`_dense_legs` step 1 takes the caller's policy) | F3 AC-4 (i) | KILLED: `the caller spawned a model worker: [[…/python, '-m', 'refmatrix.embed_worker', '--role', 'embed']]` |
| m2 a `delivered` event for every trimmed hit (`_echo_pack` delivers all rows) | F4 | KILLED by F4 only: `delivered events != named hits (a trimmed hit must have none)`; AC-10's default payload trims nothing and passes, which is why F4 exists |
| m3 a global hit's `delivered` event in the project file (`emit_recall_events`) | F4 + AC-10 | KILLED by both: `([], ['fx_dup_x', 'gx_mem_9', 'gx_mem_8', 'gx_mem_7'])` |
| m4 "subjects exempt" done by turning the rerank off under `include_subjects` | J3/J4 | KILLED by both: the subjects come back, then `J3: the opt-in changed the order of the non-subject rows` / `J4: non-subject rows not reranked as without the opt-in` |
| m5 the `proj:X:` channel default dropped | F1 guard | KILLED: `assert (None == 'X')` |
| m6 body offset never recorded (`body_offset_bytes = None`) | J6 AC-10 | KILLED: `assert 126 is None` (body_bytes without an offset) |
| m6b body offset and size both null | J6 AC-10 | KILLED: `AC-10: fx_dup_x has a body block in the payload but null body fields` |
| m7 the verb binds the project partition, not `memory_partition` | F7 routing | KILLED: `dense recall on the legacy memory partition returned nothing` and the recent leg `set() == {…}` |

{#red-rev7-mutations-table}

### Ambiguities and findings {#red-rev7-ambiguities}

- **a-j5 AC-9 at `--k 12` carries only GLOBAL bodies.** Measured on the fixture (SessionStart argv
  with `--k 12` appended, `25.1-redb-probe.log`): 12 named, 8,710 B, 6 bodies, all global
  (`fx_dup_x`, `gx_mem_9` … `gx_mem_5`), 0 project bodies. The pack takes bodies greedily in rank
  order; the newest project memories are the largest (≥ 4.9 KB), and the 1.2 KB global bodies
  fill the room first. The RED's `BODYMARK` counter therefore stays at 0 after k = 12, contrary to
  the lead's "it should pass once k = 12 lands". AC-9 says "≥ 2 bodied hits", and J6 rules that a
  body is not identified by `BODYMARK`, so AC-9 now counts `## <name>` blocks of any scope. At HEAD
  it already sees 3 global bodies; it is RED on the k count only. If the lead wants PROJECT bodies
  on SessionStart, that needs a separate decision (body order, or fixture sizes). {#a-j5}
- **a-f2 the shape of "counted as producer `recall_state`".** The spec names the producer, not a
  shape. The hook run is already in `by_command` as `recall-state` (n 1, 4,946 B at HEAD). The test
  pins `by_producer.recall_state = {n, total_bytes, max_bytes, budget}`, keyed by
  `CHANNEL_BUDGET_BYTES` names, counting only `source == "hook"` cli.log rows, and the text form
  naming `recall_state`. The lead may narrow or widen this. {#a-f2}
- **a-f3 AC-4 (i) is a guard, not RED.** The brief lists F3 among the new REDs; the spec says "Not
  RED at HEAD … a guard, killed by the mutation". It passes at HEAD and m1 kills it. The spawn is
  observed by an audit hook (`subprocess.Popen` argv), not inferred from a 5 s overrun (red-251
  a7). The child sets `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`, as the re-exec'd `rmx` has it,
  so `cli_entry`'s macOS re-exec does not escape the hook. {#a-f3}
- **a-f6 the flag.** The test uses `memory recall --verbose` (the spec's word); no `-v` is asserted.
  The per-prompt hook argv must print no leg line. `--verbose` must not change the rows. {#a-f6}
- **a-j3 the argv-level rerank guard is weaker than the verb's.** The argv compares only PROJECT
  non-subject hits (global rows are merged by score); under m4 only 2 such rows remained beside
  the subjects and the globals. The verb test, with its pre-check and the subject-rank check, is
  the main guard. {#a-j3}
- **a-j4 "keep their pre-rerank rank"** is pinned as: each subject's index in the opt-in result
  equals its index in the `include_subjects=True, rerank=False` result (ranks 0-3 on the
  fixture). If the implementer places subjects another way, the lead should confirm this
  reading. {#a-j4}
- **a-f1 a known `project=` on `rmx_bus_pub`.** The test asserts the row's `from` is the named
  store and its `project` tag is None on a `global:` channel (the transport target never becomes
  the tag); the verb has `about` and no own `project` parameter. {#a-f1}
- **a-f4 F4's payload carries no body** (2,000 B fits only hook lines). Body spans stay AC-10's
  default-payload job. {#a-f4}
- **a-ac5** unchanged: still RED until 26.4 merges. At HEAD the SessionStart pack also names
  `savestate_fx01` first. {#a-ac5}

{#red-rev7-ambiguities-list}

## GREEN rev 7 (green-251c, 2026-11-13) {#green-rev7}

rel: implements -> [[task-25.1-recall-hook-byte-budget#rev-round-7]]
rel: depends-on -> [[#red-rev7]]
rel: amends -> [[#green]]

The rev-7 REDs of [[#red-rev7-red-list]] made GREEN with `src/` code only; no test was edited.
Commit `e5a516c` holds the code, the re-rendered `.claude/settings.json` and the regenerated
README hooks table; this section and the run logs are the following docs commit. No 26.4 code
was written here (lead a5). During this GREEN the lead merged dev master with 26.4 into the
branch (`69da299`), so the full suite was run on that merge; AC-5 passes there. {#green-rev7-lead}

### What changed, per rev-7 row {#green-rev7-map}

| row | change | where |
|---|---|---|
| J3/J4 (#j3-subjects-exempt) | With `include_subjects`, when the dense leg's answer was reranked (a hit carries `reranked`), a second pass runs with `rerank=False`. `place_rerank_exempt(pre, ranked, k)` keeps each subject at its index in the unreranked answer (a-j4) and fills every other slot with the reranked answer's non-subject rows -- the rows the call without the opt-in returns, so non-subjects rerank as before. Subject rows carry `rerank_exempt: true` (their `score` is not a cross-encoder logit). Rows are fetched once across both passes. No rerank ran: one pass. The over-fetch pool is `3k` under the opt-in too, so the reranked pass fetches the pool the default call fetches | `verbs._memory_recall_rows`, `verbs._dense_rows`, `verbs._rank_order`, `verbs.place_rerank_exempt`, `verbs.RERANK_EXEMPT_MTYPES` |
| J5 (#j5-session-start-k) | SessionStart `rmx memory recall --session-start --k 12 …`; PreCompact stays 30 | `hooks._claude_hook_block` |
| J5 generated files | `.claude/settings.json`: re-rendered with the clone's generator (`hooks.render_managed`) for the owner root it records (`hooks.installed_root` = the dev checkout); exactly one entry differed, and after the write the managed multiset equals the render. README hooks table: `scripts/gen-cli-tree.py` under the clone's `PYTHONPATH`. `.claude/rmx-hooks.json`: unchanged (it records version and flags; no bump, same flags). `rmx install-hooks` was not run | `.claude/settings.json`, `README.md` |
| F6 (#f6-leg-line) | `verbs.RECALL_LEG_PREFIX` / `is_recall_leg_line`. The verb keeps the `recall leg: …` line in `warnings`. `memory recall --verbose` (new) prints it as `# rmx: recall leg: …`; without `--verbose` it is not printed; every other warning prints as before (`# rmx: warning: …`) | `cli.memory_recall`, `cli._memory_recall_impl._say_verb_warnings` |
| F6, the no-daemon leg | The step-3 line (no daemon; this process embedded the query) is a DEGRADE, so it is worded as a real warning: `no daemon: recall served from the replica snapshot (embedder: …)`. See [[#green-rev7-flags]] g7-1 | `verbs._dense_legs` |
| F2 (R11) | `summarize_context` gains `by_producer`: every `hook_budget.CHANNEL_BUDGET_BYTES` channel, over `source == "hook"` cli.log rows, as `{n, total_bytes, max_bytes, budget, over_budget}`; `telemetry.hook_producer(command, argv)` maps a row to its channel (memory recall by `--session-start` / `--stdin-json` / `--recent`, `focus hook --event input`, `recall-state`, `scan-prompt`, `curator status`, `focus context`). The text form prints a producer table. A non-integer `RMX_HOOK_BUDGET_BYTES` is a `ClickException` naming it | `telemetry.hook_producer`, `telemetry.summarize_context`, `cli.telemetry` |
| F1 (#r10-bus) | `verbs.bus_pub(root, channel, body, *, type, sender, about, reply_to)`: `about` is the message tag (hub row `project`; default the `X` of `proj:X:…`); no `project` parameter, so MCP's `project` is the transport target only. `rmx bus pub --about` | `verbs.bus_pub`, `cli.bus_pub` |

{#green-rev7-map-table}

### Signatures {#green-rev7-signatures}

- `verbs.place_rerank_exempt(pre: list[dict], ranked: list[dict], k: int) -> list[dict]`;
  `verbs.RERANK_EXEMPT_MTYPES = frozenset({"subject"})`; private `verbs._dense_rows(hits, fetch,
  patterns, k, fetched) -> list[dict]`, `verbs._rank_order(hits) -> list[dict]`,
  `verbs._hit_id(h) -> int | None`.
- `verbs.RECALL_LEG_PREFIX = "recall leg: "`; `verbs.is_recall_leg_line(w: str) -> bool`.
- `verbs.bus_pub(root, channel, body, *, type="announce", sender=None, about=None,
  reply_to=None) -> dict` (was `project=None`).
- `telemetry.hook_producer(command: str, argv: list) -> str | None`;
  `telemetry.summarize_context(...)` returns `by_producer: {channel: {n, total_bytes, max_bytes,
  budget, over_budget}}` beside `by_command`.
- CLI: `rmx memory recall --verbose`; `rmx bus pub --about TEXT`.

### Runs {#green-rev7-runs}

| run (src = `e5a516c` unless said) | result | log |
|---|---|---|
| the 10 rev-7 REDs + the F1 guard, before the no-daemon rewording | 10 passed | `workflow/review-output/plan25/25.1-green7-reds1.log` |
| the 13 touched files, before the no-daemon rewording | 2 failed, 308 passed: AC-5 and `test_ac4g_interactive_no_daemon_no_hub_uses_shared_embedder` (`AC-4 (g): no warning names the private worker`; F6 had silenced the no-daemon leg line too, see g7-1) | `workflow/review-output/plan25/25.1-green7-touched.log` |
| ac4g ×2, F6, AC-4 (i), `test_verb_parity`, `test_docs_generated`, `test_repo_hooks_in_sync`, `test_mcp_bus_passthrough`, `test_context_cost`, after the rewording | 203 passed, 1 skipped (`test_installed_hooks_match_generated`: the clone's settings.json belongs to the dev checkout; SkipGate names it, as at GREEN) | `workflow/review-output/plan25/25.1-green7-reds2.log` |
| family at `e5a516c`: 96 files (hooks, recall, verbs, MCP, scan, focus, handoff, save-state, budget, rerank, curator, bus, telemetry, context cost, docs-generated, 21.1, 3.7, plan-2/3 remedies, bigop, 25.1); includes all 13 touched files | **3 failed, 1601 passed, 1 skipped**: AC-5, and `test_task21_1_agent_usage_report` ×2 with the same E lines as `release-0.82.0-full.log` and `25.1-green-full.log` (pre-existing) | `workflow/review-output/plan25/25.1-green7-family.log` |
| mutations (13), at `e5a516c` | 12 killed, 1 survived (j4) | `workflow/review-output/plan25/mutations/25.1-green7-mut-*.log` |
| full suite at `e5a516c`, first attempt | DISCARDED: the dev-master merge `69da299` (26.4) landed in the clone mid-run, so the run mixed pre- and post-merge code | `workflow/review-output/plan25/25.1-green7-full-mixed.log` |
| **full suite at `69da299`** (this GREEN + the 26.4 merge) | **6 failed, 4426 passed, 1 skipped** (49:51). Four pre-existing, same E lines as `release-0.82.0-full.log` and `25.1-green-full.log`: `test_brief_real_daemon::test_an_unknown_class_fails_loudly_through_the_daemon` (DuckDB `Could not set lock`), `test_gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate` (the same 21 dangling-doc errors as GREEN), `test_task21_1_agent_usage_report` ×2 (`chan('prompt_recall', 5)` empty). Two are 26.4 × 25.1 merge interactions, not this GREEN's code (g7-7, g7-8). **AC-5 passes** (26.4 types `savestate_fx01` `session/recall-state`). No other failure; against `25.1-green-full.log` (38 failed) every 25.1 contract failure is gone | `workflow/review-output/plan25/25.1-green7-full.log` |

{#green-rev7-runs-table}

### Mutations {#green-rev7-mutations}

Code committed first (`e5a516c`); one mutation at a time by a scratch applier (exact-string
replace, count asserted 1); `__pycache__` cleared before each run; each restored by
`git checkout -- <file>` in its own command, `git diff --quiet -- src` checked; every fix line
grepped back after the batch (one hit each; the `# rmx: {w}` echo has two, the leg line and its
pre-existing sibling); `src/` clean at the end.

| mutation | row | result (E line) |
|---|---|---|
| j1 rerank turned off under `include_subjects` (red-251b's m4) | J3/J4 | KILLED by both: `J3: the opt-in changed the order of the non-subject rows` (`['savestate_fx01', 'fx_mem_06']` vs `[…, 'fx_mem_00', …]`); `J4: non-subject rows not reranked as without the opt-in` |
| j2 subjects appended after the reranked rows | J3/J4 | KILLED by both: no live subject named (the reranked rows fill k) |
| j3 the exemption never runs | J3/J4 | KILLED by both: no live subject named |
| j4 the reranked pass keeps the subjects (no `subject` filter) | J3/J4 | **SURVIVED**: on the fixture the cross-encoder ranks every subject below the top 3k, so the reranked rows hold none. Not equivalent: a subject the rerank lifts into the top k would appear twice. Finding g7-2 |
| j5 subjects at their RERANKED rank (no placement) | J3/J4 | KILLED by both: no live subject named |
| f1 the leg line printed as a warning again | F6 | KILLED: `F6: a normal interactive recall printed the leg line: "# rmx: warning: recall leg: daemon RPC …"` |
| f2 `--verbose` prints nothing | F6 | KILLED: `F6: --verbose did not say which leg served: ''` |
| f3 `--verbose` prints the leg line under `warning:` | F6 | KILLED: `assert not ["# rmx: warning: recall leg: daemon RPC …"]` |
| f4 the leg line dropped from the verb's `warnings` | F6 / R5 | KILLED by three: F6 `--verbose did not say which leg served`; AC-4 (i) `[]`; `test_plan3_remedy::test_verb_dense_rows_carry_the_annotation` `[]` |
| f5 the no-daemon line back under the `recall leg:` prefix | F6 / AC-4 (g) | KILLED: `AC-4 (g): no warning names the private worker: # rmx: warning: rerank skipped: …` (the MCP ac4g passes: the verb's warnings still name it) |
| b1 `about` ignored (row `project` None) -- the spec's #r10-bus mutation | F1 | KILLED by three: verb + MCP `None == 'Y'`, CLI `--about` `None == 'Y'`, the `proj:X:` guard `None == 'X'` |
| t1 interactive `recall-state` runs counted as the producer | F2 | KILLED: `({… 'n': 2 …}, 1)` / `assert 2 == 1` |
| t2 `recall-state` mapped to no producer | F2 | KILLED: `({… 'n': 0 …}, 1)` / `assert 0 == 1` |

{#green-rev7-mutations-table}

### Flags for the lead and the test engineer {#green-rev7-flags}

- **g7-1 the no-daemon leg is a warning, not a leg line (an F6 reading the lead should
  confirm).** F6 silences `recall leg: …` on a normal run; AC-4 (g)'s CLI test still requires the
  interactive no-daemon recall to name the private worker on stderr, and it failed once F6
  landed. R5 says the warnings name the leg that served "and any degraded leg"; a recall with no
  daemon, embedded by a private worker or an in-process model (6-33 s), is degraded. So step 3
  of `_dense_legs` now says `no daemon: recall served from the replica snapshot (embedder: …)`,
  printed as `# rmx: warning: …` on every run; the two healthy legs (hub-worker replica, daemon
  RPC) keep the `recall leg:` prefix and print only under `--verbose`. The MCP AC-4 (g) test
  passes either way. Mutation f5 pins it. {#g7-1}
- **g7-2 mutation j4 survives.** If the reranked pass did not filter subjects, a subject the
  cross-encoder lifted into the top k would be named twice (its exempt slot and its reranked
  slot). The fixture's rerank buries every subject, so no test sees it. For the test engineer: a
  no-duplicate-names assertion on the opt-in, or a fixture subject whose label matches the
  query. {#g7-2}
- **g7-3 the opt-in's cost.** With `include_subjects` and a rerank that ran, the dense leg runs
  twice (a second embed + ANN, `rerank=False`; no second rerank); rows are fetched once across
  both passes. The generated hooks never pass `--include-subjects`, so no hook pays it. No rerank
  ran (`RMX_RERANK=0`, `--no-rerank`, a skipped rerank): one pass. {#g7-3}
- **g7-4 `by_producer` is a superset of a-f2's shape.** Every budget channel is listed (a
  silent producer has `n` 0), and each entry adds `over_budget` (runs above `budget`). The test
  pins `n`, `total_bytes`, `max_bytes`, `budget`. {#g7-4}
- **g7-5 a subject row carries `rerank_exempt: true`** under the opt-in when a rerank ran: its
  `score` is the unreranked one, not a cross-encoder logit, so it is not comparable with its
  neighbours'. {#g7-5}
- **g7-6 rev 8 landed on the branch during this GREEN** (`cec8afe`, `4f95c23`: spec only, R12-R14,
  AC-16-AC-18). Not in this dispatch; nothing of it is built. {#g7-6}
- **g7-7 AC-4 (f) fails after the 26.4 merge (test-side parity call).** 26.4 stores
  `savestate_fx01` as `session/recall-state`. The interactive CLI passes `include_session=True`
  (the operator affordance pinned by `test_plan3_remedy::test_cli_recent_passes_include_session_
  explicitly` and `test_verb_parity`'s `rmx_memory_recall` wiring), while the test calls the
  verb with its default (`session/*` hidden). So the CLI names `savestate_fx01` first and the
  verb does not: `('memory,doc', ['savestate_fx01', 'fx_mem_00', …], ['fx_mem_00', …])`. The
  same query has the same rows once the verb gets the CLI's `include_session`. No `src/` change:
  changing the interactive default would break the two pinned contracts. For the test engineer
  (or the lead, if the interactive affordance should go). {#g7-7}
- **g7-8 26.4's AC-2 hook test reads the per-prompt hook as JSON.**
  `test_savestate_mtype.py::test_ac2_hook_mode_recall_hides_the_hand_typed_savestate_and_include_session_keeps_it`
  builds the generated `--stdin-json` argv, which has printed `--pack` text since the 25.1 GREEN
  (`16ace00`), and `json.loads` it: `JSONDecodeError: Expecting value: line 1 column 1`. The
  same contract update red-251b made for the 21.1 tests (read names through
  `task21_1_support.pack_rows`) applies. 26.4 was written before 25.1 changed the hook. For
  the test engineer. {#g7-8}
- **AC-5** failed at `e5a516c` (family: `assert 'savestate_fx01' not in ['savestate_fx01',
  'fx_dup_x', …]`), as expected; no 26.4 code was written here. It PASSES at `69da299`, after
  the lead merged 26.4. {#g7-ac5}

{#green-rev7-flags-list}

## GREEN remedy r8 (green-251c, 2026-11-14) {#green-r8}

rel: implements -> [[bsd-plan25-task251-premerge-f656f78]]
rel: amends -> [[#green-rev7]]

The remedy for bsd-251's pre-merge audit at `f656f78` (DIRTY 1B/2S/5M), per the lead's ruling
L68 in `workflow/plan-review-2026-11-13.md` on dev master. red-251b wrote the REDs and pins at
`6b48b94` (tests) and `e354957` (its mutation logs). This GREEN is `src/` only, in commit
`dc66a04`; no test was edited. {#green-r8-lead}

### Per finding {#green-r8-map}

| finding | change | where |
|---|---|---|
| s-2: a curated-hooks read failure dropped when no `warnings` list | `pack_recall` raises `VerbError("curated hooks unreadable (<Type>: <msg>); pass a warnings list …")` when the caller passes no list. With a list, it appends the warning and falls back to first sentences, as before. The CLI's busy/absent replica fall-through for `--session-start` / `--recent` / `--subject` now passes a list and prints each entry as `# rmx: warning: …` | `verbs.pack_recall`, `cli._memory_recall_impl` (the fall-through pack) |
| m-5: only `VerbError` became an `Error:` line | `rmx recall-state` builds its whole output inside the guard. A `VerbError` keeps its own words. Any other exception becomes `Error: recall-state: <Type>: <msg>` (whitespace collapsed to one line) with exit 1 and no traceback. Nothing is written to stdout before the guard succeeds | `cli.recall_state` |
| m-3: stale comment | The per-prompt hook comment now says a skip "warns on stderr, prints NOTHING on stdout (25.1 d8: no context injected this turn), exits 0" | `hooks._claude_hook_block` |
| m-4: `EVENT_SPLIT` and `MIN_USEFUL_RECALL_BYTES` read only by tests | Kept, because a requirement names both: R1 lists them as contents of `hook_budget` (spec lines 162-165). R0 (B)/(C) is the only place the spec gives them a formula (spec lines 137-145, the per-event split and the recall floor), and R0 recorded outcome (A) on both events (`hook-output-cap-probe.md#outcome-not-bc`), so no budget can be computed from `EVENT_SPLIT` today. They are now read in production at import by `hook_budget._check_tables` (see the list below the table). The `focus_input` cap is left to 25.1b AC-26, as ruled | `hook_budget._check_tables`, `_NON_R0_EVENT_CHANNELS`, `_RECALL_CHANNELS` |
| b-1: bug-224's empty-stdout degrade | No change. d8 stands for 25.1, and 25.1b gains the skip line (L68) | none |

{#green-r8-map-table}

The import-time checks that m-4 added:

- `EVENT_SPLIT` and `NON_RMX_RESERVE_BYTES` must name the same events.
- Each share must be a known channel, at or under that channel's own cap. R0 (B) makes every
  share "a hard byte cap it enforces on itself".
- Every budgeted channel except `precompact` must sit on an event. PreCompact is not an R0
  outcome event.
- No recall channel (`prompt_recall`, `session_start`, `precompact`) may have a table budget
  under `MIN_USEFUL_RECALL_BYTES`. This is R0 (C)'s floor.

Each check was shown to fail on must-fail input by editing the tables in-process and calling
`_check_tables()`:

- a share over its cap: `EVENT_SPLIT['SessionStart']['focus_context'] = 2000 B exceeds the
  channel's own cap 1500 B`;
- an unknown channel;
- `recall_state` removed from the split: `sit on no EVENT_SPLIT event`;
- the floor raised to 5,000: `recall channel 'prompt_recall' budget 4000 B is under …`.

The clean table passes. {#green-r8-m4-proof}

### Runs {#green-r8-runs}

| run (at `dc66a04`) | result | log |
|---|---|---|
| `tests/test_task25_1_recall_budget.py`, whole file | **137 passed**. The three REDs now pass: `test_s2_pack_recall_never_drops_a_curated_hooks_failure`, `test_s2_busy_fall_through_says_a_curated_hooks_failure`, `test_ac15h_any_failure_is_one_error_line_never_a_traceback`. So do the s-1 / m-1 / m-2 pins | `workflow/review-output/plan25/25.1-r8-green-file.log` |
| family of 19 files: the 14 test files 25.1 touches, plus `test_verb_parity`, `test_repo_hooks_in_sync`, `test_mcp_bus_passthrough`, `test_context_cost`, `test_docs_generated` | **543 passed, 1 skipped**. The skip is `test_installed_hooks_match_generated`, which skips in clones because the hooks belong to the dev checkout | `workflow/review-output/plan25/25.1-r8-green-family.log` |
| full suite | **4 failed, 4439 passed, 1 skipped** (49:08). All four are pre-existing; see the E-line comparison below | `workflow/review-output/plan25/25.1-r8-green-full.log` |

{#green-r8-runs-table}

E-line comparison against `release-0.82.0-full.log`, the four failures by test:

- `test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon`: the same
  E line as release-0.82.0, `_duckdb.IOException: … Could not set lock on file …
  catalog.A.duckdb: Conflicting lock`.
- `test_task21_1_agent_usage_report.py::test_ac6_frozen_fixture_prints_the_exact_counts`: the
  same E lines as release-0.82.0, `AssertionError: agent usage · window 2026-09-23 ..
  2026-10-07T11:06:35 …` / `assert []`.
- `test_task21_1_agent_usage_report.py::test_ac6_cli_log_recalls_are_split_per_channel`: the
  same E line, `chan('prompt_recall', 5)` is `[]`.
- `test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate`:
  the same test name as in 0.82.0, but a DIFFERENT error set.
  - 0.82.0 had 3 dangling-doc errors in a `workflow/bullshit/` report.
  - This run has the same 21 errors as `25.1-green7-full.log` (sorted lists diffed: identical):
    12 in `docs/INDEX.md`, 6 in `docs/adr/0000-adr-overview.md` and 2 in
    `docs/adr/0001-intuition-lance-integration.md`.
  - 25.1 changes no file under `docs/` (`git diff --name-only 0d2a270..HEAD -- docs` is empty).
    bsd-251 reproduced the same set at the master base `0d2a270`.
  - So this failure belongs to master, not to 25.1.

No other failure was found. Both earlier merge-interaction failures (g7-7 `test_ac4f`, g7-8
`test_savestate_mtype` AC-2) pass, as does AC-5. {#green-r8-eline}

### Spec lines not satisfied, and flags {#green-r8-flags}

- **m-4, a partial reading.** "Read them where the spec names them": the spec's only formula
  that consumes `EVENT_SPLIT` is R0 (B)'s per-event budget split, and it does not apply under
  outcome (A). So `EVENT_SPLIT` is now read only by the import-time consistency check. It
  computes no budget. Deleting it would contradict R1 (spec lines 162-165) and fail
  `test_r1_hook_budget_table_names_every_channel_event_and_command`, which pins it. If the lead
  wants it gone, R1 needs an amendment first. {#green-r8-m4-flag}
- **s-2's raise path has no production caller today.** Both callers now pass a list: the verb
  passes its own `warnings`, and the CLI fall-through passes a new list. The raise guards future
  callers, and `test_s2_pack_recall_never_drops…` pins it. {#green-r8-s2-flag}
- **The `focus_input` comment still says "its share is a cap"**, which is not enforced. It was
  left untouched, because the ruling gives the `focus_input` cap to 25.1b AC-26.
  {#green-r8-focus-input}

{#green-r8-flags-list}
