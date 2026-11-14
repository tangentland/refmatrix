---
gmd: "0.1"
id: task-10.2-plan-10-injection-dedup
title: "Task 10.2: names-only dedupe of the per-prompt payloads — an item the session already holds is removed from scan-prompt and the per-prompt recall and named on one 'still in play' line; nothing new is pulled in; the dedupe-vs-full reading comes from plan-28's paired series (L83)"
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
| h1 | HELD = rendered on its own (any tier above the line) on `scan_prompt`, `prompt_recall` or `session_start` on an EARLIER prompt of the session, after the last compaction marker (cross-block). It is held only at that tier and poorer ones (h15). Rev 5 said "delivered FULL"; under 25.1b's tiers that is made precise by h15 | the four held rules (lead, 2026-11-13); the definition the replay scored (v2) |
| h2 | "Earlier prompt" is decided by prompt identity, not by the STM turn: an entry is earlier when its `prompt_sha` differs from this call's, or when it is older than `stm.PRE_PROMPT_SKEW_S` (10 s) before this call's process start; a `session_start` entry is always earlier | scan-prompt and the recall run concurrently on one prompt and must not hold each other's same-prompt items; the STM turn cannot serve, because 10.4 stops counting agent-message turns while those turns still get payloads (Q10); `PRE_PROMPT_SKEW_S` is the skew 21.1 R9 already uses to tell this prompt from another |
| h3 | Compaction is the only reset (no TTL, no window, no keyframe) | lead rule 2; nothing is removed outright, so a stale "held" only moves an item to the names line, where it is still named |
| h4 | The names line is visible but never sets "held"; only a rendering at tier 1-3 does, and it records its tier (h15) | lead rule 3; an item seen only by name keeps its original full delivery as the reason it is held |
| h5 | scan-prompt dedupes in ITEM units (anchors and group entries), with its own render and its own `fit_blocks` call; the recall dedupes rows inside 25.1's pack | lead rule 4; scan is not a row list |
| h6 | State: one file per WRITING channel, `stm/<session>.emitted/<channel>.json` (`scan_prompt`, `prompt_recall`, `session_start`), each written only by its own hook after its payload is printed; every reader reads all three plus 10.3's `marker.json` | one writer per file, no read-modify-write between concurrent hooks; written after the print so a hook that dies first leaves the old state (the next prompt renders in full; an item is never named that the model did not get) |
| h7 | 21.1's `delivered` events are the MEASUREMENT, not the state | telemetry has a kill switch (`telemetry._disabled()`) and skips a failed append by design, so behaviour would silently depend on telemetry config; reading state back from a 32 MB log costs a backwards scan per prompt |
| h8 | Item key `(scope, entity_id)`, else `(scope, kind, name)`: ONE function, `telemetry.item_key`. It is BUILT by 25.1b, whose `pack` calls it ([[task-25.1b-hook-output-ladder-and-spill]]; bsd-spec-t3ab r3 S5, lead ruling). 10.2's state and `HeldSet`, scan-prompt's filter and 10.5's replay call the same function, so `covers` and the pack always agree on keys | two code symbols with one name in two files are two items; 441 hook deliveries on the 2026-11-13 windows carry no `entity_id` |
| h9 | No new candidates are pulled in: `k`, the retrieval and the rank order are unchanged; freed bytes are not re-spent. Under 25.1b's ladder this means **tier-pinned**. The pack computes the tiers the `full` run gives, with the ladder over every retrieved row at the channel budget. It then replaces each held row's rendering with its name on the line. A non-held row keeps its `full`-run tier and rendering byte-for-byte, and is never promoted into the freed bytes (rev-round 6) | Q13; the replay's 4+3 lost a use exactly by re-spending freed budget on candidates never delivered at baseline; v1/v2/v3 score the tier-pinned form (names-only at 0.469-0.470 of baseline block bytes means nothing was re-spent); promotion would also make the A/B's byte figure partly a ladder effect |
| h10 | The line, its cap of 15, its overflow and its spill page are 25.1b's (L15). 10.2 supplies only held members, and their bytes are inside the reservation 25.1b makes for the line, so the line is never cut. On scan-prompt, which has no ladder, the line holds held members only and is reserved in scan's own `fit_blocks` call | one owner per line (contra-b CB-1): two lines with one label, or one label with two meanings, is what L15 removes; a line dropped by the fitter would be removal by rule |
| h11 | The A/B lives HERE, not in 10.4 R7 (read from plan-28's paired series since L83) | the arm switches THIS task's mechanism (`dedupe` vs `full`), and 10.4 ships before 10.2 |
| h12 | `session_start`, `precompact` and explicit pulls (`rmx context`, interactive and MCP recall) never dedupe; `session_start` RECORDS its full deliveries (h1); `precompact` and explicit pulls record nothing | a boundary payload is what the window starts from; an explicit pull is the agent asking for the body, often because it lost it |
| h13 | Order of operations on the recall channel (the same order as 25.1b [[task-25.1b-hook-output-ladder-and-spill#k3]], converged with spec-t3a; [[#open-held-order]]): (1) retrieval, the four-source merge and the exclusions, unchanged; (2) 25.1b's ladder over EVERY row, with the line reserved; (3) each held row leaves its tier and becomes a HELD member of 25.1b's `still in play` line; (4) the line renders its held and over-budget members as 25.1b defines; (5) 25.1b R12's clamp, the safety net. A held row whose `full`-run tier was already the line keeps its place and is marked held | contra-b CB-1 asks for the order of held removal and the ladder to be stated; the order follows from h9, and steps 2 and 3 cannot swap without re-spending |
| h14 | The A/B's outcome counts only R12 explicit uses plus `cited_in_answer`, never 21.5's unbuilt legs | L27, L18's rule: 21.5's matcher measures proximity, not use (R12 pilot: 7% CAUSED) and is frozen until the experiment reports (D-Q3, D-Q4) |
| h15 | **Tier-aware held (lead ruling, 2026-11-13, on [[#open-held-tier]] (a)).** An item is held for a call only when the tier it was shown at is the same as, or richer than, the tier the `full` run gives it now. Full shown → held at every tier. Excerpt shown → held at excerpt, pointer and names, not at full. Pointer shown → held at pointer and names. A held state with several deliveries keeps the RICHEST tier shown since the marker. Cross-block tiers: a recall or `session_start` row records its 25.1b tier (`full` / `excerpt` / `pointer`). A scan-prompt anchor block (anchor line, tldr, body) records `full`, and a scan group entry (one line: name, kind, location) records `pointer`. 25.1b's tier shapes are: tier 1 = hook line + full body; tier 2 = hook line + excerpt; tier 3 = hook line (which carries its `(rmx memory get …)` fetch pointer) (25.1b R13's string, verbatim, r3 m1); tier 4 = the name on the line (bsd-spec-t3ab S1, lead ruling). Rank for `covers`: `full` > `excerpt` > `pointer` > `names` > `overflow`. `overflow` ranks LOWEST (lead ruling, 2026-11-13, bsd-spec-t3ab m4): an overflow row was never rendered, so it never makes an item held, and `covers` never treats it as shown. `names` and `overflow` are never recorded (h4), so a held state is always `full`, `excerpt` or `pointer` | the agent never loses content it was never shown; (b) would name an item whose body it never saw, and (c) would almost never dedupe `prompt_recall`, which is mostly pointers at 4,000 B (25.1 d3). The scan mapping is the nearest 25.1b tier by content, derived to apply the ruling across blocks, and is called out for review |
| h16 | **Held names are marked (lead ruling, 2026-11-13, on [[#open-held-mark]] (a)).** Each held member on the line carries the suffix `·held`. 10.2 supplies the held flag per member, and 25.1b's one line renderer prints the marker ([[task-25.1b-hook-output-ladder-and-spill#k2]] adopts h16; bsd-spec-t3ab B1, lead ruling), counted inside the line's bytes. The line is the LAST block of the payload (S2). Over-budget members carry no marker. Members keep one rank order across both kinds (10.6 p2). On scan-prompt every member is held and marked | a held member's content is already in the window, while an over-budget member's is only on the spill page; the marker tells the agent which names to fetch |

## Which ladder tier makes an item held (resolved: h15) {#open-held-tier}

Rev 5's h1 said "delivered FULL". Under 25.1 rev 7 that meant "its own line, not the names line".
25.1b's ladder has four forms, and no D-Q or L-row said which of them sets "held". Three options
were put to the lead: (a) tier-aware, (b) any rendering above the line, (c) only a full body. The
lead ruled (a) on 2026-11-13. It is decision h15, and AC-2 tests it. The anchor stays because
`1d7807d` and 10.5 cite it. {#open-held-tier-lead}

rel: depends-on -> [[task-25.1b-hook-output-ladder-and-spill]]

## Held removal comes after the ladder (resolved) {#open-held-order}

25.1b's first draft (k3) removed held rows BEFORE the ladder. That would have re-spent freed bytes
on promoting non-held rows, against h9 and Q13. spec-t3a changed k3 in `841ca70` to the
tier-pinned order of h13: the ladder over every row first, then held rows leave their tiers, and
the payload is never larger than the full run's. Nothing is left open here. The anchor stays
because commit `537c7e2` cites it. {#open-held-order-lead}

rel: related-to -> [[task-25.1b-hook-output-ladder-and-spill#k3]]

## Where held members sit on the line, and how they are marked (resolved: h16) {#open-held-mark}

25.1b k2 leaves this to 10.2. Order: one rank order across held and over-budget members (10.6
p2). Marker: the lead ruled (a) on 2026-11-13, so held members carry `·held` inside the line's
bytes. That is decision h16, and AC-1 and AC-14 test it. {#open-held-mark-lead}

## Requirements {#requirements}

1. **R1 The held set.** `stm.held_items(root, session, *, prompt_sha, t0) -> HeldSet` reads
   `stm/<session>.emitted/{scan_prompt,prompt_recall,session_start}.json` and 10.3's
   `stm.last_marker` once per call and returns the keys held under h1-h2. An entry is `{key, name,
   kind, scope, tier, prompt_sha, ts}`. `HeldSet.covers(key, full_run_tier)` (the `Held` protocol's parameter name, r3 m2) answers
   h15: the richest tier recorded for that key since the marker is the same as, or richer than,
   `full_run_tier`. A missing file contributes nothing; an unreadable one contributes
   nothing plus one `rmx: held state: …` stderr line and `held_error` on the call's row (the safe
   direction: everything renders full); an unreadable marker resets (10.3). {#r1}
2. **R2 The writers.** After printing, the hook `scan-prompt`, `memory recall --stdin-json` and
   `memory recall --session-start` each record the items they rendered at tiers 1-3, each with its
   tier per h15, in their own file (`stm.record_full(root, session, channel, items, *,
   prompt_sha)`, temp-file + replace). Names-line items are never recorded (h4). On recall and
   `session_start`, the tier comes from `Packed`'s per-row rendered tier
   ([[task-25.1b-hook-output-ladder-and-spill#r13]]), and `covers` compares against `Packed`'s
   full-run tier. Telemetry is never read (h7). {#r2}
3. **R3 Recall (on 25.1b's pack, tier-pinned).** **10.2 does NOT build `pack`** (bsd-spec-t3ab
   r2 S1, lead ruling). 25.1b owns `recall_pack.pack` and its `held` parameter, typed as 25.1b's
   `Held` protocol with `covers(key, full_run_tier) -> bool`
   ([[task-25.1b-hook-output-ladder-and-spill#k3]]). 10.2 supplies `stm.HeldSet`, which
   implements that protocol per h15, and passes it to 25.1b's ONE pack call. That call follows
   h13: it runs 25.1b's ladder over every row exactly as with `held=None`. Each row for which
   `held.covers(item_key, full_run_tier)` is true (h15) then
   leaves its tier and becomes a HELD member of 25.1b's `still in play` line, marked `·held`
   (h16). A row whose held tier is poorer than its full-run tier is not held for this call: it
   renders as the `full` run renders it, and that richer rendering is recorded (R2). Non-held rows keep their tiers, rank order and
   renderings byte-for-byte (h9). The line's format, its one cap of 15 in rank order across both
   member kinds ([[task-25.1b-hook-output-ladder-and-spill#k2]]), 10.6's per-member labels (no
   regrouping, 10.6 p2), its overflow and its spill page are 25.1b's. A held member past the cap
   is counted `(+N)`. Every held row's body is written to the spill page, inside the cap or past
   it, because 25.1b k3 step 4 spills the body of every row below tier 1, held rows included.
   Line members, held and over budget alike, sit in one rank order (10.6 p2; h16).
   `Packed` gains `held_named` and `held_overflow`. Held members carry the line span 25.1b defines
   for line members. The verb (25.1 R5) reads
   `internal.get("dedupe")` (CLI `--stdin-json` only, the way `embedder_policy` rides
   `**internal`), calls `stm.held_items` once and passes `held`. With `held` empty, the output is
   byte-identical to 25.1b's (the `full` arm). 10.2 supplies held members and the held flag on
   each. 25.1b's renderer prints `·held` for a flagged member (h16, adopted by 25.1b k2). 10.2
   changes nothing in `hook_budget`, the budgets, the ladder, the spill page, the generator or the
   argv (L15, contra-b CB-1; bsd-spec-t3ab B1). The line is the payload's LAST block, after the
   hits (S2). {#r3}
4. **R4 scan-prompt.** `scan.scan_prompt(..., held=None)`. A held group ENTRY is removed from
   its bundle by the same group filter that drops entries an earlier section rendered. That
   filter (`shown`) is now keyed by `telemetry.item_key` instead of the entity name. A held ANCHOR
   renders no anchor block (`context.render_text_spans(b, omit_anchor=True)`: no anchor line,
   tldr or body), and its non-held entries render under the bundle header as today. A bundle left
   with nothing is not rendered. A held item here is one whose `held.covers` is true at its scan
   tier (an anchor block is `full`, a group entry `pointer`, h15). Every held item becomes a held
   member of ONE line, marked `·held` (h16), rendered by 25.1b's line renderer. scan-prompt has no ladder (25.1 R0b), so that line holds held members
   only. It is appended as scan's LAST block (S2) and reserved in scan's `fit_blocks` call so it
   is never cut. 25.1b's spill page belongs to the pack, and scan-prompt writes none. Past the cap, scan's
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
7. **R7 The nested A/B, read from plan-28's paired series (L83; moved from 10.4 R7, h11).** {#r7}
   - **No live A/B (L83, the user's Q14: "drop the live part").** The user's own sessions are
     never assigned to an arm, and nothing is drawn at SessionStart. Every live session runs
     `A+dedupe`, the shipped default (Q13). The L79 period text (3 calendar days) is superseded
     by L83: the series is not time-boxed.
   - **Arms:** `A+dedupe` vs `A+full` (`held` is the empty set). This is a declared factor of
     plan-28's ONE leg, the paired re-entry leg (fresh agents resuming real handoffs on isolated
     littlebig clones; [[plan-28-handhold-outcome-experiment]]). Its runner
     ([[task-28.2-paired-reentry-runner]]) sets each run's cell explicitly: `A+dedupe`,
     `A+full`, `B` (push off) or `C` (bare). The series, its start and pause rules, and the
     pre-registered minimum n of paired tasks per cell are plan-28's, frozen by
     [[task-28.4-preregistration-freeze]]. Ownership is split per
     [[task-28.1-session-arms-and-push-switch#ownership]].
   - **The switch, built here:** 10.2 is built before plan-28, so it creates
     `src/refmatrix/arms.py` holding:
     - `arms.CELLS = ("A+dedupe", "A+full", "B", "C")`, the one cell enum (no weights, no period
       records, no draw);
     - `arms.cell() -> str`, read in the CLIENT process only (the hook, CLI or MCP process the
       `claude` session spawned). It reads `RMX_HANDHOLD_CELL`, which the paired runner exports
       into the `claude` process and which every hook inherits:
       - unset → `A+dedupe`;
       - a value in `CELLS` → that value;
       - any other value → one `Error: RMX_HANDHOLD_CELL …` stderr line, `arm_error` on the call's
         row, and `A+dedupe`. A hook never crashes on it.

     The verb and scan-prompt call `arms.cell()` once per call. **Only `A+full` turns dedupe
     off** (`held` is the empty set). `A+dedupe`, `B` and `C` dedupe exactly as `A+dedupe`
     would wherever any push exists (L84; r-L83 m2). Push-off (`B`) and the bare profile (`C`) are plan-28's (28.1
     `push_on`, the bare profile), and 10.2 does not branch on them. When `RMX_HANDHOLD_CELL` is
     set, the call's row records the cell as `handhold_cell`, which is distinct from 21.1's
     per-prompt `arm`. 28.1 adds `paired_override()` (run id, as-of) on top of
     `arms.cell()`, so `arms.cell()` stays the ONE reader of `RMX_HANDHOLD_CELL`.
   - **Outcomes, counts only (L27, h14), per paired run of the series:** injected bytes per
     human prompt (all per-prompt bytes of the run, non-human turns included, divided by its
     human prompts); used items per 100 human prompts, where "used" is ONLY a 21.1 R12 explicit `used` event or a
     `cited_in_answer` hit (L18's rule), with names-line items counted apart and held members
     apart from over-budget ones; and the handhold experiment's orientation proxies where its
     scorer exists (recorded, not a band). 21.5's legs (`tool`, `bash_name` and the rest) are NOT
     an outcome: they are unbuilt and frozen (D-Q3, D-Q4). `cited_in_answer` comes from the
     experiment's ONE transcript scorer ([[task-28.3-outcome-scorer#r7]]), and 10.2 has no copy.
   - **Bands, written here before the run** (S9 rows added by lead ruling, 2026-11-13). Rows
     are checked in this order:
     1. **The minimum n is plan-28's** (L83). The reading is taken from the paired series,
        against [[task-28.4-preregistration-freeze]]'s pre-registered minimum n of paired tasks
        per cell for this nested outcome. Below it, the reading is "underpowered, no verdict",
        which 10.2 reads as INCONCLUSIVE with no default change. 10.2 states no n, period or
        extension of its own.
     2. **Bytes.** If `dedupe` cuts bytes per human prompt by less than 30%, there is no default
        change: the run does not confirm `A+dedupe` as the default, and the result is reported.
        Dedupe stays ON. It ships on by default (`A+dedupe` for every live session) because the user
        chose names-only dedupe "now" in Q13, and this row never flips it to `A+full` (lead
        ruling, 2026-11-13).
     3. **Used rate (only when bytes cut ≥ 30%):**
        - within −5% of `full` (or above) → keep;
        - 5-15% below → the user decides;
        - more than 15% below → the user decides whether the names line needs more than
          names.
   - **The switch is for measurement only:** `arms.py` and its branches are deleted after the
     paired series, by the experiment's close-out, as [[task-28.5-run-and-report#r8]]
     specifies. **10.2 creates the deferral row as part of its build** (S8): a row in
     `workflow/deferral_registry.md` with these fields:
     - module `src/refmatrix/arms.py` (measurement only);
     - owner plan-28;
     - deletion at 28.5 R8;
     - end date "written by 28.5 when the series closes".

     28.1 R5 widens the row and 28.5 R8 closes it. With `RMX_HANDHOLD_CELL` unset, which is
     every live session, `arms.cell()` returns `A+dedupe` (push on, dedupe on). Correctness never
     depends on the switch.
   - **Future arm (Q13), not built:** `4+3b` — baseline-delivered non-held rows first, then new
     candidates, then held rows into leftover budget, the rest on the names line. A later A/B adds
     it as a third cell under its own spec.
8. **R8 Offline parity, re-derived (L15).** The v2 figures (0.470 block, 0.872 line, 11/11,
   16/16) were computed against 25.1 rev 7's pack, and 25.1b's ladder changes the baseline. The
   parity target is therefore 10.5's v3 run ([[task-10.5-versioned-block-gate#part-1b]]):
   tier-pinned names-only on 25.1b's pack, with the held rules and the substitution written
   independently in the replay. At GREEN, the same replay re-run with `stm.held_items` (the
   `HeldSet`), `telemetry.item_key` and 25.1b's `pack(held=…)` imported from `src/` reproduces
   v3's figures on the same clones. After G22 rev 2's operational gate deploys (L60), 10.5 R4b
   re-runs this parity check against the re-run target (r2 m5; r3 S3). A difference is a defect in one of the two and is resolved before merge. If v3
   FAILED, 10.2 is not built (10.5 R3b). {#r8}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store with a synthetic session, through the GENERATED
UserPromptSubmit and SessionStart commands (`hooks._claude_hook_block(...)`, `bash -c`, the
envelope on stdin). Unit tables over `pack`, the scan render and `held_items` are in addition.
{#acceptance-lead}

1. **AC-1 Held is named, not rendered.** Prompt 1 renders X (both payloads). Prompt 2 retrieves X
   and Y: it renders Y as the `full` run would, and X only as a held member of 25.1b's line,
   printed `X·held`; an over-budget member on the same line carries no marker; the line is the
   payload's last block, after every hit (S2).
   Prompt 3 behaves the same. RED at the 25.1b + 10.3 + 10.4 + 10.6 base.
2. **AC-2 Nothing vanishes; tier-pinned.** A property test runs over the fixture with 200 random
   held subsets (plus the empty and the full one) on both payloads. Every item the `full` run
   names is named in the `dedupe` run: rendered, on the line, or on the spill page and counted.
   Non-held items keep their relative order. No item outside the `full` run's retrieved set
   appears. On recall, every non-held row's rendering is byte-identical to its rendering in the
   `full` run (h9). The `dedupe` payload is never more bytes than the `full` payload. On 25.1b
   AC-17's fixture (40 rows, 20 KB) at 4,000 B with 10 held rows, no non-held row moves to a
   higher tier. Tier-aware legs (h15):
   - X shown as a pointer at prompt 1 and given a body by the `full` run at prompt 2 renders its
     body at prompt 2 (not held), and that is recorded.
   - X shown as a body at prompt 1 is held at prompt 2 whether the `full` run gives it a body, an
     excerpt or a pointer.
   - X shown as an excerpt is held at excerpt and pointer, not at full.
   - On scan-prompt, an item seen only as a group entry is not held for an anchor block.
   - X that fell to `overflow` (past the cap, `(+N)` only) at prompt 1 is NOT held at prompt 2. It
     renders at whatever tier the `full` run gives it, and no state entry for X was written at
     prompt 1.
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
   ([[task-25.1b-hook-output-ladder-and-spill#r14]], `rmx memory recall --page <token>`)
   returns them. On
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
11. **AC-11 The switch.**
    - With `RMX_HANDHOLD_CELL` unset, both the verb and scan-prompt run `A+dedupe` through the
      GENERATED UserPromptSubmit commands.
    - With `A+full` exported into the hook's environment, the payloads equal the no-dedupe render
      on the same fixture, and the rows carry `handhold_cell: "A+full"`.
    - With `A+dedupe`, they equal the dedupe render.
    - With `B`, wherever a push still runs (`session_start` recording, and any per-prompt payload
      28.1's `push_on` still lets through), 10.2's held handling equals `A+dedupe`'s on the same
      fixture, and the row carries `handhold_cell: "B"` (L84).
    - With `C`, likewise wherever a push still runs, held handling equals `A+dedupe`'s, and the
      row carries `handhold_cell: "C"` (L84). 10.2 branches on neither cell.
    - With a value outside `CELLS`, there is one `Error:` stderr line, `arm_error` on the row,
      exit 0 and the `A+dedupe` render.
    - The generated SessionStart entries write no arm file and no arm row, and nothing under
      `stm/` names an arm.
    - A structural test parses `src/refmatrix/`:
      - `RMX_HANDHOLD_CELL` is read only in `arms.cell`;
      - `arms` has no `draw`, `session_cell` or period record;
      - the verb and scan-prompt call `arms.cell()`.
    - `workflow/deferral_registry.md` holds the `arms.py` row (owner plan-28, deletion 28.5
      R8), added in 10.2's branch (S8).
12. **AC-12 Offline parity** (R8): the replay with `src/` imports reproduces 10.5's v3 figures on
    the same clones.
13. **AC-13 Mutations that must FAIL a test:** a held item dropped without a name (AC-2); a
    non-held item reordered (AC-2); a new candidate pulled in to fill freed bytes (AC-2); the STM
    turn used for "earlier" (AC-3, the agent-message leg); same-prompt items held (AC-3); the
    marker ignored (AC-4); names-line items recorded as held (AC-5); the names line cut by the
    fitter (AC-6); `(+N)` items given `delivered` events (AC-6); `session_start` naming (AC-8); `rmx
    context` deduped (AC-8); an unreadable state file read as "all held" (AC-10); the scan filter
    keyed by name instead of `telemetry.item_key` (a same-name pair in two files, AC-2);
    `B` or `C` treated as `A+full` (AC-11, the B/C leg); a live session assigned a cell (any
    SessionStart write of an arm, or `arms.cell()` returning
    anything but `A+dedupe` with the variable unset) (AC-11); `RMX_HANDHOLD_CELL` read outside
    `arms.cell` (AC-11, the structural test); an invalid cell crashing the hook or silently
    taken as `A+full` (AC-11); a non-held row promoted into freed bytes (AC-2,
    tier pinning); held removal applied BEFORE the ladder (AC-2: the 40-row fixture shows a
    promotion); held members printed on a second, 10.2-owned line (AC-14); a held member recorded
    with 25.1b's over-budget `form` (AC-7); the tier ignored in `HeldSet.covers` (AC-2, the
    pointer-then-body leg); the poorest tier kept instead of the richest (AC-2, the body-then-pointer
    leg); the `·held` marker missing, or put on an over-budget member (AC-1); the line placed
    above the hits instead of last (AC-1); `overflow` ranked richer than `names` in `covers`
    (AC-2); an `overflow` row counted as held, i.e. recorded or treated as shown (AC-2, the
    overflow leg).
14. **AC-14 One line.** A structural test parses `src/refmatrix/`. The literal `still in play`
    appears only in 25.1b's line renderer. The pack and scan-prompt both call that renderer, and
    neither builds a line of its own. The marker literal `·held` likewise appears only in that
    renderer.

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `held_items`, `record_full`, `HeldSet` (implements 25.1b's `Held` protocol: `covers(key, full_run_tier)` per h15; beside 10.3's marker in `.emitted/`) |
| `src/refmatrix/telemetry.py` | (`item_key` is 25.1b's, h8) the value `held` added to 25.1b's `form` (k5; the field itself is 25.1b's); `held_*` row fields; the hook-cost report's held share and bytes |
| `src/refmatrix/recall_pack.py` (25.1, 25.1b) | none: `pack`, its `held` parameter (the `Held` protocol), tier pinning and the line renderer are 25.1b's (r2 S1) |
| `src/refmatrix/hook_budget.py` (25.1, 25.1b) | none |
| `src/refmatrix/verbs.py` (`memory_recall`, `_memory_recall_rows`) | `internal["dedupe"]` → `stm.held_items` → passes the `HeldSet` to 25.1b's `pack(held=…)` |
| `src/refmatrix/cli.py` (`_memory_recall_impl`, `_RecallCall`, `scan-prompt`) | the dedupe context (`arms.cell()`); `record_full` after the print; event fields; `handhold_cell` / `arm_error` on the row |
| `src/refmatrix/scan.py` | the held filter through `shown`, the names block |
| `src/refmatrix/context.py` (`render_text_spans`) | `omit_anchor=` |
| `workflow/deferral_registry.md` | the `arms.py` row (S8): measurement only, owner plan-28, deletion 28.5 R8, end date written by 28.5 when the series closes |
| `src/refmatrix/arms.py` (new, measurement only; deleted by 28.5 R8 after the paired series) | `CELLS`; `cell()` reading `RMX_HANDHOLD_CELL` in the client process (L83: no draw, no period record, no arm file) |
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
- The `arms.py` deferral row is in `workflow/deferral_registry.md` at merge (S8).
- R8's parity against v3 at GREEN; R7's verdict, read from plan-28's paired series once its
  frozen n is reached or the user pauses it, each band named, or "underpowered, no verdict"
  (L83).
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
| One rank order across both member kinds (10.6 p2); held members marked `·held` | 25.1b k2; lead ruling on [[#open-held-mark]] (a) | h16, R3, R4, AC-1, AC-14 |
| `arms.draw(session_id, *, root, now=None)` store-scoped: period records carry `scope`; ships with no active period; out of scope or out of period → `A+dedupe` | spec-t3c, plan-28 handshake (`5ac42e5`): arms.py ships to every store | R7, AC-11 |
| No live A/B: no SessionStart draw, arm file, `session_cell`, period record or scope machinery; `arms.cell()` reads the paired runner's `RMX_HANDHOLD_CELL`; the nested reading comes from plan-28's paired series against 28.4's minimum n of paired tasks per cell; L79's period superseded; dedupe ON stays the live default | L83 (the user's Q14, 2026-11-14; dev master `715e356`) | R7, AC-11, AC-13, Files, `#done` |
| Period = plan-28's 3 calendar days (72 h, never extended); 40 per cell per store is 10.2's minimum n; below it "underpowered, no verdict" = INCONCLUSIVE; the 14-day / whichever-later / 42-day text removed | L79 (user, 2026-11-14; Q11 a; dev master `8d88d29`); plan-28 at spec-wave-t3c `7758d2a` | R7, `#done` |
| v3 re-run trigger re-keyed to G22 rev 2's operational gate (Q9 / L60 supersede the ingest exclusion) | bsd-spec-t3ab r3 S3, lead ruling | R8 |
| Arm file and `session_arm` row written only when the store's slug is in some period record's `scope` | bsd-spec-t3c r2 m6, lead ruling | R7, AC-11, AC-13 |
| bsd-spec-t3ab r3 folded, lead rulings: S5 (`telemetry.item_key` built by 25.1b, h8 cites it, removed from Files); m1 (tier-3 string verbatim from 25.1b); m2 (`covers(key, full_run_tier)`); arm file never redrawn or overwritten on compact/resume/clear | bsd-spec-t3ab-r3 | h8, h15, R1, R7, AC-11, AC-13, Files |
| Cell fixed at SessionStart: one `draw`, `stm/<session>.arm.json`, `arms.session_cell` read per prompt; 28.1 extends it | bsd-spec-t3c r1 m2 (spec-t3c's request; L59) | R7, AC-11, AC-13, Files |
| bsd-spec-t3ab r2 (DIRTY 0B/2S/8M) folded, lead rulings: S1 (10.2 builds no `pack`; it supplies `HeldSet` for 25.1b's `Held` protocol); S2 (period end and minimums deferred to 28.4; the n-floor row deleted); m3 (tier-3 wording = 25.1b's); m5 (the post-G22 parity re-run) | bsd-spec-t3ab-r2 | R3, R7, R8, h15, Files |
| `overflow` ranks lowest in `covers` and never sets held; arm C runs only on plan-28's paired leg (runner-set), never drawn | lead rulings, 2026-11-13 (bsd-spec-t3ab m4; plan-28 review, Q4, L53 P-10) | h15, R7, AC-2, AC-13 |
| bsd-spec-t3ab r1 (DIRTY 1B/10S/10M) folded, lead rulings: B1 (10.2 supplies the held flag; 25.1b's renderer prints `·held`); S1 (tier shapes, `covers` rank incl. `overflow`); S2 (line LAST); S8 (deferral row created here); S9 (n-floor + < 30% rows); m1, m2 | [[bsd-spec-t3ab-ff1d453-369e0b5]] | h15, h16, R3, R4, R7, AC-1, AC-2, AC-6, AC-11, AC-13, Files, DoD |
| Tier-aware held: held only at the tier shown and poorer ones | lead ruling on [[#open-held-tier]] (a) | h1, h4, h15, R1, R2, R3, R4, AC-2 |
| `form: "held"` is distinct from 25.1b's over-budget form | CB-2's resolution in 25.1b | R6, AC-7 |
| R8 parity target = 10.5 v3 (tier-pinned on 25.1b's pack), not v2 | L15 | R8, AC-12 |
| The A/B is the handhold experiment's run (arm A × {dedupe, full}); the outcome is R12 explicit + `cited_in_answer` only | L20, L27 | R7, h14 |
| 25.2's gate runs first only if 25.2 is built | L34, L43 | R5 |
| Depends on 25.1b and 10.6; built last of plan-10, after T4, before the experiment | L30, L20 | header |

## Revision round 7 (2026-11-14, L79) {#rev-round-7}

The user, 2026-11-14: plan-28's arms run "only 3 days", confirmed as 3 real (calendar) days with
the arms concurrent (Q11 a; L79 on dev master `8d88d29`). A pause does not extend the period, and
the n-floor no longer extends it either. Below a pre-registered minimum n, a reading is
"underpowered, no verdict". This round changes:

- R7: the period is plan-28's 3 calendar days. 40 sessions per cell per store is 10.2's minimum n,
  not an end rule.
- R7 band row 1: end = 3 calendar days; below the minimum n the reading is "underpowered, no
  verdict", read as INCONCLUSIVE with no default change. The 42-day REPORT-ONLY clause is gone.
- `#done`: "or underpowered, no verdict".

plan-28's side is 28.4 R2 at spec-wave-t3c `7758d2a`. The status stays `approved`, pending a
confirm-lite. {#rev-round-7-body}

rel: amends -> [[#r7]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[task-28.4-preregistration-freeze]]

## Approval of the L79 amendment (2026-11-14, d9co) {#approval-l79-2026-11-14}

| decision | basis | status |
|---|---|---|
| The L79 revision (plan-28's 3-calendar-day period; 40 sessions per cell per store is 10.2's minimum n, below it "underpowered, no verdict" = INCONCLUSIVE) is approved by the lead on the user's pattern (d9co) after a CLEAN ch-bsd confirm-lite | `workflow/bullshit/2026-11-14-0155-spec-t3b-l79-ca4b9a7.md` (CLEAN, over `spec-wave-t3b` `5233db4..ca4b9a7`) | status unchanged |

rel: derives-from -> [[bsd-spec-t3b-l79-ca4b9a7]]

## Revision round 8 (2026-11-14, L83) {#rev-round-8}

The user, 2026-11-14, answering Q14: "drop the live part" (measured live rates: refmatrix about
0.5 sessions a day, cliquedb about 0.1). L83 on dev master `715e356` gives plan-28 ONE leg, the
paired re-entry leg. Every reading comes from that leg, including 10.2's nested `A+dedupe` vs
`A+full`, and each reading is taken against its own pre-registered minimum n of paired tasks per
cell. The series is not time-boxed, and the user's sessions are never assigned to an arm.
{#rev-round-8-why}

- **R7, removed:** the live draw (`arms.draw`), the period records and their store `scope`, the
  SessionStart arm file (`stm/<session>.arm.json`), `arms.session_cell`, the `session_arm` row,
  the in-scope-only write rule (r2 m6), the no-redraw rule (r3) and L79's 3-day period text.
  Those rules existed only for the live draw, and nothing else needs them.
- **R7, kept or new:** the switch. `arms.CELLS` plus `arms.cell()` read `RMX_HANDHOLD_CELL`,
  which the paired runner (28.2) sets per run. Unset → `A+dedupe` (Q13's live default). An invalid
  value gets a loud stderr line, `arm_error` and `A+dedupe`.
- **Band row 1:** the minimum n is 28.4's paired-task minimum per cell. Below it the reading is
  "underpowered, no verdict" = INCONCLUSIVE, no default change.
- **AC-11:** rewritten for the switch. **AC-13:** the draw, scope, `end` and redraw mutations are
  replaced by "a live session assigned a cell", "`RMX_HANDHOLD_CELL` read outside `arms.cell`"
  and "an invalid cell crashing or read as `A+full`".
- **Not regressed:** 25.1b's `Held` contract (R3, `HeldSet.covers(key, full_run_tier)`, h15),
  `telemetry.item_key` (h8), AC-2's tier legs, AC-14 and the deferral row (S8) are unchanged.

The status stays `approved`, pending a confirm-lite. plan-28's side (28.1 `#ownership`, a6,
`paired_override` over `arms.cell()`, 28.4's paired minimum for 10.2's nested outcome) is
spec-t3c's amendment under the same ruling.

rel: amends -> [[#r7]]
rel: supersedes -> [[#rev-round-7]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[task-28.2-paired-reentry-runner]]
rel: depends-on -> [[task-28.4-preregistration-freeze]]

**L83 confirm-lite MEHs folded (2026-11-14; L84).** m1: the leftover live and period wording is removed
from `#done`, plan-10's task table and execution contract, and 10.4 n10. m2: only `A+full` turns
dedupe off; `B` and `C` dedupe as `A+dedupe` would wherever any push exists, with one AC-11
row per cell and an AC-13 mutation.
{#rev-round-8-mehs}

## Approval of the L83 amendment (2026-11-14, d9co) {#approval-l83-2026-11-14}

| decision | basis | status |
|---|---|---|
| The L83 revision (no live A/B; the paired runner sets each run's cell through `arms.cell()`; only A+full turns dedupe off; 10.2's nested reading comes from plan-28's paired series) is approved by the lead on the user's pattern (d9co) after the L83 confirm-lite MEH-only (0B/0S/2M), folded at `c494391` per L84 with no further round. The 10.2 R7 ↔ 28.1 `#ownership` link is re-checked in plan-28's L83 confirm-lite | `workflow/bullshit/2026-11-14-0210-spec-t3b-l83-dad35ca.md` (over `spec-wave-t3b` `5023620..dad35ca`) | status unchanged |

rel: derives-from -> [[bsd-spec-t3b-l83-dad35ca]]
