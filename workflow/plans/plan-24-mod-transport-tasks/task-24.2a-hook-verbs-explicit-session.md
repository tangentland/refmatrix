---
gmd: "0.1"
id: task-24.2a-hook-verbs-explicit-session
title: "Task 24.2a: every hook path the mod takes over becomes a verb, every session-dependent verb takes an explicit session and uses it verbatim, and a caller context replaces the pid ladder wherever a caller can name the session"
tags: [task, plan-24, verbs, session, hooks, parity, mod]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.2a: hook verbs with an explicit session {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20; added by the orchestrator after ch-bsd's plan-24
> review, finding b1).
> Depends on: [[task-3.7-verb-it-backlog]] merged (it rewrites `rmx_focus` into a dispatcher, adds
> `rmx_curator`, `snapshot_read` / `local_write`; this task edits the same functions).
> Feeds: 24.2 (the host serves these verbs and seeds the caller context), 24.4 (generates from
> the `@verb` fields added here), 24.6 (calls these verbs from the mod).

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: depends-on -> [[task-24.1-store-runtime-identity]]
rel: implements -> [[plan-24-mod-transport#goals]]
rel: implements -> [[exploration-claude-code-mod-transport#http-verbs-only]]
rel: derives-from -> [[bsd-plan24-spec-review-cdcfbc3#b1]]
rel: related-to -> [[task-21.1-context-usage-telemetry]]

## Why {#why}

D3 makes the per-store HTTP socket serve verbs only. The work 24.6 moves into the mod is not
verbs: `focus hook` (all five events), `scan-prompt`, `primer`, `sync --flush-queue` and `focus
summarize --promote` sit in `LEGACY_UNPAIRED` category `hook` ("not owed a verb"), and 3.7 does not
cover them (3.7 verbs `curator status` as `rmx_curator`). And the verbs that exist resolve the
session through the pid ladder: `rmx_context` and `rmx_memory_recall` take no `session` and call
`telemetry.resolve_event_session(root)`, which runs `stm.owner_lookup()` over the CALLER's process
ancestry. Inside the daemon that ancestry is launchd's, so every row would carry `session: null`
(ch-bsd b1). G1 is the opposite: the mod knows the session (`$.session.id()`, the transcript's
name) and must be believed. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | One `contextvars.ContextVar` `verbs.CALLER` holds `Caller(session, invocation, hook_event, prompt_id, agent_id, in_host)`; `resolve_session_source` reads it after the explicit argument and before the envelope, source `"caller"` | ONE resolver stays THE resolver (bug-109, 21.1 R9); a context var crosses every helper a verb calls without threading a new arg through telemetry |
| d2 | With `CALLER.in_host` set, the ladder never runs: `read`/`write` with no session raise `SessionUnresolved`, `event` returns `(None, "none")` | the host's process ancestry is launchd's; any ladder answer there is a guess (b1) |
| d3 | The tool-event verb takes the tool's name, input AND result as data (`rmx_focus_observe`), not a hook envelope blob | G3: the mod has the real result from `await next(e)`; re-parsing stdin is the thing being removed |
| d4 | The `say` event accepts `text` directly; `transcript_path` stays for the shell twin | the mod has the turn's answer (`turn.complete`); reading a transcript file from the daemon is a second way to get it |
| d5 | The pid-pointer write moves out of the observe verb into the CLI twin (`focus hook` passes `owner_pid` it computed) | the pointer exists only for callers that cannot name the session; the mod never needs it |
| d6 | Summarize/promote becomes action `summarize` on 3.7's `rmx_focus` dispatcher, not a new verb | 3.7's family pattern (one dispatcher per group, `CLI_ACTIONS` twins) |
| d7 | `@verb` gains `surface` ("model" \| "engine"), `writes` (bool, or the set of write actions), `tier` ("store" \| "hub" \| "both"), `deferred` (bool, default True) | the mod registers model tools only, the host drops queued reads but never writes (bug-116), the hub serves only hub-tier verbs; all of it read off the verb, never a side table |
| d8 | Engine verbs are not MCP tools; `mcp.TOOLS` becomes the model-surface verbs | the model must not call `rmx_focus_observe`; the MCP server dies on the Claude Code path at 24.8 anyway |
| d9 | `rmx_memory_recall` gains `trigger` ("prompt" \| "session_start" \| "precompact") which `recall_channel` reads first | the channel was inferred from `--stdin-json` and `invocation == "hook"`; the mod's call has neither, and 21.1's channels must stay true |
| d10 | `ingest-gmd`, `grep` (the shim command) and `focus record` stay in `LEGACY_UNPAIRED` | 24.6 does not move them (SessionStart bridge stays a shell hook; the shim is plan-16's) |

## Requirements {#requirements}

1. **R1 — the caller context.** `verbs.Caller` (frozen dataclass) and `verbs.CALLER:
   ContextVar[Caller | None]` (default None), with `verbs.caller(**fields)` a context manager
   that sets and resets it. `resolve_session_source(root, session, envelope=, purpose=)` order
   becomes: explicit `session` → `CALLER.session` (source `"caller"`) → envelope → (only when
   `CALLER` is None or not `in_host`) the existing ladder. In-host misses follow d2 and record a
   miss row `host-no-session` (never silent). `telemetry.invocation_source()` returns
   `CALLER.invocation` when set; `INVOCATION_SOURCES` gains `"mod"`. {#r1}
2. **R2 — explicit session everywhere.** Every verb whose body (or a helper it calls) resolves a
   session declares `session: str | None = None` and passes it to the resolver: at least
   `rmx_context`, `rmx_memory_recall`, `rmx_memory` (the `get` used-event path,
   `emit_memory_get_used`), `rmx_query` (telemetry), `rmx_focus`, `rmx_focus_note`,
   `rmx_change_subject`, `rmx_task`, `rmx_save_state`, `rmx_recall_state`, and 3.7's `rmx_session`
   / `rmx_graph` if they resolve one. `telemetry.resolve_event_session(root, envelope=None, *,
   session=None)` gains the argument. A given session is used verbatim: never validated against a
   ring's existence, never rewritten. {#r2}
3. **R3 — `rmx_focus_observe` (engine, writes).** `(event: Literal["input", "tool-pre", "tool",
   "say", "reason", "session-start"], session: str, *, tool: str | None, input: dict | None, result: dict |
   None, tool_use_id: str | None, prompt: str | None, text: str | None, transcript_path: str | None,
   agent_id: str | None, source: str | None, cwd: str | None, owner_pid: int | None,
   mentions: list[str] | None, row_uuid: str | None)`. `session` is REQUIRED (no default). The body is `focus_hook`'s
   body today (`cli.py` ~2053-2170) moved into `stm` / `verbs` helpers, unchanged in effect: the
   in-flight park/clear keyed by `tool_use_id`, the input snapshot + sweep + record order of 21.1
   R9, the git-milestone and rationale harvest, `say` from `text` else `transcript_path`.
   `session-start` writes a pid pointer ONLY when `owner_pid` is given, then returns the
   surfacing lines as `{"lines": [...], "errors": [...]}` instead of printing. `reason` (new, for
   24.6's `session.append` capture) records `text` as a `reason` event with `refs=[]`, the kind the
   commit-rationale harvest already writes, so the reasoning the assistant states in prose joins the
   intent thread without admitting prose tokens into the focus graph. `row_uuid` (24.6 d14): an
   event whose `(session, row_uuid)` was already recorded is dropped and answered `{"recorded":
   false, "reason": "duplicate row_uuid"}`; the recorded uuids are read from the ring itself (the
   event stores its `row_uuid`), so the check survives a daemon restart. `mentions` is 24.6's
   used-evidence input (R3 there); this task accepts and stores it on the event. {#r3}
4. **R4 — `rmx_scan_prompt` (engine, read; its telemetry rows and events are logs, not store
   writes).** `(prompt: str, session: str, *, max_tokens=2000,
   per_concept_tokens=600, max_concepts=5, exclude_namespace=["keyword"], include_noise=False,
   rank="ppr", degree=0, content=True, content_tokens=600, composite=True,
   composite_max_tokens=1200, composite_k=3, composite_no_expand=False, composite_every=1,
   composite_intra_edges=3, timeout=5.0, skip_block_shas: list[str] | None = None)`; returns
   `{"text": str, "blocks": [{"block_id", "block_sha", "text", "unchanged"}], "warnings": [...]}`.
   Defaults equal `scan-prompt`'s click defaults (the parity gate checks). `skip_block_shas`: a
   block whose sha is listed is omitted from `text` and its delivered event is emitted with
   `unchanged: true` (21.1's field), so 24.6's dedup never makes telemetry lie. {#r4}
5. **R5 — `rmx_primer` (engine, read).** The `primer` command's options as params; returns
   `{"text": str, "generated_at"}`; `--out` stays a CLI-only rendering of the same text. {#r5}
6. **R6 — `rmx_sync` (engine, writes).** `(action: Literal["flush", "enqueue"], *, files:
   list[str] | None, wait: bool = False, timeout: float | None = None)`: `flush` is today's
   `sync --flush-queue [--async]` (`wait=False` ⇔ `--async`), `enqueue` is `sync --enqueue-only -f`
   for each file. One attempt; busy is `VerbBusyError`, never an in-process fallback for `flush`.
   {#r6}
7. **R7 — `rmx_focus` action `summarize`.** Params `promote: bool`, `global_: bool` (alias
   `global`), `timeout`; the body of `focus summarize`. CLI `focus summarize` becomes its
   `CLI_ACTIONS` twin. {#r7}
8. **R8 — (removed in r2).** The shell's grep paths stay shell hooks; their verb forms
   (`rmx_shell_rewrite`, `rmx_grep_teach`) are 24.8 follow-up candidates (ch-bsd r2 s9). {#r8}
9. **R9 — recall trigger.** `rmx_memory_recall(..., trigger=None, session=None)`;
   `telemetry.recall_channel` takes `trigger` first (`prompt` → `prompt_recall`, `session_start` →
   `session_start`, `precompact` → `precompact`), falling back to today's inference. The CLI's
   `--stdin-json` passes `trigger="prompt"`, `--session-start` passes `"session_start"`, the
   PreCompact entry's `--recent` passes `"precompact"`. {#r9}
10. **R10 — the CLI paths become twins, and the shell keeps working.** `focus hook --event X`
    reads its envelope (`stm.read_hook_envelope`, unchanged), maps it to R3's params and calls
    `verbs.focus_observe`; `scan-prompt` → `verbs.scan_prompt`; `primer` → `verbs.primer`;
    `sync --flush-queue` / `--enqueue-only` → `verbs.sync`. Each leaves `LEGACY_UNPAIRED` (`hook`)
    for `CLI_MAP` / `CLI_ACTIONS` as `calls`. Generated hook commands are unchanged in this task;
    their output and exit codes are unchanged (the regression tests that pin them keep passing).
    {#r10}
11. **R11 — `@verb` fields.** `surface`, `writes`, `tier`, `deferred` per d7, with defaults
    `surface="model"`, `writes=False`, `tier="store"`, `deferred=True`, explicitly set on every
    verb whose truth differs (every write verb, every bus / where / search / locate / projects /
    queues / canon verb as `tier="hub"` or `"both"`). `_json_type(dict)` → `{"type": "object"}`.
    `mcp._build_tools` keeps only `surface == "model"`. {#r11}
12. **R12 — the structural gate.** `tests/test_verb_parity.py` gains: (a) every verb whose source
    (`inspect.getsource` over the verb and the module-level helpers it names) calls
    `resolve_session_source` or `resolve_event_session` declares a `session` parameter; (b) every
    `writes` verb is classified (no write verb with the default `False`: a list of write ops a verb
    reaches is asserted by recording `_call` ops during each verb's existing test, write ops being
    those not in `daemon.CLI_OPS` or in `CLI_WRITE_OPS`); (c) `set(mcp.TOOLS) == {model verbs}`.
    {#r12}
13. **R13 — timeouts are declared, not buried (r4, ch-bsd r3 s3).** `@verb` gains `timeouts:
    dict[str, float | None]`, keyed by action (`"*"` for a verb without actions; `None` =
    deliberately unbounded), holding every default bound the verb's body applies today. This
    CHANGES 3.7's verbs after it merges and is this task's requirement, not a 3.7 amendment. At
    3.7's tree the declared values are at least: `rmx_graph` recall / dense 180, timeline 60,
    describe / stats 10; `rmx_canon` link 60; `rmx_curate` forget 600 (preview and purge, 3.7
    R-RM5); `rmx_memory` read actions 10, write actions 120; `rmx_memory_recall` 30 (its legs' 60 /
    180 / 30 / 120 caps become `timeouts` keys `leg:*` the body reads); `rmx_context` 60;
    `rmx_query` 30; `rmx_save_state` None; `rmx_session` list 60. Bodies read
    `verbs.verb_timeout(name, action, key="*")` instead of a literal, and `ACTION_DEFAULTS`'
    `timeout` rows move into `timeouts`. The values join `verb_schema()` (24.1 R1), so the schema
    hash changes when a bound does. A parity test parses every verb body (`ast`) and fails on a
    numeric literal passed as `timeout=`, to `_left(...)`, or as the `else` of a `timeout`
    conditional. HELPERS (r5, ch-bsd r4 m3): every helper a verb reaches that bounds a wait —
    at 3.7's tree `_call` (60), `session_memories` (60), `global_recall_rows` (30),
    `attach_context` (120), `_memory_recall_rows` (30) and `session_memory_get` (60) — loses its default
    `timeout` (the parameter becomes keyword-only and REQUIRED), and every verb passes its declared
    timeout to it explicitly; a CLI path that calls a helper directly passes the same declared
    value. The gate extends to them: an AST walk over `verbs.py` fails on any function reached from
    a `@verb` (by name, transitively within the module) whose signature gives `timeout` a numeric
    default. {#r13}
14. **R14 — `idempotent_by` (r5, for 24.2 d15).** `@verb` gains `idempotent_by: dict[str, str |
    None]` keyed by action (`"*"` for a verb without actions), required for every `writes` action:
    `"transaction"`, a stored natural-key field name, `"natural"`, or `None` (not confirmable). The
    verb bodies for field-keyed writes skip a record whose key is already present and answer
    `{"recorded": false, "replayed": true}`; the value joins `verb_schema()`. {#r14}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1, R2).** With `verbs.caller(session="S1", invocation="mod", in_host=True)` active and
   `$RMX_SESSION=S2` plus a pid pointer for the test process naming S3: `rmx_context` writes its
   query.log row and recall events with `session == "S1"` and `invocation == "mod"`. Without a
   session and `in_host=True`: `rmx_focus_note` raises `SessionUnresolved`, `rmx_context`'s row
   carries `session: null`, and one `host-no-session` miss row is written. RED at base. {#ac-1}
2. **AC-2 (R3).** `rmx_focus_observe` called with `event="tool-pre"` then `event="tool"` (same
   `tool_use_id`, a Bash `git commit` input and a result) leaves exactly the ring the shell path
   leaves for the same envelope pair (a golden comparison: both paths run under one short root and
   the two rings' events are equal minus timestamps). `event="say", text="..."` records `say`.
   `session-start` without `owner_pid` writes no pointer file. RED at base. {#ac-2}
3. **AC-3 (R4).** `rmx_scan_prompt` on a fixture store returns the bytes `scan-prompt --format
   text` prints for the same prompt and options; with one returned block's sha in
   `skip_block_shas`, that block is absent from `text` and its recall event has `unchanged: true`.
   {#ac-3}
4. **AC-4 (R6, R7, R9).** `rmx_sync(action="flush")` against a busy daemon fixture raises
   `VerbBusyError` and touches no catalog file; `rmx_focus(action="summarize", promote=True)` with
   an explicit session promotes that session's digest; `rmx_memory_recall(trigger="prompt",
   session="S")` emits `prompt_recall` events with `invocation="mod"` under a mod caller. {#ac-4}
5. **AC-5 (R3, row_uuid).** Two `reason` observes with one `row_uuid` record one event; after a
   daemon restart a third is still dropped. {#ac-5}
6. **AC-6 (R10).** The existing hook regression suites pass unchanged
   (`test_hook_wiring.py`, `test_hooks.py`, `test_task21_1_*`), and the
   parity walk shows the moved paths as twins. {#ac-6}
7. **AC-7 (R11, R12).** The three structural gates of R12 fail on a deliberately broken copy
   (a verb copy that calls the resolver without a `session` param; a write verb left
   `writes=False`) and pass on the tree. {#ac-7}
8. **AC-8 (R13, R14).** The AST gate fails on a copied verb body containing `timeout=60.0`, and on a
   copied helper reached from a verb whose signature has `timeout: float = 60.0`, and passes on the
   tree; every `writes` action has an `idempotent_by` entry; `verb_schema()` carries `timeouts` for every verb; changing `rmx_graph`'s recall
   timeout changes that verb's hash; `verb_timeout("rmx_curate", "forget")` is 600.0. {#ac-8}

## Test strategy {#test-strategy}

New `tests/test_task24_2a_hook_verbs.py` (AC-1..AC-5) under 23.0's short-root sandbox; AC-6 is the
existing suites; AC-7 extends `tests/test_verb_parity.py`. Golden comparisons (AC-2, AC-3) run the
CLI twin and the verb against the same fixture store and compare outputs, so the move is proven
behaviour-preserving rather than re-asserted. RED first, logged to
`workflow/review-output/task24_2a-red.log`. No mock of a verb under test; the busy daemon in AC-4 is
the existing `_pingonlydaemon` / `_silentdaemon` fixture. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/verbs.py` | `Caller`, `CALLER`, `caller()`; resolver order; `session` params (R2); new verbs R3-R7; `@verb` fields (R11); `CLI_MAP` / `CLI_ACTIONS` / `LEGACY_UNPAIRED` moves (R10) |
| `src/refmatrix/telemetry.py` | `"mod"` invocation; `resolve_event_session(..., session=)`; `recall_channel(trigger=)`; `host-no-session` miss reason |
| `src/refmatrix/stm.py` | the observe body's helpers (moved from `cli.py`), no behaviour change |
| `src/refmatrix/cli.py` | `focus hook`, `scan-prompt`, `primer`, `sync`, `focus summarize`, `memory recall` become adapters |
| `src/refmatrix/mcp.py` | `_build_tools` keeps model-surface verbs |
| `tests/test_task24_2a_hook_verbs.py`, `tests/test_verb_parity.py` | AC-1..AC-8 |
| `src/refmatrix/cli.py` (~12235, the `attach_context` call) | passes the declared timeout now that the helper's `timeout` is required (R13) |
| `tests/test_plan3_remedy_r3.py` (~84), `tests/test_task3_7_folded.py` (~56) | callers broken by the required `timeout` (R13); these edits belong to the test engineer's RED step, not to GREEN |

## Revision r2 (2026-10-20, ch-bsd r2 03c2d1f) {#rev-r2}

| finding | change |
|---|---|
| s9 `rmx_shell_rewrite` / `rmx_grep_teach` built here, wired in 24.6, retired in 24.8 | R8 removed; AC-5 replaced; `search_hooks.py` row dropped; listed in 24.8's candidates |
| s3 reason / say double-record | R3 `row_uuid` with a restart-proof duplicate drop; new AC-5 |
| s5 curator drain per prompt | no change here: `rmx_curator(action="status")` is 3.7's verb; 24.6 d15 calls status only |

## Revision r4 (2026-10-20, ch-bsd r3 6d3575b) {#rev-r4}

| finding | change |
|---|---|
| s3 the mode rule could not be computed: timeouts are literals in verb bodies | R13: `@verb(timeouts=…)` per action, bodies read them, they join the schema hash, an AST parity gate forbids literals; stated as 24.2a's change to 3.7's merged verbs; AC-8 |

## Revision r5 (2026-10-20, ch-bsd r4 08b1518) {#rev-r5}

| finding | change |
|---|---|
| m3 the timeout gate missed helper defaults | R13: helpers reached from verbs take a REQUIRED keyword `timeout`, verbs pass the declared value explicitly, and the AST gate flags any helper default reachable from a verb; AC-8 |
| s1 (for 24.2 d15) | R14: `@verb(idempotent_by=…)` per write action; AC-8 |

## Revision r6 (2026-10-20, ch-bsd r5 0109574) {#rev-r6}

| finding | change |
|---|---|
| m1 callers broken by R13's required `timeout` were unlisted | files table: `cli.py` ~12235 (`attach_context`), `tests/test_plan3_remedy_r3.py` ~84, `tests/test_task3_7_folded.py` ~56; the test edits are the RED step's |

