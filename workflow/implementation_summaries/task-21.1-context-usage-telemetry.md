---
gmd: "0.1"
id: impl-task-21.1-context-usage-telemetry
title: "Task 21.1: agent context-usage telemetry and the ONE recall-event schema (GREEN + ch-bsd r1 remedy)"
tags: [implementation-summary, telemetry, recall-events, session-pointer, plan-21, task-21.1]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-10-19
---

# Task 21.1: telemetry that can count how the agent uses rmx context {#root}

rel: implements -> [[task-21.1-context-usage-telemetry]]
rel: part-of -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[bsd-task21.1-context-usage-r1-d3ec62d]]
rel: amends -> [[plan-9-context-cost-telemetry#q2]]

Branch `task-21.1-context-usage-telemetry`, clone `/Volumes/littlebig/refmatrix-task-21.1`.
RED `b335856`, GREEN `d3ec62d` (2026-10-16), test-side fixes `43f1d0c` / `5e58139` / `db725be`,
spec round 13 `b885637`, round-13 RED `d926d85`, then this remedy commit. This summary also
answers ch-bsd r1 #m5 (GREEN shipped with no summary).

## Why {#why}

The 2026-10-07 exploration counted 3 CLI `context` calls against 1,119 agent greps and could not
count MCP calls at all. No `query.log` row carried a session, a query id or a cwd. Nothing recorded
which recalled item reached a payload, or whether the agent later used it. Plan-21's 21.2-21.4 and
plan-19's 19.2/19.5/19.6 had no instrument to read. {#why-lead}

## GREEN (d3ec62d) {#green}

| area | what shipped |
|---|---|
| session layer (R9, D1-D9) | `verbs.resolve_session_source(..., purpose=)` is THE resolver: `read` gives the labelled newest ring, `write` raises `SessionUnresolved`, `event` gives null. Pointers and the pointer-error log live under `<global root>/by-pid/` with one locked writer (`stm._append_error_rows`). The SessionStart writer `rmx focus hook --event session-start` migrates, surfaces, consumes and prunes. There is one envelope parser, `stm.read_hook_envelope`, and the pre-prompt snapshot. |
| telemetry rows (R1-R8) | Rows carry `invocation` (`mcp` / `agent` / `hook` / ...), `session`, `query_id`, `cwd`, `root` and `budget_s`. `classify_outcome(budgeted=)` decides by exception type. `row_provenance` is the one classifier. `rmx telemetry --agent-usage` is new. |
| recall events (R10-R12) | `recall-events.jsonl` has `RECALL_EVENT_FIELDS_V1`, `event_kind`, `recall_channel` and the ONE writer `emit_recall_events`. Renderers return byte spans. `used` events come from `memory_get_by_name`, `context_by_name` and `focus_note` through a bounded, backwards delivered-set lookup. |

Interpretations GREEN made silently were the ones r1 charged: #b1, #b2 and #s1. They are now
decided in the spec's [[task-21.1-context-usage-telemetry#rev-round-13]] and implemented as below.

## ch-bsd r1 remedy (2026-10-19) {#remedy}

| finding | fix |
|---|---|
| #b1 flagless recall row guessed | `telemetry._recall_flags_of` returns None when no flag is present, and `channel_of_row` returns None. `agent_usage_report` prints `recall_unflagged=<n>` and puts such a row in no channel. |
| #b2 `record_miss` switch | Removed from `verbs.resolve_session_source` and `telemetry.resolve_event_session`. R9 now records a miss for every purpose and invocation. |
| #b3 table recall had no spans | `cli.memory_recall`'s table mode renders the table, plus any degree context blocks, to text with `_render_table_text` (natural width, so a long name is never cut to `…`). It writes that text through `_RecallCall.echo`, so delivered events get `offset_bytes`/`bytes`, `payload_bytes` and `block_sha`. The `[global]` marker is escaped: rich used to swallow it as markup. |
| #s1 context_by_name | The `used` lookup runs first and passes `exclude_query_id=<this call>` down to `delivered_in_session`. Any other call's delivery now counts, including an earlier context call's. `emit_context_call` hands retrieved, delivered and used events to `emit_recall_events` in one call (`call_events` builds them). The now-dead `DeliveredSet.channels` is removed. |
| #s2 silent pointer-error writes | All 12 `record_pointer_error` call sites check the result: `if not ...: stm.say_unrecorded(reason)`, one wording. `prune_dead_pointer_files` and `drop_legacy_pointers_migration` return `(done, skipped)`. The SessionStart line adds `prune_unreadable=<n>` / `legacy_pointers_undropped=<n>` when non-zero. |
| #s3 two scopes for one store | `telemetry.norm_path` (cached `realpath`) is the one spelling. `stm.scope_key` is that function, used by the writer, `_row_in_scope`, the per-root watermark hash and file, `dropped_by_root` (writer and handoff reader) and the migration rows. The classifier's private `_norm_tmp` is deleted, and `_test_base` matches `rmx-` under `norm_path("/tmp")`. |
| #s5 duplicated shapes | One span finder, `context.name_spans` (replaces `telemetry.spans_by_name` + `context.json_name_spans`). One item enumerator, `bundle_items`: `render_text_spans` records only line positions and raises if the two counts differ. One meta merge, `context.apply_item_meta`, used by the daemon recall op, `cli._hits_with_meta` and `annotate_items`. |
| #m1 dead `scan.read_stdin_prompt` | Deleted, together with its scan to cli import. The D9 caller list in `stm.read_hook_envelope` is updated. |
| #m2 scan-prompt JSON delivered | Only items with a found span are delivered. The overwritten `_finish` and the unused `items` are gone. `telemetry.call_events` also refuses an unspanned delivered item for every surface and counts it on stderr (`delivered_unspanned=<n>`). |
| #m3 skew constant | `workflow/deferral_registry.md` row: 19.0 R0 measures S. The comment's unbacked "1-3 s observed" is dropped. |
| #m4 hand-typed log path | The `handoff.session_pointer_anomalies` hook clause takes its path from `stm.errors_log_path()`. |
| #s4 AC-6 blocked (not assigned, recorded) | A deferral-registry row records the user's cutting command. |
| plan-9 r5 #m-11 | `telemetry.CountingStream.close()` closes the proxy only and never flushes the inner stream. A closed consumer now prints the interpreter's one BrokenPipe line, not a second traceback naming `telemetry.py`. This was checked A/B with a `| head -1` script. The module docstring now says `REFMATRIX_NO_TELEMETRY` gates only the log writes. |
| plan-9 r5 #s-5 | The Q2 proxy-overhead table is recorded in [[plan-9-context-cost-telemetry#q2-measured]]. |

## ch-bsd r2 remedy (2026-10-19) {#remedy-r2}

rel: derives-from -> [[bsd-task21.1-context-usage-r2-b9660ba]]

| finding | fix |
|---|---|
| r2 #b1 `--recent` / `--subject` table logged 0 delivered | Both text tables of `rmx memory recall` now go through ONE path, `cli._echo_recall_table`. It renders at natural width, escapes every cell, puts each cell on one line, writes through `rec.echo` and sets `rec.delivered`. The recent table's `console.print` is gone, so no third table can print around the capture. |
| r2 #m1 text spans found by search | `context.name_spans` is JSON-only now. A text payload brings its renderer's spans: the table records each delivered row's name at the start of its own name cell (row i = body line i), and `_render_memory_gmd_spans` records each name in its own `## <name>` heading. `_RecallCall.emit` spans nothing it was not told, and `call_events` counts any unspanned row. A memory named `name`, `rank` or `1` now spans its own name cell. |
| r2 #m3 empty root resolved to cwd | `telemetry.norm_path` returns None for a null or empty path, and only absolute spellings are cached. `stm.scope_key(None)` is None. A null or empty `root` row is an `unscoped-row` to every scoped reader and in scope for none. `migrated_from` is spelled by `scope_key` too. |
| r2 #s1 five remedies unguarded | The test-engineer added a killing test for each, proven in a mutated copy (`3e399f0`): the `[global]` label, `CountingStream.close` not flushing, a long name printed whole, `prune_unreadable=1` / `legacy_pointers_undropped=1`, unspanned delivered counted and not written, and the STM-hook clause naming `stm.errors_log_path()`. |
| r2 #s2 / bug-134 live-log guard false positive | `3e399f0` attributed appended rows. That opened a live log under the 23.0 audit hook, so `ef83617` made the per-test guard stat-only: an inode change or a shrink fails, and growth is recorded to the sandbox growth ledger. The 23.0 end-of-run check (`scripts/sandbox-proof.sh`) then reads each range once, outside the sandbox. Registry rows: `d7ef3f7`, `cf7e4bb`. |
| r2 #m2 AC-11e accepted `[]` | AC-11e now asserts `["concept"]` exactly (`3e399f0`). |
| r2 #m4 AC-11f retry on an unmeasured cause | The AC-11 setup records each retried attempt's query.log outcome (`3e399f0`). |
| r2 #m5 stale Open section | Refreshed in `89c597d`, and again in this round (r3 #s2). |

## ch-bsd r3 remedy (2026-10-19) {#remedy-r3}

rel: derives-from -> [[bsd-task21.1-context-usage-r3-cf7e4bb]]

| finding | fix |
|---|---|
| r3 #m1 table rewrote some names; prefix span check | `_echo_recall_table` adds cells as rich `Text`, and `_render_table_text` renders with markup, emoji and highlight off, so `fix:smile:now` and `trail\` print verbatim. A span requires the name, then the row's label, then the cell padding. A prefix match is no longer a span. |
| r3 #m2 `[global]` label left to the query caller | The label comes from `row["scope"] == "global"` inside `_echo_recall_table`, for every route. `--recent` / `--subject --scope both` now label global rows like the query table, and the query caller no longer adds the suffix. |
| r3 #s1 GMD spans and the one-line rule unguarded | Guarded by the test-engineer (`26f4a20`): GMD spans on their own headings, one-line cells, verbatim names, and the recent `[global]` label. |
| r3 #s2 stale summary | This revision. |

## Verification {#verification}

- r1: `workflow/review-output/task21.1-r1-remedy-full.log`.
- r2: `workflow/review-output/task21.1-r2-remedy-full.log`, then `task21.1-r2-guard-full.log`
  after the guard fix: 21 failed = 20 clone-only + AC-6, content check 0 offending.
- Final (r3), through `scripts/sandbox-proof.sh`: `workflow/review-output/task21.1-r3-final-full.log`.

## Open {#open}

- The AC-6 frozen fixture waits on the user (deferral registry row, cutting command named).
