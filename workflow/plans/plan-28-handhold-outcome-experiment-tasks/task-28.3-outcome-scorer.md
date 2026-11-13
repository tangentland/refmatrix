---
gmd: "0.1"
id: task-28.3-outcome-scorer
title: "Task 28.3: the ONE outcome scorer for the handhold experiment: orientation cost, churn, re-derivation, repeated mistakes, handhold cost, used (R12 explicit + cited_in_answer only), 10.2's nested outcomes; blinded label samplers"
tags: [task, plan-28, experiment, scorer, transcripts, labels, blinding, telemetry]
metadata:
  node_type: task
  status: drafting
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 28.3: the outcome scorer {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Drafting (spec wave 2026-11-13, G17).
> Depends on: [[task-28.1-session-arms-and-push-switch]] (the `session_arm` fields it splits by);
> 21.1's events (R12's explicit `used` evidences); 10.4's `prompt_family`.
> Builds `eval/production/handhold/`. It reads local transcripts and telemetry copies, and writes
> counts. It never appends to any store log.

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-28.1-session-arms-and-push-switch]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: derives-from -> [[exploration-handhold-outcome-experiment#outcomes]]
rel: derives-from -> [[exploration-handhold-outcome-experiment#labels]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: implements -> [[task-19.6-phased-context-and-topic-cache#ranges]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]

## Why {#why}

Plan-28's readings are only as good as the one scorer that computes them. L18 and L27 rule that
`used` counts only R12 explicit uses plus `cited_in_answer`, because 21.5's tool legs are
unbuilt and their pilot refuted them. 19.6 defines `cited_in_answer` (a later assistant message
that contains the delivered item's name, path or `doc-id#anchor` as a whole token), but 19.6 is
frozen (D-Q3), so its scorer does not exist. This task implements that clause once, and 19.6
imports it when unfrozen. {#why-body}

## Requirements {#requirements}

1. **R1 One scorer.** `eval/production/handhold/score.py` exposes one function per outcome,
   each taking a session's (or run's) local transcript files and its telemetry copy and
   returning counts. Nothing in it appends to `recall-events.jsonl`, `query.log` or any store
   file. It reads main-loop calls from `<session>.jsonl` and subagent calls from
   `<session>/subagents/agent-<id>.jsonl`. Outcomes (1)-(4) count the main loop only, and
   subagent activity is reported apart. {#r1}
2. **R2 Orientation cost, outcome (1).** From the trigger, meaning the first prompt after
   `startup` or after `/clear`, to the **endpoint**, which is the earlier of:
   - the first `Edit` / `Write` / `MultiEdit` / `NotebookEdit` to a file in the run's reference
     continuation;
   - the first assistant message labelled a correct statement of the resume point (R6's blind
     label).

   It returns the main-loop tool-call count, the tokens (input and output, from the
   transcript's usage fields) and the wall time. A run that reaches 28.2's cap is `censored`,
   with its cost at the cap. P-3 names the banded scalar. {#r2}
3. **R3 Exploratory churn, outcome (2).** Read / Grep / Glob / `rmx grep` calls (a Bash
   `rmx grep` counts) that touch a project file, where neither an edit of that file nor a
   citation of it (its path or basename as a whole token in an assistant message) follows within W
   prompts (P-4, default 3), per 100 prompts. The prompt clock is 21.5 R4's
   (`telemetry.is_prompt_row`, `prompt_clock`), if built; otherwise it is the transcript's
   user-turn sequence, and which clock was used is recorded. {#r3}
4. **R4 Labelled outcomes (3) and (4): the samplers.** {#r4}
   - (3) Re-derivation: sessions are sampled per cell per store (sizes frozen by 28.4). Each
     sampled session's labeller gets the blinded transcript (R6) and the memories and handoff
     that existed at the session's start (titles and bodies, read locally), and marks each event
     where the agent re-establishes, by search or reading, a fact one of those already held.
   - (4) Repeated mistakes: same sample; the labeller gets the feedback memories that existed
     at the session's start, and marks each event where the agent broke a rule that applied.
   - Both are reported per 100 prompts. Labels and their pair ids are committed. Excerpts and
     memory bodies are not.
5. **R5 Cost of the handholds, outcome (5).** Read from the telemetry copies, per prompt and per
   cell: injected bytes (25.1's byte unit), hook latency (`latency_ms`), and the share of the
   hook output budget. Cell `B`'s suppressed rows count as 0 bytes. {#r5}
6. **R6 Blinding.** `eval/production/handhold/blind.py` builds the labellers' excerpts. It
   removes every hook output block: SessionStart, UserPromptSubmit and PreCompact output,
   `additionalContext`, and the system reminders that carry hook text. It also removes every
   `session_arm` / `arm_period` / `suppressed` value and every refmatrix command output that
   names a cell. A second rater labels a 20% sample; Cohen's κ is reported per outcome, and P-9
   applies. {#r6}
7. **R7 Used, outcome (6) (L18, L27).** {#r7}
   - **R12 explicit uses** come from the session's `used` events whose evidence is one of
     R12's three (`memory_get_by_name`, `context_by_name`, `focus_note`), attributed to the
     delivering channel by `ref_query_id` (21.5 R6's rule).
   - **`cited_in_answer`** is ONE function, `cited_in_answer(item, later_assistant_texts) ->
     bool`, by 19.6's definition: the item's `name`, its path, or its `doc-id#anchor` appears as
     a whole token (21.1 R12's `_NOTE_TOKEN_RE`, gated by `_matchable`) in an assistant message
     after the delivery in the same session. 19.6's `score_readback.py` imports it.
   - **Never** a tool-call credit, and never 21.5's `tool_touches` (L27).
   - **The precision check (P-5).** Before outcome (6) is read, 50 `cited_in_answer` pairs,
     drawn by a frozen seed, are labelled blind with R12's rubric. If the CAUSED+INFORMED Wilson
     upper bound is below 0.50, outcome (6) is R12 explicit uses only and `cited_in_answer` is
     reported apart.
8. **R8 10.2's nested outcomes, outcome (7).** Injected bytes per human prompt: all per-prompt
   bytes of the session, non-human turns included, over its human prompts. Used per 100 human
   prompts under R7's rule, names-line items apart. Both split by 10.4's `prompt_family` and by
   cell. {#r8}

## Acceptance criteria {#acceptance}

Fixture transcripts are synthetic files in Claude Code's transcript format (an external format;
the fixtures are registered as such in `workflow/test_mock_registry.md`). The telemetry is
produced by the real hooks in 23.0's sandbox. {#acceptance-lead}

1. **AC-1 Orientation cost.** A run with 7 main-loop tool calls, then an Edit of a reference
   file: cost `7`, endpoint `edit`. The same with a subagent's 5 calls interleaved: still `7`, and
   `subagent_calls=5`. A run that never reaches an endpoint before the cap: `censored`.
   **Mutations:** subagent calls counted (`12`); the endpoint taken at the first Edit of ANY
   file. {#ac-1}
2. **AC-2 Churn.** A Read of `F` with no edit or citation of `F` in the next 3 prompts counts 1;
   the same followed by an assistant message naming `F`'s basename in prompt 2 counts 0; at W =
   3 a citation in prompt 4 still counts 1. **Mutation:** W off by one. {#ac-2}
3. **AC-3 Blinding removes every injected block.** A property test over the fixture
   transcripts: no line of any hook output and no cell value survives in an excerpt, and the
   agent's own messages survive byte-for-byte. **Mutation:** `additionalContext` kept: AC-3
   fails. {#ac-3}
4. **AC-4 Used.** An R12 `context_by_name` event counts once under its delivering channel. A
   later assistant message containing the delivered name as a whole token counts
   `cited_in_answer`, and one containing it inside a longer token does not. A Read of the
   delivered file counts nothing. **Mutations:** `tool_touches` added to used (the Read
   counts); substring matching (the longer token counts). {#ac-4}
5. **AC-5 Cost and cells.** A `B` session's suppressed rows give 0 bytes per prompt. An `A+full`
   session's bytes equal the sum of its rows' payload bytes, split by `prompt_family`.
   {#ac-5}
6. **AC-6 Nothing written.** 21.1's stat-only guard over the store copies, before and after a
   full scoring pass. {#ac-6}

## Files {#files}

| file | change |
|---|---|
| `eval/production/handhold/score.py` (new) | R1-R3, R5, R7, R8 |
| `eval/production/handhold/blind.py` (new) | R6 |
| `eval/production/handhold/labels.py` (new) | R4's samplers and the P-5 check's draw; κ |
| `tests/test_task28_3_scorer.py` (new) | AC-1 to AC-6 |
| `tests/fixtures/handhold/transcripts/` (new, test-only) | synthetic transcripts |

## Test strategy {#test-strategy}

- RED first on every AC (no scorer exists).
- The only synthetic input is the transcript format; the telemetry comes from real hooks.
- Output is captured to `workflow/review-output/pytest-task28-3.log`.

## Definition of done {#done}

- RED then GREEN, with the mutation table in the implementation summary at
  `workflow/implementation_summaries/task-28.3-outcome-scorer.md`.
- Committed on branch `task-28.3-outcome-scorer`, merged `--no-ff` to `master`.
