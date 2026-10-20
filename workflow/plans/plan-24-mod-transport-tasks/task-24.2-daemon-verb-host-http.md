---
gmd: "0.1"
id: task-24.2-daemon-verb-host-http
title: "Task 24.2: the daemon hosts the verbs — an in-daemon execution context so a verb never dials its own socket, and rmxd-http.sock serving one POST route per verb, with typed HTTP errors, budgets, a required session and a bounded pool of its own"
tags: [task, plan-24, daemon, http, verbs, session, transport, mod]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.2: the in-daemon verb host and `rmxd-http.sock` {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20).
> Depends on: [[task-24.2a-hook-verbs-explicit-session]] (the `Caller` context, `@verb` fields,
> required sessions), [[task-24.1-store-runtime-identity]] (the identity file this task completes),
> [[task-3.7-verb-it-backlog]] merged (`snapshot_read` / `local_write`, which the host redirects).
> Feeds: 24.3 (reuses `httpsock`), 24.4 (routes generated from the same `VERBS`), 24.5 (the mod's
> only per-store transport).

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-24.2a-hook-verbs-explicit-session]]
rel: depends-on -> [[task-24.1-store-runtime-identity]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: implements -> [[exploration-claude-code-mod-transport#verb-host]]
rel: implements -> [[exploration-claude-code-mod-transport#http-verbs-only]]
rel: implements -> [[exploration-claude-code-mod-transport#http-tiers]]
rel: derives-from -> [[bsd-plan24-spec-review-cdcfbc3#s4]]
rel: related-to -> [[project_daemon_arch]]
rel: related-to -> [[project_suite_reaches_live_sockets]]

## Why {#why}

The mod cannot run Python, and D3 says the per-store surface is the verbs, run server-side, so a
mod call keeps every verb's budget, partition resolution and error typing. Today `verbs.py` runs
in the CALLER (CLI or `rmx mcp`) and reaches the daemon through `_call` → `daemon.call` on
`rmxd.sock`. Run the same function inside the daemon and `_call` dials the daemon's own socket:
`require_daemon` pings itself, and the op queues behind the very request that is waiting for it.
With four cli workers, four concurrent verbs are a deadlock. `snapshot_read` would open
`catalog.read.duckdb` a second time inside the process that rotates it (bug-135's `already
attached`), and `local_write` would open the writer slot under the writer. The host needs an
execution path of its own, not a socket. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | Inside the host, `_call`, `require_daemon`, `snapshot_read`, `local_write` and `global_write` consult `CALLER.daemon` (a handle the host sets, 24.2a's `Caller` plus `daemon`): same root ⇒ in-process dispatch; another root ⇒ the normal socket path | the deadlock and the self-ping disappear by construction, and the CLI / MCP paths are untouched (CALLER is None there) |
| d2 | In-process dispatch goes through ONE extracted method `Daemon.dispatch(op, args, deadline_s)`, which `_handle` also calls | the pool choice, deadline drop, in-flight table, heartbeat and fast-exit check are the line-JSON path's; a second copy would drift (two ways to do X) |
| d3 | Verbs run on a NEW `verb_pool` (`RMX_DAEMON_VERB_WORKERS`, default 4); a verb thread only waits on op futures, never runs an op | no cycle: op pools never wait on `verb_pool`, so a full `verb_pool` queues HTTP requests and nothing else; the line-JSON server and the writer are not shared |
| d4 | The HTTP server is stdlib (`http.server.BaseHTTPRequestHandler` over a `socketserver.UnixStreamServer` subclass whose `process_request` submits to `verb_pool`), in a new module `refmatrix/httpsock.py` 24.3 reuses | no new dependency in the daemon (fastapi/uvicorn are the optional `ui` extra); synchronous verbs; a bounded pool instead of ThreadingMixIn's unbounded threads |
| d5 | Routes: `POST /v1/verbs/<rmx_name>` only, generated from `VERBS` where `tier in ("store", "both")`; 404 / 405 otherwise | D3; the route list cannot drift from `VERBS` |
| d6 | `session` is a REQUIRED request field; the host seeds `CALLER(session=..., in_host=True)` and never runs the ladder | G1; ch-bsd b1 |
| d7 | A request naming another store (`root` / `project` resolving elsewhere) is refused 400 `VerbArgsError` ("use that store's socket") | a host serving other stores would open their writer in-process on absent (C4a) inside this daemon; the mod routes by discovery (24.5) |
| d8 | `snapshot_read` in-host runs `fn` through `_read_with_fallback(d, partition, fn, private=True)` | the daemon's own read path; `private=True` because a verb's `fn` may run long, as the context op's rerank does |
| d9 | `local_write` in-host raises `VerbError("in-host local_write")` | absent cannot happen for the host's own root; reaching it is a bug, said loudly |
| d10 | A write carrying `idempotency_key` is applied once: a ledger `.refmatrix/idempotency.jsonl` (key, verb, ts, result) answers a repeated key with the recorded result | the mod's outbox (24.5) replays writes; a replay must not double an STM event or a note |
| d11 | The CLI gets one generic twin `rmx verb run <name> [--session S] [--json]` reading args JSON on stdin, sharing the host's request handler | D4's absent path spawns the PROJECT's rmx with exactly the host's semantics; one dispatcher for both |
| d12 | An ADR records the two-tier verb host (`docs/adr/0005-verb-host-http.md`), authored by ch-architect before GREEN | the daemon gains a second public surface and a third pool; that is an architectural decision, not a task detail |

## Requirements {#requirements}

1. **R1 — `Daemon.dispatch`.** The body of `_handle` after the request is parsed (ping inline;
   `CLI_OPS` → `cli_pool` else `bg_pool`; bug-116 deadline drop for cli reads; in-flight token;
   heartbeat on cli completion; `_fast_exit_if_invalidated` on an op exception) moves to
   `dispatch(op, args, deadline_s) -> dict` returning the `{ok, result | error}` dict. `_handle`
   calls it. No behaviour change on the line-JSON path (its tests pass unchanged). {#r1}
2. **R2 — the in-host short-circuit.** `verbs._call(root, op, payload, ...)`: when
   `CALLER.get()` carries a daemon whose `root` resolves equal to `root`, return
   `daemon.dispatch(op, payload, timeout)` mapped exactly as the socket reply is (`ok:false` →
   `VerbError`, `DeadlineExceeded` text → `VerbBusyError`). `require_daemon` returns the host's
   own status dict (from `_op_ping`) without a socket. `snapshot_read` / `local_write` per d8 / d9.
   `global_write` short-circuits when the host IS the global store's daemon (belt and braces: d13
   of 24.3 keeps the global daemon from hosting HTTP). {#r2}
3. **R3 — the socket.** `rmxd-http.sock` beside `rmxd.sock` (`daemon.http_socket_path(root)`),
   bound after `rmxd.sock`, mode `0o600`, a stale file unlinked only after `_reap_predecessor`
   succeeded (the line-JSON socket's rule). The global store's daemon does not bind it (24.3 d13).
   `RMX_DAEMON_HTTP=0` disables it, recorded in the identity file as `http_error:
   "disabled by RMX_DAEMON_HTTP=0"`. {#r3}
4. **R4 — sun_path fails loudly.** Before bind: `len(os.fsencode(path)) >= 104` → no bind, one
   `rmxd.log` line naming the path and its length, `http_socket: null`, `http_error: "socket path
   N bytes exceeds the AF_UNIX limit (104)"` in `identity.json`, and the daemon keeps serving
   line-JSON. `http_socket_bytes` is recorded on success too (24.5 compares it with the mod's own
   `socketPath` limit, which the types state only as "near 100 B"). {#r4}
5. **R5 — the request.** `POST /v1/verbs/<name>`, `Content-Type: application/json`, body
   `{"args": {...}, "session": str, "caller": {"hook_event"?, "prompt_id"?, "agent_id"?},
   "deadline_s"?: number, "idempotency_key"?: str}`; header `X-Rmx-Schema: <per-verb hash>`
   optional. Body cap 8 MiB (413 beyond). Headers must arrive within 30 s (the line-JSON server's
   ceiling), polled so shutdown is not pinned (bug-041's shape). {#r5}
6. **R6 — the response and the error map.** Success `200 {"ok": true, "result": ...}` (JSON via
   `default=str`, the MCP server's encoding). Errors `{"ok": false, "error": {"type", "message",
   "subject"?}}`: {#r6}

   | raised | status | notes |
   |---|---|---|
   | `VerbArgsError`, missing `session`, foreign root (d7) | 400 | `type` names the class or `SessionRequired` |
   | `SessionUnresolved` | 400 | in-host it means the request lacked what the verb needs |
   | unknown verb / wrong method | 404 / 405 | |
   | `X-Rmx-Schema` ≠ the verb's hash | 409 | body carries both hashes; the verb does not run |
   | `VerbBusyError` | 503 | `Retry-After: 1` |
   | `VerbAbsentError` | 424 | always ANOTHER daemon (hub, global store); `subject` names its root. Never the mod's "spawn" signal: that is a transport error on THIS socket (24.4's classifier) |
   | other `VerbError` | 422 | |
   | queued read past its deadline | 504 | never run (bug-116); writes are never dropped |
   | anything else | 500 | logged with its traceback to `rmxd.log`; `_fast_exit_if_invalidated` applies |

7. **R7 — budgets.** `deadline_s` (default 60, max 600) bounds the request: the host passes it as
   `timeout` to a verb that declares `timeout` and the caller left it unset, and as `deadline_s`
   to every `dispatch` the verb makes. A request whose wait in `verb_pool`'s queue already exceeds
   its deadline is answered 504 without running when the verb (or its action) is not `writes`.
   The mod has no fetch timeout of its own (`HttpInit` carries none), so this server-side bound is
   the one that holds. {#r7}
8. **R8 — idempotency (d10).** Keys up to 128 chars; the ledger is appended under the writer lock
   after the verb returns ok, read into an in-memory LRU (10,000 keys, 7 days) at start; a hit
   returns `200` with the recorded result and `"replayed": true`. A ledger write failure is a
   `rmxd.log` line and the response carries `warnings: ["idempotency not recorded"]`. {#r8}
9. **R9 — one telemetry row per call (ch-bsd s4).** Each request appends a `cli.log` row:
   `invocation: "mod"`, `cmd: "verb <name>"`, `hook_event`, `session`, `prompt_id`, `agent_id`,
   `queue_ms` (accept → verb start), `wall_ms` (accept → response written), `status`, `start_wall_ms`,
   `end_wall_ms`. 24.0's after-window reads these. No argv, no args body. {#r9}
10. **R10 — fast-exit and respawn.** The HTTP server thread stops with the daemon: `_stop` closes
    the listener, in-flight verbs get the existing shutdown budget, `verb_pool` is drained by
    `_drain_pool`'s bounded path. A fast-exit leaves the socket file; the next start replaces it
    (R3). A client mid-request sees a reset, which 24.4's classifier calls busy, not absent. {#r10}
11. **R11 — `rmx verb run`.** `rmx verb run <name> [--session S] [--deadline S] [--idempotency-key
    K] [--json]` reads `{"args": ...}` from stdin, runs the SAME request handler as R5-R8 against
    the local daemon over `rmxd-http.sock` when it answers, else (absent, by `require_daemon`) the
    verb in-process with `CALLER(invocation="mod", session=S)` and 3.7's C4a path. Prints the R6
    body; exit 0 / 2 (args) / 3 (busy) / 4 (absent dependency) / 5 (other). It is the parity walk's
    one `TRANSPORT_CLI` entry (a new map with one reason). {#r11}
12. **R12 — the ADR.** d12, written and lint-clean before the GREEN commit; `docs/adr/0000` and
    `docs/INDEX.md` rows. {#r12}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1).** The line-JSON suites (`test_daemon_*`, `test_hook_wiring.py`) pass unchanged
   after the extraction. {#ac-1}
2. **AC-2 (R2, d3).** With `RMX_DAEMON_CLI_WORKERS=1` and `RMX_DAEMON_VERB_WORKERS=4`, four
   concurrent `rmx_context` requests over `rmxd-http.sock` all answer 200 within the budget (a
   self-dial would deadlock at 1 cli worker); a recorded `daemon.call` spy shows zero socket calls
   to the host's own root. RED at base (no socket). {#ac-2}
3. **AC-3 (R2, d8, d9).** A 3.7 graph verb that uses `snapshot_read` answers in-host with
   `source` from the daemon's read path and no second DuckDB attach (the daemon log has no
   `already attached`); a verb copy forced onto `local_write` in-host gets `VerbError`. {#ac-3}
4. **AC-4 (R5, R6).** One test per table row: each status, `type` and `subject` as specified;
   409 runs nothing (a write verb's effect is absent). {#ac-4}
5. **AC-5 (R4).** Under a root whose `rmxd-http.sock` path is ≥ 104 bytes but whose `rmxd.sock`
   path is < 104 (a 5-byte window), the daemon serves ping, `identity.json` has the `http_error`,
   and `rmxd.log` has the line. {#ac-5}
6. **AC-6 (R6, R7).** A cli-read verb queued behind a held `verb_pool` (a fixture verb that
   blocks on an event) past `deadline_s` answers 504 and never runs; a write verb in the same
   position runs. {#ac-6}
7. **AC-7 (R8).** Two requests with one key and a `rmx_focus_note` body leave one note and two
   200s, the second `replayed: true`; the key survives a daemon restart. {#ac-7}
8. **AC-8 (R9).** Each request of AC-2 leaves one `cli.log` row with `invocation: "mod"`, the
   request's session, and `wall_ms ≥ queue_ms`. {#ac-8}
9. **AC-9 (R10).** A daemon fast-exited mid-request (the existing invalidation fixture) gives the
   client a reset; the respawned daemon serves the socket again. {#ac-9}
10. **AC-10 (R11).** `rmx verb run rmx_focus_note --session S` with the daemon up and with it
    absent produces the same note and the same printed body; with a busy daemon, exit 3 and no
    catalog file opened. {#ac-10}

## Test strategy {#test-strategy}

New `tests/test_task24_2_verb_host.py`; an HTTP-over-AF_UNIX client in
`tests/http_unix_support.py` (stdlib `http.client.HTTPConnection` with a connected unix socket),
never the live store (short `mkdtemp(dir="/tmp")` roots; 23.0's sandbox). The blocking fixture verb
of AC-6 is registered into a copied `VERBS` for the test only and listed in
`workflow/test_mock_registry.md`. RED run logged to `workflow/review-output/task24_2-red.log`.
{#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/httpsock.py` | new: the unix-socket HTTP server, request parsing, the R6 error map, the R9 row (shared with 24.3) |
| `src/refmatrix/daemon.py` | `dispatch` extraction (R1), `verb_pool`, `http_socket_path`, bind + sun_path check (R3, R4), shutdown wiring (R10), identity `http_*` fields, idempotency ledger (R8) |
| `src/refmatrix/verbs.py` | in-host short-circuit in `_call` / `require_daemon` / `snapshot_read` / `local_write` / `global_write` (R2); `run_request()` used by the host and `rmx verb run` |
| `src/refmatrix/cli.py` | `rmx verb run` (R11) |
| `src/refmatrix/telemetry.py` | the mod row fields (R9) |
| `docs/adr/0005-verb-host-http.md`, `docs/adr/0000-adr-overview.md`, `docs/INDEX.md` | R12 |
| `tests/test_task24_2_verb_host.py`, `tests/http_unix_support.py`, `tests/test_verb_parity.py` (`TRANSPORT_CLI`) | AC-1..AC-10 |
