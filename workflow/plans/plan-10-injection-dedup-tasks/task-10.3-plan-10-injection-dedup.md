---
gmd: "0.1"
id: task-10.3-plan-10-injection-dedup
title: "Task 10.3: a compaction marker (PreCompact and SessionStart compact|clear, 19.6 R8a's writer) resets the injection ledger, proven through the generated hooks, and the saving is re-measured live on the same corpus"
tags: [task, plan-10, hooks, stm, compaction, telemetry, measurement]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-09-15
  updated: 2026-11-13
---

# Task 10.3: compaction marker and the live re-measure {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (rewritten 2026-11-13 on the reopening; was cancelled 2026-09-15; ch-bsd spec
> review next)
> Depends on: [[task-10.2-plan-10-injection-dedup]] (the ledger and its `since_ts`).
> Builds: the compaction-marker WRITER that [[task-19.6-phased-context-and-topic-cache]] R8a names
> (`rmx focus hook --event compact-marker` + the `session-start` dispatch); 19.6 becomes a reader.

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-10.2-plan-10-injection-dedup]]
rel: realizes -> [[task-19.6-phased-context-and-topic-cache]]
rel: related-to -> [[task-25.1-recall-hook-byte-budget]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: depends-on -> [[impression_bsd_guard_cannot_fire]]
rel: depends-on -> [[impression_bsd_tests_bypass_wiring]]
rel: depends-on -> [[impression_bsd_cost_measured_idle]]

## Why {#why}

The ledger records what was SENT, not what SURVIVES ([[plan-10-injection-dedup#hazard]]).
Compaction is the moment the two diverge, so after it nothing may be held: the next delivery of
every item renders full. 10.2's turn window bounds the damage of a missed signal to 10 turns; this
task removes it for the signals Claude Code does send. {#why-lead}

Two signals, because neither is trustworthy alone: **PreCompact** fires before every compaction
(manual and auto), and **SessionStart** fires after it with `source: "compact"` (and `"clear"`
after `/clear`). rmx already runs a command on each: on PreCompact `rmx focus summarize --promote`,
the recall and the save-state checkpoint; on SessionStart `rmx focus hook --event session-start`
(matcher `startup|resume|clear|compact`, `hooks.py:255-258`, 21.1 D4). 25.1 R11 adds `rmx
recall-state --max-bytes N` on `compact|clear`.

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| f1 | ONE marker for plan-10 and 19.6: this task builds 19.6 R8a's writer as 19.6 named it (`rmx focus hook --event compact-marker`, its own PreCompact entry, plus the `session-start` dispatch on `source` = `compact`) and adds `clear` | two windows over one context would be the four-call-sites shape again ([[feedback_converge_repeated_shapes]]); 19.6 is pending (Wave 3), this task lands first, so it owns the writer and 19.6 reads it |
| f2 | The marker is written by the STM focus hook, not by 25.1 R11's `recall-state` entry | `recall-state` is a reader (the handoff); a read verb that also writes session state would hide a side effect in it; the focus hook already parses the SessionStart envelope's `source` and owns STM session state |
| f3 | The marker lives in STM session state: a ring event `{"kind": "marker", "source": …}` (provenance; refs empty) and `last_marker: {ts, source, turn}` in the focus graph | the graph is already loaded once per prompt by `stm.pre_prompt_state` (10.2 R2 reads the turn there), so the marker read is free; the ring is the record the graph is rebuilt from, so `rebuild_focus` restores `last_marker` from it |
| f4 | `resume` and `startup` write no marker | `startup` is a new session (an empty ledger by session id); `resume` reloads the transcript, so what was held is held again |
| f5 | A failed marker write exits non-zero with ONE `Error:` line on stderr | an error that stops an operation fails loudly on the console (the user's 2026-11-10 rule); the cost of a missed marker is bounded by 10.2's window, so the hook does not need to block anything |

## Requirements {#requirements}

1. **R1 The writer.** `stm.mark_compaction(root, session, *, source) -> dict` appends the ring
   event and sets `last_marker` in the graph (one write path). It is called by: {#r1}
   - `rmx focus hook --event compact-marker` (a new `--event` choice), generated as its OWN
     PreCompact entry, not chained into the summarize / recall / save-state commands, present
     whether or not the PreCompact recall entry is generated (25.1 R7 may drop it);
   - `rmx focus hook --event session-start` when the envelope's `source` is `compact` or `clear`
     (today's entry; its matcher already covers both).
2. **R2 Ring readers ignore the marker.** `_apply_turn` is never called with it as an input (no
   turn increment, no refs); `helix.build_index`, `composite.build_topic_composite`, `focus show`
   and `rebuild_focus`'s replay treat `kind == "marker"` as a no-op for the graph and restore
   `last_marker` from the newest one. {#r2}
3. **R3 The reader.** 10.2's `since_ts` becomes `max(session's first ring event ts,
   last_marker.ts)`: after a marker nothing is held, and the backwards read stops there. 19.6 R8a's
   "in the window" reads the same `last_marker` (its next revision cites this requirement). {#r3}
4. **R4 Failure surface.** `mark_compaction` failing (ring or graph unwritable) → exit non-zero,
   one `Error: compaction marker not written: …` line on stderr, no traceback; the session-start
   entry's existing pointer write and surfacing still run first. {#r4}
5. **R5 Live re-measure (the plan's execution contract).** {#r5}
   - **Before:** [[measurement-injection-already-held-2026-11-13]] (held 48.0%; hook-channel (a)
     43.2% / 51.9%; compaction-aware 42.1%), 10.4's after-numbers and 10.2's offline replay
     ([[task-10.2-plan-10-injection-dedup#r10]]).
   - **After:** deployed with 10.2, measured after the fleet has been busy for at least 5 working
     days ([[impression_bsd_cost_measured_idle]]), over at least as many sessions per store as the
     before window, read-only and counts only, with `rmx telemetry --context` and `dd-10r`'s
     criteria (a) on hook channels: per channel, bytes per human prompt, the share of delivered
     items rendered as pointers, `pointer_saved_bytes`, the held share of FULL deliveries (what
     the window and the marker let through), and how many pointers fell after a marker (must be
     0).
   - **The floor check.** Over items rendered as pointers, the share later fetched or used (21.5
     `used` events whose `ref_query_id` is a pointer delivery, plus a main-loop `Read` / `rmx memory
     get` / `rmx context` of the item within 3 turns), against the same share for full deliveries.
   - **The window check.** The gap distribution of re-deliveries in STM turns (human turns after
     10.4), in the measurement's buckets.
   - **Bands, written here before any number:**
     - UserPromptSubmit bytes per human prompt (scan-prompt + recall) fall ≥ 20% → keep;
       5-20% → keep and record; < 5% → the user decides whether the mechanism earns its place.
     - Floor: with ≥ 30 pointer items eligible, a fetched-or-used share under half the full items'
       share → the user decides (pointer content or N), nothing is changed silently.
     - Window: fewer than 50% of re-deliveries at gaps 1-10 → N is revisited with the user.
   - Written to `workflow/measurements/injection-degrade-2026-11.md` (the after section).

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 10.2's fixture (store, ring, event history), through the GENERATED hook
config: the test builds it with `hooks._claude_hook_block(...)`, takes the entry under test and
runs it with `bash -c`, the envelope on stdin and the sandbox `HOME`. A test that calls
`mark_compaction` directly does not show the hook is wired ([[impression_bsd_tests_bypass_wiring]]);
those exist only in addition. {#acceptance-lead}

1. **AC-1 Generated config.** PreCompact holds exactly one entry whose command is `rmx focus hook
   --event compact-marker`, in its own entry, with and without the PreCompact recall entry (both
   generator settings); the SessionStart `startup|resume|clear|compact` focus entry is unchanged;
   `rmx install-hooks --check` is clean after `--apply`.
2. **AC-2 PreCompact resets.** X is held (pointer at turn t); the generated PreCompact marker entry
   runs; the next per-prompt recall and scan-prompt render X in full. RED at the 10.2 base.
3. **AC-3 SessionStart resets.** Same with the generated SessionStart focus entry and
   `{"source": "compact"}`, and with `{"source": "clear"}`; with `{"source": "resume"}` and
   `{"source": "startup"}` X stays a pointer (no marker written).
4. **AC-4 The ring stays clean.** After a marker: the graph `turn` is unchanged; `helix.build_index`
   and the topic composite produce byte-identical output with and without the marker event in the
   ring; `rmx focus rebuild` restores `last_marker` from the ring.
5. **AC-5 The read stops at the marker.** With a marker one minute old and a 32 MB event history,
   `held_items`' `bytes_read` is below the bytes written since the marker plus one 64 KB block.
6. **AC-6 Loud failure.** An unwritable ring: the generated marker entry exits non-zero with one
   `Error:` line and no `Traceback`; the next prompt still renders (10.2's window still applies).
7. **AC-7 Mutations that must FAIL a test:** the PreCompact marker ENTRY removed from the generator
   (the call site, not the function: AC-1, AC-2); the marker chained into the summarize command
   (AC-1); the `session-start` dispatch dropped (AC-3 compact); `clear` left out (AC-3 clear);
   `resume` writing a marker (AC-3); the reader ignoring `last_marker` (AC-2); the marker recorded
   as an `input` (AC-4: turn moves); `rebuild_focus` losing `last_marker` (AC-4); a traceback on
   failure (AC-6).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `mark_compaction`; `last_marker` in the graph; `rebuild_focus` restores it; marker events skipped by the turn replay |
| `src/refmatrix/cli.py` (`focus hook`) | `--event compact-marker`; the `session-start` dispatch on `compact` / `clear`; R4's error line |
| `src/refmatrix/hooks.py` | the PreCompact `compact-marker` entry, independent of the recall flag |
| `src/refmatrix/telemetry.py` | `held_items`' `since_ts` from `last_marker` (through the caller); pointers-after-marker count in the report |
| `src/refmatrix/helix.py`, `src/refmatrix/composite.py` | skip `kind == "marker"` events where they read the ring (if they do not already) |
| `.claude/settings.json`, `.claude/rmx-hooks.json` | regenerated by calling the generator from Python in the task's clone (never `rmx install-hooks` against a live store) |
| `tests/test_task10_3_compaction_marker.py` (new) | AC-1..AC-7 |
| `workflow/measurements/injection-degrade-2026-11.md` | R5's after section |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-2, AC-3 at the 10.2 base, recorded.
- No mock of the hook generator, the focus hook, STM or the ledger; the generated entries run as
  bash commands, as Claude Code runs them.
- Mutations per the plan's execution contract; the call-site mutation edits `hooks.py`, not
  `stm.py`.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.3-plan-10-injection-dedup.md`.
- R5's live numbers written after deploy, with each band's verdict; any band that hands the decision
  to the user is reported to the user before plan-10 moves to `completed`.
- Committed on branch `task-10.3-plan-10-injection-dedup`; merged `--no-ff` to `master`.
