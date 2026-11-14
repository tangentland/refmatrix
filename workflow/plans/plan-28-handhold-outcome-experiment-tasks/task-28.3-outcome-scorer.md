---
gmd: "0.1"
id: task-28.3-outcome-scorer
title: "Task 28.3: the ONE outcome scorer and reading module for the handhold experiment: orientation cost, churn, re-derivation, repeated mistakes, handhold cost, used (R12 explicit + cited_in_answer on memory items, within the A cells), 10.2's nested outcomes; blinded labeller agents; the frozen readings"
tags: [task, plan-28, experiment, scorer, transcripts, labels, blinding, telemetry, readings]
metadata:
  node_type: task
  status: pending
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-14
---

# Task 28.3: the outcome scorer {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Pending: approved to build (2026-11-14, [[#approval]]; spec wave 2026-11-13, G17; r1 fold of `bsd-spec-t3c`, [[#rev-r1]]).
> Depends on: [[task-28.1-session-arms-and-push-switch]] (the `handhold_cell` and `arm_run` fields it splits by);
> 21.1's events (R12's explicit `used` evidences); 10.4's `prompt_family`.
> Builds `eval/production/handhold/`. It reads local transcripts (from the archive) and telemetry
> copies, and writes counts. It never appends to any store log.

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-28.1-session-arms-and-push-switch]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: derives-from -> [[exploration-handhold-outcome-experiment#outcomes]]
rel: derives-from -> [[exploration-handhold-outcome-experiment#labels]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: implements -> [[task-19.6-phased-context-and-topic-cache#ranges]]
rel: related-to -> [[task-21.5-tool-used-signal#r6]]
rel: related-to -> [[measurement-task-21.5-r12-pilot-2026-11-13#setup]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]

## Why {#why}

Plan-28's readings are only as good as the one scorer that computes them and the one module that
reads them. L18 and L27 rule that "used" counts only R12 explicit uses plus `cited_in_answer`,
because 21.5's tool legs are unbuilt and their pilot refuted them. 19.6 defines
`cited_in_answer`, but 19.6 is frozen (D-Q3), so its scorer does not exist. This task hosts that
clause, inside 19.6's scope. The r1 review found three problems, and this revision answers each:
- **The push reading could not fail.** It counted a "used" outcome that the push cells produce
  by construction (B1).
- **`cited_in_answer` was wider than 19.6, and its tokeniser could not match.** It covered
  every item type, and its token split broke two of its three forms (S4).
- **Its precision bar was lower than 21.5's** (S5).
{#why-body}

## Requirements {#requirements}

1. **R1 One scorer.** `eval/production/handhold/score.py` exposes one function per outcome. Each
   takes one paired run's archived transcript files and its telemetry copy and returns
   counts. Nothing in it appends to `recall-events.jsonl`, `query.log` or any store file. It reads
   main-loop calls from `<session>.jsonl` and subagent calls from
   `<session>/subagents/agent-<id>.jsonl`. Outcomes (1)-(4) count the main loop only, and subagent
   activity is reported apart. **Every input is a paired run (L83).** There is no live session
   input, so L82's `after_end` rule has no object and is gone. {#r1}
2. **R2 Orientation cost, outcome (1).** It runs from the trigger (the first prompt after
   `startup` or after `/clear`) to the **endpoint**, which is the earlier of:
   - the first `Edit` / `Write` / `MultiEdit` / `NotebookEdit` to a file in the run's reference
     continuation;
   - the first assistant message labelled a correct statement of the resume point (R6's blind
     label).

   It returns the main-loop tool-call count (the banded scalar, P-3), the tokens (input and
   output, from the transcript's usage fields) and the wall time. A run that reaches 28.2's cap
   is `censored`, with its cost taken at the cap. 28.2 R5's `leak_suspect` scan runs here, as
   `leak_scan(run)`. {#r2}
3. **R3 Exploratory churn, outcome (2) (units restated by L87).** It counts Read, Grep, Glob and
   `rmx grep` calls (a Bash `rmx grep` counts) that touch a project file, where no edit of that
   file and no citation of it follows within the next W = 10 main-loop tool calls (P-4, in tool
   calls since L87). It is reported per run and per 100 main-loop tool calls. A citation is the
   file's path or basename as a whole token in an assistant message. **The clock is the run's
   main-loop tool-call sequence**, because a paired run has one prompt (r1 #m4: 21.5's phase B
   is frozen). A churn call within the last W tool calls before the run's endpoint or cap is
   counted only if no edit or citation follows before the run ends, and the count of such
   right-censored calls is printed. {#r3}
4. **R4 Labelled outcomes (3) and (4): the samplers.** {#r4}
   - (3) Re-derivation: paired runs are sampled per cell (sizes frozen by 28.4). For each
     sampled run, a labeller gets the blinded transcript (R6) and the memories and handoff that
     existed at the task's start, the run's memory snapshot (titles and bodies, read locally). The labeller marks
     each event where the agent re-establishes, by search or reading, a fact one of those
     already held.
   - (4) Repeated mistakes: the same sample. A labeller gets the feedback memories that existed
     at the task's start, and marks each event where the agent broke a rule that applied.
   - Both are reported per run and per 100 main-loop tool calls (L87). Labels and their pair ids
     are committed; excerpts and
     memory bodies are not.
5. **R5 Cost of the handholds, outcome (5).** Read from the telemetry copies, per run (per prompt printed beside it, L87) and per
   cell: injected bytes (25.1's byte unit), hook latency (`latency_ms`), and the share of the
   hook output budget. Cell `B`'s suppressed rows count as 0 bytes. {#r5}
6. **R6 Blinding and labellers (r1 #m5).** {#r6}
   - `eval/production/handhold/blind.py` builds the excerpts. It removes every hook output block
     (SessionStart, UserPromptSubmit and PreCompact output, `additionalContext`, and system
     reminders that carry hook text), every `handhold_cell` / `arm_*` / `suppressed` value, and
     every refmatrix command output that names a cell.
   - **The labellers are blind labeller agents**, forked agents that never read the scorer, the
     arm code or any cell assignment and see only R6's excerpts. That is the `lbl-215` practice.
     - The P-5 check (R7) uses **the R12 pilot's rubric**: CAUSED / INFORMED / CONSISTENT /
       UNRELATED ([[measurement-task-21.5-r12-pilot-2026-11-13#setup]]).
     - Outcomes (3), (4) and the endpoint's "correct statement of the resume point" use rubrics
       that 28.4 writes and freezes, each with its label set and two worked examples.
   - A second blind labeller agent labels a 20% sample. Cohen's κ is reported per outcome, and κ
     < 0.6 makes that outcome report-only (P-9). The user spot-checks 10 items per labelled
     outcome. That is a user step, covered by L45's catch-all.
7. **R7 Used, outcome (6) (L18, L27; r1 #s4, #s5).** {#r7}
   - **R12 explicit uses** come from the session's `used` events whose evidence is one of R12's
     three (`memory_get_by_name`, `context_by_name`, `focus_note`). They are attributed to the
     delivering channel by `ref_query_id`, through ONE function, `attribute_explicit_use`. It is
     the one implementation of 21.5 R6's rule, and it follows phase M's precedent (lead ruling
     on r2-s3). It is defined here in `score.py` while plan-28 runs, because plan-28 runs before
     21.5's phase B. When phase B builds, it MOVES the function into
     `src/refmatrix/telemetry.py`, and `score.py` then imports it from `refmatrix.telemetry`.
     `src/` never imports from `eval/`. There is one definition at every point in time.
   - **`cited_in_answer` is hosted here, lifted from 19.6, which is frozen (D-Q3), and kept to
     19.6's scope: delivered MEMORY items.** 19.6's clause
     ([[task-19.6-phased-context-and-topic-cache#ranges]]) reads, in part: "A delivered memory
     item is READ BACK when, later in the same session, any of these points at it by `name` (or,
     for a file, its path or `doc-id#anchor`): … or a later assistant message that contains it
     as a whole token (`cited_in_answer`)." It is ONE function,
     `cited_in_answer(item, later_assistant_texts) -> bool`, over the item's three forms: its
     `name`, its `source_path`, and its `id#anchor` forms.
   - **The whole-token rule keeps `/` and `#` inside a token**, so a path and a `doc-id#anchor`
     match whole. A form matches where it appears with no character from
     `[A-Za-z0-9_\-/#]` immediately before it and none immediately after. A trailing `.`, `,`,
     `:` or `)` ends the token. 21.1's `_NOTE_TOKEN_RE` is NOT used here, because it splits on
     `/` and `#` (`telemetry.py:1473`).
   - **Extension, no weight.** The same function applied to non-memory items (code symbols,
     docs) is printed as a separately labelled extension. It carries no weight in any reading.
   - **The precision gate (lead ruling on r1 #s5; it overrides the earlier P-5 ruling).** Before
     outcome (6) is read, 50 `cited_in_answer` pairs, drawn by a frozen seed from the A cells,
     are labelled by blind labeller agents with the pilot's rubric. `cited_in_answer` carries
     weight only if CAUSED+INFORMED precision is at least 0.80 AND its Wilson lower bound is at
     least 0.65. That is 21.5's bar for a consumer weight. Otherwise outcome (6) counts R12
     explicit uses only, and `cited_in_answer` is reported apart.
   - **Never** a tool-call credit, and never 21.5's `tool_touches` (L27).
   - **Within the A cells only (lead ruling on r1 #b1).** Outcome (6) compares `A+dedupe` with
     `A+full` (10.2's nested reading). It is NOT compared across cells with and without push,
     where it is larger in A by construction. In `B` it is reported descriptively only.
8. **R8 10.2's nested outcomes, outcome (7), from the paired series (L83).** Injected bytes per
   run, with per prompt printed (L87). Used per run, under R7's
   rule. Both are compared `A+dedupe` vs `A+full`, paired by task, split by 10.4's
   `prompt_family`, with names-line items apart. **Limit (L87 m1):** a run has one resume prompt,
   so this sees only first-prompt dedupe against the run's SessionStart (and, under `clear`, warm-up)
   deliveries; the report says so. {#r8}
9. **R9 The readings, one module (r1 #b1).** `eval/production/handhold/readings.py` takes the
   scored results and 28.4's frozen file and returns every band reading. It is the only code
   that reads a band. **Every reading first checks the frozen minimum n of paired tasks per cell
   for the cells it uses (L79, L83).** Below it, the reading is `underpowered` ("underpowered, no verdict"), and the
   n reached per cell is returned with it. {#r9}
   - **Primary:** `B` vs `C` on outcome (1) (P-2), with P-8's CI rule.
   - **Push:** `A+dedupe` vs `B` on outcomes (2)-(4) per 100 main-loop tool calls (P-11, L87).
     Each outcome's A-benefit is B − A, since all three are costs. It gets a paired bootstrap
     over tasks, and the three are Holm-adjusted (r2-m5), with the Holm-adjusted (simultaneous)
     CIs printed. The reading is:
     - `keep push` when, on some outcome, the CI's lower bound is above 0;
     - `shrink` (shrink ambient injection to a gated or pointer-only form) when, on EVERY
       outcome, the CI's upper bound is below the pre-registered non-inferiority margin δ (28.4
       R2), AND A's outcome (5) cost is higher. This is non-inferiority (L87): A is shown not
       to be better by δ or more;
     - "no verdict" otherwise.

     Noise gives wide CIs that reach δ, so it reads "no verdict", never `shrink`. Outcome (6)
     is not an input.
   - **Nested:** 10.2 R7's bands on outcome (7), `A+dedupe` vs `A+full`.

## Acceptance criteria {#acceptance}

Fixture transcripts are synthetic files in Claude Code's transcript format (an external format;
the fixtures are registered as such in `workflow/test_mock_registry.md`). Telemetry is produced
by the real hooks in 23.0's sandbox. Every AC names its mutation. {#acceptance-lead}

1. **AC-1 Orientation cost.**
   - A run with 7 main-loop tool calls, then an Edit of a reference file: cost `7`, endpoint
     `edit`.
   - The same with a subagent's 5 calls interleaved: still `7`, and `subagent_calls=5`.
   - A run that never reaches an endpoint before the cap: `censored`.

   **Mutations:** subagent calls counted (`12`); the endpoint taken at the first Edit of ANY
   file. {#ac-1}
2. **AC-2 Churn, inside ONE prompt (L87).** One synthetic paired run, one resume prompt, 30
   main-loop tool calls:
   - A Read of `F` at call 3, with no edit or citation of `F` in calls 4-13, counts 1.
   - A Read of `G` at call 5, followed by an assistant message naming `G`'s basename after call
     9, counts 0.
   - A Read of `H` at call 6, cited only after call 17 (the 11th call after it), counts 1.
   - A Read of `K` at call 25, with the run ending at call 30, is right-censored: counted per
     R3, and printed in the censored count.
   - The run's churn per 100 main-loop tool calls is the count over 30 × 100.

   **Mutations:** W off by one, so `H` counts 0; W counted in prompts, so every case reads 0 in
   a one-prompt run. {#ac-2}
3. **AC-3 Blinding removes every injected block.** A property test over the fixture
   transcripts: no line of any hook output and no cell value survives in an excerpt, and the
   agent's own messages survive byte-for-byte. **Mutation:** `additionalContext` kept; AC-3
   fails. {#ac-3}
4. **AC-4 Used.** {#ac-4}
   - An R12 `context_by_name` event counts once, under its delivering channel.
   - For a delivered memory item `feedback_x` with `source_path` `memory/feedback_x.md` and an
     anchor `feedback_x#rule`, a later assistant message counts `cited_in_answer` when it
     contains:
     - `feedback_x` as a whole token;
     - `memory/feedback_x.md` (the path form);
     - `feedback_x#rule` (the anchor form).
   - The message does NOT count when it contains `feedback_xy` or `my_feedback_x`.
   - A delivered code symbol cited in an answer counts only in the extension line, never in
     outcome (6).
   - A Read of the delivered file counts nothing.

   **Mutations:**
   - the tokeniser splits on `/` or `#`, so the path or anchor case fails;
   - substring matching, so `feedback_xy` counts;
   - the memory scope dropped, so the code symbol enters outcome (6);
   - `tool_touches` added, so the Read counts.
5. **AC-5 Cost and cells.**
   - A `B` run's suppressed rows give 0 bytes per prompt.
   - An `A+full` run's bytes equal the sum of its rows' payload bytes, split by
     `prompt_family`.

   **Mutation:** suppressed rows read as missing rather than 0, so B's per-prompt mean is taken
   over fewer prompts and the 0 is not printed. {#ac-5}
6. **AC-6 Nothing written.** 21.1's stat-only guard runs over the store copies before and after
   a full scoring pass. **Mutation:** the scorer appends a summary row to the copy's `query.log`;
   the guard fails. {#ac-6}
7. **AC-7 The precision gate.**
   - 50 synthetic labelled pairs with 44 CAUSED+INFORMED (0.88, Wilson lower bound about 0.76):
     `cited_in_answer` carries weight.
   - 40 of 50 (0.80, lower bound about 0.67): it carries weight.
   - 38 of 50 (0.76): R12 explicit only.

   **Mutation:** the gate reads the upper bound < 0.50 (the overridden rule); the 38-of-50 set
   then carries weight and AC-7 fails. {#ac-7}
8. **AC-8 The push reading's three outcomes (r1 #b1, L87).** With δ = 1.0 (in each outcome's
   units, synthetic):
   - **`shrink`.** On every outcome, A − B is near 0 with a tight Holm-adjusted CI whose upper
     bound is below δ; A costs more on (5); and A has 3× B's outcome (6).
   - **`keep push`.** A is better on (3), with the CI's lower bound above 0.
   - **Holm decides `keep push`.** A's unadjusted CI on (3) excludes 0, but the Holm-adjusted
     one does not, and every upper bound is below δ, so the reading is `shrink`.
   - **Noise reads "no verdict".** The same means as the first set, with variance ×9: the CIs
     reach past δ, so neither `keep push` nor `shrink` holds.

   **Mutations:**
   - outcome (6) added to the push inputs, so the first set reads `keep push`;
   - the Holm step removed, so the third set reads `keep push`;
   - `shrink` on "not better" alone, without the δ bound, so the noisy set reads `shrink`.

   Each fails AC-8. {#ac-8}
9. **AC-9 Explicit attribution has one definition across `eval/` and `src/` (r2-s3).** An AST
   scan of `eval/` and `src/` together finds exactly one definition of the `ref_query_id` →
   delivering-channel attribution, `attribute_explicit_use`, wherever it lives: in `score.py`
   before 21.5's phase B, and in `refmatrix/telemetry.py` after it, with `score.py` importing
   it. The scan also finds no `import` of an `eval` module anywhere under `src/`.
   **Mutations:** an inline copy left in `score.py` after the move, so the scan finds two; a
   `src/` module importing from `eval/`, so the import check fails. {#ac-9}
10. **AC-10 Underpowered, no verdict (L79, L83).** A synthetic scored set where `B` and `A+full`
    each have 6 paired tasks against a frozen minimum of 10 makes the push reading and 10.2's
    nested reading both return `underpowered`, with the n reached per cell, never `shrink`, keep
    or fail. At 10 tasks the band is read. **Primary-reading case (L80 m2).** The primary's minimum n is
    28.4 R1's n per cell per trigger, counted AFTER `leak_suspect` and `arm_error` exclusions. A
    synthetic paired set where `C` has 11 runs, 2 of them `leak_suspect`, against a frozen n of
    10 keeps 9 and returns `underpowered` for the primary, with the n reached per cell and
    trigger. At 10 kept runs the band is read. **Mutations:** the minimum check removed, so the
    6-task set returns a band; the primary's n counted before exclusions, so the 11-run set
    returns a band. Either fails AC-10. {#ac-10}

## Files {#files}

| file | change |
|---|---|
| `eval/production/handhold/score.py` (new) | R1-R3, R5, R7 (`cited_in_answer`, `attribute_explicit_use`), R8, `leak_scan` |
| `eval/production/handhold/blind.py` (new) | R6's excerpts |
| `eval/production/handhold/labels.py` (new) | R4's samplers, the P-5 gate's draw, the labeller-agent briefs, κ |
| `eval/production/handhold/readings.py` (new) | R9 |
| `tests/test_task28_3_scorer.py` (new) | AC-1 to AC-10 |
| `tests/fixtures/handhold/transcripts/` (new, test-only) | synthetic transcripts |

## Test strategy {#test-strategy}

- RED first on every AC (no scorer exists).
- The only synthetic input is the transcript format; the telemetry comes from real hooks.
- Output is captured to `workflow/review-output/pytest-task28-3.log`.

## Definition of done {#done}

- RED then GREEN, with the mutation table in the implementation summary at
  `workflow/implementation_summaries/task-28.3-outcome-scorer.md`.
- Committed on branch `task-28.3-outcome-scorer`, merged `--no-ff` to `master`.

## Revision r1 (2026-11-13, `bsd-spec-t3c`; lead rulings) {#rev-r1}

| finding | disposition | where |
|---|---|---|
| b1 the push reading cannot fail: (6) is larger in A by construction | (6) leaves the push reading; push = `A+dedupe` vs `B` on (2)-(4); (6) within the A cells only; AC-8 has a set where `shrink` fires | [[#r7]], [[#r9]], [[#ac-8]] |
| s4 `cited_in_answer` widened past 19.6's memory scope under a "verbatim" label; the tokeniser splits paths and anchors | kept to memory items, quoted in part and not called verbatim; boundary rule keeps `/` and `#`; the extension carries no weight; AC-4 has path and anchor cases | [[#r7]], [[#ac-4]] |
| s5 the P-5 gate admits what 21.5 calls refuted | precision ≥ 0.80 with Wilson lower bound ≥ 0.65, or R12 explicit only (overrides the P-5 ruling) | [[#r7]], [[#ac-7]] |
| m3 ACs without a named mutation | every AC names one | [[#acceptance]] |
| m4 a dead clock branch; a second attribution implementation | the transcript clock is THE clock; `attribute_explicit_use` is canonical and 21.5 phase B imports it | [[#r3]], [[#r7]], [[#ac-9]] |
| m5 the labellers are not named | blind labeller agents; the pilot's rubric for the gate; frozen rubrics for (3), (4) and the endpoint | [[#r6]] |

## Revision r2 (2026-11-13, `bsd-spec-t3c` r2; lead rulings) {#rev-r2}

| finding | disposition | where |
|---|---|---|
| r2-s3 `src/` told to import from `eval/` | `attribute_explicit_use` lives in `score.py` until 21.5 phase B MOVES it into `refmatrix/telemetry.py`; `score.py` then imports it; AC-9 holds one definition across `eval/` and `src/`, plus no `src` → `eval` import | [[#r7]], [[#ac-9]] |
| r2-m5 "better on any" over three uncorrected CIs | Holm across outcomes (2)-(4), pre-registered; AC-8 adds a set where only the Holm step yields `shrink` | [[#r9]], [[#ac-8]] |

## Approval (2026-11-14) {#approval}

rel: derives-from -> [[bsd-spec-t3c-r3-c5d1b79]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]

**Decision row (2026-11-14):** approved by the lead on the user's pattern (d9co) after ch-bsd `bsd-spec-t3c` r3 came back MEH-only (0B/0S/2M at `c5d1b79`), with both MEHs folded (r3 m1, m2). The ch-bsd rounds were r1 DIRTY 1B/9S/11M, r2 DIRTY 0B/3S/7M and r3 MEH-only; every finding is folded, as each spec's revision tables show. This task is `pending`, which means approved to build in plan-28's order. {#approval-row}

## Revision L79 (2026-11-14, the user: "the plan 28 arms should only be 3 days"; Q11 answered (a)) {#rev-l79}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite ch-bsd round.

| change | where |
|---|---|
| every reading checks the frozen minimum n first and returns "underpowered, no verdict" below it; AC-10 | [[#r9]], [[#ac-10]] |


**Refinement (dev master `8d88d29`; the user, the same day: "3 real days will be sufficent", Q11 a):** the period is 3 CALENDAR days from its start, with the arms concurrent. A pause does NOT extend it: the period ends 3 calendar days (72 hours) after the start, whatever was paused, and paused time is not made up. The "active days" wording is replaced. The rest of L79 is unchanged. {#rev-l79-refined}

## Revision L80 (2026-11-14, `bsd-spec-t3c` L79 confirm-lite 0B/1S/4M; lead ruling L80) {#rev-l80}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| m2 AC-10 had no primary-reading case | the primary's minimum n is 28.4 R1's n per cell per trigger after exclusions, with a case and a mutation | [[#ac-10]] |
| m3 the #rev-l79 table did not render; "Q11 assumed" | blank line added; "Q11 answered (a)" | [[#rev-l79]] |


## Revision L82 (2026-11-14, `bsd-spec-t3c` L80 confirm-lite MEH-only 0B/0S/2M; lead ruling L82) {#rev-l82}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| m2 sessions randomised past 72 hours could be scored | R1 drops and counts (`after_end`) any session whose SessionStart is at or after its record's `end` | [[#r1]] |

## Approval of the L79/L80/L82 amendment (2026-11-14, d9co) {#approval-l79-2026-11-14}

| decision | basis | status |
|---|---|---|
| The 3-calendar-day session period (L79, Q11 answered a), the orchestrator-run start under L78 (L80) and the end committed with the start (L82) are approved by the lead on the user's pattern (d9co) after the L80 confirm-lite MEH-only (0B/0S/2M), folded at `49a603c` per L82 with no further round | `workflow/bullshit/2026-11-14-0200-spec-t3c-r5-l80-d42c72b.md` (with the L79 confirm-lite `2026-11-14-0150-spec-t3c-r4-l79-7758d2a.md`, over `spec-wave-t3c` `be03148..d42c72b`) | status unchanged; Q14 (where the verdicts come from) may amend this plan again |

rel: derives-from -> [[bsd-spec-t3c-r5-l80-d42c72b]]

## Revision L83 (2026-11-14, the user, Q14: "drop the live part"; lead ruling L83) {#rev-l83}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite.

| change | where |
|---|---|
| every input is a paired run; L82's `after_end` drop has no object and is removed | [[#r1]] |
| the labelled samplers draw paired runs per cell, and memories are those at the task's start | [[#r4]] |
| 10.2's nested outcome comes from the paired series, paired by task | [[#r8]] |
| the readings check the minimum n of paired tasks per cell; the push test bootstraps over tasks | [[#r9]] |
| AC-5 and AC-10 speak of runs and paired tasks, not sessions | [[#ac-5]], [[#ac-10]] |

## Revision L86 (2026-11-14, lead ruling L86 on the crossed 10.2 / 28.1 arms shapes) {#rev-l86}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite.

| change | where |
|---|---|
| the cell field it splits by and blinds is 10.2's `handhold_cell` | header, [[#r6]] |


## Revision L87 (2026-11-14, `bsd-spec-t3c` L83 confirm-lite; lead ruling L87) {#rev-l87}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite.

| finding | disposition | where |
|---|---|---|
| S2 per-prompt units in a one-prompt run | outcomes per run and per 100 main-loop tool calls; churn's W = 10 tool calls, with right-censoring counted; AC-2's cases fit inside one prompt | [[#r3]], [[#r4]], [[#r5]], [[#r8]], [[#ac-2]] |
| S3 `shrink` fires on noise | push reads `keep push`, `shrink` (non-inferiority: every Holm-adjusted upper bound below δ, and A costs more) or "no verdict"; AC-8 adds the noisy set and the "shrink without δ" mutation | [[#r9]], [[#ac-8]] |
| m1 the nested reading's reach | first-prompt dedupe only, stated as a limit | [[#r8]] |
