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
rel: derives-from -> [[bsd-plan24-spec-review-r2-03c2d1f#s6]]
rel: depends-on -> [[task-24.0-hook-cost-baseline]]

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
| d3 | Verbs run on TWO new lanes: `verb_read_pool` (`RMX_DAEMON_VERB_READ_WORKERS`, default 4) for verbs / actions that do not write, `verb_write_pool` (`RMX_DAEMON_VERB_WRITE_WORKERS`, default 4) for `writes` ones; a verb thread only waits on op futures, never runs an op, and a write's wait is bounded by its `deadline_s` | no cycle: op pools never wait on the verb lanes; the observe writes (two per tool call) queued behind a long `bg_pool` op can no longer starve reads (r2 s6 b) |
| d4 | The HTTP server is stdlib, in a new module `refmatrix/httpsock.py` 24.3 reuses: ONE thread runs a `selectors` loop that accepts and reads every connection non-blocking (per-connection buffer, 30 s header+body deadline, shutdown-aware), parses the request with `http.server`'s parsing helpers, and submits only complete, parsed requests to a lane; the lane thread runs the verb and writes the response | an idle or slow client never holds a worker (r2 s6 a, bug-041's shape); no new dependency (fastapi/uvicorn are the optional `ui` extra); bounded lanes instead of ThreadingMixIn's unbounded threads |
| d5 | Routes: `POST /v1/verbs/<rmx_name>` only, generated from `VERBS` where `tier in ("store", "both")`; 404 / 405 otherwise | D3; the route list cannot drift from `VERBS` |
| d6 | `session` is a REQUIRED request field; the host seeds `CALLER(session=..., in_host=True)` and never runs the ladder | G1; ch-bsd b1 |
| d7 | A request naming another store (`root` / `project` resolving elsewhere) is refused 400 `VerbArgsError` ("use that store's socket") | a host serving other stores would open their writer in-process on absent (C4a) inside this daemon; the mod routes by discovery (24.5) |
| d8 | `snapshot_read` in-host goes THROUGH `dispatch`: `dispatch_fn(name, fn, partition, deadline_s)` submits `_read_with_fallback(d, partition, fn, private=True, writer_wait_s=<deadline left>)` to `cli_pool` with the same in-flight entry, deadline drop, heartbeat and fast-exit check as an op | one execution path for everything that touches the store in-process (d2); the writer wait is bounded (r2 s6 d) |
| d9 | `local_write` in-host raises `VerbError("in-host local_write")` | absent cannot happen for the host's own root; reaching it is a bug, said loudly |
| d10 | A write carrying `idempotency_key` is applied once: the key is RESERVED (state `pending`) before the verb starts, and a repeat while pending is answered 409 `InFlight` (the mod treats it as busy and retries later); on success the ledger `.refmatrix/idempotency.jsonl` records `done` + result and a repeat gets the recorded result; on failure the reservation is released | the mod's outbox (24.5) replays writes that may still be queued in the daemon; recording only after success let such a replay run twice (r2 s6 c) |
| d12b | `CALLER` is set INSIDE the lane thread, by the submitted callable (`with verbs.caller(...)`), never in the accept thread: `ThreadPoolExecutor.submit` does not copy `contextvars`; ops submitted onward to `cli_pool` / `bg_pool` do not read `CALLER` (they resolve no session) | r2 s6 e: a context set in the submitting thread is invisible in the pool thread |
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
   `global_write` is unchanged: the global store's daemon hosts no HTTP (24.3 d13), so no host can
   be the global daemon. The lane callable sets `CALLER` itself (d12b). {#r2}
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
   optional. Body cap 8 MiB (413 beyond). The whole request must arrive within 30 s (the line-JSON
   server's ceiling) on the selector thread (d4), else the connection is closed with a `rmxd.log`
   line; no lane thread is involved until the request is complete. {#r5}
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

7. **R7 — budgets.** `deadline_s` (default 25, max 25 for a synchronous request: the mod's fetch
   is aborted by the engine at 30 s, [[plan-24-mod-transport#probes-batch2]]; a longer verb is
   submitted per R13, whose job deadline may be up to 600) bounds the request: the host passes it as
   `timeout` to a verb that declares `timeout` and the caller left it unset, and as `deadline_s`
   to every `dispatch` the verb makes. A read whose wait in its lane's queue already exceeds its
   deadline is answered 504 without running; a write is never dropped, and its wait for its op is
   bounded by the deadline: past it the response is 503 with 24.4's write wording ("not confirmed
   … may still complete") while the op runs on, its reservation (d10) still pending until it ends.
   The mod has no fetch timeout of its own (`HttpInit` carries none), so this server-side bound is
   the one that holds. {#r7}
8. **R8 — idempotency (d10).** Keys up to 128 chars; an in-memory table holds `pending`
   reservations (taken before the lane runs the verb) and `done` entries; `done` is appended to the
   ledger under the writer lock after the verb returns ok, and the ledger is read into the table
   (10,000 keys, 7 days) at start; a `done` hit returns `200` with the recorded result and
   `"replayed": true`; a `pending` hit returns 409 `InFlight`. A ledger write failure is a
   `rmxd.log` line and the response carries `warnings: ["idempotency not recorded"]`. {#r8}
9. **R9 — one telemetry row per call (ch-bsd s4; r2 s7).** Each request appends a `cli.log` row in
   24.0 R2's field set, written by the same `telemetry` helper the shell rows use: `invocation:
   "mod"`, `cmd: "verb <name>"`, `hook_event` (24.0 R2's vocabulary, from `caller.hook_event`; a
   value outside it is recorded as `other` with the raw value in `hook_event_raw`), `session`,
   `prompt_id` (from `caller.prompt_id`, the mod's `<session>:<n>`), `agent_id`, `t_start_ms`
   (request complete on the selector thread), `t_end_ms` (response written), `queue_ms` (lane
   queue wait), `wall_ms` (`t_end_ms - t_start_ms`), `status`. 24.0's report reads these beside the
   shell rows. No argv, no args body. {#r9}
10. **R10 — fast-exit and respawn.** The HTTP server thread stops with the daemon: `_stop` closes
    the listener, in-flight verbs get the existing shutdown budget, both verb lanes are drained by
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
13. **R13 — submit-then-poll (r3).** A request with `"mode": "submit"` is validated (schema,
    session, args, idempotency reservation) and answered at once `202 {"ok": true, "job_id":
    ...}`; the verb runs on a third lane, `verb_job_pool` (`RMX_DAEMON_VERB_JOB_WORKERS`, default
    2), under its own `deadline_s` (≤ 600) with the same `CALLER`, dispatch and error mapping. A
    new store-tier verb `rmx_job(job_id: str, wait_s: float = 20.0)` (engine surface, read)
    long-polls up to `wait_s` (max 20) and answers `{state: "running"}`, `{state: "done", result}`
    or `{state: "error", error: {type, message}}` (24.2 R6's error body). Jobs are kept in memory
    for 10 min after they end; an unknown id (expired, or lost to a daemon restart) is
    `VerbError("unknown job …; the daemon restarted or the job expired")`, never a silent empty
    answer. The registry reuses the ingest-job shape (`_register_ingest_job`). Which (verb,
    action) pairs the mod submits is 24.5 d16's rule, computed by `modgen`. {#r13}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1).** The line-JSON suites (`test_daemon_*`, `test_hook_wiring.py`) pass unchanged
   after the extraction. {#ac-1}
2. **AC-2 (R2, d3).** With `RMX_DAEMON_CLI_WORKERS=1` and `RMX_DAEMON_VERB_READ_WORKERS=4`, four
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
6. **AC-6 (R6, R7, d3).** A read verb queued behind a held `verb_read_pool` (a fixture verb that
   blocks on an event) past `deadline_s` answers 504 and never runs; a write verb whose op is held
   past its deadline answers 503 "not confirmed" and its effect lands after release; with
   `verb_write_pool` saturated by held writes, a read still answers 200 (lanes are separate). {#ac-6}
7. **AC-7 (R8, d10).** Two requests with one key and a `rmx_focus_note` body leave one note and two
   200s, the second `replayed: true`; the key survives a daemon restart; a repeat sent while the
   first is still held in its op answers 409 `InFlight` and, after release, a third repeat answers
   `replayed`. {#ac-7}
8. **AC-8 (R9).** Each request of AC-2 leaves one `cli.log` row with `invocation: "mod"`, the
   request's session, `hook_event` and `prompt_id` from its `caller`, `t_start_ms ≤ t_end_ms`, and
   `wall_ms ≥ queue_ms`; the row validates against 24.0's field set (the same schema test). {#ac-8}
9. **AC-9 (R10).** A daemon fast-exited mid-request (the existing invalidation fixture) gives the
   client a reset; the respawned daemon serves the socket again. {#ac-9}
10. **AC-10 (R11).** `rmx verb run rmx_focus_note --session S` with the daemon up and with it
    absent produces the same note and the same printed body; with a busy daemon, exit 3 and no
    catalog file opened. {#ac-10}
11. **AC-11 (d4 — r2 s6 a).** Five idle connections that send nothing hold no lane thread: a
    sixth client's verb answers within its budget with `RMX_DAEMON_VERB_READ_WORKERS=1`; the idle
    ones are closed at 30 s with a log line. {#ac-11}
12. **AC-12 (d8, d12b — r2 s6 d, e).** An in-host `snapshot_read` appears in the daemon's in-flight
    table while it runs and is dropped (504) past its deadline in the `cli_pool` queue; a verb that
    reads `verbs.CALLER` inside the lane sees the request's session (a test verb in a copied
    registry returns it). {#ac-12}
13. **AC-13 (R7, R13).** A synchronous request with `deadline_s: 60` is clamped to 25 (the row
    shows it); a fixture verb that sleeps 40 s submitted with `mode: "submit"` answers 202 within
    1 s, `rmx_job` answers `running` with each call returning within `wait_s`, then `done` with the
    result; after a daemon restart the same id answers the `unknown job` error. {#ac-13}

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
| `src/refmatrix/daemon.py` | `dispatch` + `dispatch_fn` (R1, d8), the two verb lanes, `http_socket_path`, bind + sun_path check (R3, R4), shutdown wiring (R10), identity `http_*` fields, idempotency ledger (R8) |
| `src/refmatrix/verbs.py` | `rmx_job` (R13); in-host short-circuit in `_call` / `require_daemon` / `snapshot_read` / `local_write` / `global_write` (R2); `run_request()` used by the host and `rmx verb run` |
| `src/refmatrix/cli.py` | `rmx verb run` (R11) |
| `src/refmatrix/telemetry.py` | the mod row fields (R9) |
| `docs/adr/0005-verb-host-http.md`, `docs/adr/0000-adr-overview.md`, `docs/INDEX.md` | R12 |
| `tests/test_task24_2_verb_host.py`, `tests/http_unix_support.py`, `tests/test_verb_parity.py` (`TRANSPORT_CLI`) | AC-1..AC-10 |

## Revision r2 (2026-10-20, ch-bsd r2 03c2d1f) {#rev-r2}

| finding | change |
|---|---|
| s6(a) request read on a pool thread | d4: one selector thread accepts and reads; lanes get complete requests; R5; AC-11 |
| s6(b) unbounded write wait starves reads | d3: separate read / write lanes, write wait bounded by `deadline_s` (503 "not confirmed"); R7; AC-6 |
| s6(c) idempotency key recorded only after success | d10 / R8: reserved while pending, 409 `InFlight` on repeat; AC-7 |
| s6(d) `snapshot_read` outside `dispatch` | d8: `dispatch_fn` through `cli_pool` with in-flight, deadline, fast-exit, bounded writer wait; AC-12 |
| s6(e) `CALLER` and `submit` | d12b: set inside the lane thread, stated; AC-12 |
| s7 rows did not join 24.0's | R9: 24.0 R2's field set (`t_start_ms` / `t_end_ms`, the `hook_event` vocabulary, `prompt_id` from the mod); AC-8 validates against it |
| m1 dead `global_write` short-circuit | R2: dropped |

## Revision r3 (2026-10-20, probe batch 2) {#rev-r3}

| finding | change |
|---|---|
| the engine aborts every mod fetch at 30 s | R7: synchronous `deadline_s` default and max 25; R13: submit-then-poll with a job lane and `rmx_job`; AC-13 |

