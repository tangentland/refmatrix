---
gmd: "0.1"
id: task-28.1-session-arms-and-push-switch
title: "Task 28.1: the plan-28 period record, the paired-run fields on 10.2's session cell, the paired-run override (cell and as-of memory filter), and arm B's push-off switch: per-prompt scan-prompt and recall print nothing and retrieve nothing in cell B"
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
> Status: Drafting (spec wave 2026-11-13, G17; r1 fold of `bsd-spec-t3c`, [[#rev-r1]]).
> Depends on: [[task-10.2-plan-10-injection-dedup]] merged. Its R7 CREATES `arms.py`: the full
> cell table (`A+dedupe`, `A+full`, `B`, `C` at weight 0), the store-scoped `arms.draw`, the
> SessionStart `session_arm` row, and the `dedupe` / `full` branch that the A cells use. The
> record shape and the draw signature were settled with spec-t3b on 2026-11-13 and landed in
> `a3f9d8e` ([[#ownership]]).

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-10.2-plan-10-injection-dedup]]
rel: related-to -> [[task-25.1-recall-hook-byte-budget#r8]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[exploration-handhold-outcome-experiment#arms]]

## Why {#why}

Arm B (push off) needs a switch, and none exists. The exploration's "a full off-switch for push
already exists" was false (contra-b CB-15): no env read in `hooks.py` or `scan.py`, and 25.1 R8
makes the pack "never empty". L20 puts the switch on 10.2's arm table, so the experiment and
10.2's A/B are one draw, not two.

This task also settles three things the r1 review found:
- **The session leg is drawn once per session.** A session's cell is fixed at SessionStart, so a
  session that straddles a period's start or end does not change cell midway.
- **The paired leg is pinned by the runner.** The runner sets each run's cell explicitly; period
  records are never used for it.
- **Paired runs never see a memory written after the task's start.** The as-of filter blocks
  that leak in every scope, including the global one.
{#why-body}

## Who builds what in `arms.py` (settled with spec-t3b, 2026-11-13) {#ownership}

| piece | owner |
|---|---|
| `src/refmatrix/arms.py` created, with: the period record shape (`id`, `salt`, `start`, `end`, `scope` as project slugs, `cells` with weights); the ONE cell enum (`A+dedupe`, `A+full`, `B`, `C`; `C` at weight 0, never drawn); `draw(session_id, *, root, now=None)`; the default `A+dedupe` outside every active period; the SessionStart `session_arm` row; the dedupe factor read from the cell | 10.2 R7 (built before the experiment, L20; it ships with no active period) |
| the plan-28 session-leg record's values (salt, weights per P-1, scope = refmatrix + cliquedb, start, end) | 28.4 freezes them; 28.5 commits them at the user's go |
| the session cell fixed at SessionStart: the single draw at the SessionStart hook's time, `stm/<session>.arm.json` with `{cell, period, t}` (temp-file + replace), and `arms.session_cell` (a missing file gives `A+dedupe`; an unreadable one gives `A+dedupe` plus one stderr line); the verb and scan-prompt read only `session_cell` | 10.2 R7 creates it (spec-t3b `151c81e`); 28.1 R2 extends the file's fields |
| the paired-run override (`arms.paired_override`: cell, run id, as-of) and the as-of memory filter | this task (R3, R4) |
| `arms.push_on` and arm B's push-off in the two per-prompt hooks | this task (R5) |
| `session_arm` on every per-prompt row; `arm_period`, `arm_source` and `arm_run` on the SessionStart row | this task (R2, R6) |
| deleting `arms.py`, the override and the filter after the period | plan-28's close-out, 28.5 R8, under 10.2's deferral row widened by R7 |
| the `cited_in_answer` scorer that both readings use | [[task-28.3-outcome-scorer#r7]] |
{#ownership-table}

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| a1 | ONE arm table, `arms.SESSION_ARMS` (10.2's). It holds ONE plan-28 record, for the session leg only | L20: the experiment's draw IS 10.2's. The paired leg is not drawn (a6) |
| a2 | (built by 10.2 R7; used here) The cell is drawn ONCE, at SessionStart, with `now` = the hook's time, and recorded in `stm/<session>.arm.json`. Every later read in the session uses that file through `arms.session_cell` | r1 #m2: a draw per prompt against the wall clock flips a session that straddles `start` or `end` |
| a3 | ONE predicate, `arms.push_on(session_id, *, root) -> bool`, is false only when the session's cell is `B`. Both per-prompt hooks call it BEFORE retrieval | one decision point, so the two hooks cannot disagree; no retrieval in B, so outcome (5) measures B's real cost |
| a4 | B suppresses the per-prompt payloads only. SessionStart recall and PreCompact recall still run their `--pack` in B, and recall-state, `rmx context`, interactive and MCP recall, and `memory get` behave as in A | the arms table: B keeps boundary and pull (r1 #m1 corrected the earlier "the pack is not called in B") |
| a5 | Cell `C` is never drawn. It exists for 28.2's paired runs, which set it through the runner's bare profile | 10.2 R7; P-10 |
| a6 | **The paired leg sets its cell explicitly** (lead ruling on r1 #s2). The runner exports `RMX_HANDHOLD_CELL` (`A+dedupe` or `B`), `RMX_HANDHOLD_RUN` (its run id) and `RMX_HANDHOLD_AS_OF` (the task's start time) into the `claude` process, which passes them to every hook, the MCP server and every Bash call. `arms.paired_override()` is the ONE reader of the three. When set, it decides the cell and no period record is consulted | a clone root's slug is unknown when a record is committed, a record is inert until 28.5, and `/clear` may mint a new session id; an env value passed by the runner survives all three |
| a7 | **The as-of filter** (lead ruling on r1 #s1). When `RMX_HANDHOLD_AS_OF` is set, every memory row that leaves the store on any read path, in both scopes, is admitted only if its `created` and `updated` are earlier than that time. A row missing either stamp is not admitted, and every refusal is counted | the global store holds rows written after the task started; `--scope both` would leak them to A and B but not to C, which would bias the primary B-vs-C contrast |

## Requirements {#requirements}

1. **R1 The session-leg record.** This task adds ONE record to 10.2's table. Its cells are
   `A+dedupe`, `A+full` and `B` at P-1's weights (equal thirds; `C` stays at 0), and its scope is
   the refmatrix and cliquedb slugs. It is inert, with no active dates, until 28.5 commits the
   salt, start and end from 28.4's frozen file. Scope is matched on the slug, which is the
   root's basename (10.2's shape). So before the start, 28.5 R2 lists every registered store
   whose slug matches and confirms that only the two intended roots exist (r1 #m9). {#r1}
2. **R2 The session cell: 10.2 builds it, and this task extends it.** 10.2 R7 (spec-t3b
   `151c81e`) builds the following:
   - the SessionStart focus hook calls `arms.draw` ONCE, with `now` = the hook's time;
   - it writes `stm/<session>.arm.json` as `{cell, period, t}` (temp-file + replace), plus
     the `session_arm` row;
   - `arms.session_cell(session_id, *, root)` reads that file: a missing file gives
     `A+dedupe`, and an unreadable one gives `A+dedupe` plus one stderr line;
   - the verb and scan-prompt read only `session_cell`, never `draw`.

   This task extends it in four ways:
   - **Two file fields.** The file gains `source` and `run`. `source` is `paired` when
     `arms.paired_override()` is set (then `cell` is the override's, `period` is null and
     `run` is the run id); otherwise `source` is `draw`.
   - **Three row fields.** The `session_arm` row gains `arm_period`, `arm_source` and
     `arm_run`.
   - **`arm_error`.** An unreadable file also sets `arm_error` on the row. The analysis
     excludes such sessions, counted per cell.
   - **`push_on` reads `session_cell`.**

   A `/clear` that mints a new session id runs SessionStart again and draws anew. In the
   session leg that is a new unit; in the paired leg the override gives the same cell and the
   same `run`. {#r2}
3. **R3 The paired-run override.** `arms.paired_override() -> PairedRun | None` reads
   `RMX_HANDHOLD_CELL`, `RMX_HANDHOLD_RUN` and `RMX_HANDHOLD_AS_OF`. It is the only code that
   reads them. A cell outside `{A+dedupe, B}`, a run id that does not match
   `^[a-z0-9-]{8,64}$`, or an unparseable time gives `arm_error` and one stderr line, and falls
   back to `A+dedupe`. 28.2's runner reads the SessionStart row and aborts any run whose row
   does not show the cell it set. {#r3}
4. **R4 The as-of filter.** When a paired run's as-of is set, ONE admit function,
   `arms.as_of_admit(meta, as_of) -> bool`, is applied at the point where memory rows leave the
   store for EVERY read path, in both scopes: `memory recall` (hook and interactive, CLI and
   MCP), `memory get`, recall-state's memory reads, and the memories that `context` attaches.
   Before GREEN, the builder names that one site, read from the code at the 10.2-merged base, in
   the implementation summary. `created` and `updated` come from the row's GMD metadata; a
   save-state's come from its frontmatter. Refusals are counted `as_of_excluded` on the call's
   row. {#r4}
5. **R5 Arm B's push-off switch.** {#r5}
   - `rmx scan-prompt` (the UserPromptSubmit hook) and `rmx memory recall --stdin-json` (the
     per-prompt recall hook) call `arms.push_on(session_id, root=…)` before any retrieval.
   - When it is false, the hook prints nothing and exits 0. It runs no retrieval and no
     per-prompt pack, and it emits no `retrieved` or `delivered` event.
   - It writes its `query.log` row as on any call, with `session_arm: "B"`, `suppressed: "arm"`
     and 0 payload bytes, so the hook-cost report still sees the prompt.
   - The curator status line retrieves nothing and stays on (P-7).
   - SessionStart and PreCompact recall run their `--pack` in B as in A, so 25.1 R8's "never
     empty" holds on every call that packs. The per-prompt hooks do not pack in B.
6. **R6 Rows carry the cell.** Every per-prompt `query.log` row of a session carries
   `session_arm`, read through `arms.session_cell`. `rmx telemetry --context` and the hook-cost
   report split per channel by cell. {#r6}
7. **R7 Deletion.** 10.2's deferral row (`arms.py` is deleted after the experiment's period) is
   widened by this task to cover `push_on`, `session_cell` and the arm file (10.2's), `paired_override`, the
   three env names and `as_of_admit`, with the plan-28 period's end date. If the charter decision
   keeps an arm, that decision amends the row. {#r7}

## Acceptance criteria {#acceptance}

The tests run in 23.0's sandbox, through the GENERATED UserPromptSubmit, SessionStart and
PreCompact commands (`hooks._claude_hook_block(...)`, `bash -c`, the envelope on stdin), on
25.1's fixture store, with a test record whose dates bracket the test's times. Every AC names
the mutation that must fail it (r1 #m3). {#acceptance-lead}

1. **AC-1 The draw at SessionStart.**
   - 600 synthetic ids in scope split by the weights, within ±40 per cell.
   - A root out of scope gets `A+dedupe`, and so does a SessionStart in scope before `start` or
     at `end`.
   - `C` is never drawn.

   **Mutations:** the scope ignored; a random source; `C` drawable. {#ac-1}
2. **AC-2 Cell B prints nothing and retrieves nothing.**
   - In a session whose arm file says `B`, the generated scan-prompt and per-prompt recall
     commands print zero bytes and exit 0.
   - No `retrieved` or `delivered` event is appended.
   - 23.0's connect log shows no socket write by either command after `push_on`.
   - Each command writes one `query.log` row with `session_arm: "B"`, `suppressed: "arm"` and
     `bytes: 0`.

   **Mutation:** retrieval run before `push_on`; the search op shows in the connect log.
   {#ac-2}
3. **AC-3 Boundary and pull are untouched in B.** In the same `B` session:
   - the generated SessionStart recall prints its payload, and both SessionStart and PreCompact
     recall call the pack (a pass-through spy counts one call each);
   - `rmx context X`, MCP `rmx_memory_recall` and interactive `rmx memory recall` print theirs.

   **Mutation:** `push_on` consulted by SessionStart recall; SessionStart prints nothing.
   {#ac-3}
4. **AC-4 The A cells are 10.2's.**
   - An `A+dedupe` session's payloads equal 10.2's dedupe render on the same fixture.
   - An `A+full` session's payloads equal the no-dedupe render.

   **Mutation:** the dedupe factor read from `draw` at the prompt's time rather than from
   `session_cell`, with the session straddling `end`; the `A+full` session dedupes after `end`.
   {#ac-4}
5. **AC-5 `push_on` follows the session cell (r1 #m2).** This AC guards this task's use of 10.2's
   `session_cell`; 10.2's own AC-11 tests the cell itself.
   - A session that starts `B` one second before `end` gets empty per-prompt payloads at prompts
     after `end`.
   - A session that starts one second before `start` gets full payloads after `start`.

   **Mutation:** `push_on` draws with the wall clock; both sessions flip. {#ac-5}
6. **AC-6 The paired override (r1 #s2).**
   - With `RMX_HANDHOLD_CELL=B` and `RMX_HANDHOLD_RUN=r-0001` in the environment, under a root
     that no record scopes, the session's arm file says `B`, source `paired`, run `r-0001`, and
     the per-prompt hooks print nothing.
   - A second SessionStart under a new session id, the `/clear` case, records the same cell and
     run.
   - An invalid cell value gives `A+dedupe`, `arm_error` and one stderr line.

   **Mutations:** the override ignored, so the draw gives `A+dedupe`; the env read in a second
   place (an AST scan finds exactly one reader of each of the three names, `paired_override`).
   {#ac-6}
7. **AC-7 The as-of filter on every read path (r1 #s1).**
   - The fixture holds project and global memories, one in each scope created or updated after
     the as-of time, and one with no `updated`.
   - With `RMX_HANDHOLD_AS_OF` set, none of the three is returned by SessionStart recall,
     per-prompt recall, interactive and MCP recall, `memory get <name>`, recall-state, or the
     memories `rmx context` attaches. Each call's row counts `as_of_excluded`.
   - Without the env, all are returned.

   **Mutations:** the filter on the project scope only, so the global row leaks; the filter
   admitting rows with no stamp. {#ac-7}
8. **AC-8 Rows and reports.**
   - The SessionStart row carries `session_arm`, `arm_period`, `arm_source` and `arm_run`.
   - Every per-prompt row carries `session_arm`.
   - `rmx telemetry --context` prints a per-cell split.

   **Mutation:** `session_arm` omitted on suppressed rows; the per-cell count of `B` prompts
   reads 0. {#ac-8}
9. **AC-9 Hook config unchanged.** `rmx install-hooks --check` is clean, and the generated hook
   block is byte-identical before and after. The switch lives inside the commands, and the env
   names are never interpolated into a hook line. **Mutation:** an env name interpolated into
   the generated UserPromptSubmit command; the byte comparison fails. {#ac-9}

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/arms.py` (created by 10.2, with `session_cell` and the arm file) | the arm file's `source` and `run` fields, `paired_override`, `as_of_admit`, `push_on`; the plan-28 record (inert until 28.5) |
| `src/refmatrix/cli.py` (`scan-prompt`, `_memory_recall_impl` stdin-json path, `focus hook --event session-start`) | the `source` and `run` fields on 10.2's arm file at SessionStart; `push_on` before retrieval; the suppressed row; the SessionStart row fields |
| the one memory-row read site (named before GREEN, R4) | `as_of_admit` |
| `src/refmatrix/telemetry.py` | `session_arm`, `suppressed`, `arm_error`, `as_of_excluded` row fields; the per-cell split |
| `workflow/deferral_registry.md` | 10.2's `arms.py` row widened (R7) |
| `tests/test_task28_1_session_arms.py` (new) | AC-1 to AC-9 |

## Test strategy {#test-strategy}

- RED first at the 10.2-merged base. AC-1 (no record), AC-2, AC-5, AC-6, AC-7 and AC-8 fail
  there. AC-3, AC-4 and AC-9 are guards, each proven by its named mutation.
- No mock of the hooks, the pack, the daemon or telemetry. The record's dates are a test record
  and the times are real; the env values are set in the subprocess environment, not patched.
- Output is captured to `workflow/review-output/pytest-task28-1.log`.

## Definition of done {#done}

- RED then GREEN recorded, with the mutation table and R4's named read site in the
  implementation summary at `workflow/implementation_summaries/task-28.1-session-arms-and-push-switch.md`.
- `rmx install-hooks --check` clean. Committed on branch `task-28.1-session-arms-and-push-switch`
  and merged `--no-ff` to `master`. It ships in a release; the record stays inert until 28.5
  commits its dates.

## Revision r1 (2026-11-13, `bsd-spec-t3c` DIRTY 1B/9S/11M; lead rulings) {#rev-r1}

| finding | disposition | where |
|---|---|---|
| s1 the global store leaks later memories to A and B, not C | the as-of filter on every read path, both scopes, set by the runner (lead) | a7, [[#r4]], [[#ac-7]] |
| s2 a paired record cannot be scoped to clone roots, is inert before 28.2 AC-6, and may lose the pin at `/clear` | no paired record; the runner sets the cell by env, which survives `/clear`; records serve the session leg only (lead) | a6, [[#r3]], [[#ac-6]] |
| m1 "in cell B the pack is not called" is false | corrected: SessionStart and PreCompact still pack; the edge to 25.1 R8 is now `related-to`, not `amends` | a4, [[#r5]], [[#ac-3]] |
| m2 a session can flip cell midway | the cell is fixed at SessionStart in the arm file, which 10.2 R7 creates (`151c81e`) and this task extends; `push_on` and 10.2's dedupe read go through `session_cell` | a2, [[#r2]], [[#ownership]], [[#ac-5]], [[#ac-4]] |
| m3 ACs without a named mutation | every AC names one | [[#acceptance]] |
| m9 the scope is a basename slug | 28.5 R2 checks that only the two intended roots carry those slugs | [[#r1]] |
