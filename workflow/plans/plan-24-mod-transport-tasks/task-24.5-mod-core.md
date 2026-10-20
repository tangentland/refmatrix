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
| d1 | The session id is `await $.session.id()` (the transcript's name), read per call, never cached past a `session.end` | G1; `/clear` ends the session (`session.end` reason `clear`) with no new `session.start`, so a cached id would name the dead session — the frozen `CLAUDE_CODE_SESSION_ID` defect, in TypeScript |
| d2 | Discovery: hub `rmx_discover(cwd)` first; hub down → walk `$.session.root()`'s ancestors with `$.fs.stat` for `.refmatrix/identity.json` (24.3 d10's rule, parity-tested by `discovery_cases.ts`) and `$.fs.read` it | D5's hub-down source; the only discovery logic in TS is that walk |
| d3 | Per verb: register when `VERB_HASHES[name] == identity.verb_hashes[name]`; otherwise skip it and say so (toast + status `schema: N skipped`); a version difference with equal hashes registers and shows `vX≠vY` | D5: never serve a mismatched schema silently; equal schemas across versions are safe |
| d4 | Tool results are `{ result }` holding the verb's dict; a verb error is `{ result: { error: { type, message } } }` | the shape the `refmatrix` MCP server returns today (`{"error": str}`), so the model's reading does not change; `deny` means a refusal and is logged as one |
| d5 | Absent (24.4's twin says `TransportAbsent` on THIS store's socket) → `$.process.run([identity.rmx_bin, "verb", "run", name, "--session", s, "--json"], { stdin, cwd: project_root, timeoutMs })`; busy / undialable → the typed error, never a spawn; `rmx_bin` null → an error naming `identity.json` | D4; the spawned CLI re-classifies the daemon itself (24.2 R11), so the mod never decides "absent" alone and never opens a store |
| d6 | `$.state` contract `refmatrix.{focus, health, injected, delivered}` in `mod/types/index.d.ts`; this task owns `focus` and `health` (24.6 owns `injected`, `delivered`) | render subscription redraws the status line and pane on `set`, no `invalidate`; survives a hot reload |
| d7 | NEITHER `$.state` NOR `$.store` is a system of record for memory or STM: the daemon's store and the GMD memory files stay authoritative | a crash or a worker loss drops `$.state`; the CLI, subagents, the shell fallback and save-state all read the ring from the store |
| d8 | `$.store` keys: `discovery:<cwd>` (a CACHE of discovery: socket, identity hash, version, last-seen; invalidated on any mismatch with the live answer), `settings`, `outbox` | cross-session, per plugin, JSON, 4 MiB total: fit for a cache and a small queue, not for data |
| d9 | The outbox holds ENGINE-surface writes only (24.6's observe events, focus records) that failed twice (absent AND the spawn failed); model tool writes return the error to the model instead | the model must know a write did not land; queuing it silently would change the tool's meaning |
| d10 | Outbox entries carry an idempotency key (`sha256(verb, args, session, first-attempt ts)`), replay FIFO at `session.start` and on the health tick that sees the daemon up, stop at the first busy; cap 1 MiB of JSON or 2,000 entries | 24.2 R8 makes replay exactly-once; the cap leaves the 4 MiB store room for the cache; FIFO keeps an STM ring's order |
| d11 | Outbox overflow drops the OLDEST entry and raises a toast, a transcript line and a status count every time; nothing is dropped silently | "decay may demote, never lose" cannot hold for a client queue with a hard cap, so the loss is made loud instead |
| d12 | Pane and bus wake live here (ch-bsd s5): `/rmx` opens the pane; a long-poll loop on `rmx_bus_wait` turns a wake message into `$.prompt.submit` | G5 had no home; both are core surfaces, not context injection |
| d13 | While the `refmatrix` MCP server is connected (its tools appear in `$.tool.list()`), the mod registers no colliding tool and says so | two registrations of one name with different transports; 24.8 removes the server, and the mod's tools go live then on the dev box |
| d14 | Tunables are `userConfig` fields in `plugin.json` (rows in `/config`, read as `register`'s `options`; a change reloads the module with new options); no env-var-only knobs on the mod path | the engine's own settings surface, stored per plugin under `pluginConfigs`; a picker for enumerations |
| d15 | Peer deliveries are OBSERVED: `session.receive` and `session.send` mirror the text to the bus (`proj:<store>:peer`) and pass it on unchanged (`next(e)`); nothing is consumed or rewritten | the bus becomes the record of cross-session traffic without the mod deciding what a session may receive |

## Requirements {#requirements}

1. **R1 — module shape.** `mod/src/index.ts` exports `register: Register`; hooks: `session.start`
   (handshake), `session.end` (stop timers, clear `health`), `tool.call` with one matcher per
   registered tool (`{ tool: "mcp__refmatrix__<name>" }`), `ui.render` for the pane, `command.run`
   for `/rmx`. Every hook body runs in a `try` whose `catch` writes `$.ui.log(<plugin>: <event>:
   <type>: <message>)` (transcript and debug log, G6) and then continues the chain (`next(e)`)
   where the event allows; a guard-free observer never blocks the user's work. {#r1}
2. **R2 — the handshake, awaited in `session.start`.** (a) `$.session.root()`; (b) discovery per
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
   carries `agent_id` from `e.agentId` (a subagent's call). `deadlineS` = the verb's `timeout`
   argument when given, else 60; `waitMs` = deadline + 2 s. {#r3}
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
    the pane's unread count. 503 → back off 5 s; hub down → back off 30 s; each loop error is a
    debug-log line. Stopped at `session.end`. {#r10}
11. **R11 — collision (d13).** If `$.tool.list()` contains a `mcp__refmatrix__*` tool not
    registered by this plugin, register none, status `rmx: MCP server still configured (24.8)`,
    one transcript line. {#r11}
12. **R12 — probes, before the GREEN commit, in a scratch project.** Each result is written to
    `eval/mod_probe/<probe>.json` with `$.session.version()`, and a decision row is added to this
    spec from it: {#r12}
    - **P-sub-state:** does a subagent's loop read the parent's `$.state` values and see the
      parent's `set`s? (If not, the subagent's tool calls still route by `e.agentId` under the
      parent's session; focus shown in the pane is the main loop's.)
    - **P-sub-tools:** are `$.tool.register`ed tools offered to a subagent (Agent tool), and does
      the `tool.call` hook answer them there? (If not, subagents keep the MCP route until 24.8 says
      otherwise — 24.8 cannot retire it before this reads.)
    - **P-print:** under `claude -p --plugin-dir mod`, does `session.start` run before the prompt,
      are the tools callable, and where do `$.ui.status` / `$.ui.toast` / `$.ui.log` go (the
      reference says `ui_log` messages and stderr)? (If tools are not callable in `-p`, `-p`
      sessions keep the shell + MCP path; 24.6's stand-down marker is not set there.)
    - **P-collision:** what the engine does when the MCP server and the mod register the same
      name (confirms or retires d13).
    - **P-socket:** the mod's largest accepted `socketPath` (from 24.4 R5) against 24.2's
      `http_socket_bytes`; a store above it shows `http: path too long for the mod` and is served
      by the spawn path.
13. **R13 — tests (`claude plugin test mod`).** `mod/tests/*.test.ts` drive the hooks with the
    engine's `$` and answer the `$` ops beneath the plugin (`http.fetch`, `process.run`,
    `store.*`, `env.get` are op events) with recorded host bodies; `mock.clock` advances the tick.
    {#r13}
14. **R14 — `userConfig` (d14).** Fields (each with a default equal to today's generated hook
    argument): `scan_max_tokens` 2000, `scan_timeout_s` 5, `recall_k` 5, `recall_scope`
    (picker: project / global / both, default both), `composite_every` 3, `health_interval_s` 15,
    `status_line` (picker: full / compact / off), `bus_wake` (picker: on / off), `scrub_secrets` (picker: on / off, default on; 24.6 R12), `outbox_max_entries`
    2000. 24.6 reads the scan / recall / composite fields; this task the rest. Validated by
    `claude plugin validate`; a test runs `test(name, { options }, body)` with a non-default value
    and sees it used. {#r14}
15. **R15 — timers.** The health tick and the bus loop run on `$.clock.every` /
    `$.clock.after` started in `session.start` (they outlive the dispatch, are cancelled on reload
    and at `session.end`); the bus loop re-arms with `$.clock.after(0)` after each long-poll
    returns, never with `$.clock.sleep` inside a hook (a sleep spends the hook budget). {#r15}
16. **R16 — peer deliveries (d15).** `session.receive` (origin `peer` / `coordinator`) and
    `session.send` hooks publish `{ from, to, text (first 4,000 chars), agentId }` with
    `rmx_bus_pub(channel="proj:<store>:peer", type="peer")` and return `next(e)` untouched; a
    publish failure is a debug line, never a refusal. Probe **P-send**: whether `$.session.send({
    to: { sessionId } })` reaches another local session; the result is recorded and listed as a
    follow-up candidate in 24.8, not built here. {#r16}

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
8. **AC-8 (R11).** With a foreign `mcp__refmatrix__rmx_context` in `$.tool.list()`, zero
   registrations and the line. {#ac-8}
9. **AC-9 (R12, R16).** The six probe files (R12's five, R16's P-send) exist and each has its decision row in this spec. {#ac-9}
10. **AC-10 (R1).** A hook forced to throw (a mocked `http.fetch` that throws a non-Error) leaves a
    transcript line naming the event, and the tool call still answers with an error result. {#ac-10}
11. **AC-11 (R14, R15).** With `options.health_interval_s = 5`, the mocked clock shows a tick
    every 5 s; `bus_wake: "off"` makes a `wake` message toast instead of submitting; after
    `session.end` no timer fires. {#ac-11}
12. **AC-12 (R16).** A mocked `session.receive` from a peer is passed on byte-identical and one
    `rmx_bus_pub` request names `proj:<store>:peer`; a failing publish still passes it on. {#ac-12}

## Test strategy {#test-strategy}

TypeScript tests under `mod/tests/` (`handshake.test.ts`, `routing.test.ts`, `health.test.ts`,
`outbox.test.ts`, `pane_bus.test.ts`, `config.test.ts`, `peer.test.ts`), run by `claude plugin test mod` from
`tests/test_task24_4_mod_gates.py` (24.4 R7), logs captured. Host bodies come from recorded 24.2 /
24.3 responses committed under `mod/tests/fixtures/` (produced by the Python suites, not written by
hand). Probes (R12) run in a scratch project with `--plugin-dir`, never against this repo's live
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
| `mod/src/peer.ts` | R16 |
| `mod/tests/*.test.ts`, `mod/tests/fixtures/` | AC-1..AC-12 |
| `eval/mod_probe/` | R12's records |
