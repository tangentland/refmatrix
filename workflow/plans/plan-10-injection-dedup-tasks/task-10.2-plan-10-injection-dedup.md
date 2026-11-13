---
gmd: "0.1"
id: task-10.2-plan-10-injection-dedup
title: "Task 10.2: the two per-prompt blocks (prompt-recall, scan-prompt) become 19.6's versioned blocks — keyframe every K revs and after compaction, add-only deltas between, `unchanged` lines — built on 25.1's pack ahead of the rest of 19.6"
tags: [task, plan-10, scan-prompt, memory-recall, pack, versioned-injection, telemetry]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-09-15
  updated: 2026-11-13
---

# Task 10.2: versioned per-prompt blocks {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (rewritten twice 2026-11-13; the second time onto 19.6's versioned injection,
> context diff over pointer, Q7; ch-bsd spec review next). **Built only on
> [[task-10.5-versioned-block-gate]]'s GO**; if 10.5's labelled-use check says OFF, this spec is
> re-scoped to the floor ([[#r6]]) BEFORE its RED, never switched at runtime.
> Depends on: [[task-25.1-recall-hook-byte-budget]] MERGED (GREEN on branch
> `task-25.1-recall-hook-byte-budget`, clone `/Volumes/littlebig/refmatrix-plan25-1`, spec rev 7,
> merges after 26.4); [[task-10.3-plan-10-injection-dedup]] (the marker);
> [[task-10.4-non-human-prompt-gate]] (gated prompts are not revs); 21.1's event fields.
> Realizes: [[task-19.6-phased-context-and-topic-cache]] R5 and R6 for the block ids
> `prompt-recall` and `scan-prompt` only.

rel: part-of -> [[plan-10-injection-dedup]]
rel: realizes -> [[task-19.6-phased-context-and-topic-cache]]
rel: implements -> [[exploration-session-phased-context#vi-versioned]]
rel: implements -> [[exploration-session-phased-context#vi-unchanged]]
rel: implements -> [[exploration-session-phased-context#vi-delta]]
rel: depends-on -> [[task-10.5-versioned-block-gate]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r4]]
rel: depends-on -> [[task-10.3-plan-10-injection-dedup]]
rel: depends-on -> [[task-10.4-non-human-prompt-gate]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: related-to -> [[task-21.5-tool-used-signal]]

## Why {#why}

48.0% of delivered items were already held when delivered, 46.7% by re-delivery; the per-prompt
blocks repeat at the ITEM level while their whole content changes every prompt (Table A 0.00-3.32%,
[[plan-10-injection-dedup#context-table-a]]). 19.6's versioned injection is the mechanism the
project already designed for "do not re-send what the window holds" (context diff over pointer,
Q7). This task builds its R5 / R6 on the two per-prompt blocks, on top of 25.1's pack, with 19.6's
interfaces unchanged so 19.6's later phases, cache and composite blocks land on the same
substrate. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| v1 | The block STATE is the set of items the block carried since its last keyframe; a delta adds only items outside it and drops nothing; a keyframe renders the current prompt's whole block and resets the state to it ([[task-10.5-versioned-block-gate#state]]) | a "state = this prompt's set" delta would drop and re-add nearly everything every prompt (consecutive overlap median 0.000, 10.1), so R6's half-block rule would send a keyframe every rev and save nothing; add-only is Table B's gated band and is what makes an item omitted while it is in the window |
| v2 | One state per block id; no cross-block omission | 19.6 versions blocks, not items across blocks; the two hooks run concurrently on one prompt and cannot see each other's same-prompt state |
| v3 | The state is 19.6's "last-emitted state": `stm/<session>.emitted/<block_id>.json`, one file per block, written only by that block's hook, after its payload is printed | one writer per file, no read-modify-write between concurrent hooks; written after the print so a hook that dies before printing leaves the old state (the next rev re-adds: a duplicate, never an omission); the directory is 10.3's, beside the marker |
| v4 | No separate ledger and no per-item pointer | Q7; `recall-events.jsonl` stays the MEASUREMENT of what was emitted, never the input of what to emit |
| v5 | Only the CLI hook modes version: the hook `scan-prompt` and `memory recall --stdin-json`. Not `--session-start`, PreCompact, `rmx context`, interactive or MCP recall | prompt-less channels stay fixed as in 19.6 R7; an explicit pull is the agent asking for the body, often because it lost it |
| v6 | The versioning context reaches the recall verb through `**internal["versioned"]`, as 25.1 R5 routes `embedder_policy` and `trace` | the MCP schema and verb parity are unchanged; an MCP argument of that name is dropped by `Verb.call` |
| v7 | scan-prompt's delta reuses its existing within-call de-duplication (`shown`, `scan.py`, the symbol bundles' groups filtered by what an earlier section rendered), seeded with the block state | it is already the "do not re-render what this payload holds" mechanism; extended across revs it is the delta, with no second filter |
| v8 | New event fields `rev_kind` (`keyframe` / `delta` / `unchanged`) and, on an omitted item's `retrieved` event, `held_rev`; `block_id`, `rev`, `unchanged` keep 21.1's meaning | 21.1 reserved `rev` / `unchanged` (null until 19.6); a keyframe is not otherwise visible in the log, and an omission must be countable per item |

## Requirements {#requirements}

1. **R1 Versioned blocks.** `prompt-recall` (25.1's per-prompt pack) and `scan-prompt` (the hook
   render) are versioned per [[task-10.5-versioned-block-gate#state]] with `K = 8` (d9v). Every
   other channel emits as today with `rev` null. A prompt gated by 25.2 or 10.4 emits nothing and is
   not a rev. {#r1}
2. **R2 The state store.** `stm.load_emitted(root, session, block_id) -> BlockState | None` and
   `stm.save_emitted(root, session, state)` over `stm/<session>.emitted/<block_id>.json`:
   `{schema: 1, block_id, rev, keyframe_rev, content_sha, items: {<key>: <rev added>}}`, temp-file +
   replace. Item key: `(scope, entity_id)`, else `(scope, kind, name)` — ONE function,
   `telemetry.item_key`, used by the state, both renderers and 10.5's replay. `content_sha` is the
   sha256 of the full render of the current prompt's block (19.6 R5's content hash, kept for 19.6's
   composite blocks). Missing file → keyframe (`first`); unreadable or `schema` ≠ 1 → keyframe
   (`state-unreadable`) plus one stderr line, never a silent reset. {#r2}
3. **R3 Keyframe rule.** Keyframe when: no state; `rev − keyframe_rev ≥ K`; `stm.last_marker` (10.3)
   newer than the state's keyframe (an unreadable marker counts as newer); the delta's item bytes
   exceed half of the full render's item bytes; the state is unreadable. The reason is recorded as
   `keyframe_reason` (`first`, `cadence`, `marker`, `half`, `state-unreadable`). {#r3}
4. **R4 Rendering (19.6's grammar).** {#r4}
   - **Keyframe:** the first line names the block and rev, `… · <id> rev N keyframe`, the second is
     `supersedes earlier revs of <id>`; then the block exactly as 25.1 / scan-prompt render it today.
   - **Delta:** `# <id> rev N = rev N-1 + {add: M}`; then only the added items, each rendered
     exactly as the full form renders it (25.1's hook lines; scan-prompt's bundles with their groups
     filtered to added items, an anchor shown only when the anchor item is added, a bundle with
     nothing added left out); then 25.1's trailer when any added item did not fit.
   - **Unchanged:** a delta with nothing to add is the one line `<id> rev N unchanged`.
   - Arithmetic (25.1 R8 extended): named + trailer + omitted = retrieved; an item counted in the
     trailer is not added to the state; only NAMED items enter it.
5. **R5 25.1 surfaces changed, exactly.** `recall_pack.pack(..., version: "VersionCtx | None" =
   None)` (pure: given the state it returns `Packed` with `rev_kind`, `added`, `omitted`,
   `omitted_bytes` and `next_state`); `recall_pack.header_line` gains the rev text; the verb
   (`verbs.memory_recall` / `_memory_recall_rows`, 25.1 R5) reads `internal.get("versioned")`,
   loads the state and the marker once, passes them to `pack`, and returns `next_state`;
   `cli._memory_recall_impl` (`--stdin-json` only) builds the context and, after printing, saves
   `next_state`; `_RecallCall` copies `rev`, `rev_kind`, `unchanged`, `held_rev` onto the events.
   `hook_budget`, `fit_blocks`, the budgets, the generator, the argv and the trailer format are
   untouched. {#r5}
6. **R6 The floor (only if 10.5 says OFF).** Then this task is re-scoped before RED to R5 only:
   keyframes and `unchanged` lines, no omission (a delta never omits, so every rev whose content
   hash differs is a keyframe). No runtime switch exists in either form. {#r6}
7. **R7 Events and the saving.** Every event of a versioned call carries `block_id`, `rev`,
   `rev_kind`, and `unchanged` (true only on an unchanged rev); an omitted item has a `retrieved`
   event with `held_rev` and no `delivered` event (21.1: delivered is a span in the payload).
   `RECALL_EVENT_FIELDS_V1` gains `rev_kind` and `held_rev` (nullable; `v` stays 1; 19.2's fold,
   21.5's reader and the hook-cost report run clean over a mixed file). The call's row carries
   `rev`, `rev_kind`, `keyframe_reason`, `omitted_n`, `omitted_bytes` (what the omitted items would
   have rendered as: the pack and the renderer compute both forms). `rmx telemetry --context`
   shows per block the rev-kind mix, omitted items and bytes. {#r7}
8. **R8 Kept for 19.6.** Block ids, `rev`, `unchanged`, the header and `supersedes` lines, the
   delta grammar, `K`, keyframe-after-marker, the half-block rule and the `.emitted` directory are
   19.6's; 19.6's later blocks (`stm-topic-expanded`, `stm-topic-collapsed`) add their own state
   files there. Events keep `arm = "fixed"`, `policy = "fixed-v0"` until 19.6 R7. {#r8}
9. **R9 Before / after.** {#r9}
   - **Offline, same corpus:** 10.5's replay re-run with the rules imported from `src/` (10.5 AC-2)
     over the 2026-11-13 windows; it must reproduce 10.5's R2 numbers.
   - **Live:** after deploy, the fleet busy ≥ 5 working days ([[impression_bsd_cost_measured_idle]]),
     at least as many sessions per store as the before window, `rmx telemetry --context` and the
     events, counts only. Bands written here before any number: UserPromptSubmit bytes per human
     prompt (scan-prompt + recall) fall ≥ 20% → keep; 5-20% → keep and record; < 5% → the user
     decides. Omission check: the share of omitted items the agent then fetched explicitly (a
     main-loop `rmx memory get` / `rmx context` / `Read` of the item within 3 revs) against the
     same share for items rendered in full on a re-delivery in the before window; more than twice
     → the user decides (K or the omission).
   - Written to `workflow/measurements/versioned-block-gate-2026-11.md` (after section).

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store with a synthetic session, through the GENERATED
UserPromptSubmit commands (`hooks._claude_hook_block(...)`, `bash -c`, the envelope on stdin).
Unit tables over `pack`, the scan renderer and the state store are in addition. {#acceptance-lead}

1. **AC-1 Keyframe, delta, unchanged.** Prompt 1 → keyframe (rev 1, full pack, `supersedes` line);
   prompt 2 retrieving 2 new items and 4 held ones → `rev 2 = rev 1 + {add: 2}` with exactly the 2
   new items rendered as the full form renders them; prompt 3 retrieving only held items → `rev 3
   unchanged`. Both blocks. RED at the 25.1 + 10.3 + 10.4 base.
2. **AC-2 Cadence.** Revs 1-8 under the add-only rule, rev 9 a keyframe (`cadence`) that re-renders
   every current item including ones omitted at revs 2-8, and the state then equals rev 9's items.
3. **AC-3 Marker.** After the generated PreCompact marker entry (10.3) runs, the next rev is a
   keyframe (`marker`); after SessionStart `compact` and `clear` too; after `resume`, not.
4. **AC-4 Half-block.** A delta whose added item bytes exceed half of the full render's is sent as
   a keyframe (`half`).
5. **AC-5 State failures reset.** A missing state file → keyframe `first`; a file holding `{` or
   `schema: 2` → keyframe `state-unreadable` and one stderr line; the command exits 0.
6. **AC-6 Arithmetic and events.** On every AC-1..AC-4 payload: named + trailer + omitted =
   retrieved; each omitted item has a `retrieved` event with the right `held_rev` and no
   `delivered` event; each rendered item's span slices its bytes (25.1 AC-10's multibyte rule);
   `rev`, `rev_kind`, `unchanged` right on every event; the row's `omitted_n` / `omitted_bytes`
   equal the hand-computed values.
7. **AC-7 Unversioned channels.** `--session-start`, PreCompact recall, `rmx context`, interactive
   and MCP recall carry `rev` null and render in full even when every item is in a block state; the
   MCP schema of `rmx_memory_recall` has no versioning parameter.
8. **AC-8 Blocks are independent.** An item in `scan-prompt`'s state is rendered in
   `prompt-recall`'s delta, and the reverse; concurrent runs of both hooks on one prompt leave both
   state files valid.
9. **AC-9 Gated prompts are not revs.** A `skipped_non_human` (10.4) and an `ack_only` (25.2)
   prompt leave both state files byte-identical.
10. **AC-10 Offline replay parity.** 10.5's replay with the rules imported from `src/` reproduces
    10.5's committed R2 numbers on its fixture (10.5 AC-3).
11. **AC-11 Mutations that must FAIL a test:** omitting an item NOT in the state (AC-1, AC-6);
    adding trailer'd items to the state (AC-6); no cadence keyframe (AC-2); the marker ignored
    (AC-3); the half-block rule dropped (AC-4); an unreadable state read as empty-delta instead of
    keyframe (AC-5); the state written before the payload is printed (a killed-before-print run
    leaves the new state: AC-5's variant); one shared state for both blocks (AC-8); an omitted item
    given a `delivered` event (AC-6); `--session-start` versioned (AC-7); a gated prompt advancing
    `rev` (AC-9); the scan delta filtering with its own key rule instead of `telemetry.item_key`
    (AC-8's same-name pair, two files).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `BlockState`, `load_emitted`, `save_emitted` (beside 10.3's marker in `.emitted/`) |
| `src/refmatrix/telemetry.py` | `item_key`; `rev_kind`, `held_rev` in `RECALL_EVENT_FIELDS_V1` and `call_events`; row fields; per-block rev mix and omission in the hook-cost report |
| `src/refmatrix/recall_pack.py` (25.1) | `pack(version=…)`, `header_line` rev text, `Packed` fields |
| `src/refmatrix/hook_budget.py` (25.1) | none |
| `src/refmatrix/verbs.py` (`memory_recall`, `_memory_recall_rows`) | `internal["versioned"]`; state + marker read once; `next_state` returned |
| `src/refmatrix/cli.py` (`_memory_recall_impl --stdin-json`, `_RecallCall`, `scan-prompt`) | context built, `next_state` saved after the print, event fields copied |
| `src/refmatrix/scan.py` (`scan_prompt`) | `shown` seeded from the block state; keyframe / delta / unchanged render; `next_state` via the trace |
| `tests/test_task10_2_versioned_blocks.py` (new) | AC-1..AC-11 |
| `workflow/measurements/versioned-block-gate-2026-11.md` | R9's after section |

## Test strategy {#test-strategy}

- RED first on AC-1..AC-6 and AC-9 at the 25.1 + 10.3 + 10.4 merged base, recorded; AC-7 and AC-8
  are guards proven by their mutations ([[feedback_red_test_must_fail_at_head]]).
- No mock of the pack, the renderer, the state store, the marker, the generator or telemetry.
- Mutation run per [[feedback_commit_before_mutation_revert]] and
  [[feedback_clear_pycache_after_mutation]].

## Open questions {#open-questions}

| # | question | recommendation |
|---|---|---|
| p1 | A delta says nothing about held items that are relevant AGAIN this prompt (the model must find them in its window). Add a names-only "in play" line? | not by default: it is a per-item reference in another form (Q7 steered away from it); raise it only if R9's omission check trips |
| p2 | Cross-block omission (an item in `scan-prompt`'s state omitted from `prompt-recall`)? | no (v2); 10.5 R2 reports how much it would add |

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.2-plan-10-injection-dedup.md`.
- R9's offline numbers at GREEN; live numbers after deploy with each band's verdict.
- Committed on branch `task-10.2-plan-10-injection-dedup`; merged `--no-ff` to `master`.
