---
gmd: "0.1"
id: task-19.1-pack-recall-under-budget
title: "Task 19.1: memory recall packs its hits under a character budget, without subject noise, and the hooks use it"
tags: [task, memory, recall, hooks, budget]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 19.1: pack recall under the budget {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 23.0 (test sandbox); 19.5 R1 (the threshold probe: the default budget, per-hook vs
> per-event, and the PreCompact verdict); 21.1 (the named emitters and event schema, R8). Scheduled after 23.1 in the Wave 1 order
> ([[plan-review-2026-10-14#t8-wave1]]). Its hook change deploys in the C11 batched hook-install
> window with 16.2/16.3 and 21.3, not alone.

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: depends-on -> [[task-19.5-measure-delivery]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[feedback_operational_content_not_in_graph]]
rel: specified-by -> [[bsd-plan19-spec-review-3104a81]]

## Why {#why}

The three recall hooks emit JSON with full bodies and no size bound:
- SessionStart: `--session-start --k 10 --scope both --json --timeout 10`, `hooks.py:277`.
- Per-prompt: `--stdin-json --k 5 --scope both --json`, `hooks.py:313`.
- PreCompact: `--recent --since 1h --k 20 --scope both --json`, `hooks.py:340`.

Above ~10k chars Claude Code delivers a ~2 KB preview, so the agent sees about one hit of ten.
And what it does see is often noise: on `"whats next?"` all 5 per-prompt hits were compiled
`subject_*` rows (`subject_collaboration`, `subject_drift`, …) whose whole content is a 5–13 char
label. `Store.upsert_subject` (`store.py:2618`) writes a subject as a protected `kind=memory`,
`mtype=subject` row, so it is embedded and competes in dense recall; `verbs.memory_recall`'s
default exclusion is only `session/*` (`verbs.py:679`). Raising `--k` without excluding them
spends the new budget on labels. {#why-body}

Quoted sizes are point-in-time (26,567 B in October; 16,629 B on 2026-10-14). Every AC freezes
its own baseline at RED time on the sandbox copy. {#why-baselines}

## Requirements {#requirements}

1. **R1 `--max-chars N`** on `rmx memory recall` (and the verb): the rendered payload is ≤ N
   **characters**, the unit the harness counts (the bug-045 lesson). When `--pack` is given
   without `--max-chars`, N is `RMX_HOOK_BUDGET_CHARS` if set to an integer, else the built-in
   constant `DEFAULT_HOOK_BUDGET_CHARS` (9,500 until 19.5 R1 measures it). A set but non-integer
   env value is an error naming the variable, not a silent fallback.
   - If 19.5 R1 finds the cap is PER EVENT, the per-prompt default is the measured limit minus 5%
     minus scan-prompt's measured maximum output on the same event, and the spec records both
     numbers.
2. **R2 Subjects are not recall hits** (d8a, replacing d5a).
   - `mtype=subject` rows are excluded from dense, recent and session-start hits by default: the
     default `exclude_mtype` becomes `['session/*', 'subject']`.
   - Opt-in: `--include-subjects` (verb `include_subjects=True`) brings live subject rows back.
   - Subjects marked `stale` by compile (19.4 R5) stay hidden even with the opt-in.
   - `--subject <slug>` is unchanged: it returns the subject's MEMBERS, never the subject row.
3. **R3 `--pack`**, a text format built greedily in rank order:
   - (a) one header line naming the channel, the hit count and the budget;
   - (b) per hit, one line `- <name> — <title> — <hook>  (<fetch>)`. `<hook>` is the curated hook
     from `.memory_hooks.json` / MEMORY.md when present, else the first sentence. `<fetch>` is
     scope-correct: `rmx memory get <name>` for a project row, `rmx memory get <name> --scope
     global` for a global row (R6);
   - (c) full bodies for the top hits, appended while the remaining budget allows a whole body
     (never a cut body); a body's hit already has its hook line, so bodies ⊆ named hits;
   - (d) a trailer when any retrieved hit was not named: `+N more: <cmd>`, where `<cmd>` is mode
     specific: query mode `rmx memory recall <q> --k M` with `<q>` the query collapsed to one
     line, capped at 120 chars and `shlex.quote`d; session-start mode
     `rmx memory recall --session-start --k M`; recent mode
     `rmx memory recall --recent --since <S> --k M`.

   Hook lines are emitted for ALL named hits before any body, so the budget is spent on reach
   first.
4. **R4 Hooks.** The generator (`hooks.py`) emits `--pack` in place of `--json` on the recall
   hooks and **never interpolates a budget variable into the argv**; R1's default applies.
   `--k` rises to what packing can carry (SessionStart 30, per-prompt 12, PreCompact 30).
   - PreCompact follows 19.5 R1's verdict (d5d): if the probe shows PreCompact stdout does NOT
     reach the agent, the generator drops the PreCompact recall hook and keeps only the
     save-state / promote leg. Until the verdict exists, the PreCompact recall stays; its
     `delivered` events are emitted (21.1 R11) and 19.2's fold does not count them.
   - `rmx install-hooks --check` must equal the new generation; the deploy re-installs in the C11
     window.
5. **R5 Loud overflow.** If even the header plus the first hook line exceeds N, the payload is the
   header plus a one-line error naming N. It is never empty and never over N.
6. **R6 Scope-correct fetch.** `rmx memory get` (and the `rmx_memory` verb's `get` action) gains
   `--scope {project,global}` (default project). With `--scope global` it reads the global store
   and never returns a same-named project row.
7. **R7 No silent drop; arithmetic.** For every payload: (distinct hits named, one hook line each)
   + (the trailer's N) = hits retrieved; bodies ⊆ named.
8. **R8 The pack emits `delivered` events** (21.1 R11: "19.1's pack joins later as an emitter of
   `prompt_recall`, owned by 19.1"). Through 21.1's named emitter for its channel
   (`session_start`, `prompt_recall`, `precompact`, `recall`), the packer emits one `delivered`
   event per hit it NAMED (hook line), carrying `name`, `entity_id`, `scope` and the call's
   `query_id`; trimmed hits stay `retrieved` only (21.1 already emits those). A global hit's event
   goes to the global root's `recall-events.jsonl` per 21.1 R8. The emitter's failure is printed,
   never silent, and never fails the hook.

## Acceptance criteria {#acceptance}

All ACs run in task 23.0's sandbox on a COPY of this project's catalog and memory dir, through
the CLI (the production path), with `--scope project` unless the global leg is under test (then a
tmp global store holding a copy of the global memories).

1. **Budget.** For each hook argv, `len(payload) ≤ N` for N ∈ {2000, 5000, 9500}.
2. **Reach.** On the 20-prompt set (`eval/production/memory_delivery/prompts.local.jsonl`, 20 user
   prompts from session db80475a's input events; kept local per d8f, its sha256 committed in
   `eval/production/memory_delivery/PROMPTS.sha256`), the number of DISTINCT memories named in
   the delivered payload is ≥ 5x today's.
   - "Memory" excludes `mtype=subject` and `session/*` rows.
   - Today = the current per-prompt argv (k=5, `--json`), delivered per 19.5's rule (the whole
     output when under the limit, else its first 2 KB). After = the new argv (k=12, `--pack`).
   - Also reported, not gated: the same comparison at equal k=12 (JSON vs pack), so packing's
     share of the gain is visible.
3. **No subject noise** (d8a). On `"whats next?"`, the per-prompt pack contains 0 rows of
   `mtype=subject` (pre-check: the same prompt at HEAD returns ≥ 1, recorded).
   `--include-subjects` brings live subjects back; a subject marked `stale` stays out.
4. **Unset variable.** The generated argv for each of the three hooks, RUN with
   `RMX_HOOK_BUDGET_CHARS` unset, exits 0 and its payload is ≤ `DEFAULT_HOOK_BUDGET_CHARS`.
5. **Arithmetic.** R7 holds on every payload of AC-1 and AC-2.
6. **Delivered events.** A pack naming 7 of 12 retrieved hits leaves 12 `retrieved` and 7
   `delivered` events with one shared `query_id`; a global hit's `delivered` event is in the tmp
   global root's file with `scope=global`.
7. **Global pointer.** With a project row and a global row both named `X`, a global hit's printed
   fetch command returns the global row.
8. `rmx install-hooks --check` is clean after `--apply` in the sandbox, and the generated recall
   commands contain `--pack` and no `$`.
9. **Isolation.** 23.0's guard records 0 connects to any live socket for this task's test files.
10. **Mutations that must FAIL a test:**
   - bodies before hook lines;
   - a cut body;
   - a missing trailer count;
   - counting bytes instead of chars (fixture with `—`/`→`);
   - the hook generator keeping `--json`;
   - interpolating `${RMX_HOOK_BUDGET_CHARS}` into the argv (AC-4);
   - dropping the `subject` exclusion (AC-3);
   - counting a body as a second named hit (AC-5);
   - `memory get --scope global` falling back to the project row (AC-7);
   - a `delivered` event for a trimmed hit (AC-6).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/cli.py` (`memory recall`, `memory get`) | `--max-chars`, `--pack`, `--include-subjects`, the packer; `memory get --scope` |
| `src/refmatrix/verbs.py` (`memory_recall`, `rmx_memory` get) | `max_chars` / `pack` / `include_subjects` passthrough; default `exclude_mtype` adds `subject`; `scope` on get |
| `src/refmatrix/hooks.py` (`:277`, `:313`, `:340`) | `--pack`, the raised `--k`, PreCompact per 19.5 R1 |
| `src/refmatrix/memory_index.py` | export the curated-hook lookup (`.memory_hooks.json`) for reuse |
| `eval/production/memory_delivery/` | the AC-2 script; `PROMPTS.sha256` |

## Test strategy {#test-strategy}

- **Sandbox:** task 23.0 (d1a/d1b): `HOME`, the global root, the registry and the LaunchAgents dir
  point into a short tmp root before `refmatrix` is imported; `HF_HOME` stays at the real cache
  with `HF_HUB_OFFLINE=1`; spawned `rmx` children refuse any socket outside the tmp root, so no
  test reaches `~/.refmatrix/rmxd.sock` or the live `models.sock`. `--memory-dir` is always passed
  explicitly. The SessionStart argv runs with `--scope project` unless a tmp global store is set
  up for it.
- **RED first:** run the generated SessionStart argv on a fixture store with 30 memories (bodies
  ~2 KB each) plus 5 subject rows; assert `len(out) ≤ 9500`, ≥ 20 distinct non-subject names, and
  0 subject rows. It fails today: JSON, unbounded, subjects included.
- **Unit tests for the packer:** ordering, whole bodies only, trailer arithmetic, trailer quoting
  of a multi-line query, a multibyte fixture.
- **Generator test:** runs the argv (AC-4), not a substring check.
- **Measurement:** AC-2's table goes into the implementation summary.

## Out of scope {#out-of-scope}

Ranking changes (19.2's scores feed the order later). Scan-prompt's 2,000-token budget: 19.5
records it, and 19.6 owns how the per-prompt budget is split (d5b). Expanding a subject hit into
its members: not planned here; see 19.6's out-of-scope (d8a).

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 19 #b-1; d8a (replaces d5a) | R2, AC-2 ("memory" defined), AC-3, mutation |
| 19 #b-2 | R1 (built-in default), R4 (no interpolation), AC-4, mutation |
| 19 #b-7; d1a/d1b | [[#test-strategy]], AC-8 |
| 19 #s-1; d5d | R4 PreCompact branch |
| 19 #s-2 | R1 per-event default |
| 19 #s-3 | R3(c), R7, AC-2, AC-5 |
| 19 #s-4 (scope-correct pointer) | R3(b), R6, AC-7 |
| d8e (global hits routed to the global store) | R8, AC-6 |
| 21.1 R11 (pack owned emitter) | R8, AC-6 |
| 19 #m-2 | [[#why-baselines]] |
| 19 #m-4 | header (C11 window) |
| 19 #m-5 | R3(d) |
| d8f (prompt set kept local, hash committed) | AC-2 |
| #t8-wave1 | header |
