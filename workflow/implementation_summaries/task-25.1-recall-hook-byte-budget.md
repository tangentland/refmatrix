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
