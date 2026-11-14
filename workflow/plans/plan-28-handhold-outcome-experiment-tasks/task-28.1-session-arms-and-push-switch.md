---
gmd: "0.1"
id: task-28.1-session-arms-and-push-switch
title: "Task 28.1: the paired-run override read by 10.2's session cell (cell, run, as-of), the as-of memory filter, and arm B's push-off switch: per-prompt scan-prompt and recall print nothing and retrieve nothing in cell B. No SessionStart draw (L83)"
tags: [task, plan-28, experiment, arms, scan-prompt, memory-recall, hooks, telemetry]
metadata:
  node_type: task
  status: pending
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-14
---

# Task 28.1: session arms and the push-off switch {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Pending: approved to build (2026-11-14, [[#approval]]; spec wave 2026-11-13, G17);
> amended by L83 ([[#rev-l83]], pending a confirm-lite).
> Depends on: [[task-10.2-plan-10-injection-dedup]] merged. Its R7 CREATES `arms.py` with
> `CELLS = ("A+dedupe", "A+full", "B", "C")` (no weights) and `arms.cell() -> str`. `arms.cell()`
> runs in the client process only and is the ONE reader of `RMX_HANDHOLD_CELL`:
> - unset gives `A+dedupe`;
> - a value outside `CELLS` gives one `Error:` stderr line, `arm_error` on the call's row, and
>   `A+dedupe`.
>
> 10.2 also builds the `dedupe` / `full` branch that the A cells use. Under L83 there is no
> SessionStart draw, so 10.2 builds no draw, period record, salt, scope, arm file,
> `session_cell` or `session_arm` row. This shape was set by spec-t3b on 2026-11-14
> ([[#ownership]]).

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-10.2-plan-10-injection-dedup]]
rel: related-to -> [[task-25.1-recall-hook-byte-budget#r8]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[exploration-handhold-outcome-experiment#arms]]

## Why {#why}

Arm B (push off) needs a switch, and none exists. The exploration's "a full off-switch for push
already exists" was false (contra-b CB-15): no env read in `hooks.py` or `scan.py`, and 25.1 R8
makes the pack "never empty". L20 puts the switch on 10.2's `arms`, so the experiment and 10.2's
A/B share one cell source.

Under L83 that source is the paired runner alone: plan-28 has one leg, the paired re-entry
series, and the user's own sessions are never assigned to an arm. The runner sets each run's
cell, `A+dedupe`, `A+full`, `B` or `C`, explicitly, and every paired run is filtered to its
task's start time, so it never sees a memory written later. That filter applies in every scope,
the global one included.
{#why-body}

## Who builds what in `arms.py` (L83; proposed to spec-t3b) {#ownership}

| piece | owner |
|---|---|
| `src/refmatrix/arms.py` created, with: `CELLS` (no weights); `arms.cell()`, the ONE reader of `RMX_HANDHOLD_CELL` (unset → `A+dedupe`; invalid → `Error:` line, `arm_error`, `A+dedupe`); the verb and scan-prompt reading the dedupe factor from `arms.cell()` (`A+full` → held is empty; `A+dedupe` → dedupe) | 10.2 R7 (built before the experiment, L20). No draw, period record, salt, scope, arm file, `session_cell` or `session_arm` row (L83; spec-t3b, 2026-11-14) |
| the paired-run override (`arms.parse_paired`, `arms.paired_override`): run id and as-of, with the cell taken from `arms.cell()`; the as-of memory filter | this task (R3, R4) |
| `arms.push_on` and arm B's push-off in the two per-prompt hooks | this task (R5) |
| the SessionStart `session_arm` row and the per-prompt `session_arm` field, written ONLY for a paired run | this task (R2, R6; 10.2 writes no row under L83) |
| deleting the measurement branches of `arms.py`, the override and the filter after the series | plan-28's close-out, 28.5 R8, under 10.2's deferral row widened by R7 |
| the `cited_in_answer` scorer that the readings use | [[task-28.3-outcome-scorer#r7]] |
{#ownership-table}

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| a1 | ONE cell source, 10.2's `arms.cell()`. It returns the runner's `RMX_HANDHOLD_CELL` when one is set, and `A+dedupe` otherwise. Nothing is drawn | L83: the user's own sessions are never assigned to an arm; every reading comes from the paired series |
| a2 | The cell is fixed for the whole run, because the override is an env value the runner exports into the `claude` process. It survives `/clear` and any new session id | r1 #m2's concern (a mid-session flip) cannot arise without a draw |
| a3 | ONE predicate, `arms.push_on() -> bool`, is false only when `arms.cell()` is `B` or `C`. Both per-prompt hooks call it BEFORE retrieval | one decision point, so the two hooks cannot disagree; no retrieval in B, so outcome (5) measures B's real cost. C has no hooks; false for C is the safe direction should a C value ever reach a hook |
| a4 | B suppresses the per-prompt payloads only. SessionStart recall and PreCompact recall still run their `--pack` in B, and recall-state, `rmx context`, interactive and MCP recall, and `memory get` behave as in A | the arms table: B keeps boundary and pull (r1 #m1) |
| a5 | Cell `C` is set through the runner's bare profile (no rmx hook), not through `RMX_HANDHOLD_CELL` | C has no hooks to read a cell |
| a6 | **The runner sets the cell explicitly** (r1 #s2, L83). It exports `RMX_HANDHOLD_CELL` (`A+dedupe`, `A+full` or `B`; C goes through the bare profile), `RMX_HANDHOLD_RUN` (its run id) and `RMX_HANDHOLD_AS_OF` (the task's start time) into the `claude` process, which passes them to every hook, the MCP server and every Bash call. ONE environment reader per name: `arms.cell()` (10.2's) for `CELL`, and `arms.paired_override()` for `RUN` and `AS_OF` | an env value set by the runner needs no record, no clone-root scope and no draw |
| a7 | **The as-of filter is carried as an argument, never read from env by a store process** (r1 #s1, r2-s1). Only the CLIENT process reads `RMX_HANDHOLD_AS_OF`, through `paired_override`: the hook, CLI or MCP process the `claude` session spawned. It passes `as_of` as an explicit argument on every recall, context and scan verb call. The project daemon's op and the hub's global read honour that argument and never read env. A row is admitted only if its `created` and `updated` are both earlier than `as_of`. A row missing either stamp is not admitted, and every refusal is counted | the global store holds rows written after the task started, and `--scope both` would leak them to A and B but not to C. The hub runs under launchd and the clone's daemon may predate the session, so neither process ever sees the session's env; only an argument reaches them |
| a8 | **Outside a paired run nothing changes and nothing is written** (L83). With no `RMX_HANDHOLD_*` env, `arms.cell()` is `A+dedupe`, `push_on` is true, and no `session_arm` row or field is written | the fleet's sessions are not part of the experiment |

## Requirements {#requirements}

1. **R1 No SessionStart draw (L83).** This task adds no period record and no draw. It reads no
   salt, scope, `start` or `end`. The user's own sessions, in any store, always get
   `A+dedupe` from `arms.cell()`. {#r1}
2. **R2 The cell is 10.2's `arms.cell()`; this task adds the paired rows and `push_on`.** 10.2
   R7 builds `arms.cell()`, and the verb and scan-prompt read the dedupe factor from it, never
   from anything else. This task changes nothing in `arms.cell()`. It adds:
   - **The rows, for paired runs only.** When `paired_override()` is set (a run id is
     present), the SessionStart focus hook writes one `session_arm` row on `cli.log` with
     `cell` (from `arms.cell()`), `arm_source: paired` and `arm_run`. Otherwise it writes
     nothing.
   - **`push_on` reads `arms.cell()`.**

   A `/clear` that mints a new session id runs SessionStart again, and the override gives the
   same cell and the same `run` (a2). {#r2}
3. **R3 The paired-run override.** `arms.paired_override() -> PairedRun | None` reads
   `RMX_HANDHOLD_RUN` and `RMX_HANDHOLD_AS_OF`, in the client process only, and takes `cell`
   from 10.2's `arms.cell()`, the one reader of `RMX_HANDHOLD_CELL` (spec-t3b's L83 shape). It
   is the only code that reads `RUN` and `AS_OF`. It returns None when neither is set.
   `PairedRun` has three fields, `cell`, `run` and `as_of`, each of which may be absent: {#r3}
   - **`RUN` + `AS_OF`, no `CELL` (arm C's exact env, r2-s1).** This is valid. `cell` is None,
     so no cell is recorded and the per-prompt hooks are not reached anyway, because C has no
     hooks. `as_of` is set, so the as-of filter is ON for every pull call (R4).
   - **`CELL` + `RUN` + `AS_OF` (`A+dedupe`, `A+full`, `B`).** The cell comes from the env, and
     the filter is on.
   - **Invalid values.** A cell outside `{A+dedupe, A+full, B}`, a run id that does not match
     `^[a-z0-9-]{8,64}$`, or an unparseable time each give `arm_error` and one stderr line. A
     bad cell falls back to `A+dedupe` (through `arms.cell()`, 10.2's rule). A bad run id leaves
     the cell alone, but its `arm_error` excludes the run (28.2 R2). A bad as-of turns the
     filter on at the earliest representable time, which admits nothing, so the error can never
     leak a row.
   - **One parser (r3 m1).** The parsing is ONE pure function,
     `arms.parse_paired(env: Mapping[str, str]) -> PairedRun` (it checks a cell against 10.2's
     `CELLS`, admitting `A+dedupe`, `A+full` and `B`), which raises `PairedRunError`
     on any invalid value. `paired_override()` calls it on `os.environ` and turns the error into
     the `arm_error` fallback above. 28.2's runner calls it on the env it is about to export,
     before launch.

   28.2's runner reads the SessionStart row and aborts any run whose row does not show the cell
   it set, or (for C) shows any rmx hook row.
4. **R4 The as-of filter, carried as an argument (r2-s1).** {#r4}
   - **The client passes it.** The client side (the hook, CLI and MCP adapters, through the
     verbs) reads `paired_override().as_of` and passes `as_of=` as an explicit argument on
     every verb call that returns memory rows: `memory recall` (hook and interactive, CLI and
     MCP), `memory get`, recall-state's memory reads, `context` (its attached memories) and
     `scan-prompt`.
   - **`as_of` is injected, never model-visible (r3 m2).** It rides each verb's `**internal`
     kwargs, as `trace`, `embedder_policy` and 10.2's `dedupe` do. It is not in any verb's
     `defaults`, so the generated MCP schema has no `as_of` property and the CLI has no
     `--as-of` option.
     - The adapters set it from `paired_override()` alone. A model-supplied `as_of` in MCP
       arguments, or any caller-supplied `as_of` that disagrees with the env, is dropped. The
       env value always wins, and with no env value no `as_of` is passed.
     - `tests/test_verb_parity.py` records `as_of` as an injected internal parameter, with the
       reason "measurement-only, injected from `paired_override`, never model-visible; deleted
       with `arms.py`".
   - **The store side honours it.** The daemon op and the hub's global read accept `as_of` in
     their op arguments and apply ONE admit function, `arms.as_of_admit(meta, as_of) -> bool`,
     where rows leave the store, in both scopes. Neither ever reads an environment variable.
     With no `as_of` argument they admit every row, exactly as today.
   - **Naming the sites.** Before GREEN, the builder names, from the code at the 10.2-merged
     base, the verb arguments added and the one admit site per store process, in the
     implementation summary.
   - `created` and `updated` come from the row's GMD metadata; a save-state's come from its
     frontmatter. Refusals are counted `as_of_excluded` and returned in the op's result, so the
     client's row prints the count.
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
6. **R6 Rows carry the cell, in paired runs only.** When `paired_override()` is set, every
   per-prompt `query.log` row carries `session_arm` and `arm_run`, read through `arms.cell()`
   and the override. `rmx telemetry --context` and the hook-cost report split per channel by
   cell. Without an override, rows are unchanged. {#r6}
7. **R7 Deletion.** 10.2's deferral row (`arms.py`'s measurement branches are deleted after the
   experiment) is widened by this task to cover `push_on`, `paired_override`, `parse_paired`,
   the three env names, `as_of_admit` and the paired rows. The row closes when the paired
   series ends. If the charter decision keeps an arm, that decision amends the row. {#r7}

## Acceptance criteria {#acceptance}

The tests run in 23.0's sandbox, through the GENERATED UserPromptSubmit, SessionStart and
PreCompact commands (`hooks._claude_hook_block(...)`, `bash -c`, the envelope on stdin), on
25.1's fixture store, with the paired env set in the subprocess environment. Every AC names the
mutation that must fail it. {#acceptance-lead}

1. **AC-1 No draw, no assignment outside a paired run (L83).**
   - With no `RMX_HANDHOLD_*` in the environment, 200 synthetic sessions in two fixture stores
     all get `A+dedupe` from `arms.cell()`. Their per-prompt hooks print their payloads, and no
     `session_arm` row or field is written.
   - An AST scan of `arms.py` finds no draw: no read of a salt, scope, `start` or `end`, and no
     hash of a session id.

   **Mutation:** a draw over the session id is restored; the 200 sessions split across cells,
   and AC-1 fails. {#ac-1}
2. **AC-2 Cell B prints nothing and retrieves nothing.**
   - With `RMX_HANDHOLD_CELL=B`, the generated scan-prompt and per-prompt recall commands print
     zero bytes and exit 0.
   - No `retrieved` or `delivered` event is appended.
   - 23.0's connect log shows no socket write by either command after `push_on`.
   - Each command writes one `query.log` row with `session_arm: "B"`, `suppressed: "arm"` and
     `bytes: 0`.

   **Mutation:** retrieval run before `push_on`; the search op shows in the connect log.
   {#ac-2}
3. **AC-3 Boundary and pull are untouched in B.** In the same `B` run:
   - the generated SessionStart recall prints its payload, and both SessionStart and PreCompact
     recall call the pack (a pass-through spy counts one call each);
   - `rmx context X`, MCP `rmx_memory_recall` and interactive `rmx memory recall` print theirs.

   **Mutation:** `push_on` consulted by SessionStart recall; SessionStart prints nothing.
   {#ac-3}
4. **AC-4 The A cells are 10.2's.**
   - With `RMX_HANDHOLD_CELL=A+dedupe`, the payloads equal 10.2's dedupe render on the same
     fixture.
   - With `RMX_HANDHOLD_CELL=A+full`, they equal the no-dedupe render.

   **Mutation:** the dedupe factor read from a constant instead of `arms.cell()`; the `A+full`
   run dedupes. {#ac-4}
5. **AC-5 `push_on` follows the session cell.**
   - `push_on` is false under `RMX_HANDHOLD_CELL=B` (and `C`). It is true under `A+dedupe`,
     under `A+full`, and with no env.

   **Mutation:** `push_on` ignoring the override; the `B` run prints its payloads. {#ac-5}
6. **AC-6 The paired override (r1 #s2).**
   - With `RMX_HANDHOLD_CELL=B` and `RMX_HANDHOLD_RUN=r-000001`, the SessionStart row says
     `B`, `arm_source: paired`, run `r-000001`, and the per-prompt hooks print nothing.
   - **The run id's length bound (r2-s2).** The same env with the 6-character `r-0001` puts
     `arm_error` and one stderr line on the row (the cell stays `arms.cell()`'s), and 28.2's
     runner both refuses such an env before launch and excludes any run carrying `arm_error`.
   - A second SessionStart under a new session id, the `/clear` case, records the same cell and
     run.
   - An invalid cell value gives `A+dedupe`, `arm_error` and one stderr line.

   **Mutations:**
   - the override ignored, so the cell is `A+dedupe`;
   - the env read in a second place: an AST scan finds exactly one `os.environ` reader per
     name (`arms.cell` for `RMX_HANDHOLD_CELL`, `paired_override` for `RUN` and `AS_OF`);
   - the length bound dropped from the run-id check, so `r-0001` gets no `arm_error` and the
     second leg
     fails.
   {#ac-6}
7. **AC-7 The as-of filter on every read path (r1 #s1).**
   - The fixture holds project and global memories, one in each scope created or updated after
     the as-of time, and one with no `updated`.
   - With `RMX_HANDHOLD_AS_OF` set, none of the three is returned by SessionStart recall,
     per-prompt recall, interactive and MCP recall, `memory get <name>`, recall-state, or the
     memories `rmx context` attaches. Each call's row counts `as_of_excluded`.
   - Without the env, all are returned.
   - **Arm C's exact env (r2-s1).** With `RMX_HANDHOLD_RUN=r-000001` and `RMX_HANDHOLD_AS_OF` set
     and NO `RMX_HANDHOLD_CELL`, the pull paths (`rmx context`, interactive and MCP recall,
     `memory get`) return none of the three. The global leg is served by a real throwaway
     hub-style global store under the sandbox (23.0's global root), whose process was started
     BEFORE the env was set. No row records a cell.
   - **The store side never reads env.** An AST scan of the daemon op and the global-read code
     finds no read of any `RMX_HANDHOLD_*` name.

   **Mutations:**
   - the filter on the project scope only, so the global row leaks;
   - the filter admitting rows with no stamp;
   - the daemon or global read taking `as_of` from env instead of the argument, so under C's
     env the global row leaks (its process never saw the env) and the AST scan fails;
   - `paired_override` returning None when `CELL` is unset, so C's filter is off and the C leg
     leaks.
   {#ac-7}
8. **AC-8 Rows and reports, in paired runs only.**
   - Under a paired env, the SessionStart row carries `session_arm`, `arm_source` and
     `arm_run`, and every per-prompt row carries `session_arm` and `arm_run`.
   - `rmx telemetry --context` prints a per-cell split.
   - Without the env, no row gains any of these fields.

   **Mutations:**
   - `session_arm` omitted on suppressed rows, so the per-cell count of `B` prompts reads 0;
   - rows written without an override, so the no-env leg fails.
   {#ac-8}
9. **AC-9 Hook config unchanged.** `rmx install-hooks --check` is clean, and the generated hook
   block is byte-identical before and after. The switch lives inside the commands, and the env
   names are never interpolated into a hook line. **Mutation:** an env name interpolated into
   the generated UserPromptSubmit command; the byte comparison fails. {#ac-9}
10. **AC-10 `as_of` is not model-visible (r3 m2).**
    - The generated MCP schema of every verb has no `as_of` property, and the CLI has no
      `--as-of` option. The parity test's injected-parameter record names `as_of` with its
      reason.
    - Under an env `RMX_HANDHOLD_AS_OF` = T, an MCP `rmx_memory_recall` call whose arguments
      include `as_of` = a time later than T still excludes a row written between T and that
      later time.
    - With no env, an MCP call carrying `as_of` returns that row, because the model's value is
      dropped.

    **Mutations:** `as_of` added to a verb's `defaults`, exposing it in the schema; the adapter
    preferring a caller's `as_of` over the env. Either fails AC-10. {#ac-10}

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/arms.py` (created by 10.2, with `CELLS` and `arms.cell()`) | `parse_paired`, `paired_override`, `as_of_admit`, `push_on` |
| `src/refmatrix/cli.py` (`scan-prompt`, `_memory_recall_impl` stdin-json path, `focus hook --event session-start`) | `push_on` before retrieval; the suppressed row; the paired SessionStart row |
| `src/refmatrix/verbs.py` (the verbs that return memory rows) and the CLI / MCP adapters | the client side: read `paired_override().as_of` and pass `as_of=` on every such call (R4) |
| the project daemon's memory op and the hub's global read (sites named before GREEN, R4) | the store side: accept `as_of` as an op argument and apply `as_of_admit`; return `as_of_excluded`; never read env |
| `src/refmatrix/telemetry.py` | `session_arm`, `arm_run`, `suppressed`, `arm_error`, `as_of_excluded` row fields (paired runs only); the per-cell split |
| `workflow/deferral_registry.md` | 10.2's `arms.py` row widened (R7) |
| `tests/test_task28_1_session_arms.py` (new) | AC-1 to AC-10 |
| `tests/test_verb_parity.py` | `as_of` recorded as an injected internal parameter, with its reason (R4) |

## Test strategy {#test-strategy}

- RED first at the 10.2-merged base. AC-2, AC-4's `A+full` leg, AC-5, AC-6, AC-7, AC-8 and
  AC-10 fail there. AC-1, AC-3 and AC-9 are guards, each proven by its named mutation.
- No mock of the hooks, the pack, the daemon or telemetry. The env values are set in the
  subprocess environment, not patched.
- Output is captured to `workflow/review-output/pytest-task28-1.log`.

## Definition of done {#done}

- RED then GREEN recorded, with the mutation table and R4's named read site in the
  implementation summary at `workflow/implementation_summaries/task-28.1-session-arms-and-push-switch.md`.
- `rmx install-hooks --check` clean. Committed on branch `task-28.1-session-arms-and-push-switch`
  and merged `--no-ff` to `master`. It ships in a release. Outside a paired run it changes
  nothing (a8).

## Revision r1 (2026-11-13, `bsd-spec-t3c` DIRTY 1B/9S/11M; lead rulings) {#rev-r1}

| finding | disposition | where |
|---|---|---|
| s1 the global store leaks later memories to A and B, not C | the as-of filter on every read path, both scopes, set by the runner (lead) | a7, [[#r4]], [[#ac-7]] |
| s2 a paired record cannot be scoped to clone roots, is inert before 28.2 AC-6, and may lose the pin at `/clear` | no paired record; the runner sets the cell by env, which survives `/clear`; records serve the session leg only (lead) | a6, [[#r3]], [[#ac-6]] |
| m1 "in cell B the pack is not called" is false | corrected: SessionStart and PreCompact still pack; the edge to 25.1 R8 is now `related-to`, not `amends` | a4, [[#r5]], [[#ac-3]] |
| m2 a session can flip cell midway | the cell is fixed at SessionStart in the arm file, which 10.2 R7 creates (`151c81e`) and this task extends; `push_on` and 10.2's dedupe read go through `session_cell` | a2, [[#r2]], [[#ownership]], [[#ac-5]], [[#ac-4]] |
| m3 ACs without a named mutation | every AC names one | [[#acceptance]] |
| m9 the scope is a basename slug | 28.5 R2 checks that only the two intended roots carry those slugs | [[#r1]] |

## Revision r2 (2026-11-13, `bsd-spec-t3c` r2 DIRTY 0B/3S/7M; lead rulings) {#rev-r2}

| finding | disposition | where |
|---|---|---|
| r2-s1 the as-of env never reaches the hub or the clone daemon; C's partial env is undefined | the client reads the env and passes `as_of` as an explicit verb/op argument; the daemon op and the hub's global read honour the argument and never read env; `RUN` + `AS_OF` without `CELL` (arm C) keeps the filter on; AC-7 has a leg under C's exact env against a global store started before the env, with the mutation "store reads env instead of the argument" | a7, [[#r3]], [[#r4]], [[#ac-7]], [[#files]] |
| r2-s2 AC-6's run id fails R3's own regex | AC-6 uses `r-000001`; a second leg asserts that the 6-character `r-0001` falls back with `arm_error`; the length-bound mutation | [[#ac-6]] |

## Revision r3 (2026-11-14, `bsd-spec-t3c` r3 confirm-lite MEH-only 0B/0S/2M; lead rulings) {#rev-r3}

| finding | disposition | where |
|---|---|---|
| r3 m1 a bad `AS_OF` with a valid cell runs on with zero memories | ONE parser, `arms.parse_paired`, used by `paired_override` and by 28.2's runner before launch | [[#r3]] |
| r3 m2 `as_of` as a verb parameter would be model-visible | it rides `**internal`, injected by the adapters from `paired_override`; not in the MCP schema or the CLI; the env always wins; the parity test records it with a reason; AC-10 | [[#r4]], [[#ac-10]], [[#files]] |

## Approval (2026-11-14) {#approval}

rel: derives-from -> [[bsd-spec-t3c-r3-c5d1b79]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]

**Decision row (2026-11-14):** approved by the lead on the user's pattern (d9co) after ch-bsd `bsd-spec-t3c` r3 came back MEH-only (0B/0S/2M at `c5d1b79`), with both MEHs folded (r3 m1, m2). The ch-bsd rounds were r1 DIRTY 1B/9S/11M, r2 DIRTY 0B/3S/7M and r3 MEH-only; every finding is folded, as each spec's revision tables show. This task is `pending`, which means approved to build in plan-28's order. {#approval-row}

## Revision L80 (2026-11-14, `bsd-spec-t3c` L79 confirm-lite 0B/1S/4M; lead ruling L80) {#rev-l80}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| S1 the start is delegated (L78) | the ownership row says 28.5 commits the period's values when Depends-on holds, after telling the user | [[#ownership]] |

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
| no SessionStart draw: R1 (formerly the session-leg record) now states that no record, salt, scope or draw exists; the user's sessions always get `A+dedupe` | [[#r1]], a1, a8, [[#ac-1]] |
| the cell comes from 10.2's `arms.cell()`, the one reader of `RMX_HANDHOLD_CELL` (spec-t3b's L83 shape, 2026-11-14); `session_cell`, the arm file and the period fields (`arm_period`, `source: draw`) are gone; `paired_override` reads `RUN` and `AS_OF` | [[#r2]], [[#r3]], [[#ownership]] |
| the override admits `A+full` too, because 10.2's nested reading now comes from the paired series | a6, [[#r3]], [[#ac-4]] |
| rows are written only in paired runs | a8, [[#r6]], [[#ac-8]] |
| AC-1 (the draw) is replaced by "no draw, no assignment"; AC-4's and AC-5's straddling cases are replaced by override cases | [[#acceptance]] |
| the r1 m2 / m9 machinery (a session cell fixed at SessionStart against a period; the slug check) has no object under L83 and is kept only as history above | [[#rev-r1]] |
