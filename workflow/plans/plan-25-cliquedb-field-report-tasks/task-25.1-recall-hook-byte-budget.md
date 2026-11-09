---
gmd: "0.1"
id: task-25.1-recall-hook-byte-budget
title: "Task 25.1: the recall hooks pack their hits under a per-channel UTF-8 byte budget applied after the four-source merge, and a mis-typed save-state stays out (bug-164; builds task 19.1)"
tags: [task, plan-25, bug-164, memory-recall, hooks, budget, pack, verbs, cliquedb]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-08
  updated: 2026-11-08
---

# Task 25.1: recall hook byte budget {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-08)
> Bug: bug-164 (cliquedb priority 1)
> Depends on: task 3.7 MERGED to `master` ([[plan-25-cliquedb-field-report#overlap]]); plan-26
> merged (its 26.4 owns the save-state mtype fix this task re-asserts on the packed path, and its
> 26.7 regroups `MEMORY.md`, which R3's curated-hook lookup reads); 23.0's
> test sandbox (completed 0.79.1); 21.1's single `delivered` emission site (released 0.80.0).
> Builds: [[task-19.1-pack-recall-under-budget]] R1-R8 with the deltas in [[#deltas]]; runs
> [[task-19.5-measure-delivery]] R1 (the probe) as R0.

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-26.4-savestate-mtype-normalisation]]
rel: depends-on -> [[task-26.7-memory-index-by-subject]]
rel: realizes -> [[task-19.1-pack-recall-under-budget#requirements]]
rel: amends -> [[task-19.1-pack-recall-under-budget]]
rel: realizes -> [[task-19.5-measure-delivery]]
rel: derives-from -> [[bug_registry#registry]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: related-to -> [[project_recall_hook_savestate_noise_fix]]
rel: related-to -> [[task-24.2a-hook-verbs-explicit-session]]
rel: related-to -> [[task-24.6-context-and-observation]]

## Why {#why}

The per-prompt recall hook (`hooks.py:331-336`, `rmx memory recall --stdin-json --k 5 --scope both
--json --timeout 5`) printed 29,151 B on cliquedb for "yes next" and 16,647 B for a real question
(0.80.2, 2026-11-08). Five rows, each a full body of 2.0-8.7 KB plus 430-600 B of metadata. Claude
Code passes hook output whole only up to ~10k characters and shows a ~2 KB preview beyond that
([[reference_hook_output_10k_cap]]), so the hook cliquedb most wants working delivers about one row
in five, every prompt. SessionStart (`hooks.py:296-300`, `--k 10`) printed 7,011 B that day and
26,567 B on refmatrix in October; it has no bound either. {#why-lead}

Two more facts shape the fix:

- **The budget must hold after the merge.** A hook-mode recall assembles rows from four sources:
  the daemon's recent / session-start path, the in-process path when no daemon answers, the
  dense / hybrid path (`verbs.memory_recall` at `cli.py:12446`, `_replica_memory_recall` at
  `cli.py:12553`), and the global store merged in by `_merge_scope` (`cli.py:11992`, called at
  `:12490` and `:12703`). A budget applied to any one source leaks the other three; it is applied
  once, at the single emission point (`_RecallCall`, `cli.py:12837`), to the merged, excluded list.
- **`session/*` exclusion misses a mis-typed save-state.** `savestate_7c4e19d2a8f3` came back with
  mtype `project`. Its FILE says `metadata.type: project` (hand-authored, tags `[savestate, …]`;
  4 of cliquedb's `savestate_*.md` files carry it, read 2026-11-08). The bridge takes the
  frontmatter type verbatim (`ingest_gmd.py:944-945`), so the hook-mode `session/*` default
  (0.22.1/2, [[project_recall_hook_savestate_noise_fix]]) never sees it. The fix is a
  memory-layer fact and is OWNED by [[task-26.4-savestate-mtype-normalisation]] (the user's
  2026-11-08 amendment [[plan-of-plans#override-2026-11-08b]] orders plan-26 before this plan);
  this task only re-asserts it on the packed hook path ([[#r2b]]).

## Deltas from task 19.1 {#deltas}

19.1's requirement text is this task's contract except where listed here.

| 19.1 | here | reason |
|---|---|---|
| R1 single `DEFAULT_HOOK_BUDGET_BYTES` = 9,500 | per-channel table `recall_pack.CHANNEL_BUDGET_BYTES` (`prompt` 4,000, `session_start` 9,000, `precompact` 9,000; PROVISIONAL until R0) | UserPromptSubmit shares the input with scan-prompt and the focus hook; cliquedb asked for "under ~4KB" |
| Files: packer in `cli.py` | packer in `src/refmatrix/recall_pack.py`, called by `verbs.memory_recall(pack=True)` and the CLI | the override: verb-side logic the mod reuses |
| depends on 19.5 R1 | R0 runs it | it was never run |
| R2 subjects | kept; the save-state half of bug-164 is 26.4's, re-asserted by [[#r2b]] | one owner for the bridge rule |
| AC-2 (reach on the local 20-prompt set, ≥ 5x) | reported, not gating; AC-3 here gates on the frozen fixture | the committed fixture is the reproducible gate; the local set needs session db80475a's prompts |
| folded riders #w1c-s2, #w1c-m4 | stay with 19.1 | they are time-budget, not byte-budget |

## Requirements {#requirements}

0. **R0 Probe the delivery cap first** (19.5 R1, in a SCRATCH Claude Code project, never this
   repo's settings). Probe hooks emit 9,000 / 10,000 / 11,000 characters of ASCII and of a 3-byte
   character, on UserPromptSubmit and on SessionStart; a second run puts TWO hooks of 6,000 chars
   each on one UserPromptSubmit. Record: the cap and its unit (chars or bytes), the preview size,
   per-hook vs per-event, and whether PreCompact stdout reaches the agent at all. Commit the table
   to `workflow/measurements/hook-output-cap-probe.md` and set `CHANNEL_BUDGET_BYTES` from it:
   per-hook cap → each channel's budget is `0.9 × cap`; per-event cap → the `prompt` channel's
   budget is `0.9 × cap − (scan-prompt's measured max output on the fixture) − (focus input hook's
   max output)`, both numbers written next to the constant. The probe is a measurement, recorded
   before GREEN; no AC below depends on its number except through the constant. {#r0}
1. **R1 One budget, one unit, one place** (19.1 R1 amended). `recall_pack.CHANNEL_BUDGET_BYTES:
   dict[str, int]` keyed by 21.1's channel names (`prompt_recall`, `session_start`, `precompact`).
   `rmx memory recall --max-bytes N` and `verbs.memory_recall(max_bytes=N)` override it;
   `RMX_HOOK_BUDGET_BYTES`, when set, overrides every channel; a non-integer value exits non-zero
   naming the variable. The budget is UTF-8 bytes of the rendered payload. {#r1}
2. **R2 Subjects are not hits** (19.1 R2 unchanged): default `exclude_mtype` becomes
   `['session/*', 'subject']` in hook modes and in the verb; `--include-subjects` opts back in. {#r2}
3. **R2b Save-states stay out of the pack (re-asserted, not re-implemented).** 26.4 makes the
   bridge store `session/recall-state` for any file under `savestates/` or with an id starting
   `savestate_`. This task adds NO second rule: recall's exclusion stays mtype-only. It asserts
   (AC-5) that the packed per-prompt argv, after the four-source merge, does not name a mis-typed
   save-state, so a future regression in either half is caught on the path users run. If 26.4 has
   not merged when 25.1 starts, 25.1 waits; it does not build a name-based filter in recall.
   {#r2b}
4. **R3 `--pack`** (19.1 R3 unchanged): header line; one hook line per named hit, ALL before any
   body; whole bodies only, greedily in rank order; a `+N more: <cmd>` trailer. Fetch pointers are
   scope-correct (R6). {#r3}
5. **R4 After the merge, once.** `recall_pack.pack(rows, *, max_bytes, channel, query, mode,
   k_more) -> Packed(text, spans, named, more, payload_bytes)` is pure (no I/O, no telemetry, no
   store). It is called exactly once per invocation on the final row list: after all four sources
   are merged by `_merge_scope` and after `_mt_excluded`, for every hook mode (`--recent`,
   `--session-start`, `--stdin-json`, dense, hybrid). No source is budgeted on its own. {#r4}
6. **R5 Verb-side, so the mod reuses it.** `verbs.memory_recall(..., pack: bool = False,
   max_bytes: int | None = None)` returns `{"text", "spans", "named", "more", "payload_bytes",
   "warnings"}` when `pack` is set. The CLI's hook-mode output for the same inputs is the verb's
   `text` byte for byte. The verb's `trigger` parameter (24.2a d9) is NOT added here; the channel
   comes from today's `telemetry.recall_channel` inference, so 24.2a adds `trigger` on top without
   a conflict. {#r5}
7. **R6 Scope-correct fetch** (19.1 R6 unchanged): `rmx memory get --scope {project,global}` and
   the `rmx_memory` get action's `scope`; a global hit's pointer reads `--scope global`. {#r6}
8. **R7 Hooks** (19.1 R4 amended): the generator emits `--pack` in place of `--json` on the three
   recall commands, never interpolates a budget variable, and raises `--k` (SessionStart 30,
   per-prompt 12, PreCompact 30). PreCompact follows R0's verdict: if its stdout does not reach the
   agent, the PreCompact recall command is dropped and the promote / save-state legs stay. {#r7}
9. **R8 Loud overflow and arithmetic** (19.1 R5, R7): never empty, never over N; distinct named
   hits + trailer N = hits retrieved; bodies ⊆ named. {#r8}
10. **R9 Spans to the one emitter** (19.1 R8): the pack returns per-named-hit byte spans; 21.1's
    single site in `memory recall` (`_RecallCall`) emits `delivered` from them. The packer emits
    nothing. {#r9}

## Acceptance criteria {#acceptance}

All ACs run in 23.0's sandbox on the frozen fixture ([[#fixture]]), through the GENERATED hook
argv: the test builds the hook config with `hooks._claude_hook_block(...)`, takes the command
string of the recall entry for the event under test, and runs it with `bash -c` with the
UserPromptSubmit / SessionStart envelope on stdin and the sandbox `HOME`. No AC calls the packer
directly except AC-9's unit table ([[feedback_measure_the_path_users_run]]). {#acceptance-lead}

1. **AC-1 The cliquedb shape, before and after.** On the fixture, the per-prompt argv for the
   fixture's question prompt prints more than 10,000 B at HEAD (RED, number recorded) and at most
   `CHANNEL_BUDGET_BYTES["prompt_recall"]` bytes after. The SessionStart argv likewise against its
   channel budget. PreCompact against its budget or, if R0 drops it, the generated config has no
   PreCompact recall command.
2. **AC-2 Budget for every N, multibyte.** For N ∈ {2000, 4000, 9000} passed as `--max-bytes`,
   every channel's payload is ≤ N UTF-8 bytes on a fixture whose hook lines and bodies carry ≥ 4
   of `—` / `→` each (19.1 AC-1's density rule and recorded pre-check: the chars-counting mutation
   must exceed N on every N, or the fixture is densified before the AC is admitted).
3. **AC-3 Reach.** The number of distinct non-subject, non-session memories the model receives
   (the whole payload if ≤ R0's cap, else the first `preview` bytes) is ≥ 8 for the per-prompt
   argv after; recorded for HEAD (expected ≤ 1).
4. **AC-4 Four sources, one budget.** The AC-1 bound holds in each of: daemon up, `--scope both`
   with a tmp global store holding 10 global memories; no daemon (in-process path), `--scope both`;
   `--session-start`; `--recent --since 1h`. At HEAD each is RED. A mutation that budgets the
   project rows before `_merge_scope` fails the `--scope both` case.
5. **AC-5 Mis-typed save-state, packed path.** The fixture holds `savestate_fx01.md` with
   `metadata.type: project` and the body that matches the question prompt best. After 26.4 the
   packed per-prompt argv (daemon up and no daemon, `--scope both`) does not name it, and the
   trailer count does not include it. RED-ability: at the pre-26.4 base this AC fails; at the
   25.1 base (26.4 merged) it is a regression guard, recorded as such in the summary rather than
   claimed as this task's RED.
6. **AC-6 No subjects.** 0 `mtype=subject` rows on the per-prompt argv (HEAD ≥ 1 on the fixture's
   5 seeded subjects, recorded); `--include-subjects` brings live ones back.
7. **AC-7 Verb parity.** `verbs.memory_recall(query=<prompt>, k=12, scope="both", pack=True)`'s
   `text` equals the per-prompt argv's stdout byte for byte on the same sandbox. The parity test
   (`tests/test_verb_parity.py`) lists `pack` / `max_bytes` / `include_subjects` with their CLI
   twins.
8. **AC-8 Environment.** The generated argv runs with `RMX_HOOK_BUDGET_BYTES` unset (exit 0, within
   the table); with `RMX_HOOK_BUDGET_BYTES=3000` (≤ 3000 B); with `RMX_HOOK_BUDGET_BYTES=abc` (exit
   non-zero, stderr names the variable).
9. **AC-9 Pack contract.** Arithmetic (R8) on every AC-1..AC-4 payload; a unit table over
   `recall_pack.pack`: hook lines before bodies, whole bodies, trailer count and quoting of a
   multi-line query, loud overflow when the header plus one line exceeds N.
10. **AC-10 Delivered events.** A pack naming 7 of 12 retrieved hits (3 bodied) leaves 12
    `retrieved` and 7 `delivered` events sharing one `query_id`, each span slicing exactly its hook
    line / body out of the payload bytes (19.1 AC-6).
11. **AC-11 Generator.** `rmx install-hooks --check` clean after `--apply` in the sandbox; the three
    recall commands contain `--pack`, no `--json`, no `$`.
12. **AC-12 Isolation.** 23.0's guard records 0 connects to any live socket for this task's tests.
13. **AC-13 Mutations that must FAIL a test:** budget applied before the merge (AC-4); chars
    counted instead of bytes (AC-2); bodies before hook lines (AC-9); a cut body (AC-9); the
    generator keeping `--json` (AC-11); dropping the `subject` exclusion (AC-6); the packer calling a telemetry writer
    (AC-10: 14 not 7); the CLI re-rendering instead of printing the verb's text (AC-7).

## Fixture and measurement {#fixture}

- `tests/fixtures/plan25/memory/`: 30 synthetic GMD memory files, bodies sized to cliquedb's
  measured distribution (2.0-8.7 KB; the five largest match the five row sizes measured on
  2026-11-08), each with a curated hook; 5 subject rows seeded through the daemon op the store
  uses; `savestate_fx01.md` mis-typed; 10 global memories for the tmp global store. Text is
  synthetic: no cliquedb prompt or memory body is copied ([[feedback_no_raw_prompts_in_public_repo]]);
  the fixture README records the size distribution it reproduces and its source measurement.
- Prompts: authored for the test (one question, one bare ack, one symbol-only), committed.
- **Before / after table** (bytes per hook invocation, fixture store, HEAD vs GREEN, three runs
  each): SessionStart, per-prompt (question), per-prompt (ack), PreCompact. Written to the
  implementation summary and `workflow/measurements/plan-25-hook-bytes.md`.
- **Live check after deploy** (not a gate): the same three argvs against the cliquedb store,
  read-only, sizes only.

## Files to create {#files-to-create}

| file | purpose |
|---|---|
| `src/refmatrix/recall_pack.py` | `CHANNEL_BUDGET_BYTES`, `pack()`, `Packed`; pure |
| `tests/test_task25_1_recall_budget.py` | AC-1..AC-13 |
| `tests/fixtures/plan25/` | synthetic memory + global fixtures, prompts, README |
| `workflow/measurements/hook-output-cap-probe.md` | R0's table |
| `workflow/measurements/plan-25-hook-bytes.md` | the before / after table (shared with 25.2) |

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/cli.py` (`memory recall` options + `_memory_recall_impl` emission, `memory get`) | `--pack`, `--max-bytes`, `--include-subjects`; ONE call to `recall_pack.pack` on the merged list at the `_RecallCall` emission; `memory get --scope` |
| `src/refmatrix/verbs.py` (`memory_recall`, `rmx_memory` get) | `pack`, `max_bytes`, `include_subjects`; default `exclude_mtype` adds `subject`; get `scope` |
| `src/refmatrix/memory_index.py` | export the curated-hook lookup (`.memory_hooks.json` / the `MEMORY.md` 26.7 leaves) for the pack (19.1's file plan) |
| `src/refmatrix/hooks.py` (`:296-300`, `:331-336`, `:357-362`) | `--pack`, raised `--k`, PreCompact per R0 |
| `src/refmatrix/mcp.py` (if its tool schema is hand-listed) | the new verb params |
| `tests/test_verb_parity.py` | the new params' twins |
| `workflow/bug_registry.md` | bug-164 → fixed at merge, with the mechanism and the measured before / after |

## Test strategy {#test-strategy}

- RED first: AC-1, AC-4, AC-6 run against HEAD (after 3.7's merge) and are recorded failing
  with their byte counts; a RED that passes at HEAD is not a RED
  ([[feedback_red_test_must_fail_at_head]]).
- No mock of recall, the packer, the bridge or the hook generator. The only stand-ins are 23.0's
  sandbox redirections; the embedder is the real local model (`HF_HUB_OFFLINE=1`); rerank may be
  absent in the sandbox and the payload bound must hold either way.
- The generated argv carries `HOOK_ENV`'s `PATH="$HOME/bin:…"` prefix; under the sandbox `HOME`
  there is no `~/bin/rmx`, so the dev venv's `rmx` on the inherited PATH runs. The test asserts
  which `rmx` ran (its `__file__` under the dev tree), so a deploy binary can never answer.
- Mutation run per [[feedback_commit_before_mutation_revert]] and
  [[feedback_clear_pycache_after_mutation]].

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| d1 | Provisional per-prompt budget before R0 | 4,000 B; R0's number replaces it before GREEN |
| d2 | Where the save-state mtype fix lives | in the bridge, owned by 26.4 (plan-26's draft already decides it); 25.1 re-asserts it only. The hand-authored `type: project` files are a gap in whatever agent wrote them, worth a bus note to cliquedb when plan-27 reaches it |
| d3 | Raise per-prompt `--k` to 12 under a 4,000 B budget | yes; hook lines are ~150-250 B, so 12 names fit with room for one body; the trailer covers the rest |
| d4 | Does 25.1 also land 19.1 R6 (`memory get --scope`) | yes; without it a global hit's pointer is wrong, which R3 forbids |
