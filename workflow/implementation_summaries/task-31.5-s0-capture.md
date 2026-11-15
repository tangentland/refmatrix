---
gmd: "0.1"
id: task-31.5-s0-capture
title: "Task 31.5 release A (GREEN): the injection capture in both modes, the R2.0 member filter, bug-256 and bug-268"
tags: [implementation-summary, plan-31, task-31.5, scan-prompt, injection-capture, bug-256, bug-268]
metadata:
  node_type: implementation-summary
  status: green-with-flagged-tests
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

## Flagged to the lead, not worked around {#flagged}

- **AC-0.8's node allows too little.** The content bundle's render carries the canary twice:
  in its `# refmatrix content matches` header and in its anchor line `=== context for
  `<candidate bag>` ===`. The delivered payload shows both (the stdout holds the canary
  twice). The node allows only lines that start with `# refmatrix `. GREEN stores the render
  as it would print (R0.1), so it does not strip the line. The fix belongs to the test
  (red-315) or to a ruling. {#flag-ac08}
- **Three `test_composite.py` tests pin pre-R2.0 behaviour.** They pass a bare `object()` as
  the store, use plain-word members and monkeypatch `build_context`. R2.0 asks the store
  whether it holds a plain word's concept. `object()` cannot answer, so the filter raises
  (loudly, by choice). Even if it did not raise, the members would no longer print. The fix is
  a fixture with a concept lookup, or identifier-shaped members. {#flag-composite}
- **Not done here:** mutations (not GREEN's), the version bump (the release's), and a bug-268
  registry row (no row exists at base; the lead allocates ids). {#flag-scope}
{#flagged-list}
