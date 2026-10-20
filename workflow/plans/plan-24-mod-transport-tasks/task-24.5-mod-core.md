---
gmd: "0.1"
id: task-24.5-mod-core
title: "Task 24.5: the mod core — a session.start handshake (discovery, identity, version and per-verb schema check), the store's tools registered in the engine, absent spawns the project's rmx while busy never does, a status line, toasts, a pane and a bus wake, with every failure said"
tags: [task, plan-24, mod, session, handshake, status-line, outbox, state, bus]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.5: the mod core {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20; `$.state` / `$.store` roles folded in from the user's
> question of 2026-10-20, "how do we leverage the $.state and $.store facilities in rmx memory";
> G5's pane and bus wake homed here per ch-bsd s5).
> Depends on: [[task-24.4-generated-mod-surface]] (tools, client, errors, the twin),
> [[task-24.3-hub-http-discovery]] (discovery, bus wait), [[task-24.2-daemon-verb-host-http]]
> (the per-store socket, `rmx verb run`, idempotency), [[task-24.1-store-runtime-identity]].
> Feeds: 24.6 (events and state build on this core), 24.7 (packaging), 24.8 (MCP retirement).

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-24.4-generated-mod-surface]]
rel: depends-on -> [[task-24.3-hub-http-discovery]]
rel: depends-on -> [[task-24.2-daemon-verb-host-http]]
rel: depends-on -> [[task-24.1-store-runtime-identity]]
rel: implements -> [[plan-24-mod-transport#goals]]
rel: implements -> [[exploration-claude-code-mod-transport#verb-host-absent]]
rel: implements -> [[exploration-claude-code-mod-transport#distribution]]
rel: derives-from -> [[bsd-plan24-spec-review-cdcfbc3#s5]]
rel: related-to -> [[feedback_mcp_server_reload_and_orphans]]
rel: related-to -> [[project_hub_version_handshake]]
rel: implements -> [[exploration-claude-code-mod-transport#facilities]]

## Why {#why}

G1 (real session identity), G4 (tools in the engine), G5 (live surfaces) and G6 (failures
visible) all start at one place: the moment a session starts, the mod must learn which store owns
the session's directory, what that store runs, whether its verbs match the mod's, and then serve
the model's tool calls and show the store's health — without a Python process per call, without
guessing the session, and without ever spawning over a busy daemon. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | The session id is `await $.session.id()` (the transcript's name), read per call, never cached past a `session.end`; on `session.end` reason `clear` the timers, the bus loop and 24.6's stand-down marker KEEP RUNNING and re-key to the new id; they stop only for the other reasons (exit, logout, resume, signal, the end of a `-p` run) | G1; `/clear` ends the session with no new `session.start` (types: SessionEndInput, session.start), so a cached id would name the dead session, and timers stopped there would never restart for the rest of the process (r2 b1) |
| d2 | Discovery: hub `rmx_discover(cwd)` first; hub down → walk `$.session.root()`'s ancestors with `$.fs.stat` for `.refmatrix/identity.json` (24.3 d10's rule, parity-tested by `discovery_cases.ts`) and `$.fs.read` it | D5's hub-down source; the only discovery logic in TS is that walk |
| d3 | Per verb: register when `VERB_HASHES[name] == identity.verb_hashes[name]`; otherwise skip it and say so (toast + status `schema: N skipped`); a version difference with equal hashes registers and shows `vX≠vY` | D5: never serve a mismatched schema silently; equal schemas across versions are safe |
| d4 | A tool result is a STRING: `{ result: JSON.stringify(dict) }`, the text the `refmatrix` MCP server returns today; a verb error is `{ isError: true, result: "<type>: <message>" }` | the engine validates a hook's answer against the tool's output shape and refused an object ("expected string, received object", [[plan-24-mod-transport#probes]], r2 b2); `deny` means a refusal and is logged as one |
| d5 | Absent (24.4's twin says `TransportAbsent` on THIS store's socket) → `$.process.run([identity.rmx_bin, "verb", "run", name, "--session", s, "--json"], { stdin, cwd: project_root, timeoutMs })`; busy / undialable → the typed error, never a spawn; `rmx_bin` null → an error naming `identity.json` | D4; the spawned CLI re-classifies the daemon itself (24.2 R11), so the mod never decides "absent" alone and never opens a store |
| d6 | `$.state` contract `refmatrix.{focus, health, injected, delivered}` in `mod/types/index.d.ts`; this task owns `focus` and `health` (24.6 owns `injected`, `delivered`) | render subscription redraws the status line and pane on `set`, no `invalidate`; survives a hot reload |
| d7 | NEITHER `$.state` NOR `$.store` is a system of record for memory or STM: the daemon's store and the GMD memory files stay authoritative | a crash or a worker loss drops `$.state`; the CLI, subagents, the shell fallback and save-state all read the ring from the store |
| d8 | `$.store` keys: `discovery:<cwd>` (a CACHE of discovery: socket, identity hash, version, last-seen; invalidated on any mismatch with the live answer), `settings`, `outbox` | cross-session, per plugin, JSON, 4 MiB total: fit for a cache and a small queue, not for data |
| d9 | The outbox holds ENGINE-surface writes only (24.6's observe events, focus records) that failed twice (absent AND the spawn failed); model tool writes return the error to the model instead | the model must know a write did not land; queuing it silently would change the tool's meaning |
| d10 | Outbox entries carry an idempotency key (`sha256(verb, args, session, first-attempt ts)`), replay FIFO at `session.start` and on the health tick that sees the daemon up, stop at the first busy; cap 1 MiB of JSON or 2,000 entries | 24.2 R8 makes replay exactly-once; the cap leaves the 4 MiB store room for the cache; FIFO keeps an STM ring's order |
| d11 | Outbox overflow drops the OLDEST entry and raises a toast, a transcript line and a status count every time; nothing is dropped silently | "decay may demote, never lose" cannot hold for a client queue with a hard cap, so the loss is made loud instead |
| d12 | Pane and bus wake live here (ch-bsd s5): `/rmx` opens the pane; a long-poll loop on `rmx_bus_wait` turns a wake message into `$.prompt.submit` | G5 had no home; both are core surfaces, not context injection |
| d13 | Collision with a `refmatrix` MCP server: every `$.tool.register` is wrapped in `try`, so its throw ("the session already has an MCP server named …") never skips the rest of `session.start`; a collision registers nothing further and says so once; every `mcp__refmatrix__*` `tool.call` handler calls `next(e)` for a tool the mod did not register in THIS session, so the MCP server keeps serving its own tools | batch 2 #p7: the register throws and skips the hook, and a plugin's `tool.call` hook intercepts `mcp__<name>__*` calls even for tools it never registered; 24.8 removes the server (r3) |
| d16 | Every mod verb call carries `deadline_s ≤ 25`. A (verb, action) whose effective default timeout is over 25 s, or unbounded, runs SUBMIT-THEN-POLL through 24.2 R13 (`mode: "submit"` → a job id; `rmx_job(job_id, wait_s ≤ 20)` until done), each fetch under 25 s; the rule is computed by `modgen` into `ROUTES[name].modes` per action from the verb's defaults and `ACTION_DEFAULTS`, so a new long action cannot be served synchronously by accident | the engine aborts every `$.http.fetch` at 30 s (batch 2 #p5); a synchronous 60-180 s verb would always fail (r3) |
| d17 | After `/clear` (no `session.start`, `$.state` wiped, timers alive: batch 2 #p8) the mod detects the new session by a `$.session.id()` change on the next tick or hook and RE-SEEDS `refmatrix.focus` / `refmatrix.health` from the store (`rmx_store_identity`, `rmx_focus(context)`) | the state is a projection; the store holds the truth, so re-seeding loses nothing (r3) |
| d14 | Tunables are `userConfig` fields in `plugin.json` (rows in `/config`, read as `register`'s `options`; a change reloads the module with new options); no env-var-only knobs on the mod path | the engine's own settings surface, stored per plugin under `pluginConfigs`; a picker for enumerations |

## Requirements {#requirements}

1. **R1 — module shape.** `mod/src/index.ts` exports `register: Register`; hooks: `session.start`
   (handshake), `session.end` (reason `clear`: re-key timers, `health`, the bus loop and 24.6's
   marker to the new `$.session.id()` and reset per-session state; any other reason: stop timers,
   clear `health`), `tool.call` with one matcher per
   registered tool (`{ tool: "mcp__refmatrix__<name>" }`), `ui.render` for the pane, `command.run`
   for `/rmx`. Every hook body runs in a `try` whose `catch` writes `$.ui.log(<plugin>: <event>:
   <type>: <message>)` (transcript and debug log, G6) and then continues the chain (`next(e)`)
   where the event allows; a guard-free observer never blocks the user's work. {#r1}
2. **R2 — the handshake, awaited in `session.start`.** (0) FIRST, synchronously, before any
   await: 24.6's stand-down marker is set and its own timer started (24.6 d8); (a) `$.session.root()`; (b) discovery per
   d2 (hub socket `$.env.get("RMX_HOME")` else `$.env.get("HOME")` + `/.refmatrix/hub-http.sock`);
   (c) identity from the answer or the file; (d) compare per d3; (e) `await $.tool.register` for
   each passing model tool (`isDeferred` from `TOOLS`) BEFORE `next(e)` resolves, so they are
   listed by turn one; (f) write `health`; (g) start the health tick and the bus loop
   (`$.clock.every` / `$.clock.after`, which outlive the dispatch); (h) replay the outbox. No
   store for the root → no tools, status `rmx: no store here`, nothing else. Each failed step is a
   line naming the step. {#r2}
3. **R3 — routing a tool call.** `ROUTES[name].tier` picks the target: `store` → the store's
   `http_socket`; `hub` → the hub socket; `both` → the hub when the call's `scope` is `global`, else
   the store. A `project` / `root` argument naming another store re-runs discovery for it (cached
   per d8) and targets that store's socket. `session` is always `await $.session.id()`; `caller`
   carries `agent_id` from `e.agentId` (a subagent's call). `deadlineS` = min(the verb's `timeout`
   argument or default, 25); no client race (24.4 d7). Per d16, the modes at spec time (3.7's
   defaults; `modgen` recomputes them): {#r3}

   | verb / action | default timeout | mode |
   |---|---|---|
   | `rmx_graph` recall, dense | 180 s | submit-then-poll |
   | `rmx_graph` timeline | 60 s | submit-then-poll |
   | `rmx_session` list | 60 s | submit-then-poll |
   | `rmx_canon` link | 60 s | submit-then-poll |
   | `rmx_curate` forget (preview, purge) | 600 s (3.7 R-RM5) | submit-then-poll |
   | `rmx_memory` write actions (promote, dedup, bulk_forget, score, link, …) | 120 s | submit-then-poll |
   | `rmx_save_state` | unbounded | submit-then-poll |
   | `rmx_context` | 60 s op bound, rerank budgeted inside | sync at 25 s (an unreranked answer comes back with its warning before then) |
   | `rmx_query`, `rmx_memory_recall` | 30 s | sync at 25 s (recall's legs scale by `_left`, degraded legs are warnings) |
   | `rmx_ingest` | returns a job id already | sync; `rmx_ingest_status` polls |
   | every other verb / action (≤ 25 s, bus, where / search / locate, focus, notes, discovery, identity) | ≤ 25 s | sync |

   The D4 spawn path (`rmx verb run`) is not a fetch: it runs the verb synchronously with
   `timeoutMs` = the verb's own timeout (≤ 10 min, `$.process.run`'s cap).
4. **R4 — absent, busy, undialable (d5).** As d5; a spawn's nonzero exit maps 2 → args, 3 →
   busy, 4 → absent dependency, 5 → error, other → `HostError` with stderr's first line. The
   spawn's own `cli.log` row carries 24.0's spawn split (interp / reexec / import), so 24.0's after
   window counts it. A spawn timeout is busy. {#r4}
5. **R5 — `$.state` (d6, d7).** `refmatrix.focus = { session, subject, top: string[], updated }`
   (written from `rmx_focus` after each turn by 24.6 and at the handshake here);
   `refmatrix.health = { store, state, pid, version, modVersion, skew, schemaSkipped: string[],
   queueDepth, outbox, lastFastExit, crashes5m, hub: "up" | "down", httpError }`. Writes use
   `update($, ref, fn)` (`ifVersion`, retried on a miss). Declared in `mod/types/index.d.ts`,
   named in `plugin.json` `"types"`. {#r5}
6. **R6 — the health tick (every `health_interval_s`, default 15 s).** `rmx_store_identity` on the store socket (or the file
   when the socket is absent), `rmx_queues` on the hub; derives: pid change without `stopped_at` →
   fast-exit toast; ≥ 3 pid changes in 5 min → crash-loop toast; version or schema skew → toast
   once per change; `http_error` (24.2 R4) → toast once with the path and length; hub down →
   status `hub↓`. {#r6}
7. **R7 — the status line.** One `$.ui.status` line from `health` + `focus`: `rmx <store> ●up |
   v0.81.0 | focus: <subject> | q:<depth>` plus, only when present, `vX≠vY`, `schema: N skipped`,
   `outbox:N`, `hub↓`, `http: <error>`. Busy shows `◐busy`, absent `○absent`. {#r7}
8. **R8 — the outbox (d9-d11).** `mod/src/outbox.ts`: `enqueue`, `replay`, `count`; stored under
   `$.store` `outbox` as a list; size checked as JSON length before each `set`; overflow per d11;
   replay sends `idempotencyKey` (24.2 R8). {#r8}
9. **R9 — the pane (d12).** `$.command.register({ name: "rmx", description })` at the handshake;
   `/rmx` → `$.ui.open({ id: "refmatrix", title: "refmatrix" })`; the `ui.render` hook for that
   pane draws, from `$.state` reads (subscribed): focus (subject, top symbols), the latest
   recall-state summary (`rmx_recall_state`, fetched on open and on each `turn.complete`), bus
   unread per channel (`rmx_bus_stats`), and `health`. {#r9}
10. **R10 — the bus wake (d12, 24.3 d9).** A loop started at the handshake: `rmx_bus_wait({
    channels: ["proj:<store_name>:*"], agent: <session id> })`; a `wake` message → `$.prompt.submit({
    text: "[rmx bus] <from> on <channel>: <body, first 2,000 chars>" })` at most once per 60 s
    (later wakes in the window are coalesced into one prompt listing them); a non-wake → toast and
    the pane's unread count; after acting, `rmx_bus_mark_read` up to the last handled id (24.3 R6:
    the wait never advances the cursor, so an unhandled message comes back). 503 → back off 5 s; hub down → back off 30 s; each loop error is a
    debug-log line. Stopped at `session.end` except reason `clear` (d1), where it re-subscribes with
    the new session id as `agent`. {#r10}
11. **R11 — collision (d13).** Each `$.tool.register` is in `try`; the first throw naming an MCP
    server stops further registration, sets status `rmx: MCP server "refmatrix" still configured
    (24.8)` and writes one transcript line, and `session.start` CONTINUES (health, bus, outbox,
    marker). The `tool.call` handlers (registered for every generated tool name at load) check the
    session's registered set and call `next(e)` for any name not in it. {#r11}
12. **R12 — probes, before the GREEN commit, in a scratch project.** Each result is written to
    `eval/mod_probe/<probe>.json` with `$.session.version()`, and a decision row is added to this
    spec from it: {#r12}
    - **P-sub-state — ANSWERED: shared** ([[plan-24-mod-transport#probes-batch2]]): a subagent,
      foreground or background, reads the parent's `$.state` and the same `$.session.id()`.
    - **P-sub-tools — ANSWERED yes** ([[plan-24-mod-transport#probes]], `-p`): a subagent is
      offered a registered tool, calls it, and the mod serves it; `tool.call` sees subagent calls
      with `agentId`.
    - **P-interactive — ANSWERED** (batch 2 #p8): `/clear` raises `session.end` reason `clear`, no
      `session.start`, a new id, timers survive, `$.state` wiped (d1, d17). Still open: subagent
      tool service in an interactive session (the batch-2 subagent runs were `-p`).
    - **P-print — ANSWERED for `session.start`, `prompt.compose`, `tool.call`**. Remaining: where
      `$.ui.status` / `$.ui.toast` / `$.ui.log` go under `-p` (the reference says `ui_log`
      messages and stderr).
    - **P-collision — ANSWERED** (batch 2 #p7): `$.tool.register` throws and skips the rest of the
      hook; the plugin's `tool.call` hook intercepts `mcp__<name>__*` (d13, R11).
    - **P-socket (open):** a 124-byte path fails `ENAMETOOLONG`; exactly 101 and 104 bytes are
      untested (24.4 R5). The mod's largest accepted `socketPath` against 24.2's
      `http_socket_bytes`; a store above it shows `http: path too long for the mod` and is served
      by the spawn path.
13. **R13 — tests (`claude plugin test mod`).** `mod/tests/*.test.ts` drive the hooks with the
    engine's `$` and answer the `$` ops beneath the plugin (`http.fetch`, `process.run`,
    `store.*`, `env.get` are op events) with recorded host bodies; `mock.clock` advances the tick.
    {#r13}
14. **R14 — `userConfig` (d14).** Fields (each with a default equal to today's generated hook
    argument): `scan_max_tokens` 2000, `scan_timeout_s` 5, `recall_k` 5, `recall_scope`
    (picker: project / global / both, default both), `composite_every` 3, `health_interval_s` 15,
    `status_line` (picker: full / compact / off), `bus_wake` (picker: on / off), `outbox_max_entries`
    2000. 24.6 reads the scan / recall / composite fields; this task the rest. Validated by
    `claude plugin validate`; a test runs `test(name, { options }, body)` with a non-default value
    and sees it used. {#r14}
15. **R15 — timers.** The health tick and the bus loop run on `$.clock.every` /
    `$.clock.after` started in `session.start` (they outlive the dispatch, are cancelled on reload
    and at `session.end` except reason `clear`, d1, where batch 2 shows they survive); the bus loop
    re-arms with `$.clock.after(0)` after each long-poll returns, never with `$.clock.sleep` inside a hook (a sleep spends the hook budget). {#r15}
16. **R16 — re-seed after `/clear` (d17).** Every hook and the tick compare `$.session.id()` with
    the last seen id; on a change: reset per-session module state, re-seed `refmatrix.focus` and
    `refmatrix.health` from the store, restart the per-session prompt counter (24.6 d16), and
    re-key the bus loop and outbox (d1). {#r16}

## Acceptance criteria {#acceptance}

1. **AC-1 (R2, d3).** Handshake test: a discovery answer whose `verb_hashes` differ for one model
   verb registers every other tool, not that one, toasts once, and the status line shows
   `schema: 1 skipped`; equal hashes and a different version register all and show `vX≠vY`.
   `$.tool.register` calls all resolve before `session.start`'s `next(e)`. {#ac-1}
2. **AC-2 (d2).** Hub fetch rejected (absent) → the walk over a mocked `fs` finds
   `a/.refmatrix/identity.json` from `a/b/c` and not `~/.refmatrix`; the
   `discovery_cases.ts` table passes. {#ac-2}
3. **AC-3 (R3, d1).** A tool call made after a mocked `/clear` (`session.end` reason `clear`, then
   a new `$.session.id()` value) sends the NEW session; a subagent call carries `agent_id`. {#ac-3}
4. **AC-4 (R4, d5).** Fetch rejections from the probe table: missing → one `process.run` with the
   identity's `rmx_bin` and `["verb", "run", name, "--session", ...]`; refused / reset / timeout →
   `TransportBusy`, ZERO `process.run`; too-long → undialable, zero spawns; `rmx_bin: null` → an
   error result naming `identity.json`. {#ac-4}
5. **AC-5 (R6, R7).** Over a mocked clock: pid 10 → 11 with no `stopped_at` raises the fast-exit
   toast; three changes in 5 min raise crash-loop; the status line text matches R7 for up / busy /
   absent / skew / hub down. {#ac-5}
6. **AC-6 (R8, d9-d11).** An engine write that fails absent + spawn-failed is enqueued with a key;
   the next tick with the daemon up replays it once with that key; a model tool write in the same
   state returns an error result and enqueues nothing; filling past 2,000 entries drops the oldest
   with a toast and a transcript line each time; the status shows `outbox:N`. {#ac-6}
7. **AC-7 (R9, R10).** `/rmx` opens the pane and it draws focus / bus unread from `$.state`; a
   `wake` message from a mocked `rmx_bus_wait` causes exactly one `$.prompt.submit` and a second
   within 60 s none (coalesced into the next); a non-wake causes a toast and no submit. {#ac-7}
8. **AC-8 (R11, d13).** With an `.mcp.json` server named `refmatrix` present (a scratch project
   whose stdio server serves `rmx_context` and `only_mcp`): `$.tool.register` throws, the rest of
   `session.start` still runs (the status line is set, the health tick fires), the status names the
   collision, and calls to `mcp__refmatrix__rmx_context` and `mcp__refmatrix__only_mcp` both reach
   the MCP server (its log shows both `tools/call`s), i.e. the mod's handlers passed them on. The
   same assertions run under `claude plugin test` with the register op answered by the probe's
   exact throw. {#ac-8}
9. **AC-9 (R12).** The open probes of R12 (interactive subagent service, P-print's UI half,
   P-socket) have files under `eval/mod_probe/`, and each probe, answered or open, has
   its decision row in this spec. {#ac-9}
10. **AC-10 (R1).** A hook forced to throw (a mocked `http.fetch` that throws a non-Error) leaves a
    transcript line naming the event, and the tool call still answers with an error result. {#ac-10}
11. **AC-11 (R14, R15).** With `options.health_interval_s = 5`, the mocked clock shows a tick
    every 5 s; `bus_wake: "off"` makes a `wake` message toast instead of submitting; after
    `session.end` reason `exit` no timer fires. {#ac-11}
12. **AC-12 (R1, R10, d1 — r2 b1).** Simulated `/clear`: `session.end` reason `clear`, then
    `$.session.id()` answers a new id. The mocked clock still fires the health tick, the next
    `rmx_store_identity` and `rmx_bus_wait` requests carry the NEW session / agent, 24.6's
    `RMX_MOD_LIVE` was set within the last 15 s, and the outbox and `$.state` `health` / `focus`
    are keyed to the new id. Because `/clear` WIPES `$.state` (batch 2 #p8), the simulation also
    resets every `refmatrix.*` value to version 0; after the next tick they are re-seeded from the
    store (R16). {#ac-12}
13. **AC-13 (d4 — r2 b2).** Through `$.tool.call({ tool: "mcp__refmatrix__rmx_context", ref:
    "x" })` under `claude plugin test`, with `http.fetch` answered by a recorded 24.2 body holding a
    real verb dict: the call resolves with `text` equal to `JSON.stringify(dict)` and no engine
    refusal; with a recorded 422 body it resolves `isError: true` with `"VerbError: …"`. If the
    engine refuses a hook's `isError` answer, the test records it and d4 falls back to the string
    `"error: <type>: <message>"` with a revision row. {#ac-13}
14. **AC-14 (R3, d16).** Every request the tests record carries `deadline_s ≤ 25`; a
    `rmx_graph(action="recall")` tool call sends `mode: "submit"`, then polls `rmx_job` until a
    `done` answer and returns its result as the tool's string; a mocked fetch rejected with the
    probe's `aborted: no complete answer within 30000ms` is reported busy (write: "not confirmed").
    `modgen`'s computed modes equal R3's table for 3.7's registry. {#ac-14}

## Test strategy {#test-strategy}

TypeScript tests under `mod/tests/` (`handshake.test.ts`, `routing.test.ts`, `health.test.ts`,
`outbox.test.ts`, `pane_bus.test.ts`, `config.test.ts`, `clear.test.ts`, `result_shape.test.ts`), run by `claude plugin test mod` from
`tests/test_task24_4_mod_gates.py` (24.4 R7), logs captured. Host bodies come from recorded 24.2 /
24.3 responses committed under `mod/tests/fixtures/` (produced by the Python suites, not written by
hand). The op answers beneath the plugin and `mock.clock` are doubles of the host and are registered
in `workflow/test_mock_registry.md` (r2 m3). Probes (R12) run in a scratch project with `--plugin-dir`, never against this repo's live
store or settings. RED first: each test file committed failing against a `register` that does
nothing, logged to `workflow/review-output/task24_5-red.log`. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `mod/src/index.ts` | `register`, hook wiring (R1) |
| `mod/src/handshake.ts`, `mod/src/discovery.ts`, `mod/src/route.ts` | R2, R3, R4, R11 |
| `mod/src/health.ts`, `mod/src/status.ts`, `mod/src/pane.tsx`, `mod/src/bus.ts` | R6, R7, R9, R10 |
| `mod/src/outbox.ts` | R8 |
| `mod/types/index.d.ts`, `mod/.claude-plugin/plugin.json` | the `PluginState` contract, `"types"`, `version` (R5), `userConfig` (R14) |
| `mod/tests/*.test.ts`, `mod/tests/fixtures/` | AC-1..AC-13 |
| `workflow/test_mock_registry.md` | the TS op answers beneath the plugin (`http.fetch`, `process.run`, `store.*`, `env.get`) and `mock.clock`, each classified (r2 m3) |
| `eval/mod_probe/` | R12's records |

## Revision r2 (2026-10-20, ch-bsd r2 03c2d1f) {#rev-r2}

| finding | change |
|---|---|
| b1 `/clear` killed the timers and the marker | d1, R1, R10, R15: timers, bus loop and marker survive reason `clear` and re-key; AC-11 now uses reason `exit`; new AC-12 through a simulated clear |
| b2 tool results were objects the engine rejects | d4: `JSON.stringify` string result, `isError` errors; new AC-13 through `$.tool.call` |
| s9 SendMessage→bus mirroring served no goal | d15, R16, AC-12 (old), P-send removed; listed in 24.8's candidates |
| s2 secret scrub (24.6) | `scrub_secrets` removed from R14 |
| m3 TS doubles unregistered | test strategy + files: registered in `workflow/test_mock_registry.md` |
| m4 probe evidence moved | R12: P-sub-tools and P-print answered from [[plan-24-mod-transport#probes]] (`-p`); P-interactive added for interactive parity |

## Revision r3 (2026-10-20, probe batch 2) {#rev-r3}

| finding | change |
|---|---|
| the engine aborts every fetch at 30 s | d16 / R3: `deadline_s ≤ 25`, per-verb mode table, submit-then-poll via 24.2 R13; AC-14 |
| a same-named MCP server makes `$.tool.register` throw and skip `session.start`; the plugin's `tool.call` hook intercepts its tools | d13 / R11: register in `try`, handlers pass `next(e)` for unregistered tools; AC-8 with a real `.mcp.json` server |
| `/clear` wipes `$.state`, fires no `session.start`, changes the id | d17 / R16: re-seed on an id change; AC-12 wipes state in the simulation |
| `$.state` / `$.session.id()` shared with subagents; interactive `/clear` parity | R12: P-sub-state and P-interactive answered ([[plan-24-mod-transport#probes-batch2]]) |

