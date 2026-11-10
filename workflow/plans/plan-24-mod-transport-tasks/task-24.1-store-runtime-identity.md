---
gmd: "0.1"
id: task-24.1-store-runtime-identity
title: "Task 24.1: every daemon start records the store's runtime identity (the rmx it runs, version, verb-schema hash per verb, its sockets) in one atomic file the mod reads without Python"
tags: [task, plan-24, mod, identity, daemon, verbs, schema-hash]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.1: the store's runtime identity {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20).
> Depends on: — (independent of 3.7: the hash covers whatever `VERBS` holds when the daemon starts).
> Feeds: 24.2 (adds the HTTP socket fields), 24.3 (discovery answers this record), 24.4 (the
> exported schema is the same function), 24.5 (handshake + the D4 absent-spawn binary).

rel: part-of -> [[plan-24-mod-transport]]
rel: implements -> [[plan-24-mod-transport#decisions]]
rel: implements -> [[exploration-claude-code-mod-transport#verb-host-absent]]
rel: implements -> [[exploration-claude-code-mod-transport#distribution]]
rel: related-to -> [[project_hub_version_handshake]]
rel: related-to -> [[feedback_prefer_existing_infra]]
rel: related-to -> [[feedback_deploy_tree_is_the_runtime]]

## Why {#why}

D4 says an absent daemon is replaced by the PROJECT's `rmx`, never PATH's; D5 says the mod
registers only tools whose schema matches what the store's daemon runs. Both need an answer to
"what does this store run?" that survives a hub outage and a dead daemon, and that a TypeScript
module with no Python can read. The pieces exist: `upgrade.runtime_identity()` (which tree the
interpreter runs), `launchctl._rmx_path()` (the `$RMX_BIN` / argv[0] resolver every plist writer
uses, never `which rmx`), and `daemon._process_identity()` (what ping reports). Nothing writes them
down. This task writes them, once per daemon start, beside the daemon's own socket. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | The file is `<store>/.refmatrix/identity.json` (the store dir, beside `rmxd.sock` / `rmxd.pid`) | per-store, survives the hub; the parent-walk that finds `.refmatrix/` finds it; no new directory |
| d2 | The schema export (`verbs.verb_schema()`) and its hashes are introduced HERE, not in 24.4 | the hash must exist the day the daemon records it; 24.4 writes the same export to an artifact, so there is one function |
| d3 | A hash per verb AND one over all verbs | D5 says tools "whose schema differs are not registered": that needs per-verb comparison; the whole-set hash is the fast equality check |
| d4 | The file is never deleted on stop; a graceful stop adds `stopped_at` | D4's fallback reads it exactly when no daemon runs; a crash leaves no `stopped_at`, which tells the mod "crashed" from "stopped" |
| d5 | `rmx_bin` comes from `$RMX_BIN`, else `launchctl._rmx_path()`; a failure records `null` + `rmx_bin_error`, never a guess | the one resolver (bug-028, task 4.6); a missing binary must make the mod's spawn refuse visibly, not run PATH's |
| d6 | A read verb `rmx_store_identity` and a CLI twin `rmx daemon identity [--json]`; 24.2a marks it `surface="engine"` when its `@verb` fields land (until then it is an ordinary model tool, which is harmless) | D3: the HTTP host serves verbs only, so the handshake's live read is a verb, not a side endpoint |

## Requirements {#requirements}

1. **R1 — the export.** `verbs.verb_schema() -> dict` returns
   `{"format": 1, "verbs": [{name, description, schema, defaults, aliases}, ...]}` sorted by
   `name`, JSON-safe (a default that is not JSON-serializable is rendered by `repr` and the test
   lists which). `verbs.verb_schema_hashes() -> (all_hash, {name: hash})`: `sha256` hex over
   `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, the per-verb hash
   over that verb's entry, the whole hash over the full export. Pure functions of `VERBS`; no I/O.
   24.2a's new `@verb` fields (`surface`, `writes`, `tier`, `deferred`) join the entry when they
   land, and therefore the hash. {#r1}
2. **R2 — the record.** `daemon.write_identity(d)` writes, at `serve_forever` right after the
   `rmxd.sock` bind succeeds:
   `{format: 1, pid, started_at (UTC ISO ms), started_epoch, version, rmx_bin, rmx_bin_source
   ("RMX_BIN" | "argv0" | null), rmx_bin_error, code_path, dev_tree, dev_reason, identity_error,
   python (sys.executable), store_root, project_root, store_name, socket, verb_schema_hash,
   verb_hashes, verb_count, http_socket: null, http_error: null}`. `code_path` / `dev_tree` /
   `dev_reason` / `identity_error` reuse `_process_identity()` (one computation, the one ping
   serves). `http_*` are filled by 24.2. {#r2}
3. **R3 — atomic, readable without refmatrix.** Write to `identity.json.tmp.<pid>`, `fsync`,
   `os.replace`, mode `0o600` (the socket's own permission). Plain JSON, UTF-8, one object; no
   field requires Python to interpret. A write failure is logged to `rmxd.log` and to the
   daemon's stderr log as one line naming the path and errno, and the daemon keeps serving (the
   record is for clients; the line-JSON socket does not depend on it). {#r3}
4. **R4 — stop.** The graceful stop path (the `finally` of `serve_forever`, after the store
   closes) rewrites the file with `stopped_at` / `stopped_epoch` and the same `pid`; `fast-exit`
   (`os._exit(2)`) writes nothing. A daemon that starts finds a predecessor's file and replaces it
   whole; nothing merges. {#r4}
5. **R5 — the verb and its twin.** `@verb("rmx_store_identity", ...)`: reads `identity.json`,
   adds `live: {up, busy, pid, heartbeat_age_s}` from `discovery.daemon_status(root, retries=0)`
   (or, inside the 24.2 host, from the host's own process: up, its pid, the heartbeat age), and a
   `consistent` flag (`file.pid == live.pid` while up). Missing file → `VerbAbsentError` when no
   daemon is up ("this store has never recorded an identity"), a plain `VerbError` naming the path
   when one is up (a daemon that failed R3). CLI: `rmx daemon identity [--json]`, a `calls` twin in
   `CLI_MAP`. {#r5}
6. **R6 — ping carries the hash.** `_op_ping` adds `verb_schema_hash` (computed once with
   `_process_identity`), so `hub._daemon_identity` and `rmx daemon status` can compare a live
   daemon's verbs to the CLI's without reading the file. {#r6}
7. **R7 — no `which`.** A test greps `daemon.py` / the new code for `shutil.which("rmx")` and
   `which rmx`; none. {#r7}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1).** `verb_schema()` is byte-identical across two calls and two interpreter runs;
   changing one verb's default (a monkeypatched copy of the registry, not the real verb) changes
   that verb's hash and the whole hash and no other verb's hash. RED at base (no function). {#ac-1}
2. **AC-2 (R2, R3).** A daemon started under a short `mkdtemp()` root with `RMX_BIN` set to a
   fixture executable writes `identity.json` whose `rmx_bin` equals it, `rmx_bin_source ==
   "RMX_BIN"`, `pid` equals `rmxd.pid`, `verb_schema_hash == verbs.verb_schema_hashes()[0]`, mode
   `0o600`; `json.load` of the file under `python3 -I -c` (no refmatrix on the path) succeeds.
   With `RMX_BIN` unset and argv[0] not an rmx executable, `rmx_bin` is null and `rmx_bin_error`
   names `RMX_BIN`. RED at base. {#ac-2}
3. **AC-3 (R3).** With the store dir made read-only for the tmp file (a fixture that pre-creates
   `identity.json.tmp.<pid>` as a directory), the daemon still answers ping and `rmxd.log` holds
   one line naming the path. {#ac-3}
4. **AC-4 (R4).** `rmx daemon stop` leaves the file with `stopped_at`; a fast-exit (the existing
   fast-exit test fixture) leaves it without. {#ac-4}
5. **AC-5 (R5).** `rmx_store_identity` via `VERBS[...].run` returns the file plus `live.up=True`
   and `consistent=True`; with the daemon stopped, `live.up=False` and the file still answers; with
   no file and no daemon, `VerbAbsentError`. `rmx daemon identity --json` prints the same dict. {#ac-5}
6. **AC-6 (R6, R7).** `daemon.call(root, "ping")["result"]["verb_schema_hash"]` equals the file's;
   the `which` grep is empty. {#ac-6}

## Test strategy {#test-strategy}

New `tests/test_task24_1_store_identity.py`. Daemon tests use the existing short-root fixture
(`make_daemon`/`mkdtemp(dir="/tmp")`, macOS `sun_path`), never the live store. AC-1 copies `VERBS`
into a local dict and patches `verbs.VERBS` for the test only (registered in
`workflow/test_mock_registry.md` as a registry copy, not a mock of the function under test). RED
run logged to `workflow/review-output/task24_1-red.log`. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/verbs.py` | `verb_schema()`, `verb_schema_hashes()`; `rmx_store_identity` verb; `CLI_MAP` row (R1, R5) |
| `src/refmatrix/daemon.py` | `IDENTITY_NAME`, `write_identity`, call after bind, `stopped_at` on graceful stop, ping field (R2-R4, R6) |
| `src/refmatrix/cli.py` | `rmx daemon identity [--json]` (R5) |
| `tests/test_task24_1_store_identity.py` | AC-1..AC-6 |
| `tests/test_verb_parity.py` | the new twin is walked like every other |
