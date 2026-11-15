---
gmd: "0.1"
id: task-31.5-s0-capture
title: "Task 31.5 release A (GREEN): the injection capture in both modes, the R2.0 member filter, bug-256 and bug-268"
tags: [implementation-summary, plan-31, task-31.5, scan-prompt, injection-capture, bug-256, bug-268]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-15
  branch: task-31.5-s0-capture
  base: 4b58fce
---

# Task 31.5 release A, GREEN {#root}

This is the GREEN pass for 31.5 S0 (the per-prompt injection capture, both modes), R2.0 (the
composite member filter), bug-256 (a failing composite is counted) and bug-268 (a wrong-shaped
focus graph is corrupt and never a traceback). It is production code in `src/` plus the one
fixture the spec gives GREEN. No test was authored or edited. Four nodes are flagged to the lead
as test defects ([[#flagged]]). {#root-lead}

rel: implements -> [[task-31.5-scan-prompt-block-measure]]
rel: implements -> [[task-31.5-scan-prompt-block-measure#s0]]
rel: implements -> [[task-31.5-scan-prompt-block-measure#r2-0]]
rel: implements -> [[task-31.5-scan-prompt-block-measure#r0-7]]
rel: depends-on -> [[red-report-31.5-s0-capture]]
rel: related-to -> [[bug_registry#registry]]

## What changed, by file {#files}

| File | Change |
|---|---|
| `src/refmatrix/telemetry.py` | The capture: `capture_state`, `capture_block`, `capture_hit`, `write_capture` (the ONE writer: self-ignore, pruner, bound, hard stop, `errors.jsonl`), `capture_report` and `capture_line`. `summarize_context` gains `capture` |
| `src/refmatrix/scan.py` | `scan_prompt(..., capture=None)`: blocks carry kind and state; mode `full` builds the bundles past the token stop and `names` records them `not_built`; `_composite_text` records and says its failure (bug-256); `_composite_names` |
| `src/refmatrix/composite.py` | `build_topic_composite_pending(..., status=None)` says why a composite is absent; `_printable_members` (R2.0) in `_render_gmd`, which also expands only printed members |
| `src/refmatrix/stm.py` | `FocusGraphCorrupt`, `focus_graph_problem`, `Stm._load_graph(strict=)`, `live_turn(strict=)`, `phase_fields_checked` (bug-268); `phase_fields` and `pre_prompt_state` read strictly |
| `src/refmatrix/cli.py` | `scan-prompt` hands the blocks to the writer after the print; `_RecallCall.emit` writes the recall capture (`_capture_blocks`, `_emit_events`); `telemetry --context` prints the `capture:` line |
| `src/refmatrix/recall_pack.py`, `src/refmatrix/verbs.py` | `Packed.line_bytes` and `pack_recall`'s `line_bytes`: every hit's hook-line bytes, so a dropped hit's cost is recorded |
| `tests/fixtures/injection_capture/prompts.txt` | 40 synthetic prompts for the cost method (30 carry a hub word as a plain word) |
{#files-table}

No hook command changed. `hooks.py` is untouched, and the generated block's sha256 (computed
the RED report's way, `HOME=/private/tmp/claude-501/hb315`) is
`770e217a330ddb6092111724be59f5a3de2984772f73c399e5216839b0cf2019`, equal to base
(AC-0.12). {#files-hooks}

## Signatures {#signatures}

- `telemetry.capture_state(root) -> CaptureState(mode, off_by, invalid)` with `.on`.
- `telemetry.capture_block(kind, state, *, text=None, names=(), dedup_rows=0, **extra) -> dict`.
- `telemetry.capture_hit(*, state, name, rank, mtype, scope, hook_bytes, content) -> dict`.
- `telemetry.write_capture(root, *, channel, invocation, session, query_id, prompt,
  budget_bytes, max_tokens, payload, mode, blocks, capture_built=0, build_ms=0.0,
  composite_error=None, stm_error=None, t0=None, now=None) -> dict | None`.
- `telemetry.capture_report(root, *, since=None) -> dict`; `telemetry.capture_line(rep) -> str`.
- `scan.scan_prompt(..., capture: str | None = None) -> str`. It fills `trace["capture"]`
  (`blocks`, `built`, `build_ms`) and `trace["composite_error"]`.
- `composite.build_topic_composite_pending(..., status: dict | None = None)`;
  `composite._printable_members(s, members) -> list[str]`.
- `stm.focus_graph_problem(g) -> str | None`; `stm.phase_fields_checked(root, session,
  prompt, *, t0, prompt_time) -> tuple[dict, str | None]`; `Stm._load_graph(*, strict=False)`;
  `stm.live_turn(root, session, *, strict=False)`.
{#signatures-list}

## Design choices worth checking {#choices}

- **bug-268 is fixed at the phase read, not in the shared loader.** `phase_fields` loads the
  graph strictly and validates it (`focus_graph_problem`: what the readers consume). A wrong
  shape raises `FocusGraphCorrupt`, and `phase_fields_checked` turns that into `stm_error`, one
  stderr line and null phase fields. Only `FocusGraphCorrupt` is caught. The composite keeps
  the plain loader on purpose: AC-0.16 uses the `[]` file as the real input that makes the
  composite raise, and pins `AttributeError` / `setdefault`. That failure is then
  bug-256's `composite_error`. {#choice-268}
- **Capture-only renders write no helix readership row** (`helix_pending` cleared before
  render). They reached no output. {#choice-helix}
- **`budget_bytes` is the resolved channel cap** (`hook_budget.resolve`). It equals
  `budget("scan_prompt")` when no `--max-bytes` is passed, which is what AC-0.1 pins, and it
  is the explicit value when one is passed. {#choice-budget}
- **The pruner stats before it unlinks** (it follows links), so a listed file that is gone
  takes the not-an-error branch (RED report reading 9). Other stat or unlink failures are
  `prune_failed` lines in `errors.jsonl`. {#choice-prune}
- **An unrecognised mode word, or an unreadable mode file, turns the capture off** and shows
  as an invalid mode. `RMX_INJECTION_CAPTURE` accepts `0`, `full` and `names`. Any other word
  there is invalid too. {#choice-mode}
- **Recall records** are written for every `--pack` call on a capture channel that reaches
  `emit`, empty and degraded calls included (R0.2-empty). They hold a header and trailer
  `marker` and one `recall_hit` per hit. `body_bytes` / `body_sha256` describe the memory's
  content for every hit that has one. The state says whether the body was printed. {#choice-recall}
{#choices-list}

## Per AC {#acs}

Logs are under `workflow/review-output/31.5/`. `green-capture-1.log` is
`tests/test_injection_capture.py`: 41 collected, exit 1, 40 passed, 1 failed.
`green-members-1.log` is `tests/test_stm_composite_members.py`: 4 collected, exit 0,
4 passed. {#acs-lead}

| AC | Node(s) | Code | Result |
|---|---|---|---|
| 0.1 | `test_a_scan_call_writes_one_record_with_every_block` | `telemetry.write_capture`, `scan._capture_blocks`, `cli.scan_prompt_cmd` | GREEN |
| 0.2 | `test_delivered_blocks_concatenate_to_the_payload[uncapped,byte-capped]` | the `parts` blocks plus the fit trailer as `marker` | GREEN |
| 0.3 | the five cut nodes plus `test_names_mode_records_later_bundles_as_not_built` | `scan._symbol_sections` trip branch, `_capture_cut`, the tier-1 content render | GREEN |
| 0.4 / 0.5 | `test_the_capture_never_changes_the_payload[2]`, `test_capture_only_bundles_emit_no_recall_events` | capture-only bundles never `_retrieve` | GREEN |
| 0.6 | `test_a_composite_stored_as_dropped_is_sent_on_the_next_prompt` | the marker commit is unchanged | GREEN |
| 0.7 | `test_a_packed_recall_writes_one_block_per_hit` | `cli._RecallCall._capture_blocks`, `Packed.line_bytes` | GREEN |
| 0.8 | `test_prompt_text_appears_only_inside_block_text` | — | **RED: test defect, flagged** ([[#flagged]]) |
| 0.9 | the three bound / retention nodes | `telemetry._capture_prune`, the hard stop in `write_capture` | GREEN |
| 0.10 | `test_a_failed_append_keeps_the_payload_and_is_counted`, `test_an_unwritable_capture_dir_shows_as_missing_coverage` | `append_failed`, coverage in `capture_report` | GREEN |
| 0.11 | `test_json_format_writes_no_capture_record`, `test_a_verb_recall_with_pack_writes_no_capture_record` | the capture is the CLI emitter's only; `--format json` gets none | GREEN |
| 0.12 | gate | no hook change; block sha equal to base ([[#files-hooks]]) | holds; `rmx install-hooks --check` against installed hooks is the lead's |
| 0.13 | measurement | [[#band]] | default `names` |
| 0.15 | the three git nodes | `telemetry._capture_ignore` before every write | GREEN |
| 0.16 | `test_a_raising_composite_build_is_recorded_and_counted` | `scan._composite_text` (bug-256) | GREEN |
| 0.18 | the switch, no-telemetry and mode-file nodes | `telemetry.capture_state` | GREEN |
| R0.5 step 3 | `test_the_cost_prompt_set_is_forty_synthetic_prompts` | `tests/fixtures/injection_capture/prompts.txt` | GREEN |
| bug-268 | nine `test_a_wrong_shaped_focus_graph_never_crashes_*` nodes | `stm.phase_fields_checked`, `focus_graph_problem` | GREEN |
| 2.0 | three RED nodes and one characterization | `composite._printable_members` | GREEN (4/4) |
{#acs-table}

## The pre-release cost band (AC-0.13) {#band}

**Method** ([[task-31.5-scan-prompt-block-measure#r0-5-method]]):

- The live store's `catalog.read.duckdb` (1,363,685,376 B, 172,764 entities, opened
  `read_only=True` to count) was copied into `/private/tmp/claude-501/m315.8Zev/refmatrix/.refmatrix/`.
- The project directory is named `refmatrix` so the partition resolves to the copy's
  `refmatrix` partition. A first smoke run from a directory named `p` resolved an empty
  partition and printed nothing.
- `HOME` was a scratch directory. `REFMATRIX_ROOT` and `RMX_HOME` were removed from the env, so
  the copy is found from the cwd.
- Every run was a fresh process of
  `/Volumes/littlebig/refmatrix-315-green/.venv-eval/bin/rmx scan-prompt --composite-every 3
  --max-tokens 2000 --timeout 5`, with `RMX_INVOCATION_SOURCE=hook`, `PYTHONPATH=<clone>/src`
  and a UserPromptSubmit envelope on stdin. That is the CLI read path, not the in-process
  fallback.
- `rmx version -v` of that binary: `refmatrix 0.84.0`, `code:
  /Volumes/littlebig/refmatrix-315-green/src/refmatrix/__init__.py [DEV TREE]`
  (`green-band-setup.log`).
- Each condition ran 5 passes over the 40 prompts with the arms off / full / names alternated
  per prompt, so there were 200 runs per arm.
- "Quiet" ran alone under the test-lane lock. "Loaded" ran beside the verify set
  (`green-verify-1.log`, then a second iteration).
- Script and raw rows: `green-band-measure.py`, `green-band-runs-*.jsonl`. Summaries:
  `green-band-quiet.json`, `green-band-loaded.json`.

{#band-method}

**The quiet run was not quiet.** Other agents' work outside the lane kept load1 at about 9.6
through both conditions. The quiet window opened at load 10-25 and is the worse of the two, so
it is the one read. All 40 prompts tripped the token stop on every run (step 3 needs at least
half). {#band-caveat}

| | quiet (read) | loaded |
|---|---|---|
| wall p50 / p95, off | 3,180 / 9,490 ms | 3,134 / 3,603 ms |
| wall p50 / p95, full | 3,609 / 11,268 ms | 3,670 / 3,917 ms |
| wall p50 / p95, names | 3,171 / 9,330 ms | 3,135 / 3,634 ms |
| `capture_ms` p50 / p95 / max, full | **602 / 2,041 / 3,751 ms** | 550 / 679 / 785 ms |
| `capture_ms` p50 / p95 / max, names | **1.7 / 5.2 / 11.6 ms** | 1.6 / 1.9 / 2.4 ms |
| `capture_built` per call, full | mean 1.48, max 2; 180 of 200 calls built | the same |
| ms per built bundle, full | 487 (aggregate), 316 (p50) | 308 / 314 |
{#band-table}

**Band read** ([[task-31.5-scan-prompt-block-measure#r0-5-bands]]): mode `full` p95 is
2,041 ms, over 250 ms, so the default is **`names`**. Mode `names` p95 is 5.2 ms, under
750 ms, so the capture ships on. `telemetry.CAPTURE_DEFAULT_MODE = "names"`. `full` stays one
setting away (`injection-capture.mode`). One bundle costs about 300 ms on the live catalog in
a fresh process, against ch-bsd's 34-92 ms r1 probe. Only about 1.5 bundles are built per
call, because the hook's `--max-concepts 5` leaves few names past the stop. {#band-read}

## Verify set by E line {#verify}

The family was found by AST over `tests/**/*.py`: every file that imports `refmatrix.scan`,
`composite`, `stm`, `telemetry` or `hook_budget`, as `from refmatrix import X` or
`from refmatrix.X import` (61 files). A `grep -E` pass found the same 61. Added to them:
`test_injection_capture.py`, `test_stm_composite_members.py`, `test_scan_prompt_block_order.py`,
`test_stm_composite_injection.py`, `test_scanorder_r2_l120.py`, `test_verb_parity.py`,
`test_hooks.py`, `test_hooks_reproducible.py` and `test_repo_hooks_in_sync.py`. That is 65
files. `green-verify-1.log`: exit 1, 1,450 passed, 6 failed, 1 skipped. A second identical
run (load only) gave the same six. {#verify-lead}

| Node | E line | Against `release-0.84.0-full.log` |
|---|---|---|
| `test_task21_1_agent_usage_report.py::test_ac6_frozen_fixture_prints_the_exact_counts` | `AssertionError: agent usage · window 2026-09-23 .. …` / `assert []` | same E lines at base |
| `test_task21_1_agent_usage_report.py::test_ac6_cli_log_recalls_are_split_per_channel` | the same, `where [] = …chan…('prompt_recall', 5)` | same E lines at base |
| `test_composite.py::test_intra_cluster_emits_real_verb_not_cooccurs` | `AttributeError: 'object' object has no attribute 'resolve_concept_ids'` | new: flagged ([[#flagged]]) |
| `test_composite.py::test_intra_edges_zero_drops_grounded_block` | the same | new: flagged |
| `test_composite.py::test_ltm_expansion_ranks_sparse_first_and_dedups` | the same | new: flagged |
| `test_injection_capture.py::test_prompt_text_appears_only_inside_block_text` | `the canary outside a dropped block's header: ['=== context for `zqxcanary315 why does …` ===']` | new node: flagged |
{#verify-table}

## Flagged, then ruled (L155, L156) {#flagged}

- **AC-0.8:** the node allowed only `# refmatrix ` lines, but the content bundle's render also
  carries the canary in its anchor line `=== context for `<candidate bag>` ===`. L155 widened
  the test (red-315 `30ac2f6`). GREEN keeps storing the real render. {#flag-ac08}
- **Three `test_composite.py` nodes** passed a bare `object()` store to the R2.0 filter. L156
  kept the raise and gave them a store double (`dfcedf1`). {#flag-composite}
- Merged at the tip; the three files re-run once: [[#after-merge]]. {#flag-merged}
{#flagged-list}

## After the merge {#after-merge}

Merged red-315's `dfcedf1` (with `30ac2f6`) at `d298965`. The merge touches only
`tests/test_composite.py`, `tests/test_injection_capture.py`, `workflow/test_mock_registry.md`
and review logs, so only the three files re-ran, in one lane hold
(`green-merge-3files.log`): `test_injection_capture.py`, `test_composite.py` and
`test_stm_composite_members.py` gave 64 collected, 64 passed, exit 0, no E lines. {#after-merge-body}

## Self-audit {#self-audit}

1. **Real run** (`green-selfaudit-real.log`): the dev `rmx` was run by path on a throwaway
   store, with the cwd discovering the store and capture in the default mode. Hook-shaped
   `scan-prompt` exits 0 and writes `.gitignore` plus one record (7 blocks, `capture_ms` 0.5,
   `capture_mode` names). `memory recall --session-start --pack` writes a `session_start`
   record (13 blocks). `--recent --since 1h --pack` writes a `precompact` record (24 blocks).
   `telemetry --context` prints `capture: on (mode names) · … · 3 captured of 3 hook calls
   · errors none · composite_errors=0 · stm_errors=0 · malformed=0`. The band (AC-0.13) ran
   the hook command 1,200 times on a copy of the live catalog. {#sa-1}
2. **Wiring:** every capture node runs the real `rmx scan-prompt` or `rmx memory recall
   --pack` as a child process. The bug-268 nodes send the hook's `--stdin-json` envelope.
   `test_a_verb_recall_with_pack_writes_no_capture_record` goes through `verbs.memory_recall`
   with a sandbox daemon. Nothing in `src/` is patched. {#sa-2}
3. **Census** (`green-selfaudit-census-hooks.log`, `green-selfaudit-census-sites.log`): the
   generated hook commands that print to the model are `scan-prompt`, `curator status` (×2),
   `memory recall --pack` (×3: prompt, session start, precompact), `recall-state` and
   `focus context`. Captured: scan-prompt and the three recall packs (the spec's four
   channels). Left: `curator status`, `recall-state` and `focus context`, outside R0.2's
   channel list and census row. `fit_blocks` has 5 sites; two record a capture (`scan._finish`
   via the CLI, `recall_pack.pack` via `_RecallCall`). Both recall pack routes (verb and replica
   fall-through) end in `_echo_pack`, so both capture. JSON and MCP do not capture (AC-0.11).
   {#sa-3}
4. **Bound:** the capture makes no RPC. In mode `names` it costs one stat (`.gitignore`), one
   listdir, one stat per day file (at most 43) and one append; measured p95 5.2 ms and max
   11.6 ms. In mode `full` it adds up to `max_concepts` (5) `build_context` calls with no time
   bound of their own; measured max 2 builds and 3,751 ms. That is why the default is
   `names`, and the spec's live fallback table (AC-0.17) is a setting. {#sa-4}
5. **Busy / down:** the capture never calls a daemon. With the daemon down, the recall falls
   through to the replica and is captured (Q1 stderr: `reading the replica`). With the daemon
   busy, the degraded pack prints nothing and `emit` writes a record with empty `blocks`,
   because the call still counts for coverage. Busy was not forced in a live run. {#sa-5}
6. **Guards, each reached by a real state:**
   - `over_bound`: a 65 MiB sparse day file (`test_a_day_file_over_the_bound_stops_appending`).
   - Vanished file: a dangling link, which stat follows to ENOENT
     (`test_a_file_another_process_removed_is_not_an_error`).
   - `.gitignore` creation: a bare directory (`test_an_existing_capture_dir_without_gitignore_gets_one`).
   - Invalid mode: the word `bogus` in the mode file (`test_the_mode_file_selects_the_path`).
   - `FocusGraphCorrupt`: three real files (nine bug-268 nodes).
   - `suppressed_cadence` / `suppressed_unchanged`: two AC-0.3 nodes.
   - Member filter: the AC-2.0 nodes.
   - Not exercised by a test: `prune_failed` (an unlink EPERM) and the 1 MiB `errors.jsonl` cap.
   {#sa-6}
7. **Loud** (Q1 log): an unwritable day file gives exit 0, the same payload, and stderr
   `rmx: injection capture: append_failed for query … (PermissionError …)`. A `[]` focus graph
   gives exit 0 and stderr `rmx scan-prompt: STM composite build failed, sent without it
   (AttributeError: 'list' object has no attribute 'setdefault')` plus `rmx: STM focus graph of
   session … is corrupt (FocusGraphCorrupt: … not a JSON object (list))`. A bogus mode gives
   `capture: off (invalid mode: 'bogus' in injection-capture.mode) · … errors
   append_failed=1 · composite_errors=1 · stm_errors=1`. No `except: pass` was added; every
   handler says and counts. {#sa-7}
8. **Handoff:** live checks AC-0.14 and AC-0.17 are spec ACs run after the deploy. Mutations
   are in the spec's `#mutations`, for the lead. bug-268 has no registry row yet (the lead
   allocates it). The version bump belongs to R1. {#sa-8}
{#self-audit-list}
