---
gmd: "0.1"
id: task-24.3-hub-http-discovery
title: "Task 24.3: the hub serves the mod's global tier on hub-http.sock — discovery (cwd or project → store, sockets, identity, state), global memory, federated where/search/locate/canon, the bus, and a long-poll that lets the mod wake an idle session"
tags: [task, plan-24, hub, http, discovery, bus, federated, mod]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.3: hub HTTP — discovery, global, federated, bus {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20).
> Depends on: [[task-24.2-daemon-verb-host-http]] (`httpsock`, `run_request`, the error map),
> [[task-24.1-store-runtime-identity]] (the record discovery answers),
> [[task-24.2a-hook-verbs-explicit-session]] (`tier`, `Caller`).
> Feeds: 24.5 (handshake, status line, pane, bus wake).

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-24.2-daemon-verb-host-http]]
rel: depends-on -> [[task-24.1-store-runtime-identity]]
rel: depends-on -> [[task-24.2a-hook-verbs-explicit-session]]
rel: implements -> [[exploration-claude-code-mod-transport#http-tiers]]
rel: implements -> [[plan-24-mod-transport#goals]]
rel: related-to -> [[project_shared_worker_private_split]]
rel: related-to -> [[reference_claude_channel_mcp_push]]
rel: derives-from -> [[bsd-plan24-spec-review-r2-03c2d1f#meh]]

## Why {#why}

D2 splits HTTP by ownership: a store's verbs on its own daemon (24.2), and what belongs to no one
store on the hub — the global memory store, federated lookups across stores, the bus, and
discovery ("which store owns this cwd?"), asked once per session so store discovery is not
re-implemented in TypeScript. Today the hub speaks line-JSON on `hub.sock` (every `rmx` client,
the watchdog, `subscribe_stream`) and serves a browser UI on TCP :7777 when the `ui` extra is
installed. Neither is the mod's surface as it stands. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | A NEW unix socket `~/.refmatrix/hub-http.sock` (0600), served by 24.2's `httpsock`, in the hub process | filesystem permissions as auth, like the per-store tier; no TCP port (the :7777 app has unauthenticated POSTs such as `/api/projects/init` that spawn processes); works in a headless hub with no `ui` extra; `hub.sock`'s line-JSON clients are untouched |
| d2 | Not :7777: the browser UI stays as it is and is not the mod's transport | a second consumer would freeze the UI's ad-hoc JSON shapes into an API; the mod's surface is verbs (D3's rule applied to the hub tier too) |
| d3 | Not `hub.sock`: changing its protocol breaks `rpc`, `subscribe_stream`, the watchdog and every deployed `rmx` mid-upgrade | a version handshake already restarts the fleet on skew; a protocol change would add a window where old clients cannot speak to the new hub |
| d4 | The hub tier serves verbs only: `tier in ("hub", "both")`, routes `POST /v1/verbs/<name>`, the same request / response / error map as 24.2 | one transport contract for the mod, one generator (24.4) |
| d5 | Discovery and bus wait are verbs: `rmx_discover` and `rmx_bus_wait` (engine surface, hub tier) | D3 consistency; both get CLI twins (`rmx discover`, `rmx bus wait`) and the parity gate |
| d6 | `tier="both"` verbs (global memory) run on the hub with `root = hub.global_store_root()` | the global memory store is the hub's to front; the hub never hosts a project store's verbs (404 "use the store socket") |
| d7 | Hub-tier verbs run in-process in the hub with a `Caller(hub=self)`: `_hub_rpc` dispatches to `Hub.OPS` directly, never dialing `hub.sock` | the 24.2 self-dial problem, one level up |
| d8 | `rmx_bus_wait` is a long-poll (≤ 25 s, cursor-based on the existing bus read cursors) on a dedicated `hub-wait` pool (default 16) | `$.http.fetch` has no streaming read; a long-poll fits it, and waits must not starve the verb pool |
| d9 | A wake is a bus message of `type` `request` or `wake` on `proj:<project>:*`, or any message on `proj:<project>:session:<session_id>`; others only count as unread | waking a session on every `global:*` announcement would start turns nobody asked for |
| d10 | Discovery's cwd rule is ONE Python function, `discovery.store_for_cwd(cwd)`: `$REFMATRIX_ROOT` → the `~/.claude/projects/<slug>` rule (`cli._root_from_projects_slug`) → nearest ancestor holding `.refmatrix/` that is NOT the global store (`discovery.is_global_root`) → none; 24.5's hub-down TS walk is parity-tested against a fixture table this function generates | the only discovery logic the mod keeps is the 10-line fallback walk, and it cannot drift silently |
| d11 | Discovery answers the 24.1 record VERBATIM plus live state (up / busy / absent by `discovery.daemon_status`) and never spawns anything | busy ≠ absent; spawning is the mod's D4 decision with the project's rmx, not the hub's |
| d12 | Discovery of a store with no daemon and no identity file answers `state: "absent", identity: null` and names `rmx_bin` from the hub's own registry row when one exists, else null | the mod must refuse visibly rather than guess a binary |
| d13 | The global store's daemon does not bind `rmxd-http.sock` | its verbs are served here (d6); two doors to the global store would be two ways to do X |
| d14 | The hub has NO job lane in plan-24. A `tier="both"` verb served on the hub (`scope="global"`) runs SYNCHRONOUSLY with its budget clamped to 25 s, through `global_write`'s budgeted path (status probe, spawn and the one write all inside the budget, a timeout worded "not confirmed"); a (verb, action) whose declared timeout (24.2a R13) is over 25 s or unbounded is REFUSED on the hub with 422 `HubJobUnsupported` naming the limit and the CLI command that runs it. A hub job lane is a 24.8 follow-up candidate | `global_write(timeout=…)` already bounds the whole global write, so the writes the mod sends (add, promote, forget, retag, link) fit in 25 s; adding a job lane, a durable ledger and polling to the hub is a second copy of 24.2 R13 for actions nobody calls from a session today (r4, ch-bsd r3 s4) |

## Requirements {#requirements}

1. **R1 — the socket.** `hub.hub_http_sock_path()` = `hub_home() / "hub-http.sock"`; bound in
   `Hub.run` after `hub.sock`, before the HTTP UI, with 24.2's sun_path check (a failure is a
   `hub.log` line and `hub_info.http_error`). `hub_info` / `rmx hub status` report `http_sock`,
   `http_error`. Stopped by `Hub.shutdown`. `RMX_HUB_HTTP=0` disables it, reported as such. {#r1}
2. **R2 — `rmx_discover(cwd: str | None = None, project: str | None = None)`** (engine, hub,
   read). Exactly one of `cwd` / `project` (else `VerbArgsError`). Answers `{store_root,
   project_root, store_name, state: "up" | "busy" | "absent", pid, identity: <identity.json or
   null>, identity_error, socket, http_socket, hub: {version, verb_schema_hash}}`; `project`
   resolves through `mcp._resolve_project_root`'s rule, moved to `discovery.root_for_project`
   (one implementation; mcp calls it). No store for the cwd → `200` with `store_root: null`. {#r2}
3. **R3 — `discovery.store_for_cwd` + the parity fixture.** d10's function, used by `rmx_discover`,
   `mcp._resolve_root` and the CLI's `_root()` (one walk; the CLI keeps its documented fallback to
   the global store when the walk answers none, and `mcp._resolve_root` gains the slug rule and the
   global-store exclusion it lacks today — a session under `~` with no project store must not
   discover `~/.refmatrix` as its project). `python -m refmatrix.modgen
   --discovery-cases` (24.4's generator) renders the table into the mod's tests. {#r3}
4. **R4 — global memory over the hub.** `rmx_memory`, `rmx_memory_add`, `rmx_memory_recall`
   become `tier="both"`; on the hub they run against the global store root (d6), through
   `global_write` / `global_recall_rows` exactly as a project caller's `scope=global` does. A
   `scope="project"` request on the hub is `VerbArgsError` ("project scope is served by the
   store's socket"). {#r4}
5. **R5 — federated + bus verbs.** `rmx_where`, `rmx_search`, `rmx_locate`, `rmx_projects`,
   `rmx_queues`, 3.7's `rmx_canon` and `rmx_refine`, and every `rmx_bus_*` verb are
   `tier="hub"` (served here, 404 on a store socket). Their bodies are unchanged; inside the hub
   `_hub_rpc` dispatches in-process (d7). {#r5}
6. **R6 — `rmx_bus_wait(channels: list[str], agent: str, timeout_s: float = 25.0)`** (engine,
   hub, READ: it never advances `agent`'s read cursor). Returns as soon as at least one message
   unread by `agent` matches `channels` (with every such message), or `{"messages": []}` at
   `timeout_s` (max 25). The caller acknowledges what it has acted on with the existing
   `rmx_bus_mark_read(channel, agent, up_to=<id>)`; until then the same messages are returned
   again, so a mod that dies between receiving and acting loses nothing. Implemented on
   `Bus.subscribe` (the `_stream_bus_sub` mechanism) after a check of the unread backlog,
   unsubscribed in `finally`. Each message carries `wake: bool` per d9. {#r6}
7. **R7 — pools.** Hub verbs on `hub-verb` (default 8, `RMX_HUB_VERB_WORKERS`); `rmx_bus_wait`
   on `hub-wait` (default 16, `RMX_HUB_WAIT_WORKERS`); a full wait pool answers 503 immediately
   (the mod backs off), never queues a long-poll behind long-polls. {#r7}
8. **R8 — telemetry.** One row per request, 24.2 R9's shape, into the hub home's `cli.log`
   (global store root). {#r8}
9. **R9 — global writes within 25 s (d14).** On the hub, a `tier="both"` verb gets `timeout =
   min(caller deadline_s, 25)`; its global path uses `global_write(..., timeout=…)`. A request for a
   (verb, action) whose declared timeout exceeds 25 or is None answers 422 `HubJobUnsupported`
   (`message` names the action, the 25 s limit and the `rmx memory … --global` command), and
   `mode: "submit"` on the hub answers the same. {#r9}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1).** A hub started under a short `RMX_HOME` (`mkdtemp(dir="/tmp")`) binds
   `hub-http.sock` 0600 with no `ui` extra importable (fastapi masked from `sys.modules` for the
   test); `rmx hub status --json` names it. RED at base. {#ac-1}
2. **AC-2 (R2, R3).** For a fixture tree (store at `a/`, nested `a/b/c` without one, unrelated
   `z/`, `REFMATRIX_ROOT` set and unset): `rmx_discover(cwd=...)` agrees with
   `store_for_cwd`, `mcp._resolve_root({})` (under that cwd) and the CLI's `_root()` (whose answer
   for "none" is the global store, by its documented fallback); a cwd under a fixture `$HOME` with
   only the home store answers `store_root: null`; state is
   `up` / `busy` / `absent` against the up / `_silentdaemon` / no-daemon fixtures; nothing is
   spawned (no new pid appears). {#ac-2}
3. **AC-3 (R4).** `rmx_memory_add` over the hub socket lands in the global store (readable by
   `rmx memory get --global`); `scope="project"` answers 400. {#ac-3}
4. **AC-4 (R5, d7).** `rmx_bus_pub` + `rmx_bus_history` over the hub socket round-trip, and a
   spy on `hub.rpc` records zero calls (in-process dispatch). `rmx_context` on the hub answers 404.
   {#ac-4}
5. **AC-5 (R6, R7).** A `rmx_bus_wait` on `proj:p:*` returns within 1 s of a `request` message
   published from another thread, with `wake: true`; an `announce` on `global:x` returns with
   `wake: false`; with no message it returns empty at its `timeout_s` (set to 1 s in the test);
   17 concurrent waits leave the 17th answered 503. {#ac-5}
6. **AC-6 (d13).** The global store's daemon has no `rmxd-http.sock`. {#ac-6}
7. **AC-7 (R9, d14).** On the hub: `rmx_memory(action="promote", scope="global")` with a held
   global daemon answers 503 "not confirmed within 25s" at ~25 s; `rmx_memory(action="dedup",
   scope="global")` (declared 120 s) answers 422 `HubJobUnsupported` without running; a
   `mode: "submit"` request answers 422 too. {#ac-7}

## Test strategy {#test-strategy}

New `tests/test_task24_3_hub_http.py`, the hub run in-process under a short hub home (the
`test_hub_watchdog.py` fixtures), with 24.2's `tests/http_unix_support.py` client. Never the live
hub: the suite's isolation from live sockets ([[project_suite_reaches_live_sockets]]) is asserted by
23.0's sandbox, and these tests set `RMX_HOME` before importing the hub. RED run logged to
`workflow/review-output/task24_3-red.log`. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/hub.py` | `hub_http_sock_path`, bind/stop, pools, in-process `Caller(hub=)`, `hub_info` fields (R1, R7, d7) |
| `src/refmatrix/discovery.py` | `store_for_cwd`, `root_for_project` (R2, R3) |
| `src/refmatrix/verbs.py` | `rmx_discover`, `rmx_bus_wait`; `tier` on memory / federated / bus verbs; `_hub_rpc` in-process branch (R2-R6) |
| `src/refmatrix/mcp.py`, `src/refmatrix/cli.py` | call the one cwd / project resolver; `rmx discover`, `rmx bus wait` twins |
| `src/refmatrix/daemon.py` | skip the HTTP bind for the global store (d13) |
| `tests/test_task24_3_hub_http.py` | AC-1..AC-6 |

## Revision r2 (2026-10-20, ch-bsd r2 03c2d1f) {#rev-r2}

| finding | change |
|---|---|
| m5 the cursor / ack wording contradicted itself | R6: the wait is a pure read that never advances the cursor; acknowledgement is `rmx_bus_mark_read` after acting; unacknowledged messages are returned again |

## Revision r4 (2026-10-20, ch-bsd r3 6d3575b) {#rev-r4}

| finding | change |
|---|---|
| s4 the hub had no job lane for `scope=global` long writes | d14 / R9: synchronous within 25 s through `global_write`'s budget, longer actions refused with `HubJobUnsupported`; hub job lane listed as a 24.8 candidate; AC-7 |

