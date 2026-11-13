---
gmd: "0.1"
id: task-24.6-context-and-observation
title: "Task 24.6: context and observation move into the engine — prompt.submit / prompt.compose / prompt.section / prompt.context replace scan-prompt, per-prompt and session-start recall; tool.call, turn.complete, session.append and session.compact replace the focus, Stop and PreCompact hooks and observe each result; the shell hooks stay as a fallback that stands down while the mod is live, and stop hiding their failures"
tags: [task, plan-24, mod, hooks, context, observation, stm, fallback, telemetry]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-11-13
---

# Task 24.6: context and observation move in {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20; the facilities rows assigned to 24.6 in
> [[exploration-claude-code-mod-transport#facilities]] folded in; the stand-down marker, hook
> loudness and the subagent / `-p` probes added per ch-bsd s5; `refmatrix.injected` /
> `refmatrix.delivered` per the user's question of 2026-10-20 on `$.state`; revised for ch-bsd r2,
> [[#rev-r2]]; r5 and r6 (2026-11-11) align the tool observation with task 21.5, [[#rev-r5]],
> [[#rev-r6]]; r7 (2026-11-13) follows 21.5 rev 3, [[#rev-r7]]).
> Depends on: [[task-24.2a-hook-verbs-explicit-session]] (every verb this task calls),
> [[task-24.5-mod-core]] (handshake, routing, state contract, outbox, timers),
> [[task-24.0-hook-cost-baseline]] (its before window closed before this deploys; its row schema).
> Feeds: 24.0's after window; 24.8's re-specified held items build on these events.

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-24.2a-hook-verbs-explicit-session]]
rel: depends-on -> [[task-24.5-mod-core]]
rel: depends-on -> [[task-24.0-hook-cost-baseline]]
rel: implements -> [[plan-24-mod-transport#goals]]
rel: implements -> [[exploration-claude-code-mod-transport#facilities]]
rel: derives-from -> [[bsd-plan24-spec-review-cdcfbc3#s5]]
rel: derives-from -> [[bsd-plan24-spec-review-r2-03c2d1f]]
rel: derives-from -> [[plan-24-mod-transport#probes]]
rel: related-to -> [[task-21.1-context-usage-telemetry]]
rel: related-to -> [[reference_hook_output_10k_cap]]
rel: related-to -> [[feedback_install_hooks_no_claude_reaps]]
rel: related-to -> [[feedback_bind_capture_to_mandatory]]

## Why {#why}

The hot hooks are where the integration is thinnest: three `UserPromptSubmit` processes race each
other (the focus `input` hook writes the state that `scan-prompt` and `recall` read, in parallel),
their output is capped at ~10k characters and lands in the transcript, `focus hook --event tool`
re-parses a stdin envelope to learn what the tool did, and every failure ends `2>/dev/null ||
true`. In the engine, the prompt events can be ORDERED, context goes where the model reads it
(G2), a tool call is seen with its result (G3), and a failure is a line (G6). The shell hooks stay:
not every context is known to load a mod, and a broken mod must not leave a session with nothing.
{#why-lead}

## The event map {#event-map}

"Unprobed" marks a row whose event is not yet shown to fire in that loop; its shell entry is not
stood down until the probe reads (R7). Per [[plan-24-mod-transport#probes]] and
[[plan-24-mod-transport#probes-batch2]]: `tool.call`, `turn.step` and `turn.complete` fire for
subagents (foreground and background) with `agentId`; `turn.start` fires for them WITHOUT one;
`prompt.compose` and `prompt.section` fire for the main loop only; `prompt.context` is computed
once and its blocks reach every subagent; `agent.spawn` can rewrite a subagent's task; `skill.prompt`
never fired (unprobed). {#event-map-lead}

| engine event (mod) | verbs, in order | shell entry it stands in for |
|---|---|---|
| `classic.SessionStart` (its `e.source`: startup / resume / clear / compact) | `rmx_focus_observe(session-start)`; then in parallel `rmx_memory_recall(trigger=session_start, k=10, scope=both)`, `rmx_memory(action=brief)`, `rmx_curator(action=status)`, `rmx_sync(flush)`, and on `resume` `rmx_focus(context, top=15)`; then `$.ui.invalidate("prompt.section")` and `$.ui.invalidate("prompt.context")` | SessionStart focus / recall / resume-focus / sync-flush + curator entries |
| `prompt.compose` (main loop) | append the id `refmatrix:memory` (`scope: "session"`) after every `shared` section | — (new) |
| `prompt.section` on `refmatrix:memory` | answer the memory brief; cached by the engine until the next invalidate | — |
| `prompt.context` (main loop) | append one block: session-start recall + (on resume) the focus context + the curator count line | SessionStart's stdout |
| `prompt.submit` | `rmx_focus_observe(input, prompt)` AWAITED first; then in parallel `rmx_scan_prompt(prompt, max_tokens, composite_every, timeout, skip_block_shas=<injected>)`, `rmx_memory_recall(query=prompt, trigger=prompt, k, scope, timeout)`, `rmx_curator(action=status)` → `next({ ...e, context: [...] })` | the three UserPromptSubmit entries |
| `tool.call` on EVERY tool (no tool filter; r6), main loop and subagents | `rmx_focus_observe(tool-pre)`; `const ran = await next(e)`; `rmx_focus_observe(tool, input, result: ran, mentions, tool_use_id, agent_id)`; edits (Edit / Write / MultiEdit / NotebookEdit, by `String(e.tool)`): `rmx_sync(enqueue, files)`; return `ran` unchanged | PreToolUse / PostToolUse focus and enqueue (the shell matcher covers only Edit / Write / MultiEdit / NotebookEdit / Read / Bash / Grep / Glob) |
| `session.append`, door `response`, main loop | OBSERVE ONLY: the row's text (≥ 40 chars) is held, and sent as `rmx_focus_observe(reason, text, row_uuid)` when the NEXT response row of the turn arrives (so it was not the final answer) | — (new: reasoning capture) |
| `turn.complete` (main loop) | the held last response row is sent as `rmx_focus_observe(say, text, row_uuid)` (never also as `reason`); `rmx_focus(summarize, promote=True, timeout=5)`; `rmx_sync(flush)`; refresh `refmatrix.focus` | Stop's three entries |
| `turn.complete` (`e.agentId` set; probed: fires) | `rmx_sync(flush)`; subagent turns are attributed by this event and `turn.step` (both carry `agentId`), never by `turn.start` | SubagentStop |
| `agent.spawn` (foreground and background) | `next({ ...e, prompt: e.prompt + "\n\n" + brief })` where `brief` is a short labelled refmatrix block (≤ 1,500 chars: `[refmatrix context — added by the refmatrix plugin]`, the `rmx_context` / `rmx_memory_recall` tool names, the session's focus subject and top symbols from `refmatrix.focus`) | — (new: subagent context route) |
| `skill.prompt` — UNPROBED (never fired in batch 2) | none | — |
| `session.compact`, main loop, trigger `manual` / `auto` | before `next(e)`: `rmx_focus(summarize, promote=True, timeout=30)`, then `rmx_save_state(message="auto: pre-compact checkpoint", promote=False, sync=False)`; `instructions` and `messages` passed unchanged | PreCompact promote + save-state |
| — (stays shell, no guard) | SessionStart `ingest-gmd --as-memory --detach`; SessionStart's backgrounded `rmx primer --out …/PRIMER.md` (the file CLAUDE.md imports); the user-global grep-rewrite-guard and grep-tool-teach; the project's enforce-test-to-file, enforce-rmx-grep, adr-gate and p20-0 hooks; PreCompact `memory recall --recent` | — |

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | The input observation is awaited BEFORE scan and recall start | 21.1 R9's order (snapshot, sweep, record) exists because scan and recall read what the input hook writes; in the shell they race, in the engine they need not |
| d2 | Per-prompt context goes in `prompt.submit`'s `context` entries; session-fixed context goes in a `prompt.context` block and one `refmatrix:memory` section | `context` is read beside the prompt and never shown, with no 10k cap (G2); `prompt.section` answers are cached, so the section is cache-stable across turns |
| d3 | The session context is built at `classic.SessionStart`, which carries `source`; `session.start` fires once per process and not after `/clear` | `/clear`, `/compact` and resume each need a fresh block, and only the classic event says which happened |
| d4 | The primer stays where it is: CLAUDE.md's `@.refmatrix/PRIMER.md` import, regenerated by the unguarded SessionStart shell entry; the mod adds no primer section (r2 s4). The import is removed only by a later decision, after this task's AC-13 proves the `agent.spawn` route carries refmatrix context into a subagent | subagents read CLAUDE.md and `prompt.compose` does not fire for them ([[plan-24-mod-transport#probes]]), so dropping the import would leave subagents with no primer; a mod section beside the import would double it for the main loop |
| d4b | Session-start recall, the resume focus and the curator line go in a `prompt.context` block, not the system prompt | conversation facts that change per session; the engine re-reads that block on compaction and `/clear`, exactly when they must be rebuilt |
| d4c | Core's own sections (`memory` and the rest) are never rewritten: the mod's `prompt.section` hook matches only `refmatrix:memory` | Claude Code's auto-memory index is the user's file |
| d5 | `refmatrix.injected = { session, shas }` (21.1's `block_sha`s delivered this session, cap 500) is passed to `rmx_scan_prompt` as `skip_block_shas`; the VERB omits them and emits `unchanged: true` | the composite is not re-sent every turn, and delivered events stay true because the daemon decides what was delivered |
| d6 | `refmatrix.delivered = { session, items: [{ name, kind, query_id }] }` (cap 2,000) from scan / recall answers; `tool.call` finds those names in `ran.text` and sends them as `mentions`; the daemon records them RAW on the tool's STM ring event as `result_mentions` (with 21.5's ring fields), checks them against nothing at observe time, and emits NO `used` — amended 2026-11-11 ([[#rev-r5]], [[#rev-r6]]) | `used` evidence of tool use is derived at report time by [[task-21.5-tool-used-signal]], never emitted by a hook or the mod. An observe-time `delivered_in_session` check would be the per-tool-call 2 × 4 MB backward read 21.5 D1 rules out, and would make `$.state` a second delivered-set source (21.5 r1 x-3); `$.state` only pre-filters which names are sent. 21.5 keeps `result_mentions` as a reserved field its matcher ignores (counted `result_mentions_present`) until a `match_on: tool_result` leg, checked against the delivered events at report time, is measured against its bands |
| d7 | STM events go to the daemon on every call, never buffered in `$.state`; concurrent `$.state` updates use `update` (`ifVersion`); a failed engine write goes to 24.5's outbox | 24.5 d7: `$.state` is not a system of record |
| d8 | Stand-down marker: `$.env.set("RMX_MOD_LIVE", "<epoch s>")` and `$.env.set("RMX_MOD_EVENTS", "<classes>")` are set SYNCHRONOUSLY as the first statements of 24.5's `session.start` handler (before the discovery await), and refreshed by a timer of their own, `$.clock.every(10_000)`, independent of `health_interval_s`; the guard window is 45 s (four refreshes); the timer survives `session.end` reason `clear` (24.5 d1) | r2 s1(a)(b) and b1: a marker refreshed only by the configurable health tick, or stopped at `/clear`, lets the shell resume beside the mod |
| d9 | ONE class list for the whole process (`$.env` is one value per process, shared by the main loop and its subagents): `start,prompt,tool,stop,compact`. Instead of per-context lists, a generated entry carries the guard only when the mod's equivalent is shown to fire in EVERY loop that entry fires in; SubagentStop's entry is now guarded too (batch 2: `turn.complete` fires with `agentId`) | r2 s1(c): per-context lists cannot be expressed in one process-wide variable |
| d10 | If P-env shows settings hooks do NOT inherit `$.env.set`, the marker is a file `<store>/.refmatrix/mod-live/<session_id>.json` (epoch + classes) written by the same timer, and the guard reads `session_id` from the envelope with `jq` (stdin saved and replayed to the command); the generator emits exactly the one mechanism the probe chose. If the marker reaches other hooks but NOT the SessionStart entries (set too late for them), the `start` class is dropped from the marker and the mod's `classic.SessionStart` hook does only the `refmatrix:memory` brief (the shell entries do the rest) | the types name Bash children, MCP servers and `$.process.run` as inheriting, not settings hooks; whichever mechanism, one event is never handled twice |
| d11 | Fallback loudness (G6): every generated rmx entry drops `2>/dev/null` and `|| true`; the hook twins exit 1 with one stderr line on failure (a non-blocking error Claude Code shows), never 2; backgrounded commands append stderr to `<store>/.refmatrix/hooks.stderr.log`, which 24.5's tick counts and the status line shows | the project rule (no silent failures on memory paths) and G6, on the path that stays |
| d12 | `session.compact` replaces the PreCompact entries for promote and save-state, and passes `instructions` / `messages` UNCHANGED; the PreCompact `memory recall --recent` entry stays on shell, unguarded | whether compaction should be told what to keep is 19.6 R8's question (re-specified by 24.8); keeping that one entry leaves 21.1's `precompact` channel as it is |
| d13 | `session.append` is OBSERVE-ONLY: every hook returns `next(e)` with the event it received, for every door; nothing is rewritten (r2 s2) | a rewrite is stored and sent in place of the original, so the model and the transcript never see the original; no goal needs one |
| d14 | Reason and say never record the same row: a response row is sent as `reason` only once a LATER response row of the same turn proves it was not the final answer; the final row is sent once, as `say`; both carry `row_uuid` (`e.uuid`) and the verb drops a second event for a `(session, row_uuid)` it has recorded (24.2a R3) | r2 s3: the final answer is a `response` row AND `turn.complete`'s text |
| d15 | The curator is STATUS-ONLY on the mod path: `rmx_curator(action="status")` per prompt and at session start; the count is shown (status line `cur:N`, the context line); only the curator agent's `drain --token` removes entries (3.7 remedy R-B1) | r2 s5: a drain per prompt drains what no one consumed (3.7 r1 B3), and 3.7's verb takes one `action` with a token for drain |
| d16 | Each mod call carries `caller.hook_event` from the shared vocabulary (24.0 R2: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`, `PreCompact`, plus the mod-only `SessionAppend` and `ModelTool`) and `caller.prompt_id` = `<session>:<n>`, `n` the mod's per-session prompt counter (`refmatrix.focus.promptSeq`, incremented at each `prompt.submit` with `update`, reset on a new session id) | r2 s7: 24.0's report groups shell and mod rows into the same prompts only if both speak one vocabulary and one prompt key |
| d17 | The subagent context route is `agent.spawn` rewriting the task with a short LABELLED brief (event map), plus the shared `prompt.context` block (computed once for the conversation); `session.append` rewrites stay out (d13 observe-only) | batch 2: both reach foreground and background subagents; the label is there because the parent loop never sees injected subagent text and treated it as unexplained (#p2) (r3) |

## Requirements {#requirements}

1. **R1 — the session context (d2-d4c, d15).** `mod/src/context.ts`: on `classic.SessionStart`
   (main loop), run the event map's first row and keep the parts in module memory (not `$.state`:
   derived, and the contract holds four keys) keyed by session, rebuilt lazily on the next read
   after a hot reload. `prompt.compose` appends the `refmatrix:memory` id after every `shared`
   section; `prompt.section` matched on exactly `{ name: "refmatrix:memory" }` answers the brief;
   `prompt.context` appends one block. Each part has a heading line naming its verb; a failed part
   is one line `[rmx] <part> unavailable: <type>: <message>`, logged (G6). Probe **P-section**: is
   `prompt.section` raised for a plugin-added section? If not, compose carries the brief's text
   itself, answering the same text until the next `classic.SessionStart`. {#r1}
2. **R2 — the prompt (d1, d2, d5, d15, d16).** `prompt.submit` (main loop; a `$.prompt.submit`
   from 24.5's bus wake is treated the same): increment `promptSeq`; observe → parallel scan /
   recall / curator status → `next({ ...e, context: [...(e.context ?? []), scanText, recallText,
   curatorLine] })`, empty parts omitted; the curator count also goes to `refmatrix.health`. Update
   `refmatrix.injected` / `refmatrix.delivered` with `update`. Budgets and sizes come from 24.5's
   `userConfig` (`scan_max_tokens`, `scan_timeout_s`, `recall_k`, `recall_scope`,
   `composite_every`); observe carries `deadline_s` 2. {#r2}
3. **R3 — the tool call (d6; widened in r6).** `tool.call` per the event map, for EVERY tool
   (Agent / Task and `mcp__*` included, which the shell matcher never records; 21.5 D6), for the
   main loop and subagents. Each observe passes `agent_id` = `e.agentId` (absent in the main
   loop) and `tool_use_id` = the event's tool-use id (null when the event carries none, which the
   ring keeps as null). `tool-pre` is awaited before `next`; the post-observe is awaited after
   `next` resolves; the hook returns `ran` UNCHANGED. `mentions` = the names of
   `refmatrix.delivered` found in `ran.text` by whole-identifier match, sent as found. A failed
   observe is an outbox entry, never a failed tool call. No command is rewritten (the grep
   rewrite stays on its shell hook; 24.8 lists its mod form as a candidate). {#r3}
4. **R4 — the observation, never a `used` event (Python; amended 2026-11-11, [[#rev-r5]],
   [[#rev-r6]]).** `rmx_focus_observe(tool, ...)` builds the tool's STM ring event with
   [[task-21.5-tool-used-signal#r1]]'s ONE builder, `stm.tool_event_fields(tool_name, tool_input,
   *, cwd, tool_use_id, agent_id, origin_known=True)`, and writes it through `Stm.record`. So the
   mod's events carry exactly the shell hook's fields: `t`, `t_start` (from the awaited
   `tool-pre`'s park), `tool`, `cwd`, `tool_use_id`, `origin` (`agent:<agentId>` when
   `agent_id` is given, else `parent`: the mod knows its loop, 21.5 D13, 19.0 R2's field), and
   the capped `input_path` / `pattern` / `command` / `prompt` / `args` (an `mcp__*` tool's
   string arguments, 21.5 D17) with `input_truncated`. **Every tool-call line takes them (r7):**
   `tool-pre`'s park stores the builder's fields, so a call the next turn sweeps as `abandoned`
   keeps its `origin`, `tool` and `tool_use_id` (21.5 D14); and a Bash git milestone's `git`
   line, which 24.2a R3's shared observe writes with its own `terse` and diffstat `refs`, takes
   every other field from the builder, so 21.5 matches it on `command`, never on the diffstat
   (21.5 R1, R3). It adds
   `result_mentions` = the `mentions` as received, RAW: no `delivered_in_session` call and no
   other read of the event files (d6). It emits NO `used` event and adds no evidence kind: 21.1
   R12's "no `used` from a hook" holds for the mod as well, and tool use of a delivered item is
   derived at report time by 21.5. {#r4}
5. **R5 — the stop and reasoning capture (d13, d14).** `session.append` matched `{ door:
   "response" }`, main loop: hold the row's text and `e.uuid`; when the next response row of the
   same turn arrives, send the held one as `reason`; return `next(e)` with `e`. At `turn.complete`
   (main loop): the held row (or, if none was held, `next(e)`'s resolved `text` with no uuid) is
   sent as `say`; then summarize / promote (`timeout=5`) and sync flush; then refresh
   `refmatrix.focus` from `rmx_focus(context, top=5)`. {#r5}
6. **R6 — the stand-down (d8-d10).** `mod/src/standdown.ts` sets and refreshes the marker per d8;
   `hooks.py` gains `MOD_GUARD(event_class)`, prefixed to every generated entry the event map moves
   and whose equivalent is probed for every loop it fires in (d9). Env form:
   `[ -n "${RMX_MOD_LIVE:-}" ] && [ $(( $(date +%s) - RMX_MOD_LIVE )) -lt 45 ] && case
   ",${RMX_MOD_EVENTS:-}," in *,<class>,*) exit 0;; esac;`. Unmoved entries carry no guard.
   `install-hooks --check` stays clean after `--apply`. {#r6}
7. **R7 — probes, before the GREEN commit, in a scratch project.** Results go to
   `eval/mod_probe/`, each with a decision row added here: {#r7}
   - **P-env — ANSWERED under `-p`: present** (batch 2 #p4), so d10's env mechanism is the one
     generated. Still open: the SessionStart entry specifically (the marker is set at the top of
     `session.start`; does the SessionStart settings hook see it?), and the same in an interactive
     session.
   - **P-print (rest):** under `claude -p --plugin-dir mod`, do `classic.SessionStart`,
     `prompt.submit`, `turn.complete`, `session.append` and `session.compact` fire? (`session.start`,
     `prompt.compose` and `tool.call` are answered yes in [[plan-24-mod-transport#probes]].)
   - **P-sub — ANSWERED** (batch 2 #p2, #p3): `turn.complete` and `turn.step` fire with
     `agentId`; `turn.start` without one.
   - **P-agent-route — ANSWERED for `agent.spawn`** (it reaches foreground and background
     subagents); `skill.prompt` UNPROBED (it never fired). d17 uses `agent.spawn`.
   - **P-section:** R1's question (open: batch 2 logged core sections only). Interactively
     `prompt.section` re-runs at every prompt (batch 2 #p8), so the answer must be the same text
     until the next `classic.SessionStart` or the cache is spent.
8. **R8 — loudness (d11).** Every generated rmx command loses `2>/dev/null` / `|| true`; the hook
   twins (`focus hook`, `scan-prompt`, `curator status`, `sync`) return exit 1 + one stderr line on
   failure and 0 otherwise (`focus hook` with no `session_id` keeps its recorded row AND exits 1);
   backgrounded commands append stderr to `hooks.stderr.log` with a timestamp and the command name.
   The generated `curator status` entries carry no `--drain` (d15; 3.7 R-B1 already removes it from
   the hooks, this task keeps it removed). {#r8}
9. **R9 — the primer stays (d4).** CLAUDE.md keeps `@.refmatrix/PRIMER.md`; the SessionStart
   background primer entry is not guarded; a test pins both. {#r9}
10. **R10 — the shared row (d16) and 24.0's after window.** The mod sends `caller.hook_event` and
    `caller.prompt_id` on every call (24.2 R9 writes them in 24.0 R2's field set). Once this
    deploys, 24.0's after window opens; the deploy sha is recorded in the implementation summary
    for the report's `--since`. {#r10}
11. **R11 — compaction (d12).** `session.compact` matched on trigger `manual` and `auto`, main
    loop: `rmx_focus(summarize, promote=True)` (synchronous, `deadline_s` 25), then
    `rmx_save_state(...)`, which is a SUBMITTED write (24.5 R3: its timeout is unbounded) sent with
    a JOB deadline of 30 s and an idempotency key (24.2 R13, d13); the hook polls `rmx_job` until
    `done`, or until the job answers `NotConfirmed` at 30 s, which becomes one transcript line
    ("pre-compact save-state not confirmed within 30s; it may still complete") while compaction
    proceeds. Then `return next(e)` with the event received; never `{ skip }`. The two moved
    PreCompact entries take the guard class `compact`. {#r11}
12. **R12 — the subagent route (d17).** `mod/src/subagent.ts`: the `agent.spawn` hook appends the
    brief and returns `next(...)`'s answer unchanged; a failure passes `next(e)` with a debug line.
    Subagent STM events (24.2a observe) carry `origin: agent:<agentId>` from `tool.call` /
   `turn.complete` (r6: one ring field, 19.0 R2's `origin`; `agent_id` is only the verb's input
   parameter). {#r12}

## Acceptance criteria {#acceptance}

1. **AC-1 (R2, d1).** `prompt.submit` test: `rmx_focus_observe(input)` resolves before scan or
   recall is requested (ordering read off the mocked `http.fetch` log); the next hook sees
   `context` with the scan and recall texts and the curator line; a scan failure leaves recall's
   text and one transcript line. RED at base. {#ac-1}
2. **AC-2 (d5).** Two prompts in one session: the second scan request carries the first's block
   shas in `skip_block_shas`; a new session id resets `injected`. {#ac-2}
3. **AC-3 (R3, R4, d6; r6).** {#ac-3}
   - **Read.** A Read whose result names a memory in `refmatrix.delivered` sends it in
     `mentions` (a name not in `refmatrix.delivered` is not sent). The Python test of R4 finds
     ONE ring event for that tool call carrying 21.5's ring fields (`t`, `t_start`, `tool`,
     `cwd`, `tool_use_id`, `origin: "parent"`, `input_path`) and `result_mentions` = the
     mentions as sent, and ZERO `used` events written to `recall-events.jsonl` by the observe.
     The observe opens neither events file (23.0's audit hook records no open of
     `recall-events.jsonl` during the call).
   - **Agent.** A main-loop Agent call reaches the ring as ONE event with `tool: "Agent"`,
     `prompt` (capped per 21.5 R1) and `origin: "parent"`; 21.5's report then credits the
     Agent `name` leg for a delivered memory named in that prompt.
   - **MCP.** An `mcp__refmatrix__rmx_context` call reaches the ring as ONE event with that
     `tool`; 21.5's report counts it under `skipped_explicit_tool_calls` and credits nothing.
     An `mcp__refmatrix__rmx_grep` call whose pattern names a delivered item reaches the ring
     with `args`, and 21.5's report credits it under `mcp_name` (r7; 21.5 D17).
   - **Git (r7).** A main-loop Bash `git commit` reaches the ring as ONE `git` line carrying
     `t_start`, `tool: "Bash"`, `cwd`, `command`, `tool_use_id` and `origin: "parent"` beside
     its diffstat `refs`.
   - **Swept (r7).** A subagent's `tool-pre` (event with `agentId: "a1"`) whose post-observe
     never arrives is swept at the next `prompt.submit` as ONE `abandoned` line carrying
     `origin: "agent:a1"`, `tool` and `tool_use_id`, and 21.5's report counts it under
     `subagent_tool_events`.
   - **Subagent.** A subagent's tool call (event with `agentId: "a1"`) is observed with
     `origin: "agent:a1"`, and 21.5's report counts it under `subagent_tool_events`.
   - The tool's result reaches the model unchanged in every case.
4. **AC-4 (R1, d3).** `classic.SessionStart` with `source: "clear"` rebuilds the context block (a
   new recall request); `prompt.compose` appends `refmatrix:memory` after the shared sections;
   `prompt.section` for core's `memory` passes through untouched. {#ac-4}
5. **AC-5 (R6, d8, d9).** The marker is set before `session.start`'s first `$.http.fetch` (op
   order), and with `health_interval_s = 600` it is still refreshed every 10 s. Rendering the hook
   block: every moved, probed entry starts with its class guard, SubagentStop's included (d9: batch 2
   showed `turn.complete` fires with `agentId`), unmoved ones do not; under `bash -c` with `RMX_MOD_LIVE=$(date +%s)` and the class listed, a guarded
   entry exits 0 without running `rmx` (a recording `rmx` on `PATH` shows no call); with the marker
   60 s old it runs. `rmx install-hooks --check` is clean after `--apply` on a fixture project.
   {#ac-5}
6. **AC-6 (R8).** No generated rmx command contains `2>/dev/null`, `|| true` or `--drain`;
   `focus hook` with an envelope lacking `session_id` exits 1 with one stderr line and the
   recorded row. {#ac-6}
7. **AC-7 (R7).** The probe files exist, and d9 / d10 and the event map's "unprobed" marks match
   their results. {#ac-7}
8. **AC-8 (R9).** CLAUDE.md still imports `@.refmatrix/PRIMER.md`; the mod registers no primer
   section. {#ac-8}
9. **AC-9 (R5, d13, d14).** A turn with three response rows: rows 1 and 2 are observed as
   `reason` (each once, with its uuid), row 3 only as `say`; a replayed observe with row 2's uuid
   records nothing new (Python, 24.2a R3). Every `session.append` hook returns the event it
   received. {#ac-9}
10. **AC-10 (d13 — r2 s2).** Content round-trips unchanged: over fixture rows of EVERY door
    (prompt, command, response, tool-result, tool-message, delivery, attachment, hook-context,
    note, compaction, notice), `next` is called with the same object; and through the engine, a
    Read of a fixture file containing secret-shaped strings followed by an Edit of an unrelated
    line leaves every other byte of the file unchanged. {#ac-10}
11. **AC-11 (R11).** A mocked `session.compact` (`auto`) issues the summarize request, then a
    save-state request with `mode: "submit"`, `deadline_s: 30` and an idempotency key, polls
    `rmx_job`, then calls `next` with an event deep-equal to its input; a job answering
    `NotConfirmed` writes the transcript line and still calls `next`; `precompute` issues neither. {#ac-11}
12. **AC-12 (R10, d16).** Requests from AC-1, AC-3, AC-9 and AC-11 carry `hook_event`
    `UserPromptSubmit`, `PreToolUse` / `PostToolUse`, `SessionAppend` / `Stop`, `PreCompact`, and
    a `prompt_id` `<session>:<n>` that increments once per `prompt.submit` and restarts at 1 after
    a simulated `/clear`. The query.log rows the daemon writes for one `prompt.submit`'s scan and
    recall calls both satisfy `telemetry.is_prompt_row` and carry the same `prompt_id`, so 21.5's
    prompt clock counts them as one prompt (21.5 R4; r6). {#ac-12}
13. **AC-13 (R12, d4, d17).** In a scratch project with `--plugin-dir mod` (as batch 2 ran), a
    foreground AND a background subagent each quote back the brief's label and its focus subject
    (the probe's code-word method); the `agent.spawn` hook's `next` result is passed on unchanged;
    `turn.complete` rows of each subagent carry its `agentId` and drive the SubagentStop sync.
    This AC is the evidence the d4 import decision waits on. {#ac-13}

## Test strategy {#test-strategy}

TS: `mod/tests/context.test.ts`, `observe.test.ts`, `standdown.test.ts`, `append.test.ts`,
`compact.test.ts` (answering `http.fetch` beneath the plugin with recorded host bodies, as 24.5;
those doubles and `mock.clock` are registered in `workflow/test_mock_registry.md`). Python:
`tests/test_task24_6_hooks_standdown.py` (AC-5, AC-6, AC-8 over `hooks.py` / `search_hooks.py`
renders, plus `bash -c` runs of the guard), `tests/test_task24_6_observe_ring.py` (R4: the ring event, no `used`). AC-10's
engine half runs in a scratch project with `--plugin-dir`. The existing hook suites
(`test_hooks.py`, `test_hook_wiring.py`, `test_hooks_reproducible.py`, `test_repo_hooks_in_sync.py`,
`test_search_hooks.py`) are updated for the guard and loudness, never skipped. Re-applying the live
hooks follows [[feedback_install_hooks_no_claude_reaps]]: back up `settings.json`, `--apply`, diff.
RED first, logged to `workflow/review-output/task24_6-red.log`. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `mod/src/context.ts`, `mod/src/observe.ts`, `mod/src/standdown.ts`, `mod/src/append.ts`, `mod/src/compact.ts`, `mod/src/subagent.ts`, `mod/src/index.ts` | R1-R3, R5, R6, R11, R12 |
| `mod/tests/context.test.ts`, `observe.test.ts`, `standdown.test.ts`, `append.test.ts`, `compact.test.ts` | AC-1..AC-5, AC-9..AC-12 |
| `src/refmatrix/hooks.py` | `MOD_GUARD`, guarded entries, loudness, no `--drain` (R6, R8) |
| `src/refmatrix/cli.py` | hook twins' exit codes (R8) |
| `src/refmatrix/verbs.py`, `src/refmatrix/stm.py` | `rmx_focus_observe` calls 21.5's `stm.tool_event_fields` (`origin_known=True`); `mentions` → the ring event's raw `result_mentions`; no `delivered_in_session` call; no `used` (R4) |
| `.claude/settings.json` | regenerated by `rmx install-hooks --apply` (never hand-edited) |
| `tests/test_task24_6_hooks_standdown.py`, `tests/test_task24_6_observe_ring.py`, the existing hook suites | AC-5, AC-6, AC-8, R4 |
| `workflow/test_mock_registry.md` | the TS host doubles |
| `eval/mod_probe/` | R7 |

## Revision r2 (2026-10-20, ch-bsd r2 03c2d1f) {#rev-r2}

| finding | change |
|---|---|
| b1 the marker died at `/clear` | d8: the marker's own timer survives reason `clear` (24.5 d1); 24.5 AC-12 checks it |
| s1(a) marker set late | d8: set synchronously at the top of `session.start`; AC-5 checks the op order; P-env checks the SessionStart entry, d10 says what happens if it cannot see it |
| s1(b) 45 s window vs a configurable tick | d8: own 10 s timer, independent of `health_interval_s`; AC-5 |
| s1(c) per-context class lists in a process-wide env | d9: one list; guard only entries whose mod equivalent is probed in every loop they fire in |
| s2 the scrub altered what the model reads | removed (d13 observe-only); AC-10 round-trip; listed in 24.8's candidates |
| s3 final answer recorded as reason and say | d14 defer-by-one + `row_uuid` dedupe; AC-9 |
| s4 subagents would lose the primer | d4 keeps the import, no primer section; R9 / AC-8; subagent rows marked unprobed; P-agent-route |
| s5 curator drain | d15 status-only, count surfaced; R8 no `--drain` |
| s7 rows did not join | d16 shared `hook_event` vocabulary and `prompt_id`; R10; AC-12 |
| s9 scope creep | `rmx_shell_rewrite` / `rmx_grep_teach` wiring and the `tool.check` policy port removed; the grep and enforce hooks stay on shell; both listed in 24.8's candidates |
| m3 TS doubles unregistered | test strategy + files |

## Revision r3 (2026-10-20, probe batch 2) {#rev-r3}

| finding | change |
|---|---|
| `agent.spawn` rewrite and `prompt.context` reach subagents; `prompt.section` / `prompt.compose` do not | d17 / R12: the subagent route; event map rows; AC-13 proves it, and d4's import stays until it does |
| `turn.start` has no `agentId`; `turn.step` / `turn.complete` do | event map: attribute subagent turns by `turn.step` / `turn.complete`; SubagentStop now guarded (d9) |
| `skill.prompt` never fired | event map and R7: unprobed |
| `$.env.set` reaches settings hooks under `-p` | R7 P-env answered for `-p`; d10's env mechanism generated; SessionStart and interactive still open |
| `prompt.section` re-runs every prompt interactively | R7 P-section: the answer must stay the same text between `classic.SessionStart`s |

## Revision r4 (2026-10-20, ch-bsd r3 6d3575b) {#rev-r4}

| finding | change |
|---|---|
| s1 how R11's 30 s applies to a submitted save-state | R11: a write job with a 30 s job deadline and a key; `NotConfirmed` at expiry is a transcript line and compaction proceeds; AC-11 |
| s7 AC-5 still said SubagentStop is unguarded | AC-5 aligned with d9: SubagentStop's entry carries the guard |

## Revision r5 (2026-11-11, user decision on 21.5 OD-1) {#rev-r5}

rel: depends-on -> [[task-21.5-tool-used-signal]]
rel: amends -> [[task-21.1-context-usage-telemetry#req-schema]]

The user approved the recommendation of [[task-21.5-tool-used-signal]]'s open decision OD-1
(2026-11-11): the mod's `tool.call` observe must not emit `used`. Emitting it from result text
would be a second tool-evidence kind, would credit mere re-exposure (a name appearing in output the
agent did not act on), and would put an unmeasured matcher into plan-19 19.2's never-decaying
counters; 21.5 instead derives tool use at report time from the STM ring.

| change | anchor |
|---|---|
| d6: `mentions` are recorded on the ring event as `result_mentions`; no `used` | [[#decisions]] |
| R4: the observe writes 21.5's ring fields + `result_mentions` through `Stm.record`; no `used`, no new evidence kind | [[#r4]] |
| AC-3: one ring event with `result_mentions`, zero `used` events | [[#ac-3]] |
| test + files: `tests/test_task24_6_observe_ring.py`; `verbs.py` / `stm.py` | [[#test-strategy]], [[#files]] |

## Revision r6 (2026-11-11, 21.5 spec r1's addendum vs r5) {#rev-r6}

rel: derives-from -> [[bsd-task-21.5-spec-r1-15e8f64#addendum-246]]
rel: depends-on -> [[task-21.5-tool-used-signal#r1]]
rel: related-to -> [[task-19.0-stm-cluster-hygiene#requirements]]

ch-bsd's review of 21.5 r1 audited r5's interface with 21.5 and found three SKETCHY items and one
MEH (x-1..x-4), plus the condition under which 21.5 keeps its Agent and MCP legs. The decisions
below were made by the lead as the user would; 21.5 rev 2 records the same decisions on its side
([[task-21.5-tool-used-signal#rev-2]]).

| item | change | anchor |
|---|---|---|
| x-1 two shapes of the tool's input | R4 builds the ring event with 21.5 R1's ONE builder, `stm.tool_event_fields`, so the mod and the shell hook write the same fields (structured `input_path` / `pattern` / `command` / `prompt`, capped, `input_truncated`) | [[#r4]], [[#files]] |
| x-2 subagent identity spelled three ways | one ring field, `origin` (19.0 R2's name): `agent:<agentId>` or `parent`; `agent_id` stays only the verb's input parameter; `tool_use_id` passed and stored | [[#r3]], [[#r4]], [[#r12]] |
| x-3 observe-time delivered check | `result_mentions` recorded RAW, pre-filtered only by `$.state`'s `refmatrix.delivered`; no `delivered_in_session` call at observe time; 21.5 checks at report time | [[#decisions]] d6, [[#r4]] |
| x-4 `result_mentions` absent from 21.5 | 21.5 reserves the field, its matcher ignores it, its report counts `result_mentions_present` | [[#decisions]] d6 |
| on b-3: Agent / mcp legs need a producer | `tool.call` observes EVERY tool (the event map's row and R3); AC-3 adds an Agent call and an `mcp__refmatrix__` call that reach the ring, and a subagent call with `origin` | [[#event-map]], [[#r3]], [[#ac-3]] |
| 21.5 rev 2 D9: the prompt clock | AC-12: one `prompt.submit`'s scan and recall rows satisfy `telemetry.is_prompt_row` and share `prompt_id` | [[#ac-12]] |

Cost of observing every tool: one more `tool-pre` / `tool` observe pair per Agent and MCP call,
each an append through the daemon; the tool's result is unchanged and a failed observe is an
outbox entry, never a failed call (R3).
{#rev-r6-cost}

## Revision r7 (2026-11-13, 21.5 spec rev 3) {#rev-r7}

rel: derives-from -> [[bsd-task-21.5-spec-r2-540ab50]]
rel: depends-on -> [[task-21.5-tool-used-signal#r1]]
rel: related-to -> [[task-19.0-stm-cluster-hygiene#requirements]]

ch-bsd's r2 review of 21.5 rev 2 found two gaps in the ring fields this task's observe writes
through 21.5's ONE builder, and one in the MCP leg. 21.5 rev 3 closes them on its side
([[task-21.5-tool-used-signal#rev-3]]); r7 makes the mod's path match. The decisions were made
by the lead as the user would.

| item | change | anchor |
|---|---|---|
| 21.5 r2 s-1: `git` lines carry no builder fields and match on a diffstat | the git-milestone line takes the builder's fields (its own `terse` and diffstat `refs` kept); 21.5 matches it on `command` only | [[#r4]], [[#ac-3]] |
| 21.5 r2 m-3: a swept call loses its fields | `tool-pre`'s park stores the builder's fields; the swept `abandoned` line carries them, `origin` included | [[#r4]], [[#ac-3]] |
| 21.5 r2 m-5: every `mcp__refmatrix__` tool skipped | the builder records an `mcp__*` tool's string arguments as `args`; 21.5 skips only R12's three and matches the others under `mcp_name` | [[#r4]], [[#ac-3]] |

No change to the event map, the decisions table, or what the mod emits: still no `used`, no
delivered-set read at observe time (d6).
{#rev-r7-note}
