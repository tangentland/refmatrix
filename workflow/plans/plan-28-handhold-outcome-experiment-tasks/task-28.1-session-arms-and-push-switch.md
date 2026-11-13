---
gmd: "0.1"
id: task-28.1-session-arms-and-push-switch
title: "Task 28.1: the handhold cells in arms.SESSION_ARMS, a store-scoped draw, and arm B's push-off switch: per-prompt scan-prompt and recall print nothing and retrieve nothing in cell B"
tags: [task, plan-28, experiment, arms, scan-prompt, memory-recall, hooks, telemetry]
metadata:
  node_type: task
  status: drafting
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 28.1: session arms and the push-off switch {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Drafting (spec wave 2026-11-13, G17).
> Depends on: [[task-10.2-plan-10-injection-dedup]] merged. Its R7 builds `arms.py`
> (`SESSION_ARMS`, `draw`), the SessionStart `session_arm` row, and the `dedupe` / `full` branch
> that the A cells use.

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-10.2-plan-10-injection-dedup]]
rel: amends -> [[task-10.2-plan-10-injection-dedup]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r8]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[exploration-handhold-outcome-experiment#arms]]

## Why {#why}

Arm B (push off) needs a switch, and none exists: the exploration's "a full off-switch for push
already exists" was false (contra-b CB-15; no env read in `hooks.py` or `scan.py`; 25.1 R8 makes
the pack "never empty"). L20 puts the switch on 10.2's arm table, so the experiment and 10.2's
A/B are one draw, not two. The draw must also be scoped to the two experiment stores. 10.2's
`arms.draw(session_id)` sees only the session id, so a period active in the deployed code would
randomise every store in the fleet. {#why-body}

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| a1 | ONE arm table, `arms.SESSION_ARMS`, holds a period record: `id`, `salt`, `start`, `end`, `scope` (project slugs, as `handoff.default_memory_dir` derives them), `cells` with weights; outside every period, `draw` returns 10.2's default (`dedupe`) | L20: the experiment's draw IS 10.2's; one table, no second source |
| a2 | `draw` stays pure: `arms.draw(session_id, *, root, now) -> str` is a function of `sha256(session_id + salt)`, the root's slug and `now`; no state file, no env flag | 10.2 R7's rule; a measurement switch must not create state that outlives the period |
| a3 | ONE predicate, `arms.push_on(session_id, *, root, now) -> bool`, is false only in cell `B`. Both per-prompt hooks call it BEFORE retrieval | one decision point, so the two hooks cannot disagree; no retrieval in B, so outcome (5) measures B's real cost |
| a4 | B suppresses the per-prompt payloads only. SessionStart recall, recall-state, PreCompact, `rmx context`, interactive and MCP recall, and `memory get` behave as in A | the arms table: B keeps boundary and pull |
| a5 | Cell `C` is never drawn; it exists for 28.2's paired runs, which pin it by profile | 10.2 R7 already says C is never drawn; P-10 |

## Requirements {#requirements}

1. **R1 The period record.** `arms.SESSION_ARMS` gains the plan-28 period. Its cells are
   `A+dedupe`, `A+full` and `B`, weighted per P-1 (default: equal thirds). Its scope is the
   refmatrix and cliquedb slugs. Salt, start and end come from 28.4's frozen pre-registration and
   are committed by 28.5 at the user's go, never earlier. A second record, scoped to the paired
   leg's clone roots, holds cells `A+dedupe` and `B` for 28.2. Every record names its cells
   from ONE enum shared with 10.2 (`dedupe` is `A+dedupe` and `full` is `A+full` inside a
   handhold period). {#r1}
2. **R2 The store-scoped draw (amends 10.2 R7).** `arms.draw(session_id, *, root, now=None)`:
   when `now` lies in a period's `[start, end)` and the root's slug is in its scope, it returns
   the cell that `sha256(session_id + salt)` picks by weight; otherwise it returns `dedupe`.
   10.2's callers pass `root`. The SessionStart focus hook records `session_arm` (the cell) and
   `arm_period` (the period id) once per session on a `cli.log` row (10.2's row, two fields).
   {#r2}
3. **R3 Arm B's push-off switch.** {#r3}
   - `rmx scan-prompt` (the UserPromptSubmit hook) and `rmx memory recall --stdin-json` (the
     per-prompt recall hook) call `arms.push_on` before any retrieval.
   - When it is false, the hook prints nothing and exits 0. It runs no retrieval and no pack,
     and it emits no `retrieved` or `delivered` event.
   - It writes its `query.log` row as on any call, with `session_arm: "B"`, `suppressed: "arm"`
     and 0 payload bytes, so the prompt clock (21.5 R4) and the hook-cost report still see the
     prompt.
   - The curator status line is not a retrieval and stays on (P-7).
   - 25.1's pack is never called in B, so 25.1 R8's "never empty" governs every call where the
     pack runs, and B is outside it.
4. **R4 Rows carry the cell.** Every per-prompt `query.log` row of a session in a period carries
   `session_arm`. `rmx telemetry --context` and the hook-cost report split per channel by cell.
   {#r4}
5. **R5 Deletion.** 10.2's deferral row (`arms.py` deleted after its period) is widened by this
   task to cover the B branch, `push_on` and the scope field, with the plan-28 period's end date.
   If the charter decision keeps an arm, that decision amends the row. {#r5}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox through the GENERATED UserPromptSubmit and SessionStart commands
(`hooks._claude_hook_block(...)`, `bash -c`, the envelope on stdin), on 25.1's fixture store,
with a test period whose dates bracket `now`. {#acceptance-lead}

1. **AC-1 The draw.** `draw` is deterministic per (session id, salt, slug, now). 600 synthetic
   ids in scope split by the weights within ±40 per cell. A session id under a root out of scope
   draws `dedupe`, and so does one in scope before `start` or at `end`. `C` is never drawn.
   **Mutations:** the scope ignored (out-of-scope draws a cell); a random source (non-deterministic);
   `C` added to the drawable cells. {#ac-1}
2. **AC-2 Cell B prints nothing and retrieves nothing.** For a session drawn `B`, the generated
   scan-prompt and per-prompt recall commands print zero bytes and exit 0. No `retrieved` or
   `delivered` event is appended, and the daemon receives no search op (23.0's connect log shows
   no socket write from either command after `push_on`). Each command writes one `query.log` row
   with `session_arm: "B"`, `suppressed: "arm"` and `bytes: 0`. **Mutation:** retrieval run
   before `push_on`: the search op shows in the connect log. {#ac-2}
3. **AC-3 Boundary and pull are untouched in B.** In the same `B` session, the generated
   SessionStart recall prints its payload, `rmx context X`, MCP `rmx_memory_recall` and
   interactive `rmx memory recall` print theirs, and PreCompact's legs run. **Mutation:**
   `push_on` consulted by SessionStart recall: SessionStart prints nothing and AC-3 fails. {#ac-3}
4. **AC-4 The A cells are 10.2's.** An `A+dedupe` session's payloads equal 10.2's dedupe render
   on the same fixture, and an `A+full` session's equal the no-dedupe render. {#ac-4}
5. **AC-5 Rows and reports.** The SessionStart row carries `session_arm` and `arm_period`, every
   per-prompt row carries `session_arm`, and `rmx telemetry --context` prints a per-cell split.
   {#ac-5}
6. **AC-6 Hook config unchanged.** `rmx install-hooks --check` is clean and the generated hook
   block is byte-identical before and after. The switch lives inside the commands, so no install
   window is needed. {#ac-6}

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/arms.py` (10.2's) | the period record, `scope`, `draw(…, root, now)`, `push_on`, the plan-28 and paired-leg records |
| `src/refmatrix/cli.py` (`scan-prompt`, `_memory_recall_impl` stdin-json path, `focus hook --event session-start`) | `push_on` before retrieval; the suppressed row; `arm_period` on the SessionStart row |
| `src/refmatrix/telemetry.py` | `session_arm`, `suppressed` row fields; the per-cell split in `--context` and the hook-cost report |
| `workflow/deferral_registry.md` | 10.2's `arms.py` row widened (R5) |
| `tests/test_task28_1_session_arms.py` (new) | AC-1 to AC-6 |

## Test strategy {#test-strategy}

- RED first at the 10.2-merged base: AC-1 (no scope), AC-2 (no switch) and AC-5 (no fields)
  fail. AC-3 and AC-4 are guards proven by their mutations.
- No mock of the hooks, the pack, the daemon or telemetry. The period's dates are a test record
  in the table, not a patched clock: `draw` takes `now`.
- Output is captured to `workflow/review-output/pytest-task28-1.log`.

## Definition of done {#done}

- RED then GREEN recorded; mutation table in the implementation summary at
  `workflow/implementation_summaries/task-28.1-session-arms-and-push-switch.md`.
- `rmx install-hooks --check` clean. Committed on branch `task-28.1-session-arms-and-push-switch`
  and merged `--no-ff` to `master`. It ships in a release; the period stays inert (no record is
  active) until 28.5 commits the dates.
