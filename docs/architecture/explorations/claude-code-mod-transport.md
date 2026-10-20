---
gmd: "0.1"
id: exploration-claude-code-mod-transport
title: "Exploration: refmatrix's Claude Code integration as a mod (function-hook plugin) instead of shell hooks + an MCP stdio server"
tags: [exploration, mod, plugin, hooks, mcp, transport, session, plan-24]
metadata:
  node_type: exploration
  status: in-progress
  created: 2026-10-20
---

# Exploration: refmatrix as a Claude Code mod {#root}

**Date:** 2026-10-20
**Status:** Research Complete. Option A chosen by the user (2026-10-20: "write up the mod
exploration doc with option A"); the measurement gate ([[#gate]]) decides whether plan-24 builds.
**Motivation:** The user asked what refmatrix would gain by becoming a Claude Code mod, and what
that does to the development plan. A mod is a TypeScript module the Claude Code engine loads in
process: it hooks events (`tool.call`, `prompt.submit`, `prompt.compose`, `session.start` /
`session.end`, `ui.render`), registers tools the model calls (`$.tool.register`), draws a status
line, toasts and panes, runs host commands (`$.process.run`) and makes HTTP calls, including over a
Unix socket (`$.http.fetch(url, { socketPath })`). {#motivation}

rel: amends -> [[plan-review-2026-10-14#t11-folded-waves]]
rel: related-to -> [[plan-16-invisible-grep-shim]]
rel: related-to -> [[plan-21-agent-context-usage]]
rel: related-to -> [[task-19.5-measure-delivery]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache]]
rel: related-to -> [[task-19.0-stm-cluster-hygiene]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: related-to -> [[feedback_mcp_server_reload_and_orphans]]
rel: related-to -> [[feedback_go_no_go_ranges_not_predrop]]

## Background: what the integration is today {#background}

refmatrix reaches Claude Code three ways, all outside the engine: {#background-lead}

1. **Shell hooks.** `hooks.py` / `search_hooks.py` GENERATE the hook config into
   `.claude/settings*.json`; `rmx install-hooks --check` gates that installed == generated. Every
   hook event spawns a fresh `rmx` Python process.
2. **An MCP stdio server.** `rmx mcp`, one process per client, tools generated from `verbs.py`.
3. **Files the session reads.** `.refmatrix/PRIMER.md` (regenerated at SessionStart) pulled in by
   `@` import from CLAUDE.md; memory files under `~/.claude/projects/<slug>/memory/`.

### Measured, 2026-10-13 to 2026-10-20 (refmatrix store, `cli.log`, `source=hook`) {#measured}

| hook command | calls | p50 / p95 `latency_ms` |
|---|---|---|
| `focus hook` | 22,455 | 1 / 7 |
| `sync` | 3,915 | 21 / 116 |
| `memory recall` | 412 | 1,290 / 5,014 |
| `curator status` | 396 | 0 / 0 |
| `scan-prompt` | 395 | 7,166 / 17,346 |
| `focus summarize` | 292 | 211 / 5,052 |

28,294 hook rows over 395 prompts (`scan-prompt` runs once per prompt): **~72 hook processes per
prompt**, ~57 of them `focus hook` on tool events. {#measured-counts}

**`latency_ms` excludes interpreter start.** It is timed inside the process after imports
(`telemetry.py` ~559), which is why `focus hook` reads 1 ms. Process start-up was measured
separately: `rmx version` took 0.13-0.15 s wall over five runs, and `import refmatrix.cli` alone
0.06 s. Rough arithmetic: 72 × ~0.14 s is about **10 s of spawn per prompt**. How much of that the
turn waits on is unknown: it depends on which events block and on concurrency. This is a
preliminary reading, not the gate measurement ([[#gate]]). {#measured-spawn}

**The two slow hooks are slow in their WORK, not their spawn.** `scan-prompt` (7.2 s p50) and
`memory recall` (1.3 s p50) spend their time in the daemon / rerank. A mod does not make that work
faster; the work stays in Python. A mod removes the spawn tax and the shell-hook defects listed
below. {#measured-work}

## The defect families a mod addresses {#defects}

| family (recurring) | today | under a mod |
|---|---|---|
| Session identity guessed | `$CLAUDE_PID`, pointer files, "latest ring" — bug-109, 21.1's resolver, bug-139 (`focus clear` cleared the wrong ring) | every event carries the session; the resolver ladder retires for the Claude Code path |
| Hook output caps | ~10k chars whole, ~2 KB preview beyond ([[reference_hook_output_10k_cap]]); 19.5 R1 exists to probe it | `prompt.compose` adds a system-prompt section (`scope: 'session'`), `prompt.submit` rewrites the prompt; size is ours |
| Silent hook failure | generated `2>/dev/null \|\| true` (one removed by 3.7) | a failing hook is a transcript line and a debug-log line |
| Hook config drift | `install-hooks --check`, `--no-claude` reaping ([[feedback_install_hooks_no_claude_reaps]]), hand edits to settings.json | one versioned plugin folder, hot-reloaded |
| MCP server process | per-client stdio; a deploy needs `/mcp` reconnect; orphans pile up | `$.tool.register` serves tools in the engine (`mcp__<plugin>__<name>`) |
| Grep shim | PreToolUse rewrite + BASH_ENV route + shim binary (plan-16) | `tool.call` sees and rewrites Bash/Grep and, with `await next(e)`, reads the RESULT |
| Invisible store trouble | DuckDB crash loop that `daemon status` cannot see; stale daemons; hub version skew | status line, toast on fast-exit / version mismatch, pane over focus / recall-state / bus |
| Bus push | experimental `claude/channel` MCP capability | `$.prompt.submit` wakes an idle session; `$.ui.toast` |

## Option A: decide now — measurement gate, plan-24, hook-shaped Wave 2 work held {#option-a}

**Chosen.** Add **plan-24 "mod transport"** whose first task is the measurement in [[#gate]]. Until
the gate reads, hold the hook-shaped work whose design a mod would change; Wave 1 (engine work)
continues unchanged. {#option-a-lead}

- **Held at the gate** (specs kept; no build): plan-16's build (16.1 → 16.2/16.3 → 16.5, 16.4);
  19.5 R1 (the hook-limit probe, already waiting on the user); 19.6's injection design;
  21.2-21.4's surfaces. {#option-a-held}
- **Unaffected, proceeds:** 23.x, 17.x, 18.x, 22.x, 20.x, 19.1 / 19.2, the plan-4 and plan-2
  riders, the helix. 3.7 is a PREREQUISITE, not throwaway: the verbs are the single source a mod's
  tool registrations are generated from. {#option-a-proceeds}
- **Cost:** a short pause on plan-16. **Buys:** plan-16 is not built if a mod makes it moot; the
  hook-shaped Wave 2-3 work is built once. {#option-a-cost}

## Option B: defer the decision past Wave 3 {#option-b}

Build plan-16, 19.6 and 21.2-21.4 on hooks, migrate later. Lowest risk now; the hook-shaped work
is built twice. Rejected for that reason.

## Option C: mod only for new surfaces {#option-c}

Status line, toasts, a pane; hooks and `rmx mcp` stay. Cheap; fixes none of [[#defects]]'s
recurring families. Kept as plan-24's first build step, not as the whole answer.

## The measurement gate (plan-24 task 24.0) {#gate}

Bands written BEFORE the data, per [[feedback_go_no_go_ranges_not_predrop]]. {#gate-lead}

**Instrument.** For every hook event of one working week (≥5 sessions, refmatrix only — the
user, 2026-10-20: "right now refmatrix is the only active project"; the gate measures the
workload that exists, and a second project re-runs it if one becomes active), record: the
event, wall time from Claude Code dispatch to hook exit (a wrapper timestamp, NOT `latency_ms`,
which starts after imports), the in-process `latency_ms`, and whether the event blocks the turn.
Spawn share = (wall − in-process) / wall. Per prompt: blocking spawn seconds = Σ (wall −
in-process) over the prompt's BLOCKING hook events. {#gate-instrument}

| blocking spawn per prompt (p50) | action |
|---|---|
| < 0.5 s | speed is not a reason. Build only if the defect families justify it alone: decide on [[#defects]], scope plan-24 to session identity + MCP + Option C surfaces |
| 0.5 - 2 s | build plan-24 for the hottest hooks (focus hook, scan-prompt, recall, grep guard) with shell hooks kept as fallback; re-scope plan-16 onto `tool.call` |
| 2 - 5 s | build plan-24 in full; plan-16, 19.6 and 21.2-21.4 retarget to the mod |
| > 5 s | as above, and it jumps ahead of Wave 2 |

A second, non-speed check runs in the same week: count session-resolution misses (21.1 records a
miss per purpose) and hook-output truncations (19.5's instrument). Either nonzero strengthens the
non-speed case at every band. {#gate-second}

## Findings {#findings}

- **Process spawn is ~0.14 s per `rmx` hook, and there are ~72 per prompt** (preliminary,
  [[#measured-spawn]]). The blocking share is the gate's question.
- **The two slowest hooks are slow in daemon work** ([[#measured-work]]); a mod does not change
  that. Any speed claim beyond spawn would be false.
- **A mod cannot call Python.** No Node, no DOM: everything goes through `$`. The daemons speak
  line-JSON over Unix sockets, not HTTP, so the mod needs HTTP surfaces, in two tiers
  ([[#http-tiers]]). `$.process.run` would bring the spawn back.
- **Where the verbs run is the real design question** ([[#verb-host]]). Today `verbs.py` runs
  CLIENT-side (CLI or `rmx mcp` process) and calls daemon ops; a mod calling raw ops would have to
  re-implement the verb layer in TS.
- **Verb parity becomes cross-language.** Tool registrations and hook payloads must be GENERATED
  from `verbs.py` (a schema export), with a parity test across the boundary, or the drift class
  `verbs.py` exists to kill returns.
- **Not every context loads a mod.** `claude -p` has no hot reload (`--plugin-dir` works);
  whether subagents run mod hooks is unverified. Shell hooks stay as the fallback until both are
  known.
- **Tooling gap.** Mod tests run under `claude plugin test`, apart from pytest; the ch-* agents
  and ch-bsd audits are Python-centric today.

## HTTP surfaces: per-store and hub (user, 2026-10-20) {#http-tiers}

The user, 2026-10-20: "wouldn't we have http endpoints per-rmx installation in addition to hub
endpoints". Yes: two tiers, split by ownership. {#http-tiers-lead}

- **Per store, in each project's daemon.** That project's verbs (context, query, memory, focus,
  graph, session, matrix, curate) over a Unix socket beside `rmxd.sock`
  (`<root>/.refmatrix/rmxd-http.sock`, reached with `$.http.fetch(url, { socketPath })`): no TCP
  port per project, filesystem permissions as auth, no hub hop. A project's reads and writes keep
  working through a hub outage ([[project_shared_worker_private_split]] is what a hub outage cost
  last time), and busy / absent stays per store, as `classify_transport_error` models it. The
  ~104-byte `sun_path` limit applies here as it does to `rmxd.sock`.
- **Hub** (`hub.sock` / :7777): the global memory store, federated lookups (`where`, `search`,
  `locate`, `canon find`), bus, queues, model workers, fleet status, and DISCOVERY — "which store
  owns this cwd?" → its socket path, asked once per session and cached, so store discovery is
  not re-implemented in TS.

## Where the verbs run {#verb-host}

- **Mod calls raw daemon ops:** the verb layer (budgets, partition resolution, payload builders,
  C4a) is re-written in TS. Rejected: that is the drift class `verbs.py` exists to remove.
- **The daemon hosts the verbs (preferred):** one HTTP endpoint per verb runs `verbs.<fn>`
  server-side; the mod's tool registrations are generated from the same signatures. Needs an
  in-daemon execution path, since a verb inside the daemon cannot `_call` its own socket.
- **No daemon — decided (user, 2026-10-20): "the mod should spawn the project rmx when
  needed".** C4a (in-process) is impossible from TS, so on ABSENT only the mod runs the verb
  through `$.process.run` of the PROJECT's `rmx`, which then takes its own C4a path. The spawn
  cost returns on this rare path only. Busy is never treated as absent and never spawns.
  "The project rmx" is the binary that store's installation runs, never the first `rmx` on PATH
  (the same rule plist writers follow: `RMX_BIN` / argv[0], never `which rmx`). The hub's
  discovery answer carries it beside the socket path. With the hub down, the mod reads it from a
  file the store records when its daemon starts, so a hub outage does not strand the fallback.
  {#verb-host-absent}
- **Transport errors** (refused / missing / path too long / timeout) arise client-side in TS, so
  the classifier gets a TS twin, parity-tested against `classify_transport_error`; errors the
  daemon returns keep their Python wording. {#verb-host-lead}
- **Verbs only — decided (user, 2026-10-20).** Each daemon's HTTP socket serves one endpoint per
  verb, `verbs.<fn>` run server-side, and nothing else. Raw daemon ops stay on `rmxd.sock`
  line-JSON for the CLI and operator tooling. A mod therefore cannot bypass a verb's budget,
  partition resolution or error typing, and the route list is generated from `VERBS`, so the
  existing parity gate covers it. {#http-verbs-only}

## Distribution: marketplace AND deploy-tree `--plugin-dir` (user, 2026-10-20) {#distribution}

The user, 2026-10-20: "distribution should allow for both". {#distribution-lead}

- **One source.** The mod lives IN the refmatrix repo (a `mod/` folder), generated from `verbs.py`
  at build. The deploy tree carries it, so `--plugin-dir ~/refmatrix/mod` loads the exact build
  the daemons run. The public repo (github.com/tangentland/refmatrix) carries a marketplace file,
  so `/plugin install refmatrix --marketplace tangentland/refmatrix` installs a tagged release.
- **Version handshake.** A marketplace install can be older or newer than the `rmx` a store's
  daemon runs. At `session.start` the mod reads each store's version and verb-schema hash (from
  the hub's discovery answer, or the store's recorded file when the hub is down). Tools whose
  schema differs are not registered, and the skew is shown as a toast plus a status-line entry,
  never silently served. The same handshake the hub already does with the daemons
  ([[project_hub_version_handshake]]), one level out.
- **Both installed at once.** The deploy-tree `--plugin-dir` copy wins and the marketplace copy
  stands down, saying so at load: two copies would register every tool and hook twice.
- **Releases.** A refmatrix release tags the mod with the same version; the marketplace entry
  points at the tag. {#distribution-body}

## Transition Summary {#transition-summary}

**Status:** IN PROGRESS

**Date:** 2026-10-20
**Proposed Plan:** [[plan-24-mod-transport]] (`status: drafting`, 2026-10-20); its gate task is
[[task-24.0-spawn-cost-gate]].

### What Survived Analysis {#what-survived-analysis}

- Option A: a measured go/no-go before any mod build, hook-shaped Wave 2-3 work held at the gate.
- Option C's surfaces as plan-24's first build step regardless of band.

### What Was Eliminated {#what-was-eliminated}

- Option B: builds plan-16, 19.6 and 21.2-21.4 twice.
- A full rewrite into the mod: the engine, CLI, launchd services and evals stay Python.

### Key Constraints Discovered {#key-constraints-discovered}

- `cli.log` cannot measure spawn ([[#measured-spawn]]); the gate needs a wrapper timestamp.
- Each daemon needs an HTTP verb surface, and the hub a global / federated / discovery one
  ([[#http-tiers]]); the verbs move server-side ([[#verb-host]]).
- Tool and payload generation from `verbs.py` is mandatory, not optional.

### Open Questions Requiring User Decisions {#open-questions-requiring-user-decisions}

- Q1 — decided (user, 2026-10-20): refmatrix alone carries the gate week; it is the only
  active project ([[#gate-instrument]]).
- Q2 — decided (user, 2026-10-20): the per-store HTTP surface serves **verbs only**
  ([[#http-verbs-only]]). The no-daemon fallback is decided too: spawn the project's `rmx`
  ([[#verb-host-absent]]).
- Q3 — decided (user, 2026-10-20): "distribution should allow for both" ([[#distribution]]).

### What Is NOT Moving Forward {#what-is-not-moving-forward}

- Making `scan-prompt` / `memory recall` faster through the mod: their cost is daemon work.

## References {#references}

- Mod API: the plugin-authoring skill's `reference.md` and `types/claude-code.d.ts` (Claude Code
  2.1.293): `$.tool.register`, `prompt.compose`, `tool.call`, `$.http.fetch(socketPath)`,
  `$.process.run`, the per-dispatch hook budget.
- Wave order: [[plan-review-2026-10-14#t11-folded-waves]].
