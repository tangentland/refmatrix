---
gmd: "0.1"
id: task-21.1-context-usage-telemetry
title: "Task 21.1: telemetry that can count how the agent uses rmx context, and the ONE recall-event schema"
tags: [task, telemetry, context, mcp, agent, recall-events]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-14
---

# Task 21.1: make agent context usage measurable {#root}

> Plan: [plan-21-agent-context-usage](../plan-21-agent-context-usage.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 1
> Depends on: 23.0 only (the shared test sandbox; [[plan-review-2026-10-14#t8-wave1]]). The event
> emission does NOT depend on plan-23's queue (d4a); only 19.2's fold does.

rel: part-of -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[exploration-agent-context-usage]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[task-19.2-memory-usage-record]]
rel: related-to -> [[task-19.5-measure-delivery]]
rel: related-to -> [[exploration-session-phased-context]]

## Why {#why}

The exploration measured 3 CLI `context` calls against 1,119 agent greps (2026-09-23 to
2026-10-07T11:06), and could not count MCP calls at all. Checked at HEAD `b1c4324`:
- `invocation` is `unknown` on every agent grep and context row: an agent's Bash call has no tty
  and no hint (`telemetry.invocation_source`, `telemetry.py:151`).
- `mcp.serve_stdio` (`mcp.py:312`) never sets `RMX_INVOCATION_SOURCE`, although the docstring at
  `telemetry.py:154` says the MCP server does. `mcp` is already a member of `INVOCATION_SOURCES`
  (`telemetry.py:57`).
- No `query.log` row is written by the daemon's `_op_context` (`daemon.py:4687`), by
  `verbs.context` (`verbs.py:538`), or by the CLI's daemon route (`cli.py:5152`). Only the replica
  (`cli.py:5100`) and direct (`cli.py:5231`) routes log.
- `query.log` rows carry no session, no query id and no cwd (`telemetry.log_query.__exit__`), so no
  per-session count (21.3 AC-4, 19.2 R3) can be computed and no event can be joined to its query.
- `grep-stdin` rows (`cli.py:6202`) never set `cardinality`: it is `null` on all 3,521 rows of the
  window. The `-E` replica-path "0 cardinality" defect the exploration named does not reproduce in
  October data (bsd #s-4).

Without these, no change in 21.2–21.4 can be shown to change behaviour, and plan-19's 19.2 / 19.5 /
19.6 have no instrument. {#why-body}

## Requirements {#requirements}

### Invocation source {#req-invocation}

1. **R1 The MCP server sets its source.** `mcp.serve_stdio` sets `RMX_INVOCATION_SOURCE=mcp` in its
   own process environment before it reads the first request, so every verb it serves and every
   child it spawns inherits it. (`mcp` is already in `INVOCATION_SOURCES`; bsd #m-1.)
2. **R2 An `agent` source with a stated precedence** (d4f; decision-log #m-2). `agent` joins
   `INVOCATION_SOURCES`. `invocation_source()` resolves, in this order:
   1. explicit `RMX_INVOCATION_SOURCE` (hooks: `hook`; MCP: `mcp`; harnesses: `internal`);
   2. `CLAUDECODE` set → `agent`;
   3. stdin is a tty → `interactive`;
   4. otherwise `unknown`.

   Consequences stated, not hidden: a `!`-typed human command inside Claude Code logs `agent`, and
   a bare grep the `grep-rewrite-guard` hook rewrote to `rmx grep` logs `agent` although the agent
   never chose rmx. Adoption reads therefore separate CHOSEN calls from rewritten ones by `source`
   (`grep-replica` with `answered_by`, `context-*`) and by event `channel`, never by `invocation`
   alone. Every eval harness (`eval/production/*`, 21.2's replay, 21.4's runner) sets
   `RMX_INVOCATION_SOURCE=internal` explicitly.

### query.log rows {#req-query-log}

3. **R3 One row per context call, on every route** (bsd #s-5). Each of the four routes writes
   exactly one `query.log` row with `kind=context`, and `source` names the route:
   - MCP `rmx_context` → `verbs.context` → daemon op: `source=context-mcp`;
   - CLI replica route (`cli.py:5100`): `context-replica` (exists);
   - CLI daemon route (`cli.py:5152`): `context-daemon` (missing today);
   - CLI direct route (`cli.py:5231`): `context` (exists).

   The row is written on the CALLER side (the verb or the CLI), never inside a daemon op and never
   under the daemon's writer lock. `memory_recall` reached from the CLI or MCP gets the same
   treatment with `kind=recall`. `ann_search` is NOT covered: it has no verb (`cli.py:10718` calls
   the op directly), and R4 does not report it.
4. **R4 New row fields.** Every `query.log` row (all kinds) gains:
   - `session`: resolved by [[#req-session]] (null when nothing resolves, never guessed);
   - `query_id`: a uuid4 hex minted by the caller once per call and shared with every recall event
     of that call (R7);
   - `cwd` and `root`: the process cwd and the resolved store root, so d8d's predicate (R5) can
     apply to new rows.
5. **R5 One shared pytest-temp predicate** (d8d). `telemetry.is_test_artifact_row(row)` is true
   when the row's `cwd` or `root` lies under a pytest temp dir (the `pytest-of-<user>` base, or a
   `tmp_path`-shaped root under the platform temp dir). EVERY reader of `query.log` and
   `recall-events.jsonl` (R4's report, 19.2's fold, 21.4's question draw) calls this one function;
   no reader carries its own copy. Rows with neither field (legacy) are not matched; the report
   prints them as a separate `legacy_unattributed` count instead of silently including or dropping
   them.
6. **R6 `grep-stdin` cardinality** (bsd #s-4, retargeted). The stdin filter path (`cli.py:6202`)
   sets `cardinality` to the number of lines it emitted. The `-E` replica-path claim is dropped:
   it does not reproduce at HEAD (live `-E` row 2026-10-14T11:08:31 logged `cardinality: 15`).
7. **R7 `rmx telemetry --agent-usage`** (bsd #m-2, #s-3, #s-5). `telemetry` is a `@main.command`
   (`cli.py:7521`), so this is a FLAG on it, not a subcommand. It reuses `--since` and adds
   `--until` (ISO prefixes); no `--days`. It prints, per `invocation`, the counts and p50/p95
   latency for context (per route), grep (per `source` / `answered_by`), and recall, plus a
   `--by-session` table (calls per `session`). It:
   - reads `query.log` and `cli.log` of ONE store root;
   - counts a `cli.log` command once (excludes `phase=start` intent rows, as `summarize_context`
     already does);
   - applies R5's predicate and prints the excluded count;
   - excludes `invocation=internal` rows by default (`--include-internal` to keep them).

   The report covers context, grep and recall only. Other MCP tools are not claimed.

### The ONE recall-event schema (C7) {#req-schema}

8. **R8 The sink** (d4a). Events are appended to `<store root>/recall-events.jsonl`, a NEW
   append-only file, written lock-free like `query.log`: one `write()` of one complete
   newline-terminated JSON line per event, `O_APPEND`, never under the daemon's writer lock. The
   file is never truncated or rotated by any writer; it is the retained replay source for 19.2's
   fold (d2a amendment) and is read by 23.1's non-consuming tail reader, which stops at the last
   complete newline. A hit on a GLOBAL memory is appended to `~/.refmatrix/recall-events.jsonl` with
   `scope=global`, so it is counted in the global store keyed by name (d8e). A failed append is
   never silent: the emitter prints one `rmx: recall-event append failed: <error>` line to stderr
   and the command continues (telemetry never fails the command it describes). Readers count and
   print unparseable lines; they never skip them silently. No other recall log format may be added
   (AC-9).
9. **R9 Session, turn and identity.** Every event and every `query.log` row
   resolves `session` from, in order: the hook envelope's `session_id` → `CLAUDE_CODE_SESSION_ID`
   → `RMX_SESSION` → null. `stm.latest_session` (`stm.py:127`) is NEVER consulted (bsd #b-1;
   bug-100's shape). `turn` is the count of `input` events in that session's STM ring at emission
   (the prompt-capture hook records one per prompt), null when the session has no ring. Turn is
   logged, never used as a phase signal (d5b). {#req-session}
10. **R10 The event fields.** One event per item per stage. The schema is versioned (`v: 1`).

    | field | meaning |
    |---|---|
    | `v`, `ts`, `session`, `turn`, `query_id` | R9; `query_id` equals the `query.log` row of the same call |
    | `channel` | closed SURFACE enum: `session_start`, `prompt_recall`, `scan_prompt`, `precompact`, `context`, `recall`, `nudge` (bsd #b-2). `invocation` is a separate field with R2's values; `cli`/`mcp` are never channels |
    | `invocation` | R2 |
    | `name`, `entity_id`, `kind` | `name` is the stable key 19.2 counts by (a purge-and-re-add keeps history); `entity_id` is the catalog id at emission (code); `kind` ∈ `code`, `doc`, `memory`, `session`, `subject` |
    | `scope` | `project` or `global` (d8e) |
    | `rank`, `stage` | 1-based rank in the retrieval; `stage` ∈ `retrieved`, `delivered`, `used` |
    | `offset_bytes`, `bytes`, `payload_bytes` | `delivered` only: the item's byte offset and length inside the emitted payload, and the payload's total size. `delivered` means EMITTED; `seen` is derived as `offset_bytes + bytes ≤ cap` against whatever cap 19.5 R1 measures (bsd #s-1) |
    | `arm`, `policy` | allocation arm ∈ `fixed`, `phased`, `phased+cache`, and the allocation policy version. Until 19.6 ships, every emitter writes `arm=fixed`, `policy=fixed-v0`; 19.6 chooses and logs the arm per prompt (d5b) |
    | `stm_session`, `stm_events_n`, `focus_topics_n`, `overlap` | the RAW phase inputs at injection, on prompt-time channels (`session_start`, `prompt_recall`, `scan_prompt`, `precompact`): which ring was read (R9's session, never `latest_session`), its event count, the number of `stm.topic_composites` topics, and the prompt-term ∩ composite-member overlap |
    | `phase`, `restored_cluster_id` | the label the pre-registered rule computed (`cold`, `warm`, `return`, `new`), and on a topic-cache return the restored cluster id. Null until 19.6 writes them |
    | `block_id`, `block_sha`, `rev`, `unchanged` | versioned injection ([[exploration-session-phased-context#vi-evidence]]): the emitted block's stable id (`scan-prompt`, `prompt-recall`, `stm-topic-composite`, …) and the sha256 of its body, filled by 21.1's emitters now; `rev` and `unchanged` are null until 19.6's versioned blocks write them. The byte-identical share is recomputable from `block_sha` + `payload_bytes` before 19.6 lands |
    | `evidence`, `ref_query_id`, `lag_turns` | `used` only: what showed the use, which delivered event it points back to, and after how many turns |

11. **R11 Named emitters** (bsd #b-3). Each surface below emits `retrieved` for every item its
    retrieval returned and `delivered` for every item in the payload it wrote:
    - `scan_prompt`: the `rmx scan-prompt` command (`scan.py`), the UserPromptSubmit hook;
    - `prompt_recall`: `rmx memory recall --stdin-json`, the per-prompt recall hook
      (`hooks.py:301-316`);
    - `session_start`: the SessionStart recall;
    - `precompact`: the PreCompact recall. Its `delivered` events are emitted, and consumers do NOT
      count them as delivered until 19.5's probe decides whether PreCompact stdout reaches the
      agent (d5d);
    - `context`: the context verb on all four routes of R3;
    - `recall`: `rmx memory recall` / MCP `rmx_memory_recall` called by the agent;
    - `nudge`: 21.3's hook (it emits `delivered` only).

    19.1's pack joins later as an emitter of `prompt_recall` (owned by 19.1).
12. **R12 `used` events** (bsd #s-2). Emitted at an explicit agent call that names an item
    delivered earlier in the same session, with `evidence` ∈ `context_by_name` (a `context` call
    whose ref equals a delivered `name`), `memory_get_by_name` (an agent `memory_get`; recall's
    internal `memory_get` never counts, 19 #b-6), or `focus_note` (`rmx_focus_note` naming it).
    `ref_query_id` points at the delivering event's `query_id`. Calls whose `invocation` is `hook`
    never emit `used`, so the helix confound cannot recur. The enum reserves `file_read` and
    `cited_in_answer` for a transcript scorer (owner open: plan [[plan-21-agent-context-usage#open-after-revision]]).

## Acceptance criteria {#acceptance}

Every AC runs inside 23.0's sandbox and ends by asserting that the live `.refmatrix/query.log`,
`~/.refmatrix/query.log`, `.refmatrix/recall-events.jsonl` and `~/.refmatrix/recall-events.jsonl`
line counts are unchanged.

1. **MCP route.** An MCP `rmx_context` call through the real stdio server (a subprocess; `HOME` =
   tmp, `REFMATRIX_ROOT` = tmp, `RMX_HUB_MODELS=0`, short root for `sun_path`) produces exactly one
   `query.log` row with `invocation=mcp`, `kind=context`, `source=context-mcp`, a non-null
   `query_id`, and `session` equal to the `CLAUDE_CODE_SESSION_ID` the test set. RED at HEAD (no
   row).
2. **CLI routes.** On a tmp store, `rmx context X` forced down each of the replica, daemon and
   direct routes writes exactly one row with the route's `source`. RED at HEAD for
   `context-daemon` (no row).
3. **Precedence.** `invocation_source()` returns, for the env combinations
   {explicit `hook` + `CLAUDECODE`, `CLAUDECODE` alone, tty alone, none}: `hook`, `agent`,
   `interactive`, `unknown`. RED at HEAD on `CLAUDECODE` alone (returns `unknown`).
4. **Session never guessed.** Two subprocesses in ONE tmp root with different
   `CLAUDE_CODE_SESSION_ID`s, plus a newer STM ring for a third session id on disk, log disjoint
   `session` values equal to their own ids; with no envelope, no `CLAUDE_CODE_SESSION_ID` and no
   `RMX_SESSION`, `session` is null, not the third ring's id.
5. **`grep-stdin` cardinality.** `printf 'a\nb\nc\nd\n' | rmx grep -E 'a|b|c'` logs a
   `grep-stdin` row with `cardinality=3`. RED at HEAD (`null`).
6. **The frozen fixture** (bsd #s-3). A REDACTED copy of this project's `query.log` and `cli.log`
   cut at `2026-10-07T11:06:35` (bodies replaced by their sha256 and paths scrubbed, per d8f;
   counts are invariant under redaction) is committed under `tests/fixtures/agent_usage/`.
   `rmx telemetry --agent-usage --since 2026-09-23 --until 2026-10-07T11:06:35` on it prints
   EXACTLY: 3 context calls (`context-replica`), 1,119 `grep-replica` greps, 34 memory recalls
   (not 68: `phase=start` rows excluded). The cut excludes the 20 replay rows of
   2026-10-07T11:06:35-11:07:13 by window.
7. **The predicate** (d8d). A `query.log` holding one row with `cwd` under a pytest temp dir, one
   with a project cwd, and one legacy row with neither: `--agent-usage` counts 1, prints
   `excluded_test_rows=1` and `legacy_unattributed=1`. The same three rows as events in
   `recall-events.jsonl` are filtered by the same function (a test asserts both readers import it).
8. **Real emitters** (bsd #b-3). On a tmp store with 10 indexed memories, one real
   `rmx scan-prompt` run and one real `rmx memory recall --stdin-json` run, each fed a recorded
   UserPromptSubmit envelope on stdin through the GENERATED hook command line (not a direct
   function call), append to `recall-events.jsonl`: per surface, one `retrieved` event per
   retrieved item and one `delivered` event per emitted item, all sharing that call's `query_id`
   and the envelope's `session_id`, with `offset_bytes + bytes ≤ payload_bytes` and
   `payload_bytes` equal to the bytes the command wrote to stdout. A run whose payload carries 3 of
   10 retrieved items logs exactly 10 `retrieved` and 3 `delivered`.
9. **One format.** A test enumerates every writer of a `*.jsonl` file under `src/refmatrix/` and
   fails on any new file name that carries recall items other than `recall-events.jsonl`.
10. **Global scope** (d8e). A recall that returns one project and one global memory appends the
    global hit to the GLOBAL root's file with `scope=global` and `name` set, and the project hit to
    the project file.
11. **`used`.** In one session: a `prompt_recall` delivers memory `m`; an agent-invocation
    `memory_get m` then emits one `used` event with `evidence=memory_get_by_name` and
    `ref_query_id` = the delivering call's `query_id`; the same `memory_get` with
    `invocation=hook` emits none; recall's internal `memory_get` emits none.
12. **Mutations that must FAIL a test** (pre-registered):
    - the MCP env set after the first verb call (AC-1);
    - the `query.log` row written inside `_op_context` under the lock (AC-1: a lock-held probe sees
      the write; the caller-side assertion fails);
    - `context-daemon` route row removed (AC-2);
    - `CLAUDECODE` checked before the explicit env (AC-3);
    - `session` falling back to `stm.latest_session` (AC-4);
    - `grep-stdin` cardinality left unset (AC-5);
    - `phase=start` rows counted (AC-6: 68, not 34);
    - each reader given its own copy of the predicate (AC-7);
    - each surface's emitter removed, one at a time (AC-8);
    - `delivered` logged for every retrieved item (AC-8: 10, not 3);
    - global hits written to the project file (AC-10);
    - `used` emitted for `invocation=hook` (AC-11).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/mcp.py` | set the env in `serve_stdio` before the first request |
| `src/refmatrix/telemetry.py` | `agent` source + precedence; `session`/`query_id`/`cwd`/`root` on rows; `is_test_artifact_row`; the `--agent-usage` report; the recall-event writer and reader |
| `src/refmatrix/verbs.py` | caller-side row + events for `context` and `memory_recall` (MCP route) |
| `src/refmatrix/cli.py` | `context-daemon` row; `grep-stdin` cardinality; `--agent-usage`/`--until`/`--by-session`; events on the CLI context and recall routes |
| `src/refmatrix/scan.py` | `scan_prompt` emitter with payload offsets and raw phase inputs |
| `src/refmatrix/cli.py` (`memory recall`), `hooks.py` | `prompt_recall`, `session_start`, `precompact` emitters; the generated hook lines carry the envelope through |
| `tests/fixtures/agent_usage/` | the redacted frozen `query.log`/`cli.log` cut |

## Test strategy {#test-strategy}

- **Sandbox:** every test runs under 23.0's sandbox ($HOME, global root, registry and LaunchAgents
  redirected before `refmatrix` is imported; spawned `rmx` children refuse sockets outside the tmp
  dir). Subprocess tests additionally pass `HOME`, `REFMATRIX_ROOT` and `RMX_HUB_MODELS=0`
  explicitly, because bug-088's recorder cannot see a child's connects. Each test asserts the live
  log line counts above are unchanged; no test writes the log this task measures (bsd #s-7).
- **RED first** (`feedback_red_test_must_fail_at_head`): AC-1, AC-2 (`context-daemon`), AC-3
  (`CLAUDECODE`), AC-4, AC-5, AC-7, AC-8, AC-10, AC-11 are run against HEAD before any `src/`
  change and the failing assertion is recorded. AC-6 fails at HEAD because `--agent-usage` does not
  parse. No AC is admitted that passes at HEAD.
- **Hook path:** AC-8 runs the command string `hooks.py` GENERATES for UserPromptSubmit, not a
  hand-written one, so a generator change that drops the emitter is caught.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding or decision | answered at |
|---|---|
| bsd #b-1 (session, query_id, join key) | [[#req-session]] R9; R4; AC-1, AC-4 |
| bsd #b-2 (name key, channel enum) | R10 (`name`, `entity_id`, `channel`); AC-10 |
| bsd #b-3 (no production emitter, no sink) | R8, R11; AC-8, AC-9 |
| bsd #s-1 (delivered vs seen) | R10 (`offset_bytes`, `bytes`, `payload_bytes`); AC-8 |
| bsd #s-2 (phase fields, `used` emitter) | R10 (`arm`, `policy`, raw inputs, `restored_cluster_id`), R12; AC-11 |
| bsd #s-3 (AC-4 cannot fail) | R7; AC-6 |
| bsd #s-4 (`-E` not reproduced) | R6; AC-5 |
| bsd #s-5 (CLI daemon route, `ann_search`, MCP tools) | R3, R7; AC-2 |
| bsd #s-6 / d4f (agent stays unknown) | R2; AC-3 |
| bsd #s-7 / d1a, d1b (tests touch live logs) | [[#test-strategy]]; [[#acceptance]] preamble |
| bsd #m-1 (`mcp` already a source) | R1 |
| bsd #m-2 (`telemetry` is a command) | R7 |
| bsd #m-4 / d4a (dependency and sink) | header; R8 |
| bsd #m-3, #m-5, #m-6, #m-7 | not this task: 21.3 (#m-3, #m-5, #m-6), plan `#decisions` (#m-7) |
| d4a + d2a amendment (retained replay source, tail reader) | R8 |
| d5b (turn logged, never a phase signal; 19.6 owns the arm) | R9, R10 |
| d5d (PreCompact not counted as delivered) | R11 |
| d8d (shared pytest-temp predicate) | R5; AC-7 |
| d8e (`scope`, global hits in global store) | R8, R10; AC-10 |
| d8f (redacted fixture) | AC-6 |
| decision-log #m-2 (`CLAUDECODE` precedence) | R2 |
| exploration #vi-evidence (`block_id`, `rev`, `unchanged`) | R10 |
| #t8-wave1 (21.1 needs only 23.0) | header |
