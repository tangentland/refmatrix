---
gmd: "0.1"
id: task-19.1-pack-recall-under-budget
title: "Task 19.1: memory recall packs its hits under a UTF-8 byte budget, without subject noise, and the hooks use it"
tags: [task, memory, recall, hooks, budget]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-15
---

# Task 19.1: pack recall under the budget {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 23.0 (test sandbox); 19.5 R1 (the threshold probe: the default budget, per-hook vs
> per-event, and the PreCompact verdict; a manual probe that runs in Wave 1 BEFORE 19.1, see the
> plan's [[plan-19-adaptive-memory-budget#tasks]] row for 19.5; re-review #m-1); 21.1 (the named emitters and event schema, R8). Scheduled after 23.1 in the Wave 1 order
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
label. `Store.upsert_subject` (`store.py:2692` at `23ad703`) writes a subject as a protected `kind=memory`,
`mtype=subject` row, so it is embedded and competes in dense recall; `verbs.memory_recall`'s
default exclusion is only `session/*` (`verbs.py:679`). Raising `--k` without excluding them
spends the new budget on labels. {#why-body}

Quoted sizes are point-in-time (26,567 B in October; 16,629 B on 2026-10-14). Every AC freezes
its own baseline at RED time on the sandbox copy. {#why-baselines}

## Requirements {#requirements}

1. **R1 `--max-bytes N`** on `rmx memory recall` (and the verb `max_bytes`): the rendered
   payload is ≤ N **UTF-8 bytes**. ONE unit for the budget, the event offsets (21.1 R10) and
   19.5's `seen` derivation ([[plan-review-2026-10-14#t9-fixes]]; re-review #s-2). Why bytes is
   safe whichever unit the harness counts: for any UTF-8 text the byte count is ≥ the character
   count, so a payload within N bytes is within N characters too. A char-counting harness (the
   bug-045 unit, for the `MEMORY.md` loader) therefore never sees an over-budget payload; the cost
   is under-filling by the multibyte share, which 19.5 R2 reports. When `--pack` is given without
   `--max-bytes`, N is `RMX_HOOK_BUDGET_BYTES` if set to an integer, else the built-in constant
   `DEFAULT_HOOK_BUDGET_BYTES` (9,500 until 19.5 R1 measures it). A set but non-integer env value
   is an error naming the variable, not a silent fallback.
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
8. **R8 The pack RETURNS byte spans; it emits nothing** (re-review #s-1, #s-2; one owner of
   `delivered` = 21.1, [[task-21.1-context-usage-telemetry#requirements]] R11). `--pack` REPLACES
   21.1's JSON renderer on the hook argv; like it, the packer returns, per hit it NAMED, the
   span record `{name, entity_id, kind, scope, partition, offset_bytes, bytes, body_offset_bytes,
   body_bytes}`:
   - `offset_bytes` / `bytes`: the byte range of the hit's hook line (R3(b)), newline included;
   - `body_offset_bytes` / `body_bytes`: the byte range of its body (R3(c)) when one was
     appended, else null;
   - plus `payload_bytes`, the total.

   21.1's single emission site in `memory recall` turns these into one `delivered` event per
   named hit (and its own `retrieved` events for every retrieved hit), with the call's
   `query_id`, routing global hits to the global root's file (21.1 R8). The packer calls no
   telemetry writer; a packer that also emits doubles `delivered` (AC-6). The emission's failure
   is 21.1 R8's printed line, never silent, never failing the hook.

## Acceptance criteria {#acceptance}

All ACs run in task 23.0's sandbox on a COPY of this project's catalog and memory dir, through
the CLI (the production path), with `--scope project` unless the global leg is under test (then a
tmp global store holding a copy of the global memories).

1. **Budget.** For each hook argv, `len(payload.encode("utf-8")) ≤ N` for N ∈ {2000, 5000,
   9500}, on a fixture whose hooks and bodies contain `—` and `→`.
   - **Multibyte density, stated** (round-3 #m-3). Each fixture hook line and body carries at
     least 4 of `—` / `→` (3 bytes, 1 character each: 2 bytes of excess apiece), so for every N
     the payload's multibyte excess (UTF-8 bytes minus characters) is larger than the largest
     slack the greedy packer leaves below N (the length of the longest whole line or body it
     could not fit). A character-counting packer therefore fills past N bytes on every N.
   - **Pre-check, recorded before GREEN:** run the chars-counting mutation and record, per N, the
     payload's byte length (> N) and its excess vs. slack; an N where the mutation stays ≤ N makes
     the fixture too sparse, and the fixture is densified before the AC is admitted.
2. **Reach.** On the 20-prompt set (`eval/production/memory_delivery/prompts.local.jsonl`, 20 user
   prompts from session db80475a's input events; kept local per d8f, its sha256 committed in
   `eval/production/memory_delivery/PROMPTS.sha256`), the number of DISTINCT memories named in
   the delivered payload is ≥ 5x today's.
   - "Memory" excludes `mtype=subject` and `session/*` rows.
   - Today = the current per-prompt argv (k=5, `--json`), delivered per 19.5's rule (the whole
     output when ≤ 19.5 R1's measured `cap`, else its first `preview` bytes; round-3 #m-8). After = the new argv (k=12, `--pack`).
   - Also reported, not gated: the same comparison at equal k=12 (JSON vs pack), so packing's
     share of the gain is visible.
3. **No subject noise** (d8a). On `"whats next?"`, the per-prompt pack contains 0 rows of
   `mtype=subject` (pre-check: the same prompt at HEAD returns ≥ 1, recorded).
   `--include-subjects` brings live subjects back; a subject marked `stale` stays out. The stale
   subject is SEEDED in the fixture with 19.4 R5's field, `metadata.stale = true` plus
   `stale_since`, so this AC does not wait on 19.4 (Wave 2; re-review #m-1).
4. **Unset variable.** The generated argv for each of the three hooks, RUN with
   `RMX_HOOK_BUDGET_BYTES` unset, exits 0 and its payload is ≤ `DEFAULT_HOOK_BUDGET_BYTES` bytes.
5. **Arithmetic.** R7 holds on every payload of AC-1 and AC-2.
6. **Delivered events.** A pack naming 7 of 12 retrieved hits (3 with bodies) leaves exactly 12
   `retrieved` and 7 `delivered` events with one shared `query_id` (not 14: one emission site);
   for each `delivered` event, the payload bytes at `[offset_bytes, offset_bytes + bytes)` are
   that hit's hook line, and for the 3 bodied hits the bytes at `[body_offset_bytes,
   body_offset_bytes + body_bytes)` are its body; the other 4 have null body fields. The fixture
   places ≥ 3 `—` before the LAST hook line and in every body (≥ 6 bytes of excess before each
   checked span, more than any span's own slack), so spans counted in characters miss on every
   bodied hit; recorded as a pre-check like AC-1's. This is the `--pack` leg of 21.1's
   chars-vs-bytes mutation: the JSON renderer is ASCII-escaped, so 21.1 cannot test it there
   ([[task-21.1-context-usage-telemetry#acceptance]] AC-8d). A global
   hit's `delivered` event is in the tmp global root's file with `scope=global`.
7. **Global pointer.** With a project row and a global row both named `X`, a global hit's printed
   fetch command returns the global row.
8. `rmx install-hooks --check` is clean after `--apply` in the sandbox, and the generated recall
   commands contain `--pack` and no `$`.
9. **Isolation.** 23.0's guard records 0 connects to any live socket for this task's test files.
10. **Mutations that must FAIL a test:**
   - bodies before hook lines;
   - a cut body;
   - a missing trailer count;
   - counting chars instead of bytes (AC-1: the `—`/`→` fixture is within N chars but over N
     bytes);
   - the packer calling the telemetry writer itself (AC-6: 14, not 7);
   - spans in characters (AC-6: the byte ranges miss on the multibyte fixture);
   - the hook generator keeping `--json`;
   - interpolating `${RMX_HOOK_BUDGET_BYTES}` into the argv (AC-4);
   - dropping the `subject` exclusion (AC-3);
   - counting a body as a second named hit (AC-5);
   - `memory get --scope global` falling back to the project row (AC-7);
   - a `delivered` event for a trimmed hit (AC-6).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/cli.py` (`memory recall`, `memory get`) | `--max-bytes`, `--pack` (returns spans to 21.1's emission site), `--include-subjects`, the packer; `memory get --scope` |
| `src/refmatrix/verbs.py` (`memory_recall`, `rmx_memory` get) | `max_bytes` / `pack` / `include_subjects` passthrough; default `exclude_mtype` adds `subject`; `scope` on get |
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
  ~2 KB each) plus 5 subject rows; assert `len(out.encode()) ≤ 9500`, ≥ 20 distinct non-subject names, and
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

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9-fixes]].

| finding / decision | answered at |
|---|---|
| re-review #s-1 (`delivered` claimed three ways) / #t9-fixes "one owner for `delivered`" | R8 (the pack returns spans; 21.1 R11's single site emits); AC-6 (12 / 7, not 14); mutation |
| re-review #s-2 (units clash; no offsets) / #t9-fixes "one unit (bytes)" | R1 (`--max-bytes`, `RMX_HOOK_BUDGET_BYTES`, `DEFAULT_HOOK_BUDGET_BYTES`; why bytes is safe under a char cap); R8 (hook-line and body spans); AC-1, AC-4, AC-6; mutations |
| re-review #m-1 (stale field from a Wave 2 task; 19.5 R1 in no wave) | AC-3 (seeded `metadata.stale`); header (19.5 R1 in Wave 1 before 19.1); plan [[plan-19-adaptive-memory-budget#tasks]] |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan19-21-spec-rereview-r3-6091648]]. Code fact re-read at `636b210`:
`cli.py:12110` and `:12322` print `json.dumps(rows, indent=2)` with the default `ensure_ascii`, so
today's hook JSON is ASCII.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r3-6091648]]

| finding / decision | answered at |
|---|---|
| round-3 #m-1 (title said "a character budget") | front-matter title (UTF-8 byte budget; R1 is `--max-bytes`) |
| round-3 #m-3 (multibyte density for the chars-vs-bytes mutations) | AC-1 (density rule + recorded pre-check), AC-6 (≥ 6 bytes of excess before each checked span; pre-check) |
| round-3 #b-3 (21.1's chars mutation cannot fail on the ASCII JSON renderer) | AC-6 owns the `--pack` leg of that mutation |
| round-3 #m-8 (one preview definition) | AC-2 "Today" uses 19.5 R1's measured `cap` / `preview`, not 2 KB |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]] #nm-7 (one cite). Read at write time at HEAD
`23ad703`: `Store.upsert_subject` is defined at `store.py:2692` (the round-8 report's `:2620`
did not match HEAD; the symbol was read, not the report's number). 19.1 has no other round-8
item: #nm-5's outcome field lives on 21.1's rows, which 19.1's pack does not write.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]

| finding / decision | answered at |
|---|---|
| round-8 #nm-7 (`store.py:2618`) | [[#why]] (`Store.upsert_subject`, `store.py:2692`) |
