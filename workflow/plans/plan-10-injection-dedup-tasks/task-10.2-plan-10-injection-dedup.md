---
gmd: "0.1"
id: task-10.2-plan-10-injection-dedup
title: "Task 10.2: names-only dedupe of the per-prompt payloads — an item the session already holds is removed from scan-prompt and the per-prompt recall and named on one 'still in play' line; nothing new is pulled in; live A/B dedupe vs full"
tags: [task, plan-10, scan-prompt, memory-recall, pack, injection, dedupe, telemetry]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-09-15
  updated: 2026-11-13
---

# Task 10.2: names-only dedupe {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (rewritten 2026-11-13 onto names-only, Q13; ch-bsd spec review next). Built
> only after [[task-10.5-versioned-block-gate]]'s precondition: the design replay PASSED (v1, v2);
> the 50-probe read-back test is still to run.
> Depends on: [[task-25.1-recall-hook-byte-budget]] MERGED (GREEN on branch
> `task-25.1-recall-hook-byte-budget`, clone `/Volumes/littlebig/refmatrix-plan25-1`, spec rev 7,
> merges after 26.4); [[task-10.3-plan-10-injection-dedup]] (the compaction marker);
> [[task-10.4-non-human-prompt-gate]] (the family field the A/B splits by); 21.1's events.

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-10.5-versioned-block-gate]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r4]]
rel: depends-on -> [[task-10.3-plan-10-injection-dedup]]
rel: depends-on -> [[task-10.4-non-human-prompt-gate]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13#design-replay]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13#design-replay-v2]]
rel: related-to -> [[task-21.5-tool-used-signal]]
rel: related-to -> [[exploration-handhold-outcome-experiment#assignment]]
rel: depends-on -> [[open-questions]]

## Why {#why}

48.0% of delivered items were already held when delivered, 46.7% by re-delivery
([[measurement-injection-already-held-2026-11-13#result]]). The pre-registered design replay
([[measurement-injection-already-held-2026-11-13#design-replay]]; v2 under the four held rules,
[[measurement-injection-already-held-2026-11-13#design-replay-v2]]) scored five designs over
1,472 prompt calls with 11 labelled and 16 R12 explicit uses: names-only (design 3) kept every use
visible (11/11, 16/16) at 0.469-0.470 of baseline block bytes (0.872 of item-line bytes in v2);
the novelty ranking (4+3) lost a labelled use under block bytes; the block diff (design 5) lost 4
labelled and 6 R12 uses. Chosen: names-only (Q13), applied to non-human turns too (Q10). {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| h1 | HELD = delivered FULL on `scan_prompt`, `prompt_recall` or `session_start` on an EARLIER prompt of the session, after the last compaction marker (cross-block) | the four held rules (lead, 2026-11-13); the definition the replay scored (v2) |
| h2 | "Earlier prompt" is decided by prompt identity, not by the STM turn: an entry is earlier when its `prompt_sha` differs from this call's, or when it is older than `stm.PRE_PROMPT_SKEW_S` (10 s) before this call's process start; a `session_start` entry is always earlier | scan-prompt and the recall run concurrently on one prompt and must not hold each other's same-prompt items; the STM turn cannot serve, because 10.4 stops counting agent-message turns while those turns still get payloads (Q10); `PRE_PROMPT_SKEW_S` is the skew 21.1 R9 already uses to tell this prompt from another |
| h3 | Compaction is the only reset (no TTL, no window, no keyframe) | lead rule 2; nothing is removed outright, so a stale "held" only moves an item to the names line, where it is still named |
| h4 | The names line is visible but never sets "held"; only a full rendering does | lead rule 3; an item seen only by name keeps its original full delivery as the reason it is held |
| h5 | scan-prompt dedupes in ITEM units (anchors and group entries), with its own render and its own `fit_blocks` call; the recall dedupes rows inside 25.1's pack | lead rule 4; scan is not a row list |
| h6 | State: one file per WRITING channel, `stm/<session>.emitted/<channel>.json` (`scan_prompt`, `prompt_recall`, `session_start`), each written only by its own hook after its payload is printed; every reader reads all three plus 10.3's `marker.json` | one writer per file, no read-modify-write between concurrent hooks; written after the print so a hook that dies first leaves the old state (the next prompt renders in full; an item is never named that the model did not get) |
| h7 | 21.1's `delivered` events are the MEASUREMENT, not the state | telemetry has a kill switch (`telemetry._disabled()`) and skips a failed append by design, so behaviour would silently depend on telemetry config; reading state back from a 32 MB log costs a backwards scan per prompt |
| h8 | Item key `(scope, entity_id)`, else `(scope, kind, name)`: ONE function, `telemetry.item_key`, for the state, both renderers and 10.5's replay | two code symbols with one name in two files are two items; 441 hook deliveries on the 2026-11-13 windows carry no `entity_id` |
| h9 | No new candidates are pulled in: `k`, the retrieval and the rank order are unchanged; freed bytes are not re-spent | Q13; the replay's 4+3 lost a use exactly by re-spending freed budget on candidates never delivered at baseline |
| h10 | The names line holds at most 15 names (rank order), then `(+N)`; its bytes are reserved first in the budget so it is never cut | the replay's cap; a names line dropped by the fitter would be removal by rule |
| h11 | The live A/B lives HERE, not in 10.4 R7 | the arm switches THIS task's mechanism (`dedupe` vs `full`), and 10.4 ships before 10.2 |
| h12 | `session_start`, `precompact` and explicit pulls (`rmx context`, interactive and MCP recall) never dedupe; `session_start` RECORDS its full deliveries (h1); `precompact` and explicit pulls record nothing | a boundary payload is what the window starts from; an explicit pull is the agent asking for the body, often because it lost it |

## Requirements {#requirements}

1. **R1 The held set.** `stm.held_items(root, session, *, prompt_sha, t0) -> HeldSet` reads
   `stm/<session>.emitted/{scan_prompt,prompt_recall,session_start}.json` and 10.3's
   `stm.last_marker` once per call and returns the keys held under h1-h2. An entry is `{key, name,
   kind, scope, prompt_sha, ts}`. A missing file contributes nothing; an unreadable one contributes
   nothing plus one `rmx: held state: …` stderr line and `held_error` on the call's row (the safe
   direction: everything renders full); an unreadable marker resets (10.3). {#r1}
2. **R2 The writers.** After printing, the hook `scan-prompt`, `memory recall --stdin-json` and
   `memory recall --session-start` each record their FULL-rendered items in their own file
   (`stm.record_full(root, session, channel, items, *, prompt_sha)`, temp-file + replace).
   Names-line items are never recorded (h4). {#r2}
3. **R3 Recall (25.1 surfaces, exactly).** `recall_pack.pack(..., held: "Collection | None" =
   None)`: rows whose `item_key` is held are taken out of the rows the hook lines are fitted from;
   the remaining rows keep their rank order and 25.1's rules (hook lines, bodies, trailer); one
   line `still in play: a, b, c (+N)` (h10) follows the header, its bytes reserved before the fit;
   `Packed` gains `held_named`, `held_overflow` and `names_span`. The verb (25.1 R5) reads
   `internal.get("dedupe")` (CLI `--stdin-json` only, the way `embedder_policy` rides `**internal`),
   calls `stm.held_items` once and passes `held`. `hook_budget`, `fit_blocks`, the budgets, the
   generator, the argv and the trailer format are untouched. {#r3}
4. **R4 scan-prompt.** `scan.scan_prompt(..., held=None)`: a held group ENTRY is removed from its
   bundle by the same group filter that drops entries an earlier section rendered (`shown`, now
   keyed by `telemetry.item_key` instead of the entity name); a held ANCHOR renders no anchor
   block (`context.render_text_spans(b, omit_anchor=True)`: no anchor line, tldr or body) and its
   non-held entries render under the bundle header as today; a bundle left with nothing is not
   rendered; every held item goes to ONE names line, appended as its own block and reserved in
   scan's `fit_blocks` call (25.1 R0b) so it is never cut. The composite is untouched. {#r4}
5. **R5 Every turn, human or not.** The dedupe runs on every prompt that reaches the two hooks,
   non-human turns included (Q10); the call's row carries 10.4's `prompt_family` so the effect is
   split by family. 25.2's ack-only gate still runs first where it applies. {#r5}
6. **R6 Events and counts.** Every named item emits a `delivered` event: a full item's span is its
   rendering with `form: "full"`, a names-line item's span is the names line with `form: "names"`;
   `(+N)` overflow items have a `retrieved` event only and are counted. `form` joins
   `telemetry.RECALL_EVENT_FIELDS_V1` (nullable, `v` stays 1; 19.2's fold, 21.5's reader and the
   hook-cost report run clean over a mixed file). The row carries `held_n`, `held_named`,
   `held_overflow`, `held_saved_bytes` (bytes the held items would have rendered as, minus the
   names line). `rmx telemetry --context` shows per channel the held share and bytes saved. {#r6}
7. **R7 Live A/B, per session (moved from 10.4 R7, h11).** {#r7}
   - **Arms:** `dedupe` vs `full` (`held` is the empty set), equal weights, a fixed period written
     before the run (≥ 14 days and ≥ 40 sessions per arm per store, whichever is later), refmatrix
     and cliquedb.
   - **One arm table, nested with the handhold experiment:** `arms.SESSION_ARMS` (new, tiny, pure)
     and `arms.draw(session_id) -> str`, a pure function of `sha256(session_id + period salt)`, no
     state file; the SessionStart focus hook records the arm once (`session_arm` on a `cli.log`
     row); the verb and scan-prompt ask `arms.draw`. If the handhold experiment runs in the same
     period, its arm A (push on) splits into `A+dedupe` / `A+full`, its B (no push) has no dedupe
     factor, its C (bare, opt-in) is never drawn. `session_arm` is not 21.1's per-prompt `arm`.
   - **Outcomes, counts only:** injected bytes per human prompt (all per-prompt bytes of the
     session, non-human turns included, over its human prompts); used items per 100 human prompts
     (21.5's legs plus R12 explicit `used`), names-line items counted apart; the handhold
     experiment's orientation proxies where its scorer exists (recorded, not a band).
   - **Bands, written here before the run:** `dedupe` cuts bytes per human prompt ≥ 30% and its
     used rate is within −5% of `full` (or above) → keep; used rate 5-15% below → the user decides;
     more than 15% below → the user decides whether the names line needs more than names.
   - **The switch is for measurement only:** `arms.py` and its branch are deleted after the
     period (a row in `workflow/deferral_registry.md` with the end date); outside the period `draw`
     returns `dedupe`. Correctness never depends on it.
   - **Future arm (Q13), not built:** `4+3b` — baseline-delivered non-held rows first, then new
     candidates, then held rows into leftover budget, the rest on the names line. A later A/B adds
     it as a third cell under its own spec.
8. **R8 Offline parity.** 10.5's replay re-run with the held rules and the renderers' rules
   imported from `src/` reproduces dd-10r's v2 names-only figures on the same clones (0.470 block,
   0.872 line, 11/11, 16/16); a difference is a defect in one of the two, resolved before merge.
   {#r8}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store with a synthetic session, through the GENERATED
UserPromptSubmit and SessionStart commands (`hooks._claude_hook_block(...)`, `bash -c`, the
envelope on stdin). Unit tables over `pack`, the scan render and `held_items` are in addition.
{#acceptance-lead}

1. **AC-1 Held is named, not rendered.** Prompt 1 renders X in full (both payloads); prompt 2
   retrieving X and Y renders Y in full and X only on `still in play: X`; prompt 3 the same. RED
   at the 25.1 + 10.3 + 10.4 base.
2. **AC-2 Nothing vanishes.** Property test over the fixture, 200 random held subsets (and the
   empty and the full one), both payloads: every item the `full` run names is named in the
   `dedupe` run, in full or on the names line, or counted in `(+N)` or the trailer; non-held items
   keep their relative order; no item outside the `full` run's retrieved set appears.
3. **AC-3 Earlier prompts only.** scan-prompt and recall run concurrently on one prompt: neither
   names the other's same-prompt items; a `session_start` delivery is held on the first prompt; an
   identical prompt text re-sent later than `PRE_PROMPT_SKEW_S` does hold; an agent-message turn
   between two human prompts holds what it delivered for the second.
4. **AC-4 Compaction resets.** After the generated PreCompact marker entry (10.3) runs, the next
   prompt renders X in full; the same after SessionStart `compact` and `clear`; not after `resume`.
5. **AC-5 The names line never refreshes held.** X full at prompt 1, named at 2..9; no entry for X
   is written at 2..9; after a marker at 10, X renders full.
6. **AC-6 Cap and budget.** 20 held items → 15 names then `(+5)`, in rank order; the names line is
   present at 2,000 / 4,000 / 9,000 B (25.1 AC-2's budgets) and the payload stays within each; the
   `(+5)` items have `retrieved` events and no `delivered` events.
7. **AC-7 Events.** Spans slice exactly (full item: its rendering; names item: the names line),
   with ≥ 3 `—` before them (25.1 AC-10's multibyte rule); `form` right on each; the row's `held_*`
   counts equal the hand-computed values.
8. **AC-8 Channels.** `--session-start` writes its file and never names; PreCompact recall, `rmx
   context`, interactive and MCP recall neither name nor write while X is held; the MCP schema of
   `rmx_memory_recall` has no dedupe parameter.
9. **AC-9 Non-human turns.** An `<agent-message` prompt gets the same dedupe; its row carries
   `prompt_family: "agent-message"`.
10. **AC-10 State failures.** An unreadable channel file → everything full, one stderr line,
    `held_error` on the row, exit 0; an unreadable marker → full (10.3's reset).
11. **AC-11 The arm draw.** `arms.draw` is deterministic per session id and salt; 400 synthetic
    ids split 200 ± 30; a `full` session's payloads equal the no-dedupe render; the SessionStart
    entry records one `session_arm` row; outside the period every session is `dedupe`; with the
    handhold rows present the nested cells are drawn and C never is.
12. **AC-12 Offline parity** (R8) on 10.5's fixture.
13. **AC-13 Mutations that must FAIL a test:** a held item dropped without a name (AC-2); a
    non-held item reordered (AC-2); a new candidate pulled in to fill freed bytes (AC-2); the STM
    turn used for "earlier" (AC-3, the agent-message leg); same-prompt items held (AC-3); the
    marker ignored (AC-4); names-line items recorded as held (AC-5); the names line cut by the
    fitter (AC-6); `(+N)` items given `delivered` events (AC-6); `session_start` naming (AC-8); `rmx
    context` deduped (AC-8); an unreadable state file read as "all held" (AC-10); the scan filter
    keyed by name instead of `telemetry.item_key` (a same-name pair in two files, AC-2);
    `arms.draw` using a random source (AC-11).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `held_items`, `record_full`, `HeldSet` (beside 10.3's marker in `.emitted/`) |
| `src/refmatrix/telemetry.py` | `item_key`; `form` in `RECALL_EVENT_FIELDS_V1` and `call_events`; `held_*` row fields; the hook-cost report's held share and bytes |
| `src/refmatrix/recall_pack.py` (25.1) | `pack(held=…)`, the names line, `Packed` fields |
| `src/refmatrix/hook_budget.py` (25.1) | none |
| `src/refmatrix/verbs.py` (`memory_recall`, `_memory_recall_rows`) | `internal["dedupe"]` → `held_items` → `pack(held=…)` |
| `src/refmatrix/cli.py` (`_memory_recall_impl`, `_RecallCall`, `scan-prompt`, `focus hook --event session-start`) | the dedupe context; `record_full` after the print; event fields; the `session_arm` row |
| `src/refmatrix/scan.py` | the held filter through `shown`, the names block |
| `src/refmatrix/context.py` (`render_text_spans`) | `omit_anchor=` |
| `src/refmatrix/arms.py` (new, measurement only; deleted after R7's period) | `SESSION_ARMS`, `draw()` |
| `tests/test_task10_2_names_only.py` (new) | AC-1..AC-13 |
| `workflow/measurements/names-only-2026-11.md` (new) | R7's live run and R8's parity |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-3..AC-7, AC-9, AC-10 at the 25.1 + 10.3 + 10.4 merged base; AC-2 and AC-8
  are guards proven by their mutations ([[feedback_red_test_must_fail_at_head]]).
- No mock of the pack, the renderer, the state, the marker, the generator or telemetry.
- Mutations per [[feedback_commit_before_mutation_revert]] and [[feedback_clear_pycache_after_mutation]].

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.2-plan-10-injection-dedup.md`.
- R8's parity at GREEN; R7's live verdict after the period, each band named.
- Committed on branch `task-10.2-plan-10-injection-dedup`; merged `--no-ff` to `master`.
