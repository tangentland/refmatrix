---
gmd: "0.1"
id: task-10.2-plan-10-injection-dedup
title: "Task 10.2: an item the session already holds is rendered as a one-line pointer, read from 21.1's delivery log inside a turn window, in 25.1's recall pack and in scan-prompt's renderer; never dropped, always counted"
tags: [task, plan-10, scan-prompt, memory-recall, pack, telemetry, helix, injection]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-09-15
  updated: 2026-11-13
---

# Task 10.2: degraded rendering from the delivery log {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (rewritten 2026-11-13 on the reopening; was cancelled 2026-09-15 when 10.1 did
> not clear; ch-bsd spec review next)
> Depends on: [[task-25.1-recall-hook-byte-budget]] MERGED to `master` (25.1 is GREEN on branch
> `task-25.1-recall-hook-byte-budget`, clone `/Volumes/littlebig/refmatrix-plan25-1`, spec rev 7,
> and merges after 26.4); [[task-10.4-non-human-prompt-gate]] merged (the STM turn this task's
> window counts is a human-turn count after it, [[plan-10-injection-dedup#order]]); 21.1's
> delivery log (released 0.80.0).
> User decision: D1 of 2026-11-13, degrade never suppress.

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[task-10.4-non-human-prompt-gate]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r4]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: depends-on -> [[feedback_prefer_existing_infra]]
rel: depends-on -> [[feedback_reuse_shared_stoplist]]
rel: depends-on -> [[impression_bsd_dead_flag_surface]]
rel: related-to -> [[task-21.5-tool-used-signal]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache]]

## Why {#why}

48.0% of delivered items were already held by the session when delivered, 46.7% by re-delivery
alone; restricted to the hook channels this task degrades, 43.2% (refmatrix) and 51.9% (cliquedb)
([[measurement-injection-already-held-2026-11-13#breakdowns]]). By channel: scan_prompt 42.2% /
45.6%, prompt_recall 57.6% / 77.3%, session_start 46.5% / 58.8%. The repeats are spread over the
session and arrive on different words, so a consecutive-call or same-words rule would miss them;
the session's own delivery record does not. {#why-lead}

The cost check (6 of 13 labelled used items were re-deliveries) is why the item is degraded, not
dropped: the pointer keeps the address the agent needs to fetch it again.

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| e1 | The ledger is 21.1's `delivered` events in `recall-events.jsonl` (project and global files), read by the existing backwards reader `telemetry.delivered_in_session`; no new store, no STM field | the log already carries session, turn, item key, channel and span for every delivery; a second record is a second lifecycle ([[feedback_prefer_existing_infra]]); plan Q2 |
| e2 | Ledger key: `(scope, entity_id)` when the event has an `entity_id`, else `(scope, kind, name)` | two code symbols with one name in two files are two items; 441 scan_prompt code/doc deliveries carry no `entity_id` and fall back to the name (counted on the two clones, 2026-11-13) |
| e3 | Only HOOK deliveries make an item held: `scan_prompt`, `prompt_recall`, `session_start`. Not `context`, `recall`, `nudge` (agent-pulled), not `precompact` | an agent-pulled delivery may have been a SUBAGENT's tool result, which the main context never held (the measurement's own limit); PreCompact output feeds the compaction that resets the ledger. The measurement's hook-only (a) is 43.2% / 51.9%, still above the ≥ 30% band |
| e4 | Only FULL deliveries make an item held; a pointer delivery never refreshes the ledger, and "shown turn N" names the last full delivery | otherwise a pointer keeps re-arming itself and the item never renders full again |
| e5 | Degrade on `scan_prompt`, `prompt_recall`, `session_start`; NEVER on `precompact`, and never on an explicit pull (`rmx context`, interactive and MCP `memory recall`, `nudge`) | PreCompact's text is what survives compaction; an explicit pull is the agent asking for the body, often BECAUSE it lost it |
| e6 | The turn window lives HERE, not in 10.3: held iff `1 ≤ now_turn − full_turn ≤ 10` | a ledger with no window must never sit on `master`, and no flag may stage it ([[impression_bsd_dead_flag_surface]]); plan decision P1 |
| e7 | N = 10 turns | see [[#r4]] |
| e8 | Gap 0 (same turn) is never held | scan-prompt and the per-prompt recall run concurrently on one prompt; neither can see the other's events, so the rule would depend on which wrote first. The measurement found 29 same-prompt repeats |
| e9 | The event field is `form: "full" \| "pointer"`, not `degraded` | "degraded" already names the error-degrade path (`cli._degrade_or_raise`, `_RecallCall.degraded`, the `degraded` counts at `cli.py:11346`); a report column called "degraded" would merge a failed call with a deliberate pointer |
| e10 | Freed bytes are re-spent only inside the retrieved set: `k` is unchanged, and a shorter pointer line lets more of the same `k` rows be named instead of counted in the trailer; no extra retrieval | "saves context" and "returns more" are different products (the 2026-09 spec's open point); this keeps both the arithmetic (25.1 R8) and the saving measurable |
| e11 | The window compare is `helix.in_window(age, window)`, extracted from `helix.annotate` (`age < _window_s()` there today); helix's ring index is NOT reused | per-entity last-seen + a window is the helix primitive ([[plan-10-injection-dedup#helix]]); the ring index records what the agent touched, the ledger needs what was injected |
| e12 | The ledger context reaches the recall verb through its `**internal` channel (`internal["ledger"]`), as 25.1 R5 routes `embedder_policy` and `trace`; the MCP schema and verb parity are unchanged | only the CLI's hook modes may degrade (e5); an MCP caller cannot ask for it and an MCP argument of that name is dropped by `Verb.call` |

## Requirements {#requirements}

1. **R1 Channels.** Degrade applies to `scan_prompt` (the hook's `rmx scan-prompt`),
   `prompt_recall` (`rmx memory recall --stdin-json`) and `session_start` (`--session-start`).
   `precompact`, `rmx context`, interactive and MCP recall and `nudge` never consult the ledger and
   always render full (e5). {#r1}
2. **R2 The ledger read.** {#r2}
   - `telemetry.delivered_in_session` gains keyword-only `key_fn`, `channels`, `since_ts`,
     `full_only`. With none passed it is byte-for-byte today's R12 lookup (21.1's `used` tests pass
     unchanged). `since_ts` stops the backwards read once it passes `since_ts −
     LEDGER_TS_SLACK_S` (5 s: events are appended in write order, stamped at write); the 4 MB cap
     stays and its cut is counted.
   - `telemetry.held_items(session, *, root, global_root, now_turn, since_ts) -> HeldSet`: a
     `Mapping[key, HeldItem(turn, query_id, channel, name, kind, scope)]` over
     `delivered_in_session(key_fn=ledger_key, channels=HOOK_CHANNELS, since_ts=…, full_only=True)`,
     kept only where the window holds ([[#r4]]). `full_only` keeps an event whose `form` is
     `"full"` or null (every event written before this task is a full delivery).
   - `telemetry.ledger_key(item_or_event)` is THE key function (e2), used by the reader and by both
     renderers; no second key rule.
   - `since_ts` in this task is the session's first STM ring event; 10.3 raises it to the last
     compaction marker ([[task-10.3-plan-10-injection-dedup#r3]]).
   - The hook computes `now_turn` and the session from the SAME `stm.pre_prompt_state` read its
     telemetry already does (21.1 R10: one state read per call), and passes them in.
3. **R3 A failed read degrades nothing, loudly.** An `OSError` or a cap cut never raises out of the
   hook: an unreadable file means no item is held (everything renders full, the safe direction), a
   one-line `rmx: injection ledger: …` on stderr, and `ledger_error` / `ledger_cap_hit` on the
   call's row. Never a bare `except` ([[plan-10-injection-dedup#execution]]). {#r3}
4. **R4 The window, N = 10.** Held iff the last full hook delivery is at `full_turn` with `gap =
   now_turn − full_turn` and `1 ≤ gap` and `helix.in_window(gap, INJECTION_WINDOW_TURNS)` where
   `INJECTION_WINDOW_TURNS = 10` and `helix.in_window(age, window) := age <= window`.
   `helix.annotate` calls the same function for its own check (its behaviour is unchanged except
   at exact float equality). A null `full_turn` or `now_turn`, or a negative gap (a ring rebuilt
   since), is not held. {#r4}
   **Why 10.** The measurement's re-delivery gaps (in hook prompts): 0 → 29; 1 → 1,168; 2-3 →
   1,811; 4-10 → 2,049; ≥ 11 → 2,293. A window of 10 degrades the 5,028 repeats at gaps 1-10 (68%
   of 7,350) and re-promotes the 31% beyond; 10 is the largest boundary the measurement resolves
   (its top bucket is open-ended), so a larger N would be a guess. After 10.4 the turn counts human
   prompts only, so 10 turns span at least 10 hook prompts and the degraded share is at least that.
   The window is the backstop for context loss no hook reports (10.3 adds the compaction marker);
   a stale pointer still carries the address. 10.3's live re-measure checks N
   ([[task-10.3-plan-10-injection-dedup#r5]]).
5. **R5 Recall rendering (25.1 surfaces).** {#r5}
   - `recall_pack.pack(..., held: "Mapping | None" = None)`. A row whose `ledger_key` is in `held`
     renders `pointer_line(row, held_item)` = `- <name>  (<fetch>)  [shown turn N]\n` (`<fetch>`
     is 25.1 R6's scope-correct `rmx memory get …`) in its rank position among the hook lines, and
     never gets a body. Every other row is 25.1's `hook_line` and body rules, unchanged.
   - `Packed` gains `pointers: list[str]` (names rendered as pointers) and `pointer_saved_bytes:
     int`; each span gains `form`, and on a pointer `ref_query_id` (the full delivery's
     `query_id`) and `lag_turns` (the gap).
   - `hook_budget` is UNCHANGED: `fit_blocks` fits the shorter lines as it fits any block.
   - `verbs.memory_recall` / `_memory_recall_rows` (25.1 R5) read `internal.get("ledger")`; when
     present (CLI hook modes `--stdin-json` and `--session-start` only), the verb calls
     `telemetry.held_items` once and passes `held` to `pack`. Absent → `held=None`.
   - `cli._memory_recall_impl`'s hook modes build the ledger context (session, `now_turn`,
     `since_ts`) and pass it through `**internal`; `_RecallCall` copies `form`, `ref_query_id`,
     `lag_turns` from the spans onto the `delivered` events.
6. **R6 scan-prompt rendering.** `context.render_text_spans(b, *, held=None)`: {#r6}
   - a held ANCHOR renders `anchor: <name>  [<kind>]  [shown turn N]  (rmx context <name>)` and
     drops its tldr and its body (an attached memory body included);
   - a held group ENTRY renders `  <name>  [<kind>]  <path>:<line>  [shown turn N]` (the location
     from `_location_block`, the first one when there are several; no snippet, hit lines, tldr or
     body);
   - helix notes, headers, linkage labels and the completeness notes render as today (they are not
     items);
   - `bundle_items` is unchanged: WHICH items a bundle names is not this task's business, only HOW.
   - `scan.scan_prompt` passes `held` (computed once per call) to every `render_text_spans` call;
     25.1's `_finish` and its `fit_blocks` call are unchanged; the spans carry `form` etc. as in R5.
   - `rmx context` calls `render_text_spans` with no `held` (e5).
7. **R7 Every pointer is a delivery.** A pointer emits a `delivered` event whose span is the pointer
   line, with `form: "pointer"`, `ref_query_id`, `lag_turns`; a full item emits `form: "full"`.
   `telemetry.RECALL_EVENT_FIELDS_V1` gains `form`; `v` stays 1 (an added nullable field; every
   reader uses `.get`, and a test runs 19.2's fold, 21.5's reader and the hook-cost report over a
   mixed file). 21.1's R12 `used` lookup is unchanged (newest delivery per its key, pointer or
   full); the `used` event's `ref_query_id` points at it, so 21.5 can split used-after-pointer from
   used-after-full. {#r7}
8. **R8 The saving, reported.** Each degrading call writes `pointer_n` and `pointer_saved_bytes`
   on its row (scan-prompt's `query.log` row; the recall row). `pointer_saved_bytes` = Σ over
   pointer items (UTF-8 bytes of the item's full rendering in this call − bytes of its pointer
   line); for a recall row on a body channel the full rendering includes the body only when it
   would have fit (the pack computes both). `rmx telemetry --context` shows, per channel, the
   pointer share of delivered items and the bytes saved. {#r8}
9. **R9 Budget.** `k` and the retrieval are unchanged by `held`; the retrieved events of a call are
   identical with and without it (e10). {#r9}
10. **R10 Offline re-measure on the same corpus.** At GREEN, replay the 2026-11-13 corpus
    (APFS clones of both stores' `recall-events.jsonl`, the global file and the STM rings, as
    `dd-10r` did, read-only) through `held_items` and the GREEN key / window rules, event by event
    in log order: per channel, the share of hook deliveries that would render as pointers and the
    item-line bytes saved. Counts only, to `workflow/measurements/injection-degrade-2026-11.md`
    (GMD; 10.3 appends the live numbers). {#r10}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store, extended with a synthetic STM ring for the session
and a synthetic `recall-events.jsonl` history (turns, keys, forms), through the GENERATED
UserPromptSubmit and SessionStart commands (`hooks._claude_hook_block(...)`, `bash -c`, the
envelope on stdin). Unit tables over `pack`, `render_text_spans` and `held_items` are in addition.
{#acceptance-lead}

1. **AC-1 First full, repeat a pointer.** On the per-prompt recall and the scan-prompt commands: a
   prompt at turn t delivers item X in full; the next human prompt (t+1) naming the same topic
   renders X as a pointer that carries its address (`rmx memory get X` / `path:line` / `rmx
   context X`) and `[shown turn t]`. RED at HEAD (X renders full again).
2. **AC-2 Never dropped (the plan's one non-negotiable).** Property tests over the fixture: for 200
   random subsets of the retrieved keys used as `held` (and the empty and the full subset), (a)
   `pack`: `set(named(held)) ⊇ set(named(None))`, `len(named) + more == len(rows)`, and every held
   row that is named carries a pointer line; (b) `render_text_spans`: the delivered item set with
   `held` equals the set without it; (c) through the generated commands, a session where EVERY
   retrieved item is held still prints every item that the no-ledger run prints, as pointers.
3. **AC-3 Full-only.** X full at turn 3, pointers at 4..13, full again at 14 (gap 11); each
   pointer says `[shown turn 3]`; the turn-14 full delivery re-arms it (pointer at 15 says
   `[shown turn 14]`).
4. **AC-4 Window edges.** gap 0 → full; 1 → pointer; 10 → pointer; 11 → full; null `full_turn` →
   full; negative gap → full.
5. **AC-5 Channels.** An item whose only earlier delivery is on `context`, `recall`, `nudge` or
   `precompact` renders full. The PreCompact recall command never prints a pointer. `rmx context
   X`, MCP `rmx_memory_recall` and interactive `rmx memory recall "q"` never print a pointer while X
   is held. The MCP input schema of `rmx_memory_recall` has no ledger parameter.
6. **AC-6 Events.** Every pointer has a `delivered` event with `form: "pointer"`, the right
   `ref_query_id` and `lag_turns`, and a byte span that slices exactly the pointer line (with ≥ 3
   `—` before it, 25.1 AC-10's multibyte rule); full items carry `form: "full"`; a pre-task event
   (no `form`) is read as full by `held_items`; 19.2's fold, 21.5's reader and `rmx telemetry
   --context` run clean over the mixed file.
7. **AC-7 Saving.** On a fixture call with 3 pointers, `pointer_n == 3` and `pointer_saved_bytes`
   equals the hand-computed difference; `rmx telemetry --context` shows the channel's pointer
   share and bytes.
8. **AC-8 Budget.** With and without `held`: identical `retrieved` events; with a budget that trims
   rows at `held=None`, the held run names at least as many of the same `k` rows and retrieves none
   beyond them.
9. **AC-9 Key.** Two code entities with one name in two files: after the first is delivered, only
   the first renders as a pointer. An event with a null `entity_id` keys on `(scope, kind, name)`.
   A project and a global memory named X are two keys.
10. **AC-10 A failed ledger read.** An unreadable `recall-events.jsonl`: both commands exit 0,
    render every item full, print one `rmx: injection ledger:` line on stderr, and the rows carry
    `ledger_error`. A file over the 4 MB cap counts `ledger_cap_hit`.
11. **AC-11 R12 unchanged.** 21.1's `used`-event tests pass with no edit; `delivered_in_session`
    called with no new keyword returns the same `DeliveredSet` as at HEAD on a mixed file.
12. **AC-12 Ledger cost, with bands written before the run.** `held_items` over a 32 MB synthetic
    event file shaped like the live refmatrix file (2026-11-13: 32,001,183 B), 50 calls, p50 / p95
    recorded with `bytes_read`. Bands: p95 ≤ 50 ms ship; 50-200 ms ship and record the number in
    the summary; > 200 ms stop, the user decides. A `since_ts` one hour back reads fewer bytes than
    the cap (asserted).
13. **AC-13 Structure.** A structural test parses `recall_pack.py`, `context.py` and `scan.py`:
    `held` membership is tested only where the pointer renderer is chosen over the full one; no
    `os.environ` read and no `continue` / filter / `return` is conditioned on it; no parameter or
    variable named like `suppress` / `skip_held` / `drop` exists in the three modules.
14. **AC-14 Mutations that must FAIL a test:** a held row `continue`d (AC-2a); held rows removed
    from `rows` before `pack` (AC-2a); held rows counted into the trailer instead of named (AC-2a:
    `named ⊇` fails while the arithmetic holds); `pointer_line` returning `""` (AC-1, AC-2); a held
    scan entry omitted from the render (AC-2b); a suppression branch behind an env var
    (AC-13); the pointer delivery not emitted (AC-6); pointer deliveries refreshing the ledger
    (`full_only` dropped: AC-3); `<` for `<=` in the window (AC-4: gap 10 full); gap 0 held (AC-4);
    agent-pulled channels counted as held (AC-5); PreCompact degraded (AC-5); `rmx context`
    degraded (AC-5); name-only key (AC-9); the ledger error swallowed with no stderr / row field
    (AC-10); `delivered_in_session`'s default behaviour changed (AC-11).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/telemetry.py` | `delivered_in_session` keywords (`key_fn`, `channels`, `since_ts`, `full_only`); `ledger_key`, `held_items`, `HeldItem`, `HOOK_CHANNELS`, `INJECTION_WINDOW_TURNS`, `LEDGER_TS_SLACK_S`; `form` in `RECALL_EVENT_FIELDS_V1` and `call_events`; `pointer_n` / `pointer_saved_bytes` / `ledger_*` in the hook-cost report |
| `src/refmatrix/helix.py` | `in_window(age, window)`; `annotate` calls it |
| `src/refmatrix/recall_pack.py` (25.1) | `pack(held=…)`, `pointer_line`, `Packed.pointers` / `pointer_saved_bytes`, span `form` / `ref_query_id` / `lag_turns` |
| `src/refmatrix/hook_budget.py` (25.1) | none |
| `src/refmatrix/verbs.py` (`memory_recall`, `_memory_recall_rows`, 25.1 R5) | `internal["ledger"]` → `held_items` → `pack(held=…)` |
| `src/refmatrix/cli.py` (`_memory_recall_impl` hook modes, `_RecallCall`, `scan-prompt`) | build the ledger context from the one `pre_prompt_state` read; copy span fields to events; row fields |
| `src/refmatrix/context.py` (`render_text_spans`) | `held=` with the anchor and entry pointer lines |
| `src/refmatrix/scan.py` (`scan_prompt`) | one `held_items` call per call, passed to every `render_text_spans`; row fields |
| `tests/test_task10_2_degrade.py` (new) | AC-1..AC-14 |
| `tests/fixtures/plan10/` (new) | synthetic ring + event history + README (shapes only) |
| `workflow/measurements/injection-degrade-2026-11.md` (new) | R10's offline replay |

The 25.1 surfaces this task changes are exactly: `recall_pack.pack`'s signature and output fields,
the span fields 25.1 R9 hands to `_RecallCall`, the verb's `**internal` read and the CLI hook-mode
context. 25.1's fitter, budgets, generator, `--pack` argv, header and trailer are untouched.
{#surfaces-25-1}

## Test strategy {#test-strategy}

- RED first on AC-1, AC-3, AC-4, AC-6, AC-7, AC-9, AC-10 at the 25.1 + 10.4 merged base, recorded;
  AC-2 and AC-11 are guards (they hold at HEAD) and are proven by their mutations instead
  ([[feedback_red_test_must_fail_at_head]]).
- No mock of the pack, the renderer, the ledger reader, the hook generator or telemetry; the event
  history is a real file the real reader reads.
- Mutation run per [[feedback_commit_before_mutation_revert]] and
  [[feedback_clear_pycache_after_mutation]]; a mutation must fail a test, not hang it.

## Open questions {#open-questions}

| # | question | recommendation |
|---|---|---|
| p1 | 19.6 R5 versions BLOCKS (`<id> rev N unchanged`, the STM composite); this task degrades ITEMS. Overlap? | none in scope: this task never touches the composite block; 19.6 (pending, Wave 3) should read 10.3's marker and this task's `in_window` rather than define its own window (flag for 19.6's next revision) |
| p2 | Should a pointer also drop its helix note? | no: helix notes are not items and have their own readership log; revisit with 10.3's live numbers |

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table and AC-12's timing in the implementation
  summary.
- Implementation summary at `workflow/implementation_summaries/task-10.2-plan-10-injection-dedup.md`.
- R10's offline replay written.
- Committed on branch `task-10.2-plan-10-injection-dedup`; merged `--no-ff` to `master`.
