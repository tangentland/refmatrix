---
gmd: "0.1"
id: red-report-31.5-s0-capture
title: "RED report: task 31.5 S0, the injection capture (release A), bug-256, bug-268 and the R2.0 member filter"
tags: [report, red, plan-31, task-31.5, scan-prompt, injection-capture, bug-256, bug-268]
metadata:
  node_type: report
  created: 2026-11-15
  branch: task-31.5-s0-capture
  base: 606c0c8
---

# RED report: task 31.5 S0, the injection capture (release A), bug-256, bug-268 and the R2.0 member filter {#root}

The RED tests for 31.5 step 0 are in `tests/test_injection_capture.py`, and those for R2.0
(AC-2.0, release A, added on the lead's instruction) in `tests/test_stm_composite_members.py`, on branch
`task-31.5-s0-capture` in `/Volumes/littlebig/refmatrix-315`, based on `606c0c8`. Nothing in
`src/` is touched, and no fix is sketched anywhere. No mock or patch is used.

rel: specified-by -> [[task-31.5-scan-prompt-block-measure#s0]]
rel: depends-on -> [[task-31.5-scan-prompt-block-measure#s0-acceptance]]
rel: depends-on -> [[task-31.5-scan-prompt-block-measure#mutations]]
rel: specified-by -> [[task-31.5-scan-prompt-block-measure#ac-2-0]]
rel: related-to -> [[bug_registry#registry]]

## Runs {#runs}

| Log | Command | Exit | Collected | Result |
|---|---|---|---|---|
| `red-base-r2.log` | `pytest tests/test_injection_capture.py -q -rA`, with the bug-268 nodes (L152) | 1 | 41 | 36 failed, 5 passed |
| `red-base-bug268.log` | the same, `-k 'wrong_shaped or writes_one_record_with_every or prompt_text_appears'` | 1 | 41 (30 deselected) | 11 failed |
| `red-base.log` | `pytest tests/test_injection_capture.py -q -rA`, before bug-268 | 1 | 32 | 27 failed, 5 passed |
| `red-base-ac08.log` | the same, `-k prompt_text_appears` (after the AC-0.8 fixture fix) | 1 | 32 (31 deselected) | 1 failed |
| `red-base-r1.log` | the first full run, before the AC-0.8 fixture fix | 1 | 32 | 27 failed, 5 passed (AC-0.8 failed on its own fixture check) |
| `red-base-ac20.log` | `pytest tests/test_stm_composite_members.py -q -rA` | 1 | 4 | 3 failed, 1 passed |
| `guard-ac06-existing-base.log` | `tests/test_scanorder_r2_l120.py::test_s3_a_composite_the_cap_dropped_is_delivered_when_there_is_room` | 0 | 1 | 1 passed |
| `probe.log` | an uncommitted probe file (deleted), kept for the defect below | 0 | 1 | 1 passed |
{#runs-table}

Every run went through `/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`, with
`PYTHONPATH=<clone>/src` and the dev interpreter `.venv-eval/bin/python`. The logs are under
`workflow/review-output/31.5/`. {#runs-how}

## Nodes and their base E lines {#nodes}

The 5 green nodes are the guards and characterizations the spec marks as green at base.
Every red node fails on its intended reason: the capture does not exist, or bug-256's silence.
The query ids and tmp paths are shortened below. {#nodes-lead}

| AC | Node | Base | E line at base |
|---|---|---|---|
| 0.1 | `test_a_scan_call_writes_one_record_with_every_block` | RED | `R0.2: one capture record per call, found 0; …/injection-capture does not exist` |
| 0.2 | `test_delivered_blocks_concatenate_to_the_payload[uncapped]` | RED | `no capture record for query_id <qid> (R0.2: …); …/injection-capture does not exist` |
| 0.2 | `test_delivered_blocks_concatenate_to_the_payload[byte-capped]` | RED | the same |
| 0.3 | `test_a_block_the_byte_fit_dropped_is_stored_as_dropped_bytes` | RED | the same |
| 0.3 | `test_bundles_past_the_token_stop_are_built_and_stored_as_dropped_tokens` | RED | the same |
| 0.3 | `test_content_after_a_tier_1_token_stop_is_stored_with_text[full]` | RED | the same |
| 0.3 | `test_content_after_a_tier_1_token_stop_is_stored_with_text[names]` | RED | the same |
| 0.3 | `test_names_mode_records_later_bundles_as_not_built` | RED | the same |
| 0.3 | `test_an_unchanged_composite_is_recorded_as_suppressed_unchanged` | RED | the same |
| 0.3 | `test_a_cadence_skip_is_recorded_as_suppressed_cadence` | RED | the same |
| 0.4 | `test_the_capture_never_changes_the_payload[token-stop]` | green (guard) | — |
| 0.4 | `test_the_capture_never_changes_the_payload[byte-fit]` | green (guard) | — |
| 0.5 | `test_capture_only_bundles_emit_no_recall_events` | green (guard) | — |
| 0.6 | `test_a_composite_stored_as_dropped_is_sent_on_the_next_prompt` | RED | `no capture record for query_id <qid> …` (the delivery half is green at base) |
| 0.7 | `test_a_packed_recall_writes_one_block_per_hit` | RED | `no capture record for query_id <qid> …` |
| 0.8 | `test_prompt_text_appears_only_inside_block_text` | RED | `no capture record for query_id <qid> …` |
| 0.9 | `test_old_and_oversize_day_files_are_pruned_and_listed` | RED | `no record appended today; …/injection-capture: ['.gitignore', 'capture-20260926.jsonl', 'capture-20261105.jsonl', 'capture-20261110.jsonl']` |
| 0.9 | `test_a_day_file_over_the_bound_stops_appending` | RED | `errors.jsonl: []; …/injection-capture: ['.gitignore', 'capture-20261115.jsonl']` (`assert [] == ['over_bound']`) |
| 0.9 | `test_a_file_another_process_removed_is_not_an_error` | RED | `no capture record for query_id <qid> …: ['.gitignore', 'capture-20260926.jsonl']` |
| 0.10 | `test_a_failed_append_keeps_the_payload_and_is_counted` | RED | `errors.jsonl: []; …` (`assert [] == ['append_failed']`) |
| 0.10 | `test_an_unwritable_capture_dir_shows_as_missing_coverage` | RED | ``R0.6: `rmx telemetry --context` prints 0 `capture:` line(s), not one`` |
| 0.11 | `test_json_format_writes_no_capture_record` | green (characterization) | — |
| 0.11 | `test_a_verb_recall_with_pack_writes_no_capture_record` | green (characterization) | — |
| 0.15 | `test_the_capture_dir_ignores_itself` | RED | `no capture written; …/injection-capture does not exist` |
| 0.15 | `test_an_existing_capture_dir_without_gitignore_gets_one` | RED | `no capture written; …/injection-capture: []` |
| 0.15 | `test_an_errors_only_write_into_a_bare_capture_dir_is_ignored` | RED | `no errors.jsonl line; …/injection-capture: ['capture-20261115.jsonl']` |
| 0.16 | `test_a_raising_composite_build_is_recorded_and_counted` | RED | `bug-256: the composite failure said on stderr: []` |
| 0.18 | `test_the_capture_switch_leaves_telemetry_on[env]` | RED | `no capture record for query_id <qid> …` (the switched-off half is green at base) |
| 0.18 | `test_the_capture_switch_leaves_telemetry_on[marker]` | RED | the same |
| 0.18 | `test_no_telemetry_implies_no_capture` | RED | the same |
| 0.18 | `test_the_mode_file_selects_the_path` | RED | `no capture record for query_id <qid> …` |
| 2.0 | `test_stopwords_and_unknown_plain_words_are_not_printed_as_members[question-held]` | RED | ``store holds `question`: True; printed members ['scan-prompt', 'store.py', 'the', 'buigger', 'question'], expected ['question', 'scan-prompt', 'store.py'] …`` |
| 2.0 | `test_stopwords_and_unknown_plain_words_are_not_printed_as_members[not-held]` | RED | ``store holds `question`: False; printed members ['scan-prompt', 'store.py', 'the', 'buigger', 'question'], expected ['scan-prompt', 'store.py'] …`` |
| 2.0 | `test_a_topic_with_no_printable_member_is_not_emitted` | RED | `a topic with no printable member was emitted: … ## Topic 1: the … Members: the, buigger, and, zorbleplain` |
| 2.0 | `test_the_focus_graph_is_unchanged_by_the_filter` | green (characterization) | — |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_scan_prompt[int-node]` | RED | `bug-268: scan-prompt exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:9872` → `stm.phase_fields`, `AttributeError: 'int' object has no attribute 'get'`) |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_recall[int-node-prompt_recall]` | RED | `bug-268: memory recall (prompt_recall) exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:13344` `emit`, `AttributeError: 'int' object has no attribute 'get'`) |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_recall[int-node-session_start]` | RED | `bug-268: memory recall (session_start) exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:13347` `emit`, `AttributeError: 'int' object has no attribute 'get'`) |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_scan_prompt[list]` | RED | `bug-268: scan-prompt exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:9872` → `stm.phase_fields`, `AttributeError: 'list' object has no attribute 'setdefault'`) |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_recall[list-prompt_recall]` | RED | `bug-268: memory recall (prompt_recall) exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:13344` `emit`, `AttributeError: 'list' object has no attribute 'setdefault'`) |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_recall[list-session_start]` | RED | `bug-268: memory recall (session_start) exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:13347` `emit`, `AttributeError: 'list' object has no attribute 'setdefault'`) |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_scan_prompt[nameless-node]` | RED | `bug-268: scan-prompt exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:9872` → `stm.phase_fields`, `KeyError: 'name'`) |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_recall[nameless-node-prompt_recall]` | RED | `bug-268: memory recall (prompt_recall) exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:13344` `emit`, `KeyError: 'name'`) |
| bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_recall[nameless-node-session_start]` | RED | `bug-268: memory recall (session_start) exited 1 on a wrong-shaped focus graph: …` (traceback through `cli.py:13347` `emit`, `KeyError: 'name'`) |
| R0.5 step 3 | `test_the_cost_prompt_set_is_forty_synthetic_prompts` | RED | `…/tests/fixtures/injection_capture/prompts.txt does not exist (spec #files: new in release A)` |
{#nodes-table}

Fixture checks run before each AC assertion, and each one names its own failure. One of them
fired on the first run: AC-0.8's capped call dropped the content block, so the payload carried
no canary. AC-0.8 was rewritten to make three calls (see [[#readings]] item 7). The check is
now satisfied at base, and the node fails on the missing record. {#nodes-fixture}

## Mutation to node map {#mutations}

| Mutation | Must fail |
|---|---|
| M0-1 render into the delivered `parts` | `test_the_capture_never_changes_the_payload[token-stop]`, `[byte-fit]`. Mode `full` at the tier-3 stop builds the capture-only bundles, so a render into `parts` changes stdout |
| M0-2 capture-only bundles call `_retrieve` | `test_capture_only_bundles_emit_no_recall_events`. The on arm runs in mode `full` at the tier-3 stop, and the `retrieved` events grow |
| M0-3 marker committed when stored, not delivered | `test_a_composite_stored_as_dropped_is_sent_on_the_next_prompt`, and the existing `test_scanorder_r2_l120.py::test_s3_…` |
| M0-4 every block `delivered` | all five AC-0.3 tests: `…dropped_bytes`, `…dropped_tokens`, `…content_after_a_tier_1…[full,names]`, `…suppressed_unchanged`, `…suppressed_cadence`. `test_names_mode_…` fails too |
| M0-5 step 1: the stop returns before recording the tripping bundle | `test_content_after_a_tier_1_token_stop_is_stored_with_text` (the trip must be `ledger_codec`, `dropped_tokens`); `test_bundles_past_the_token_stop_…` (the tripping `harbor` bundle is in `calib["tier3"]`); `test_names_mode_…` (exactly one tripped bundle) |
| M0-5 step 2: before rendering the content block | `test_content_after_a_tier_1_token_stop_is_stored_with_text[full]` and `[names]` |
| M0-6 step 1: a `prompt` field; step 2: the canary copied into a second field | `test_prompt_text_appears_only_inside_block_text` (exact key set; canary absent outside `blocks[*].text` and absent from every non-text block field) |
| M0-7 step 1: prune the current day | `test_a_day_file_over_the_bound_stops_appending` (`today.exists()`) |
| M0-7 step 2: prune nothing | `test_old_and_oversize_day_files_are_pruned_and_listed` |
| M0-7 step 3: keep appending over the bound | `test_a_day_file_over_the_bound_stops_appending` (size unchanged; one `over_bound`) |
| M0-8 step 1: a failed append raises; step 2: no `errors.jsonl` line | `test_a_failed_append_keeps_the_payload_and_is_counted` (rc and stdout compared to a capture-off control; one `append_failed`) |
| M0-9 recall records only the named hits | `test_a_packed_recall_writes_one_block_per_hit` (12 blocks; 4 `dropped_bytes`) |
| M0-10 step 1: no `.gitignore` | `test_the_capture_dir_ignores_itself` |
| M0-10 step 2: `.gitignore` only when the dir is created | `test_an_existing_capture_dir_without_gitignore_gets_one`, `test_an_errors_only_write_into_a_bare_capture_dir_is_ignored` |
| M0-11 back to a silent `comp = ""` | `test_a_raising_composite_build_is_recorded_and_counted` |
| M0-12 step 1: switch ignored; step 2: it also disables the `query.log` row | `test_the_capture_switch_leaves_telemetry_on[env]`, `[marker]` (no dir; one more `query.log` row; the call's events) |
| M0-13 the verb's pack branch writes a record | `test_a_verb_recall_with_pack_writes_no_capture_record` |
| M0-14 step 1: `names` builds the skipped bundles | `test_names_mode_records_later_bundles_as_not_built` (`capture_built == 0`; `not_built` present) |
| M2-1 step 1: keep stoplist words; step 2: keep unknown plain words | both `test_stopwords_and_unknown_plain_words_are_not_printed_as_members` params (`the`; `buigger`, and `question` when not held) and `test_a_topic_with_no_printable_member_is_not_emitted` |
| (no spec id; proposed M-268) a wrong-shaped graph reaches `phase_fields` again, or its failure is not counted | all nine `test_a_wrong_shaped_focus_graph_never_crashes_*` nodes (exit 0 and no traceback; then `stm_error` on the record; then the `capture:` line count) |
| M0-14 step 2: the mode file ignored | `test_the_mode_file_selects_the_path`. Both words are written to the file, so neither release default can hide an ignored file |
{#mutations-table}

## Mock registry {#mock-registry}

There are no rows to add. Nothing is patched or mocked. The inputs are all real: a corrupt
focus-graph file, sparse day files, a dangling link, file and directory modes, a real git
repository, and a real sandbox daemon (AC-0.11's verb leg, `RMX_NO_EMBED_WARMUP=1`,
`RMX_RERANK=0`). {#mock-none}

## Stale citations reconciled at 606c0c8 {#citations}

- AC-0.6 cites `tests/test_scanorder_r2_l120.py::test_s3_a_composite_the_cap_dropped_is_delivered_when_there_is_room`.
  It exists (line 209) and is green at base.
- Caller census `#census`, re-counted at base over `src/`, `eval/` and `scripts/`:
  `scan.scan_prompt` has 1 caller (`cli.py:9827`); `scan._composite_text` 1 (`scan.py:1058`);
  `hook_budget.fit_blocks` 5 sites (`cli.py:1378`, `cli.py:9495`, `handoff.py:924`,
  `recall_pack.py:202`, `scan.py:1065`); `recall_pack.pack` 1 (`verbs.py:1177`);
  `build_topic_composite_pending` 2 (`scan.py:942`, plus the `composite.py:163` wrapper behind
  `build_topic_composite`). These match the spec's counts.
- `#r0-7-registry` and `#seen` say bug-256's registry remedy names "stderr the hook keeps".
  At base the row already reads "the hook discards stderr, so stderr is not a surface" (L139),
  so those two spec paragraphs are stale. R0.7 still asks for one stderr line for callers that
  keep stderr, and AC-0.16 tests it.
- AC-0.12 says "the existing hooks-in-sync tests". `tests/test_hooks_reproducible.py` tests the
  `--check` mechanics, and no existing test pins the generated block byte for byte to base. As
  a reference I recorded the base sha256 of `json.dumps(_claude_hook_block(Path("/nonexistent/.refmatrix")), sort_keys=True)`,
  computed with `HOME=/private/tmp/claude-501/hb315`:
  `770e217a330ddb6092111724be59f5a3de2984772f73c399e5216839b0cf2019`. Recompute it the same
  way on the GREEN tree. `rmx install-hooks --check` against installed hooks is the lead's
  gate.
{#citations-list}

## Readings of what the spec leaves open {#readings}

These are pinned in the tests. A ruling that differs means editing the test, not working
around it.

1. **The record file** is `<store root>/injection-capture/capture-<UTC yyyymmdd>.jsonl` (R0.4).
2. **"The printed payload"** is stdout. The delivered and marker texts, joined in order, must
   equal it, allowing only the one newline `click.echo` adds. A marker counts as delivered
   when its state is `delivered` or absent. `payload_sha256` is sha256(stdout) and equals the
   events' `block_sha`.
3. **`budget_bytes`** is `hook_budget.budget("scan_prompt")` (9,000), not the `cap - 1`
   passed to `scan_prompt`. **`max_tokens`** is the value passed. **`v`** is 1. **`ts`** has
   `event_ts`'s shape. **`rmx_version`** is `refmatrix.__version__`.
4. **The `capture:` line** is exactly one line starting `capture:` (wrapped continuations are
   joined). The counts are read lexically: `N captured of M hook call(s)`; `<reason>=N`,
   `<reason>: N`, `<reason> N` or `N <reason>` for `errors.jsonl` reasons and for
   `composite_error(s)`; and the words `invalid mode`.
5. **A "hook call"** is a `query.log` row with `invocation` `hook`. Control calls that must
   not count use `RMX_INVOCATION_SOURCE=internal`.
6. **Block fields.** Every scan block carries `i, kind, state, bytes, sha256, names,
   dedup_rows`. When a block has text, `bytes` and `sha256` describe that text. A
   `recall_hit` carries `kind, state, name, rank, mtype, scope, hook_bytes, body_bytes,
   body_sha256`. For a bodied hit, `body_bytes` and `body_sha256` describe the memory's
   content, which is what the pack's spans count. `hook_bytes` is the hook line's bytes with
   its newline. `pruned` lists file names or paths, compared by basename.
7. **AC-0.8's "uncapped render" case** (corrected by ruling L155). The canary is a prompt term
   the store does not hold, so only the content block can carry it. It carries it in two
   places: the `# refmatrix content matches for prompt:` header (the first eight terms), and
   the bundle's first body line, its anchor `=== context for `<candidate bag>` ===`. The first
   reading allowed only the `# refmatrix` line, and it failed on green-315's faithful render
   (R0.1). In a block that is not delivered, a canary line is now allowed only if it is the
   `# refmatrix` header, or the first `=== context for` line of a block of kind `content`.
   The check that the canary is in no record field outside block text is unchanged. Call 1
   delivers the content block. Call 2 is the same prompt with tier 1 tripping the token stop,
   so the content block is `dropped_tokens` and the canary sits only in that block's header
   and anchor. Call 3 is the canary alone and produces nothing. Proof of the widened node
   (`l155-*.log`, each run under lockf). At base it is still RED, failing on the missing
   record (`l155-red-base.log`, exit 1). On green-315's working tree it passes
   (`l155-green-wip.log`, `l155-green-wip-after.log`, exit 0). This was a snapshot of its
   uncommitted `src/` and prompts fixture, copied into `/Volumes/littlebig/refmatrix-315-verify`,
   because its branch tip held no GREEN commit. Two mutations make it fail (exit 1), each
   restored before the next run (`l155-mut.sh`). MA writes the prompt into the record's
   `session` field: `the canary is in a record field outside blocks`. MB appends a second
   candidate-bag anchor carrying the prompt to a stored content block: `the canary outside a
   dropped block's header: ['=== context for `zqxcanary315 …` ===']`.
8. **AC-0.7's budget.** The per-prompt pack carries no bodies (25.1 d3), so the test uses the
   SessionStart pack. A budget that names 8 hits and bodies 2 exists only when a body block is
   shorter than a hook line. The fixture memories therefore carry a long title and a short
   two-line content (`Rule NN.` / `BODYQNN`), and the budget is derived from an uncapped pack.
   It runs the no-daemon replica fall-through leg ("reading the replica"). The daemon-routed
   leg is not covered by AC-0.7.
9. **AC-0.9 without injection hooks.** The spec says "bound and clock injected" but names no
   writer function to inject into. The tests are black-box instead: the real clock and the
   real 64 MiB bound, with day-file names and mtimes set relative to now, and sparse files for
   the large ones. A run that crosses UTC midnight fails and says to rerun. "Another process
   removed it" is modelled by an old day file that is a dangling link: it is listed, then
   stat says ENOENT. **Limitation:** if GREEN uses `lstat`, or unlinks without a stat, that
   node passes without exercising the race path. Proving the race directly would need a named
   writer with an injectable unlink. The lead may want to name one.
10. **Tests that are RED at base only through a positive control.** AC-0.6 (labelled a
    guard), AC-0.15 and AC-0.18 would pass trivially at base: no capture dir means nothing to
    see. Each therefore also asserts that the capture really wrote something, so it fails at
    base on that check, and the guard half is proven by its mutation.
11. **R0.5 step 3's prompt set.** `tests/fixtures/injection_capture/prompts.txt` is GREEN's to
    author (spec `#files`). The test pins only the static half: 40 distinct lines, at least 10
    carrying a hub word as a plain word, and no transcript-looking line. "At least half trip
    the token stop" can only be checked on the copy of the live catalog, so it belongs to
    AC-0.13's measurement.
{#readings-list}

## Not followable as written {#not-followable}

- **AC-2.0's empty-topic case cannot reach the filter through the public path.** The 0.84.0
  grounded-topic gate (`_has_grounded_member`) runs first, and every member it accepts is
  identifier-shaped, so it is printable. `test_a_topic_with_no_printable_member_is_not_emitted`
  therefore calls `composite._render_gmd` directly, which is where `#census` puts the filter. A
  GREEN that put the filter anywhere else would fail this test while behaving correctly.
  Whether a composite with zero emitted topics prints its header at all is not specified, and
  is not pinned.
- **AC-0.12, 0.13, 0.14, 0.17** are gates and measurements. They have no RED.
- **AC-0.16's input.** A corrupt focus graph works only when the call carries no session; see
  the defect below. The test runs with no session, so only the composite reads the ring.
{#not-followable-list}

## Deliberate test changes (ruling L156) {#l156}

R2.0's member filter asks the store whether it holds each plain-word member. Three existing
nodes in `tests/test_composite.py` called `composite._render_gmd` with a bare `object()` store
and plain-word members. On green-315's tip they failed with `AttributeError: 'object' object
has no attribute 'resolve_concept_ids'`, and that raise stays. The three nodes are
`test_intra_cluster_emits_real_verb_not_cooccurs`, `test_intra_edges_zero_drops_grounded_block`
and `test_ltm_expansion_ranks_sparse_first_and_dedups`. {#l156-why}

Each now passes `_ConceptStore(<its members>)`, a store double that answers only
`resolve_concept_ids`, returning an id for each word it holds. The members (parser / lexer /
tokens, alpha / bravo) all print as before, and the tests keep their subject: intra-cluster
verbs and LTM expansion. Their assertions are unchanged. The double is registered in
[[test_mock_registry#registry]] as a double of a dependency (`internal-active`). It graduates
together with these tests' `build_context` patch. The filter itself is tested on a real store in
`tests/test_stm_composite_members.py`. The proof against green-315's committed tip `c3e04d3`
is in the `l156-*.log` and `l155-c3e04d3-*.log` files (script `l155-156-proof.sh`, run under
lockf). {#l156-what}

rel: amends -> [[test_mock_registry#registry]]

## bug-268 (ruling L152) {#defect}

The defect found while writing AC-0.16 is bug-268: `stm.phase_fields` crashes `rmx scan-prompt`
and `rmx memory recall` when a focus graph is valid JSON of the wrong shape. L152 folds it into
release A beside bug-256. Its nine nodes are in `tests/test_injection_capture.py`: three
shapes (`[]`, `{"nodes": {"x": 1}}`, a node with no `name`), each on `scan-prompt` (the hook's
`--stdin-json` envelope, `cli.py:9872`) and on both recall routes. The per-prompt route
(`cli.py:13344`) runs `--stdin-json --recent --pack`, the recent leg, which needs no embedder.
The session-start route (`cli.py:13347`) runs `--session-start --pack`. Each node asserts exit 0
with no traceback, the payload (for `scan-prompt`, byte-identical to the call with the
composite absent; for recall, the pack), the call's recall events, `stm_error` on the capture
record, and one `stm_error` on the `capture:` line. All nine are RED at base with exit 1 and
the tracebacks tabulated in [[#nodes]]. The repro is in `probe.log`. {#defect-body}

**A reading the lead should confirm:** L152 says the corruption is "counted on the capture
record" but names no field, and R0.2's list has none for it. These tests add `stm_error` to
the record schema: the class and message, else null. AC-0.8's exact key set includes it, and
AC-0.1 asserts it is null on a healthy call. On the `capture:` line it is read like
`composite_error`. When the composite's own build also fails on the same file (the `[]`
shape), `composite_error` is set as well. The tests do not forbid that. {#defect-reading}

## L178 fold RED (bsd-315 r1) {#l178}

The RED half of the fold in ruling L178. The source is unchanged from GREEN's `51bbdfb`. Commits:
`dfbfdc3` adds the tests, and `7a4a94b` fixes AC-0.16's setup and sets the M1 floor at a quarter
build. Every run went through `scripts/lane-mini.sh`, with logs in `workflow/review-output/`.
The run at `7a4a94b` (`315-l178-red-at-51bbdfb.log`) ended exit 1: 25 failed, 43 passed. Every
failure is the intended E line. {#l178-run}

rel: depends-on -> [[bsd-315-r1-51bbdfb]]

| Item | Node | At 51bbdfb |
|---|---|---|
| S1 / bug-276 | `test_a_capture_failure_never_changes_the_exit_or_loses_the_capture_line[scan_prompt-surrogate, scan_prompt-dir-0o300, prompt_recall-surrogate, session_start-dir-0o300]` | RED: `bug-276: <route> with <fault> exited 1` (UnicodeEncodeError on the lone surrogate; PermissionError from `os.listdir` in the pruner) |
| S2 / bug-277 | `test_a_composite_whose_printed_members_did_not_change_is_suppressed` | RED: `bug-277: a composite whose printed members did not change: [... ('composite', 'delivered')]` |
| S3 | `test_stm_composite_members.py`: the store holds `the` | green (the fixture is stronger, the behaviour is right); M2-1a KILLED (`315-l178-mut-m2-1a.log`: 3 failed, `printed members [..., 'the', ...]`) |
| S4 / bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_scan_prompt[int-node, list, nameless-node]` | RED: `bug-268: the composite raised on the corrupt graph: "AttributeError …" / "KeyError: 'name'"` |
| S4 / bug-268 | `test_a_wrong_shaped_focus_graph_never_crashes_a_reader[focus-hook-*, focus-context-*, pin-*]` (12) | RED: `focus hook --event input exited 1`, `focus context exited 1` or `said it 0 times`, `pin said the corrupt graph 0 times` or a `pin` AttributeError |
| S4 / bug-268, non-finite turn | `…scan_prompt[nonfinite-turn]`, `…recall[nonfinite-turn-prompt_recall, nonfinite-turn-session_start]`, `…a_reader[*-nonfinite-turn]` | RED: exit 1, `OverflowError: cannot convert float infinity to integer` (`{"turn": Infinity}` passes `focus_graph_problem`; kept by the lead's ruling) |
| S4, AC-0.16 re-pointed | `test_a_raising_composite_build_is_recorded_and_counted` | green: re-pointed to a child-process patch of `composite.topic_composites` (registered). M0-11 KILLED (`315-l178-mut-m0-11.log`: `bug-256: the composite failure said on stderr: []`) |
| M1 | `test_bundles_past_the_token_stop_are_built_and_stored_as_dropped_tokens`, capture_ms floor | green; X-1 KILLED (`315-l178-mut-x-1.log`: `capture_ms 0.5 does not cover 2 built bundle(s)`) |
| M2 (X-3) | `test_a_day_file_the_pruner_cannot_remove_is_counted_and_kept` (P4) | green; X-3 KILLED (`315-l178-mut-x-3.log`: `errors.jsonl: [] == ['prune_failed']`) |
| M2 (X-2) | `test_a_capped_errors_file_is_named_on_the_capture_line` | RED: `a capped errors.jsonl is not named: 'capture: …'` |
| M3 | `test_the_coverage_window_starts_at_the_first_capture_record` | RED: `… 1 captured of 4 hook calls …` |
{#l178-table}

**These could not fail first:** S3, M1, the P4 node and the re-pointed AC-0.16. Each pins
behaviour that `51bbdfb` already gets right, so its proof is the mutation it kills. The kills are
M2-1a, X-1, X-3 and M0-11, each from a scratch commit (`efc80e8`, `e096f76`, `b53c7af`,
`d13649c` on `scratch-l178-*` branches, never merged). X-2 has a RED node and has not been run
as a mutation: it is re-run after GREEN. {#l178-not-first}

**Setup error fixed:** the first run's AC-0.16 child exited 2 (`can't open file '…/rmx'`).
`cli_entry` re-execs `sys.argv` unless `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` is set. {#l178-setup}

**Contracts pinned:**
- a corrupt graph is said in one stderr line containing `focus graph` and `corrupt` (GREEN's
  bug-268 wording), once per process;
- the `capture:` line names a capped errors file with the token `errors_capped`;
- with no capture record at all, every hook row counts in the coverage, so a capture that never
  wrote reads 0 of N (AC-0.10's existing node keeps that).
{#l178-contracts}
