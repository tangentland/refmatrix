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
> Status: Pending (rewritten 2026-11-13 onto names-only, Q13; revision round 6 the same day
> re-specs it against 25.1b, [[#rev-round-6]]; ch-bsd spec review next). It is built only after
> [[task-10.5-versioned-block-gate]]'s precondition. The design replay PASSED (v1, v2) on 25.1 rev
> 7's pack and must PASS again on 25.1b's (v3, [[task-10.5-versioned-block-gate#part-1b]]). The
> 50-probe read-back test is still to run.
> Depends on: [[task-25.1-recall-hook-byte-budget]] merged (rev 7, 0.83.0);
> [[task-25.1b-hook-output-ladder-and-spill]] MERGED (the ladder, the spill page and the `still in play`
> line that this task adds held members to, L15); [[task-10.3-plan-10-injection-dedup]] (the compaction marker);
> [[task-10.4-non-human-prompt-gate]] (the family field the A/B splits by);
> [[task-10.6-injection-presentation]] (kind labels at every tier); 21.1's events.
> Order (L30): last of plan-10, after T4 (10.5 probe → 10.6 → 10.4 → 10.2). It is built before
> the handhold experiment starts, because the experiment's run is this task's A/B (L20).

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-10.5-versioned-block-gate]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r4]]
rel: depends-on -> [[task-25.1b-hook-output-ladder-and-spill]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[task-10.3-plan-10-injection-dedup]]
rel: depends-on -> [[task-10.4-non-human-prompt-gate]]
rel: depends-on -> [[task-10.6-injection-presentation]]
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
| h9 | No new candidates are pulled in: `k`, the retrieval and the rank order are unchanged; freed bytes are not re-spent. Under 25.1b's ladder this means **tier-pinned**. The pack computes the tiers the `full` run gives, with the ladder over every retrieved row at the channel budget. It then replaces each held row's rendering with its name on the line. A non-held row keeps its `full`-run tier and rendering byte-for-byte, and is never promoted into the freed bytes (rev-round 6) | Q13; the replay's 4+3 lost a use exactly by re-spending freed budget on candidates never delivered at baseline; v1/v2/v3 score the tier-pinned form (names-only at 0.469-0.470 of baseline block bytes means nothing was re-spent); promotion would also make the A/B's byte figure partly a ladder effect |
| h10 | The line, its cap of 15, its overflow and its spill page are 25.1b's (L15). 10.2 supplies only held members, and their bytes are inside the reservation 25.1b makes for the line, so the line is never cut. On scan-prompt, which has no ladder, the line holds held members only and is reserved in scan's own `fit_blocks` call | one owner per line (contra-b CB-1): two lines with one label, or one label with two meanings, is what L15 removes; a line dropped by the fitter would be removal by rule |
| h11 | The live A/B lives HERE, not in 10.4 R7 | the arm switches THIS task's mechanism (`dedupe` vs `full`), and 10.4 ships before 10.2 |
| h12 | `session_start`, `precompact` and explicit pulls (`rmx context`, interactive and MCP recall) never dedupe; `session_start` RECORDS its full deliveries (h1); `precompact` and explicit pulls record nothing | a boundary payload is what the window starts from; an explicit pull is the agent asking for the body, often because it lost it |
| h13 | Order of operations on the recall channel (the same order as 25.1b [[task-25.1b-hook-output-ladder-and-spill#k3]], converged with spec-t3a; [[#open-held-order]]): (1) retrieval, the four-source merge and the exclusions, unchanged; (2) 25.1b's ladder over EVERY row, with the line reserved; (3) each held row leaves its tier and becomes a HELD member of 25.1b's `still in play` line; (4) the line renders its held and over-budget members as 25.1b defines; (5) 25.1b R12's clamp, the safety net. A held row whose `full`-run tier was already the line keeps its place and is marked held | contra-b CB-1 asks for the order of held removal and the ladder to be stated; the order follows from h9, and steps 2 and 3 cannot swap without re-spending |
| h14 | The live A/B's outcome counts only R12 explicit uses plus `cited_in_answer`, never 21.5's unbuilt legs | L27, L18's rule: 21.5's matcher measures proximity, not use (R12 pilot: 7% CAUSED) and is frozen until the experiment reports (D-Q3, D-Q4) |

## Open for the lead: which ladder tier makes an item held {#open-held-tier}

h1 says an item is HELD when it was "delivered FULL". Under 25.1 rev 7 there were only two forms,
the item's own line (hook line, sometimes with a body) and the names line. "FULL" therefore meant
"its own line", and v1/v2 scored that. 25.1b's ladder has four forms: body, excerpt, pointer and
line member. No D-Q or L-row says which of them sets "held". The choice changes what tier pinning
replaces, and it changes v3. This revision does not pick one. R2's `record_full` and h1 read
"rendered at any tier above the line" until the lead settles it. {#open-held-tier-lead}

- **(a) Recommended: tier-aware.** `record_full` stores the tier each item was rendered at. An
  item is held for a call when its stored tier is the same as, or richer than, the tier the
  `full` run gives it now. A body held covers a body, an excerpt or a pointer. A pointer held does
  not cover a body, so the agent never loses content it was never shown. AC-2 gains a leg for
  this.
- **(b) Any rendering above the line sets held.** This is v2's literal reading. It is simpler, but
  an item shown only as a pointer at prompt 2 would be reduced to a name at prompt 5 even when
  prompt 5 would have shown its body.
- **(c) Only a body (tier 1) sets held.** Safe, but on `prompt_recall` at 4,000 B the pack is
  mostly pointers (25.1 d3), so recall would almost never dedupe.

rel: depends-on -> [[task-25.1b-hook-output-ladder-and-spill]]

## Held removal comes after the ladder (resolved) {#open-held-order}

25.1b's first draft (k3) removed held rows BEFORE the ladder. That would have re-spent freed bytes
on promoting non-held rows, against h9 and Q13. spec-t3a changed k3 in `841ca70` to the
tier-pinned order of h13: the ladder over every row first, then held rows leave their tiers, and
the payload is never larger than the full run's. Nothing is left open here. The anchor stays
because commit `537c7e2` cites it. {#open-held-order-lead}

rel: related-to -> [[task-25.1b-hook-output-ladder-and-spill#k3]]

## Open for the lead: where held members sit on the line, and how they are marked {#open-held-mark}

25.1b k2 leaves this to 10.2. 10.6 p2 (the user-agreed rule that labels never reorder and rank
order is kept) settles the ORDER: one rank order across held and over-budget members, under the
one cap of 15. It does not settle whether the agent can tell the two kinds apart on the line. The
difference matters: a held member's content is already in the window, while an over-budget
member's content is only on the spill page. {#open-held-mark-lead}

- **(a) Recommended: mark held members.** Each held member carries one short marker in the line
  (for example a trailing `·held`), and the marker's bytes count inside the line's reservation.
  The agent then knows which names to fetch.
- **(b) No marker.** The line stays as rev 5 drew it. The agent fetches from the page when it
  cannot find a name in its window.

This spec writes order = rank order. The marker waits on this item. {#open-held-mark-order}

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
3. **R3 Recall (on 25.1b's pack, tier-pinned).** `recall_pack.pack(..., held: "Collection |
   None" = None)` follows h13. The pack runs 25.1b's ladder over every row exactly as it does with
   `held=None`. Each row whose `telemetry.item_key` is held then leaves its tier and becomes a
   HELD member of 25.1b's `still in play` line. Non-held rows keep their tiers, rank order and
   renderings byte-for-byte (h9). The line's format, its one cap of 15 in rank order across both
   member kinds ([[task-25.1b-hook-output-ladder-and-spill#k2]]), 10.6's per-member labels (no
   regrouping, 10.6 p2), its overflow and its spill page are 25.1b's. A held member past the cap
   is counted `(+N)`. Every held row's body is written to the spill page, inside the cap or past
   it, because 25.1b k3 step 4 spills the body of every row below tier 1, held rows included.
   Line members, held and over budget alike, sit in one rank order (10.6 p2;
   [[#open-held-mark]]).
   `Packed` gains `held_named` and `held_overflow`. Held members carry the line span 25.1b defines
   for line members. The verb (25.1 R5) reads
   `internal.get("dedupe")` (CLI `--stdin-json` only, the way `embedder_policy` rides
   `**internal`), calls `stm.held_items` once and passes `held`. With `held` empty, the output is
   byte-identical to 25.1b's (the `full` arm). 10.2 changes nothing in `hook_budget`, the budgets,
   the ladder, the line's format, the spill page, the generator, the argv or the trailer. It
   supplies the line's held members and nothing else (L15, contra-b CB-1). {#r3}
4. **R4 scan-prompt.** `scan.scan_prompt(..., held=None)`. A held group ENTRY is removed from
   its bundle by the same group filter that drops entries an earlier section rendered. That
   filter (`shown`) is now keyed by `telemetry.item_key` instead of the entity name. A held ANCHOR
   renders no anchor block (`context.render_text_spans(b, omit_anchor=True)`: no anchor line,
   tldr or body), and its non-held entries render under the bundle header as today. A bundle left
   with nothing is not rendered. Every held item becomes a held member of ONE line, rendered by
   25.1b's line renderer. scan-prompt has no ladder (25.1 R0b), so that line holds held members
   only. It is appended as its own block and reserved in scan's `fit_blocks` call so it is never
   cut. 25.1b's spill page belongs to the pack, and scan-prompt writes none. Past the cap, scan's
   held items are counted `(+N)` with `retrieved` events only, which is rev 5's rule kept. The
   composite is untouched (10.6 owns it). {#r4}
5. **R5 Every turn, human or not.** The dedupe runs on every prompt that reaches the two hooks,
   non-human turns included (Q10); the call's row carries 10.4's `prompt_family` so the effect is
   split by family. If 25.2 is built (its gate passes L34's bands), its ack-only gate runs first
   where it applies. If L43's else-branch fires, 25.2 is not built and nothing runs first. {#r5}
6. **R6 Events and counts.** Every named item emits a `delivered` event. A rendered item's span
   is its rendering, with the `form` of its tier (`full` / `excerpt` / `pointer`, from
   [[task-25.1b-hook-output-ladder-and-spill#k5]], which adds the field). A held member's span is
   the line span, with `form: "held"`. That one value is added to 25.1b's k5 set, so held members
   are told apart from 25.1b's over-budget `names` members. Held members past the cap are treated
   as 25.1b treats its own over-cap members (a `retrieved` event only, counted, and spilled on
   recall) and never get a `delivered` event. 19.2's fold, 21.5's reader and the hook-cost report
   run clean over a mixed file.
   The row carries `held_n`, `held_named`, `held_overflow` and `held_saved_bytes`: the bytes the
   held rows would have rendered as at their `full`-run tiers, minus their bytes on the line.
   `rmx telemetry --context` shows the held share and the bytes saved per channel. {#r6}
7. **R7 Live A/B, per session (moved from 10.4 R7, h11).** {#r7}
   - **Arms:** `dedupe` vs `full` (`held` is the empty set), at equal weights, in refmatrix and
     cliquedb.
   - **The run is the handhold experiment's run (L20).** The A/B is not a serial step and has no
     period of its own. It is a declared factor of the experiment: arm A (push on) splits into
     `A+dedupe` / `A+full`, arm B (no push) has no dedupe factor, and arm C (bare, opt-in) is never
     drawn. The experiment's spec owns the period (≥ 14 days, and ≥ 40 sessions per cell per
     store, whichever is later, written before the start), its salt and its user-gated start.
     That spec is [[plan-28-handhold-outcome-experiment]], from
     [[exploration-handhold-outcome-experiment#assignment]].
   - **One arm table, built here:** 10.2 is built before the experiment starts, so it creates
     `arms.SESSION_ARMS` (new, tiny, pure) holding the experiment's full cell table (`A+dedupe`,
     `A+full`, `B`, and `C` at weight 0), plus `arms.draw(session_id) -> str`, a pure function of
     `sha256(session_id + period salt)` with no state file. The SessionStart focus hook records
     the arm once (`session_arm` on a `cli.log` row). The verb and scan-prompt ask `arms.draw` for
     the dedupe factor. The experiment wires arm B's push-off to the same draw.
     `session_arm` is not 21.1's per-prompt `arm`.
   - **Outcomes, counts only (L27, h14):** injected bytes per human prompt (all per-prompt
     bytes of the session, non-human turns included, divided by its human prompts); used items per
     100 human prompts, where "used" is ONLY a 21.1 R12 explicit `used` event or a
     `cited_in_answer` hit (L18's rule), with names-line items counted apart and held members
     apart from over-budget ones; and the handhold experiment's orientation proxies where its
     scorer exists (recorded, not a band). 21.5's legs (`tool`, `bash_name` and the rest) are NOT
     an outcome: they are unbuilt and frozen (D-Q3, D-Q4). `cited_in_answer` comes from the
     experiment's transcript scorer, the one the experiment uses for its own outcome, with no
     10.2 copy.
   - **Bands, written here before the run:** `dedupe` cuts bytes per human prompt ≥ 30% and its
     used rate is within −5% of `full` (or above) → keep; used rate 5-15% below → the user decides;
     more than 15% below → the user decides whether the names line needs more than names.
   - **The switch is for measurement only:** `arms.py` and its branches are deleted after the
     experiment's period, by the experiment's close-out (a row in `workflow/deferral_registry.md`
     with the end date). Outside the period `draw` returns `A+dedupe` (push on, dedupe on).
     Correctness never depends on it.
   - **Future arm (Q13), not built:** `4+3b` — baseline-delivered non-held rows first, then new
     candidates, then held rows into leftover budget, the rest on the names line. A later A/B adds
     it as a third cell under its own spec.
8. **R8 Offline parity, re-derived (L15).** The v2 figures (0.470 block, 0.872 line, 11/11,
   16/16) were computed against 25.1 rev 7's pack, and 25.1b's ladder changes the baseline. The
   parity target is therefore 10.5's v3 run ([[task-10.5-versioned-block-gate#part-1b]]):
   tier-pinned names-only on 25.1b's pack, with the held rules and the substitution written
   independently in the replay. At GREEN, the same replay re-run with `stm.held_items`,
   `telemetry.item_key` and `pack(held=…)` imported from `src/` reproduces v3's figures on the
   same clones. A difference is a defect in one of the two and is resolved before merge. If v3
   FAILED, 10.2 is not built (10.5 R3b). {#r8}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store with a synthetic session, through the GENERATED
UserPromptSubmit and SessionStart commands (`hooks._claude_hook_block(...)`, `bash -c`, the
envelope on stdin). Unit tables over `pack`, the scan render and `held_items` are in addition.
{#acceptance-lead}

1. **AC-1 Held is named, not rendered.** Prompt 1 renders X (both payloads). Prompt 2 retrieves X
   and Y: it renders Y as the `full` run would, and X only as a held member of 25.1b's line.
   Prompt 3 behaves the same. RED at the 25.1b + 10.3 + 10.4 + 10.6 base.
2. **AC-2 Nothing vanishes; tier-pinned.** A property test runs over the fixture with 200 random
   held subsets (plus the empty and the full one) on both payloads. Every item the `full` run
   names is named in the `dedupe` run: rendered, on the line, or on the spill page and counted.
   Non-held items keep their relative order. No item outside the `full` run's retrieved set
   appears. On recall, every non-held row's rendering is byte-identical to its rendering in the
   `full` run (h9). The `dedupe` payload is never more bytes than the `full` payload. On 25.1b
   AC-17's fixture (40 rows, 20 KB) at 4,000 B with 10 held rows, no non-held row moves to a
   higher tier.
3. **AC-3 Earlier prompts only.** scan-prompt and recall run concurrently on one prompt: neither
   names the other's same-prompt items; a `session_start` delivery is held on the first prompt; an
   identical prompt text re-sent later than `PRE_PROMPT_SKEW_S` does hold; an agent-message turn
   between two human prompts holds what it delivered for the second.
4. **AC-4 Compaction resets.** After the generated PreCompact marker entry (10.3) runs, the next
   prompt renders X in full; the same after SessionStart `compact` and `clear`; not after `resume`.
5. **AC-5 The names line never refreshes held.** X full at prompt 1, named at 2..9; no entry for X
   is written at 2..9; after a marker at 10, X renders full.
6. **AC-6 Cap and budget.** With 20 held items, 25.1b's line names its cap (15) in rank order,
   and the 5 past the cap are counted `(+5)`. On recall, all 20 held rows are on the spill page
   with their bodies (25.1b k3 step 4, R14), and the line's fetch command
   ([[task-25.1b-hook-output-ladder-and-spill#r14]], spelling open as O1) returns them. On
   scan-prompt the 5 are counted `(+5)`, and no page is written. The
   line is present at 2,000 / 4,000 / 9,000 B (25.1 AC-2's budgets), and the payload stays within
   each. Held overflow items have `retrieved` events and no `delivered` events. 25.1b R12's clamp
   does not fire (its `capped` row is absent).
7. **AC-7 Events.** Spans slice exactly (rendered item: its rendering at its tier; held member:
   the line span 25.1b defines), with `form: "held"` distinct from 25.1b's over-budget value,
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
    ids split between `A+dedupe` and `A+full` within ± 30 of their table share; a `full` session's payloads equal the no-dedupe render; the SessionStart
    entry records one `session_arm` row; outside the period every session is `A+dedupe`; inside
    it the four cells are drawn at their table weights and C never is.
12. **AC-12 Offline parity** (R8): the replay with `src/` imports reproduces 10.5's v3 figures on
    the same clones.
13. **AC-13 Mutations that must FAIL a test:** a held item dropped without a name (AC-2); a
    non-held item reordered (AC-2); a new candidate pulled in to fill freed bytes (AC-2); the STM
    turn used for "earlier" (AC-3, the agent-message leg); same-prompt items held (AC-3); the
    marker ignored (AC-4); names-line items recorded as held (AC-5); the names line cut by the
    fitter (AC-6); `(+N)` items given `delivered` events (AC-6); `session_start` naming (AC-8); `rmx
    context` deduped (AC-8); an unreadable state file read as "all held" (AC-10); the scan filter
    keyed by name instead of `telemetry.item_key` (a same-name pair in two files, AC-2);
    `arms.draw` using a random source (AC-11); a non-held row promoted into freed bytes (AC-2,
    tier pinning); held removal applied BEFORE the ladder (AC-2: the 40-row fixture shows a
    promotion); held members printed on a second, 10.2-owned line (AC-14); a held member recorded
    with 25.1b's over-budget `form` (AC-7).
14. **AC-14 One line.** A structural test parses `src/refmatrix/`. The literal `still in play`
    appears only in 25.1b's line renderer. The pack and scan-prompt both call that renderer, and
    neither builds a line of its own.

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `held_items`, `record_full`, `HeldSet` (beside 10.3's marker in `.emitted/`) |
| `src/refmatrix/telemetry.py` | `item_key`; `form` in `RECALL_EVENT_FIELDS_V1` and `call_events`; `held_*` row fields; the hook-cost report's held share and bytes |
| `src/refmatrix/recall_pack.py` (25.1, 25.1b) | `pack(held=…)` tier-pinned (h13); held members passed to 25.1b's line renderer; `Packed` fields |
| `src/refmatrix/hook_budget.py` (25.1, 25.1b) | none |
| `src/refmatrix/verbs.py` (`memory_recall`, `_memory_recall_rows`) | `internal["dedupe"]` → `held_items` → `pack(held=…)` |
| `src/refmatrix/cli.py` (`_memory_recall_impl`, `_RecallCall`, `scan-prompt`, `focus hook --event session-start`) | the dedupe context; `record_full` after the print; event fields; the `session_arm` row |
| `src/refmatrix/scan.py` | the held filter through `shown`, the names block |
| `src/refmatrix/context.py` (`render_text_spans`) | `omit_anchor=` |
| `src/refmatrix/arms.py` (new, measurement only; deleted after R7's period) | `SESSION_ARMS`, `draw()` |
| `tests/test_task10_2_names_only.py` (new) | AC-1..AC-14 |
| `workflow/measurements/names-only-2026-11.md` (new) | R7's live run and R8's parity |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-3..AC-7, AC-9, AC-10 at the 25.1b + 10.3 + 10.4 + 10.6 merged base; AC-2, AC-8 and AC-14
  are guards proven by their mutations ([[feedback_red_test_must_fail_at_head]]).
- No mock of the pack, the renderer, the state, the marker, the generator or telemetry.
- Mutations per [[feedback_commit_before_mutation_revert]] and [[feedback_clear_pycache_after_mutation]].

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.2-plan-10-injection-dedup.md`.
- R8's parity against v3 at GREEN; R7's live verdict after the experiment's period, each band
  named.
- Committed on branch `task-10.2-plan-10-injection-dedup`; merged `--no-ff` to `master`.

## Revision round 6 (2026-11-13, spec wave, spec-t3b) {#rev-round-6}

Driven by G11 and L15, L20, L27, L30 and L43 ([[plan-review-2026-11-13#lead]]), and by contra-b
CB-1. 10.2 was written against 25.1 rev 7 and claimed that "`hook_budget`, `fit_blocks`, the
budgets, the generator, the argv and the trailer format are untouched". Its R8 parity gate
reproduced figures from a pack without the ladder. 25.1b's ladder and spill page change both
(CB-1).

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[task-25.1b-hook-output-ladder-and-spill]]

| change | driver | where |
|---|---|---|
| The line is 25.1b's; 10.2 adds held members and owns no line | L15, CB-1 | h10, R3, R4, AC-14 |
| Tier-pinned: the ladder runs over every row first; held rows then leave their tiers; non-held rows never take freed bytes | h9 applied to the ladder (CB-1 asks for the order) | h9, h13, R3, AC-2 |
| Every held row's body goes to 25.1b's spill page (k3 step 4); held overflow is counted `(+N)` | L15 | R3, AC-6 |
| One rank order across both member kinds (10.6 p2); the held marker is open | 25.1b k2 | R3, [[#open-held-mark]] |
| `form: "held"` is distinct from 25.1b's over-budget form | CB-2's resolution in 25.1b | R6, AC-7 |
| R8 parity target = 10.5 v3 (tier-pinned on 25.1b's pack), not v2 | L15 | R8, AC-12 |
| The A/B is the handhold experiment's run (arm A × {dedupe, full}); the outcome is R12 explicit + `cited_in_answer` only | L20, L27 | R7, h14 |
| 25.2's gate runs first only if 25.2 is built | L34, L43 | R5 |
| Depends on 25.1b and 10.6; built last of plan-10, after T4, before the experiment | L30, L20 | header |
