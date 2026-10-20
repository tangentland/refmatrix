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
| d1 | Inside the host, `_call`, `require_daemon`, `snapshot_read` and `local_write` consult `CALLER.daemon` (a handle the host sets, 24.2a's `Caller` plus `daemon`): same root ⇒ in-process dispatch; another root ⇒ the normal socket path | the deadlock and the self-ping disappear by construction, and the CLI / MCP paths are untouched (CALLER is None there) |
| d2 | In-process dispatch goes through ONE extracted method `Daemon.dispatch(op, args, deadline_s)`, which `_handle` also calls | the pool choice, deadline drop, in-flight table, heartbeat and fast-exit check are the line-JSON path's; a second copy would drift (two ways to do X) |
| d3 | Synchronous verbs run on two new lanes (jobs and polls have their own, d14): `verb_read_pool` (`RMX_DAEMON_VERB_READ_WORKERS`, default 4) for verbs / actions that do not write, `verb_write_pool` (`RMX_DAEMON_VERB_WRITE_WORKERS`, default 4) for `writes` ones; a verb thread only waits on op futures, never runs an op, and a write's wait is bounded by its `deadline_s` | no cycle: op pools never wait on the verb lanes; the observe writes (two per tool call) queued behind a long `bg_pool` op can no longer starve reads (r2 s6 b) |
| d4 | The HTTP server is stdlib, in a new module `refmatrix/httpsock.py` 24.3 reuses: ONE thread runs a `selectors` loop that accepts and reads every connection non-blocking (per-connection buffer, 30 s header+body deadline, shutdown-aware), parses the request with `http.server`'s parsing helpers, and submits only complete, parsed requests to a lane; the lane thread runs the verb and writes the response | an idle or slow client never holds a worker (r2 s6 a, bug-041's shape); no new dependency (fastapi/uvicorn are the optional `ui` extra); bounded lanes instead of ThreadingMixIn's unbounded threads |
| d5 | Routes: `POST /v1/verbs/<rmx_name>` only, generated from `VERBS` where `tier in ("store", "both")`; 404 / 405 otherwise | D3; the route list cannot drift from `VERBS` |
| d6 | `session` is a REQUIRED request field; the host seeds `CALLER(session=..., in_host=True)` and never runs the ladder | G1; ch-bsd b1 |
| d7 | A request naming another store (`root` / `project` resolving elsewhere) is refused 400 `VerbArgsError` ("use that store's socket") | a host serving other stores would open their writer in-process on absent (C4a) inside this daemon; the mod routes by discovery (24.5) |
| d8 | `snapshot_read` in-host goes THROUGH `dispatch`: `dispatch_fn(name, fn, partition, deadline_s)` submits `_read_with_fallback(d, partition, fn, private=True, writer_wait_s=<deadline left>)` to `cli_pool` with the same in-flight entry, deadline drop, heartbeat and fast-exit check as an op | one execution path for everything that touches the store in-process (d2); the writer wait is bounded (r2 s6 d) |
| d9 | `local_write` in-host raises `VerbError("in-host local_write")` | absent cannot happen for the host's own root; reaching it is a bug, said loudly |
| d10 | A write carrying `idempotency_key` is applied at most once, and the key is SETTLED ATOMICALLY WITH THE EFFECT, by the write's class (d15): a CATALOG write records the key (and its result) in an `idempotency_keys` table inside the SAME DuckDB transaction as the write, so after a crash "key present" means landed and "key absent" means safe to re-run; a RING / JSONL write stores its natural key (`row_uuid`, `tool_use_id`, or the idempotency key itself) in the record it appends and skips when that key is already there; a NATURAL write (set semantics) is harmless to repeat. While a keyed request runs, an in-memory reservation answers a repeat 425 `InFlight`. `NotConfirmed` is left only for the writes that can do none of these (d15's list) | the r2 design fsynced a separate `pending` marker before the write, so after a crash it could not tell a lost update from a landed one and refused both forever (r5, ch-bsd r4 s1) |
| d11 | The CLI gets one generic twin `rmx verb run <name> [--session S] [--json]` reading args JSON on stdin, sharing the host's request handler | D4's absent path spawns the PROJECT's rmx with exactly the host's semantics; one dispatcher for both |
| d12 | An ADR records the two-tier verb host (`docs/adr/0005-verb-host-http.md`), authored by ch-architect before GREEN | the daemon gains a second public surface and five new bounded lanes (d3, d14); that is an architectural decision, not a task detail |
| d12b | `CALLER` is set INSIDE the lane thread, by the submitted callable (`with verbs.caller(...)`), never in the accept thread: `ThreadPoolExecutor.submit` does not copy `contextvars`; ops submitted onward to `cli_pool` / `bg_pool` do not read `CALLER` (they resolve no session) | r2 s6 e: a context set in the submitting thread is invisible in the pool thread |
| d13 | Every SUBMITTED write (R13) carries an `idempotency_key`; a submit of a `writes` (verb, action) without one is 400 `VerbArgsError` | a job lives in memory, so after a fast-exit only the key can say whether the write happened (r4, ch-bsd r3 s2) |
| d14 | Four job lanes / waits, each bounded and separate: `verb_read_pool` / `verb_write_pool` (synchronous), `verb_job_read_pool` / `verb_job_write_pool` (submitted jobs, default 2 each), and `verb_wait_pool` (default 16) for `rmx_job` polls, which answers 503 at once when full | a 20 s poll must never hold a read worker (24.3 d8's reason), and a 180 s graph read must never queue a save-state behind it (r4, ch-bsd r3 s1) |
| d15 | Every `writes` (verb, action) declares how it is made idempotent, on `@verb(idempotent_by=…)` (per action): `"transaction"` (catalog writes; each daemon op it reaches records the key through ONE helper, `Store.record_idempotency(key, verb, result)`, inside its write transaction), a field name (`"row_uuid"`, `"tool_use_id"`, `"idempotency_key"`: ring / JSONL writes that store it and skip a duplicate), `"natural"` (set semantics: taxonomy add / remove, flags, sync enqueue / flush), or `None` = NOT CONFIRMABLE. At 3.7 + 24.2a the not-confirmable writes are those whose effect leaves the store's catalog and rings: `rmx_save_state` (memory-dir file, bridge ingest, promote), and any write that reaches ANOTHER store or the hub (`global_write` paths, `rmx_bus_*` writes); a parity test fails on an undeclared `writes` action and lists the `None` ones | one declaration per write, read by the host and checked by a test, instead of one ledger that cannot see the store's commit (r5) |
| d16 | The `idempotency_keys` table is a CATALOG fact like every other: its DDL is in `duckdb_catalog.CATALOG_DDL` (and the SQLite mirror in `store.py`'s `CATALOG_DDL`, whose shapes must match); every key write is ALSO a `facts.log` event of kind `idempotency`, carried in the EFFECT'S OWN post-commit `_log_events` batch (facts.log is appended after the DuckDB commit, as a plain file write, `Store._log_events`), so after a crash the key and the effect are in the log together or absent together, and `rebuild_index_from_log` replays keys alongside effects; the event carries the key's own `key_ts`, which dump and replay preserve (never the dump or replay time); `dump_catalog_to_log` emits the keys whose `key_ts` is younger than the 7-day retention; `replica_merge` merges the table by key (union, the earlier `ts` wins, never a duplicate). The check-and-insert happens INSIDE the op's own transaction (`INSERT … ON CONFLICT (key) DO NOTHING RETURNING`; no row returned ⇒ the effect is skipped and the recorded result answered), never as a host pre-check on the read path. A verb that makes several write ops keys each one `<key>#<op-index>`, so after a crash between them the first answers `replayed` and the second RUNS | facts.log is the store's authority: a key kept only in the catalog vanishes on a rebuild while its effect returns, making "absent ⇒ safe to re-run" false; the mirror and snapshot lag the writer; one key per verb would mark a half-done verb complete (r6, ch-bsd r5 s1) |

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
   "subject"?}}`. CLIENTS MAP AN ERROR BY `error.type`, NEVER BY STATUS: several types share a
   status (503 carries `VerbBusyError`, `NotConfirmed` and the full wait lane's busy), and the
   status is for HTTP-level tooling only (r5, ch-bsd r4 m2): {#r6}

   | raised | status | notes |
   |---|---|---|
   | `VerbArgsError`, missing `session`, foreign root (d7) | 400 | `type` names the class or `SessionRequired` |
   | `SessionUnresolved` | 400 | in-host it means the request lacked what the verb needs |
   | unknown verb / wrong method | 404 / 405 | |
   | `X-Rmx-Schema` ≠ the verb's hash | 409 | `SchemaMismatch`; body carries both hashes; the verb does not run |
   | idempotency key pending (d10) | 425 | `InFlight` (Too Early); `Retry-After: 2`; nothing runs |
   | a NOT-CONFIRMABLE write's key pending from before a restart (d10, d15), or a write job past its deadline (R13) | 503 | `NotConfirmed`, with the "not confirmed … may still complete / may have completed" wording |
   | `rmx_job` for an unknown or expired id | 410 | `UnknownJob` |
   | `verb_wait_pool` full | 503 | `VerbBusyError`, answered at once |
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
8. **R8 — idempotency (d10, d15).** Keys up to 128 chars. The host reads the verb's
   `idempotent_by` for the request's action and passes the key down: `"transaction"` → into every
   daemon op payload the verb makes, as `<key>#<op-index>` (d16), where `Store.record_idempotency`
   does the check-and-insert of `(key, verb, key_ts, result_json)` inside the op's own transaction
   and RETURNS the key's `idempotency` facts.log record, which the op adds to its own post-commit
   `_log_events` batch (never written by a separate `_log_event` call) (a conflict skips the effect and returns the
   recorded result; when every op of the request answered from a recorded key, the response is
   `200` with `"replayed": true`; a verb whose response
   differs from its op's result updates the row with its final result after the op, best-effort,
   and a replay whose row lacks it answers `{replayed: true, result: null, note: "applied; result
   not recorded"}`); a field name → into the verb, which skips a record whose field matches and
   answers `replayed`; `"natural"` → the verb simply runs; `None` → a durable `pending` marker
   (`.refmatrix/idempotency-pending.jsonl`, fsynced before the write, `done` / `released` after),
   and a key still `pending` after a restart answers `NotConfirmed` (d10), never re-run. The
   in-memory reservation answers 425 `InFlight` while a keyed request is running. Rows and markers
   are kept 7 days (pruned by the existing maintenance tick); the mod's outbox caps entry age at 3
   days (24.5 d10), below that retention. A failure to record is a `rmxd.log` line and the response
   carries `warnings: ["idempotency not recorded"]`. {#r8}
9. **R9 — one telemetry row per call (ch-bsd s4; r2 s7).** Each request appends a `cli.log` row in
   24.0 R2's field set, written by the same `telemetry` helper the shell rows use: `invocation:
   "mod"`, `cmd: "verb <name>"`, `hook_event` (24.0 R2's vocabulary, from `caller.hook_event`; a
   value outside it is recorded as `other` with the raw value in `hook_event_raw`), `session`,
   `prompt_id` (from `caller.prompt_id`, the mod's `<session>:<n>`), `agent_id`, `t_start_ms`
   (request complete on the selector thread), `t_end_ms` (response written), `queue_ms` (lane
   queue wait), `wall_ms` (`t_end_ms - t_start_ms`), `status`. 24.0's report reads these beside the
   shell rows. No argv, no args body. {#r9}
10. **R10 — fast-exit and respawn.** The HTTP server thread stops with the daemon: `_stop` closes
    the listener, in-flight verbs get the existing shutdown budget, all five lanes (two synchronous, two job, one wait) are drained by
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
    ...}`; the verb runs on `verb_job_read_pool` or `verb_job_write_pool` by its `writes`
    classification (d14), under the CALLER's `deadline_s` (≤ 600; the caller states it: 24.6's
    pre-compact save-state submits with 30), with the same `CALLER`, dispatch and error mapping.
    A write submit needs an `idempotency_key` (d13). A new store-tier verb `rmx_job(job_id: str,
    wait_s: float = 20.0)` (engine surface, read) runs on `verb_wait_pool` (d14), long-polls up to
    `wait_s` (max 20) and answers `{state: "running"}`, `{state: "done", result}` or `{state:
    "error", error: {type, message}}` (R6's error body). At the job's deadline a READ job is
    answered `error` `DeadlineExceeded` (it is abandoned); a WRITE job still running is answered
    `error` `NotConfirmed` with the "not confirmed within Ns … may still complete" wording, while
    the write runs on and its key settles in the ledger. Jobs are kept in memory for 10 min after
    they end; an unknown id (expired, or lost to a daemon restart) is `UnknownJob` (R6), never a
    silent empty answer: the client re-submits a keyed write with the same key (by d15 it then answers `replayed`, runs
    once because the key was never committed, or answers `NotConfirmed` for a not-confirmable
    write) and reports a read as lost. The registry reuses the ingest-job shape (`_register_ingest_job`). Which (verb,
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
7. **AC-7 (R8, d10, d15).** Two requests with one key and a `rmx_focus_note` body (a ring write,
   `idempotent_by="idempotency_key"`) leave one note and two 200s, the second `replayed: true`; the
   key survives a daemon restart (it is in the ring); the same with a `rmx_memory_add` body (a
   catalog write, `"transaction"`) leaves one memory row and one `idempotency_keys` row; a repeat sent while the
   first is still held in its op answers 425 `InFlight` and, after release, a third repeat answers
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
14. **AC-14 (R13, d13, d10 — kill mid-job).** For a CATALOG write job (`rmx_memory` promote): (a)
    SIGKILL with the daemon while the op is held AFTER the reservation and BEFORE its transaction
    commits (the old fsync point): after respawn `rmx_job` answers 410 `UnknownJob`, a re-submit
    with the same key RUNS the write, and the store holds exactly one effect; (b) SIGKILL after the
    commit, before the response: the re-submit answers `replayed` and the store still holds exactly
    one effect. For a RING write (`rmx_focus_observe` with a `row_uuid`) killed after its append:
    the re-run records nothing new. For a NOT-CONFIRMABLE write (`rmx_save_state`) killed mid-run:
    the re-submit answers `NotConfirmed` and does not run. A write submit without a key answers
    400. {#ac-14}
15. **AC-15 (d14, R13).** With `verb_read_pool` at 1 worker, three `rmx_job` polls waiting 20 s
    and a 180 s read job running leave a synchronous `rmx_context` answering 200; a save-state
    job queued while two 180 s read jobs hold the job-read lane starts at once on the job-write lane (`verb_job_write_pool`);
    a write job submitted with `deadline_s: 30` whose op is held answers `NotConfirmed` at 30 s
    and its effect lands after release; a read job past its deadline answers `DeadlineExceeded`.
    {#ac-15}
16. **AC-16 (d15, R6).** The parity test fails on a copied registry with a `writes` action lacking
    `idempotent_by`, and lists exactly the declared `None` actions; three 503 responses
    (`VerbBusyError`, `NotConfirmed`, a full wait lane) carry three distinct `error.type`s. {#ac-16}
17. **AC-17 (d16 — rebuild).** A keyed `rmx_memory_add` lands; `rebuild_index_from_log` runs (the
    daemon op); a re-submit with the same key answers `replayed` and the store holds ONE memory
    row; `dump_catalog_to_log` of a store with a 6-day-old and an 8-day-old key emits only the
    first; a replica merge of two slots holding the same key keeps one row. The 6-day / 8-day case
    runs through a `dump_catalog_to_log` AND a `rebuild_index_from_log`: both keys keep their
    original `key_ts` (the 6-day key still answers `replayed`, the 8-day key is gone). A crash
    injected between the op's DuckDB commit and its `_log_events` append (a fixture that kills
    the daemon there), followed by a rebuild: neither the effect nor the key is in the rebuilt
    catalog, and the re-submit runs the write exactly once. {#ac-17}
18. **AC-18 (d16 — multi-op).** A fixture verb making two keyed write ops is SIGKILLed between
    them; the re-submit answers the first op from its key (`<key>#0`, not re-applied) and RUNS the
    second (`<key>#1`); the store holds exactly one effect of each; a second re-submit answers
    `replayed`. A concurrent duplicate of a keyed op inside the writer (two transactions) leaves one
    effect: the `ON CONFLICT` inside the op decides, not a read-path check. {#ac-18}

## Test strategy {#test-strategy}

New `tests/test_task24_2_verb_host.py`; an HTTP-over-AF_UNIX client in
`tests/http_unix_support.py` (stdlib `http.client.HTTPConnection` with a connected unix socket),
never the live store (short `mkdtemp(dir="/tmp")` roots; 23.0's sandbox). Environment: the
idempotency ACs (AC-14, AC-17, AC-18) are pinned to DuckDB 1.5.3, the deploy venv's version; the
dev venv runs 1.5.2 (pre-existing skew), so the RED / GREEN logs record `duckdb.__version__` and
those ACs run under 1.5.3. The blocking fixture verb
of AC-6 is registered into a copied `VERBS` for the test only and listed in
`workflow/test_mock_registry.md`. RED run logged to `workflow/review-output/task24_2-red.log`.
{#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/httpsock.py` | new: the unix-socket HTTP server, request parsing, the R6 error map, the R9 row (shared with 24.3) |
| `src/refmatrix/duckdb_catalog.py` | `idempotency_keys` DDL in `CATALOG_DDL` (d16) |
| `src/refmatrix/store.py` | the SQLite `CATALOG_DDL` mirror; `Store.record_idempotency` (check-and-insert + the `idempotency` facts.log event, d15 / d16); `rebuild_index_from_log` replays and `dump_catalog_to_log` emits (≤ 7 days) `idempotency` events |
| `src/refmatrix/replica_merge.py` | the `idempotency_keys` merge rule (d16) |
| `src/refmatrix/daemon.py` | `dispatch` + `dispatch_fn` (R1, d8), the verb lanes, `http_socket_path`, bind + sun_path check (R3, R4), shutdown wiring (R10), identity `http_*` fields, idempotency ledger (R8) |
| `src/refmatrix/verbs.py` | `rmx_job` (R13); in-host short-circuit in `_call` / `require_daemon` / `snapshot_read` / `local_write` (R2); `run_request()` used by the host and `rmx verb run` |
| `src/refmatrix/cli.py` | `rmx verb run` (R11) |
| `src/refmatrix/telemetry.py` | the mod row fields (R9) |
| `docs/adr/0005-verb-host-http.md`, `docs/adr/0000-adr-overview.md`, `docs/INDEX.md` | R12 |
| `tests/test_task24_2_verb_host.py`, `tests/http_unix_support.py`, `tests/test_verb_parity.py` (`TRANSPORT_CLI`) | AC-1..AC-18 |

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

## Revision r4 (2026-10-20, ch-bsd r3 6d3575b) {#rev-r4}

| finding | change |
|---|---|
| s1 `rmx_job` polls held read workers; one FIFO job lane; R10 lane count | d14: separate job-read / job-write lanes and a wait lane for polls; R13: job deadline is the caller's, write jobs answer `NotConfirmed` at expiry; R10 names all five; AC-15 |
| s2 a submitted write lost to a restart could run twice | d13: every submitted write is keyed; d10: `pending` is durable, a pre-restart pending key answers `NotConfirmed` and never re-runs; R13: `UnknownJob` → re-submit with the same key; AC-14 kills mid-job |
| s5 409 meant two things | `InFlight` is 425; R6 rows for `InFlight`, `NotConfirmed`, `UnknownJob`, the wait-lane 503 |
| m1 leftovers | d1 and the files table drop `global_write`; R10 counts the lanes; files table AC-1..AC-15 |

## Revision r5 (2026-10-20, ch-bsd r4 08b1518) {#rev-r5}

| finding | change |
|---|---|
| s1 a pending key could not tell a lost update from a landed one | d10 / d15 / R8: catalog writes record the key in the same DuckDB transaction; ring / JSONL writes dedupe on a stored natural key (`@verb(idempotent_by=…)`); `NotConfirmed` only for the listed not-confirmable writes; retention 7 days above the outbox's 3-day cap; AC-14 crashes before and after the commit; AC-16 |
| m2 three meanings shared 503 | R6: clients map by `error.type`, never status; AC-16 |
| m4 stale wording | d12 "five new bounded lanes"; AC-15 "job-write lane" |

## Revision r6 (2026-10-20, ch-bsd r5 0109574) {#rev-r6}

| finding | change |
|---|---|
| s1(a) DDL in the wrong file | d16: `duckdb_catalog.CATALOG_DDL` (+ the SQLite mirror); files table lists `duckdb_catalog.py` |
| s1(b) a rebuild dropped keys but kept effects | d16: each key is also an `idempotency` facts.log event in the same transaction; rebuild replays it; dump keeps 7 days; `replica_merge` rule; AC-17 |
| s1(c) a read-path pre-check could read stale data | d16 / R8: check-and-insert inside the op's transaction (`ON CONFLICT … RETURNING`); AC-18 |
| s1(d) a two-op verb looked complete after one op | d16: one key per op, `<key>#<op-index>`; AC-18 |

## Revision r7 (2026-10-20, ch-bsd r6 34fedb1) {#rev-r7}

| finding | change |
|---|---|
| s1 facts.log is appended after the commit, not inside the transaction | d16 / R8: the key's event rides in the effect's own post-commit `_log_events` batch; `record_idempotency` returns the record instead of appending it; AC-17 adds a crash between commit and append, then rebuild, then exactly-once re-submit |
| m1 dump / replay re-dated keys | d16: `key_ts` preserved by dump and replay; AC-17's 6-day / 8-day case runs through a dump and a rebuild |
| (note) DuckDB 1.5.2 dev vs 1.5.3 deploy | test strategy pins the idempotency ACs to 1.5.3 |

