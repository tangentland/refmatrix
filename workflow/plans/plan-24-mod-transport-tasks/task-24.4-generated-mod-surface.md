---
gmd: "0.1"
id: task-24.4-generated-mod-surface
title: "Task 24.4: the verb-schema export becomes one committed artifact, and the mod's tool specs, route client, typed errors and test tables are GENERATED from it, with a TypeScript twin of classify_transport_error held to Python by a shared case table"
tags: [task, plan-24, mod, codegen, verbs, parity, transport, typescript]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.4: the generated mod surface {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20).
> Depends on: [[task-3.7-verb-it-backlog]] merged (its 8 verbs — `rmx_curate`, `rmx_taxonomy`,
> `rmx_curator`, `rmx_graph`, `rmx_canon`, `rmx_matrix`, `rmx_session`, `rmx_refine` — are part
> of the generated surface, read in the 3.7 clone for this spec), [[task-24.2a-hook-verbs-explicit-session]]
> (`surface` / `tier` / `writes` / `deferred`), [[task-24.2-daemon-verb-host-http]] and
> [[task-24.3-hub-http-discovery]] (the routes and the error map the client speaks).
> Feeds: 24.5 (imports the generated modules), 24.7 (the artifact ships with the release).

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: depends-on -> [[task-24.2a-hook-verbs-explicit-session]]
rel: depends-on -> [[task-24.2-daemon-verb-host-http]]
rel: depends-on -> [[task-24.3-hub-http-discovery]]
rel: implements -> [[exploration-claude-code-mod-transport#findings]]
rel: implements -> [[exploration-claude-code-mod-transport#verb-host-lead]]
rel: implements -> [[exploration-claude-code-mod-transport#distribution]]
rel: related-to -> [[feedback_converge_repeated_shapes]]

## Why {#why}

`verbs.py` exists because the CLI and the MCP server hand-built payloads for the same ops and
drifted (the parity audit of 2026-09-06). A TypeScript mod is a third surface in a second language:
written by hand, its tool names, argument names, defaults and error handling would drift the same
way, and no pytest would see it. The exploration's finding: tool registrations must be GENERATED
from `verbs.py`, with a parity test across the boundary. And transport errors (refused, missing,
path too long, timeout) now arise in TypeScript, where `classify_transport_error` cannot run, so
the busy / absent rule (busy never spawns, D4) needs a twin held to the original. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | The generator is `src/refmatrix/modgen.py` (`python -m refmatrix.modgen --write \| --check`), a sibling of `hooks.py`'s generator | the repo's rule for generated config: one generator, a `--check` that diffs installed against generated (as `install-hooks --check`) |
| d2 | Generated files are COMMITTED under `mod/src/generated/` and carry a header naming the generator and the schema hash | the engine loads `.ts` directly with no build step; a marketplace install must work from a tag with no Python run |
| d3 | One artifact, `mod/src/generated/verb-schema.json`, is `verbs.verb_schema()` (24.1) written out; every other generated file is rendered from the artifact, not from `VERBS` a second time | one source per run; a test asserts artifact == fresh export |
| d4 | Tool names are the verb names: `$.tool.register({ name: "rmx_context" })` lists as `mcp__refmatrix__rmx_context`, the name the `refmatrix` MCP server's tool has today | prompts, skills, agent overlays and memories that name `mcp__refmatrix__rmx_*` keep working through 24.8 |
| d5 | Only `surface == "model"` verbs become tool specs; every verb (both surfaces) becomes a route entry with its `tier` | the model calls tools; the mod's own hooks call engine verbs |
| d6 | The classifier twin is HAND-WRITTEN (`mod/src/transport.ts`) and held by a case table generated from `tests/fixtures/transport_errors.json`, which pytest runs against Python and `claude plugin test` runs against TypeScript | the twin classifies TS-side rejections no Python can raise; what can be shared is the cases and the expected class and words |
| d7 | No client-side race timer: the engine aborts EVERY `$.http.fetch` at 30 s (`aborted: no complete answer within 30000ms`) and a raced-away fetch is not cancelled ([[plan-24-mod-transport#probes-batch2]]); the bound is the server's `deadline_s ≤ 25` (24.5 R3) under the engine's 30 s, and the engine abort is classified BUSY ("not confirmed" for a write) | a race frees nothing and the hook budget pauses during `$` calls, so the engine's abort is the only client bound there is (r3) |
| d8 | The case table's TypeScript inputs come from a recorded probe, not from guesses | the types declare `$.http.fetch`'s resolution, not its rejection shapes; the twin may only match what the engine actually throws |
| d9 | `claude plugin validate` and `claude plugin test` are build gates run from pytest; a missing `claude` binary is a FAILURE naming the gap, never a skip | "ALL tests run"; the cross-language half of the parity gate cannot be optional |
| d10 | The mod's directory is `mod/` at the repo root (D5), its plugin name `refmatrix` | D5's one source; the name makes the `mcp__refmatrix__` prefix (d4) |

## Requirements {#requirements}

1. **R1 — layout (the generated part).** `modgen --write` renders: {#r1}
   - `mod/src/generated/verb-schema.json` — the export, byte-equal to `verb_schema()`;
   - `mod/src/generated/verbs.ts` — `SCHEMA_HASH`, `VERB_HASHES: Record<string, string>`,
     `TOOLS: readonly ToolSpec[]` (`name`, `description`, `inputSchema` = the verb's schema,
     `isDeferred` = `deferred`), `ROUTES: Record<string, { tier: "store" | "hub" | "both";
     surface: "model" | "engine"; writes: boolean | readonly string[]; hash: string; timeouts:
     Record<string, number | null>; modes: Record<string, "sync" | "submit"> }>`. `timeouts` is
     the verb's declared `@verb(timeouts=…)` (24.2a R13); `modes` is computed from it per action
     (`"*"` for a verb without actions): `submit` when the timeout is over 25 or null, else
     `sync` — the one place 24.5 d16's rule is evaluated;
   - `mod/src/generated/client.ts` — `callVerb($, target, name, args, opts)` where `target` is
     `{ socketPath }`, `opts` = `{ session, caller?, deadlineS?, idempotencyKey? }` (`deadlineS` capped at 25);
     POSTs 24.2 R5's body to `http://rmx/v1/verbs/<name>` with `X-Rmx-Schema`, awaits the fetch
     (no race, d7), parses 24.2 R6's body, and returns `{ ok: true, result }` or throws
     a typed error from `errors.ts`. For a `submit` (verb, action) it sends `mode: "submit"` (with
     `idempotencyKey`, REQUIRED for a write: the client generates one when the caller gave none),
     expects `202 { job_id }`, then polls `rmx_job(job_id, wait_s: 20)` until `done` / `error`
     (each fetch under 25 s), up to the action's timeout; on `UnknownJob` it re-submits a keyed
     write ONCE with the same key (24.2 R13) and reports a read as lost; a 425 `InFlight` waits
     `Retry-After` and retries;
   - `mod/src/generated/errors.ts` — `VerbArgsError`, `SessionRequired`, `SessionUnresolved`,
     `SchemaMismatch` (409, with both hashes), `InFlight` (425), `NotConfirmed` (503, the "may still
     complete / may have completed" wording), `UnknownJob` (410), `HubJobUnsupported` (422, 24.3
     d14), `VerbBusyError`, `VerbAbsentError` (a dependency, with `subject`), `VerbError`,
     `HostError` (500), and `TransportAbsent` / `TransportBusy` /
     `TransportUndialable` (from the twin), each with `status`, `type`, `message`;
   - `mod/src/generated/transport_cases.ts` and `discovery_cases.ts` — the case tables (R4, and
     24.3 R3's cwd table).
   Each starts with `// GENERATED by python -m refmatrix.modgen from verb-schema.json <hash> — do
   not edit`. A generated `ToolSpec.description` over 2,048 characters (the engine's cap on what the
   model reads) fails generation naming the verb. {#r1-list}
2. **R2 — `--check`.** Exit 0 when every generated file equals a fresh render, else exit 1 with a
   unified diff per file; `scripts/lint-gmd.sh`'s neighbour `scripts/check-generated.sh` runs it
   with `rmx install-hooks --check`. {#r2}
3. **R3 — the twin.** `mod/src/transport.ts` exports `classifyTransportError(err, { op, socketPath,
   write }): TransportAbsent | TransportBusy | TransportUndialable`. The engine throws a
   `HooksError` with NO `code`, so the twin parses `err.message` (r3, [[plan-24-mod-transport#probes-batch2]]):
   `/ failed: (E[A-Z]+): /` gives the errno, and `/aborted: no complete answer within (\d+)ms/` the
   engine abort. Five shapes, with Python's words: {#r3-list}
   - `ENOENT`, `ECONNREFUSED` → absent "not running … found no listening socket";
   - `ENAMETOOLONG` → undialable (NEVER absent: absent licenses the D4 spawn);
   - the engine's 30 s abort → busy "did not answer within 30s", plus "the write is not confirmed
     … may still complete" when `write`;
   - any other errno (reset, broken pipe) or an unparseable message → busy naming the message;
   - a response that is not 24.2's JSON → busy naming it.

   An HTTP response with 24.2's body is never classified here: a status means the host answered
   (24.2 R6 owns it). {#r3}
4. **R4 — the case table.** `tests/fixtures/transport_errors.json`: rows `{case, py: {exc,
   args}, ts: {rejection, from_probe}, expect: {class, words: [...]}}` for missing, refused,
   too-long, engine abort (read and write), an unknown errno, and a non-JSON body. The `ts`
   cells of the first four are the probe's EXACT strings, e.g. `{"name": "HooksError", "message":
   "refmatrix: $.http.fetch(http://rmx/v1/verbs/rmx_context) over <socketPath> failed: ENOENT:
   ENOENT: Was there a typo in the url or port?"}` and `{"name": "HooksError", "message": "…
   aborted: no complete answer within 30000ms"}` (with the probe's plugin and path replaced by
   the mod's; the replacement is the only edit). pytest constructs each `py` exception
   and asserts `classify_transport_error`'s class and that each `words` fragment appears; the TS
   test feeds each `ts.rejection` (an object as the probe recorded it) to the twin with the same
   assertions. {#r4}
5. **R5 — the probe (P-fetch).** ANSWERED for missing, refused, a 124-byte path and the 30 s
   abort by batch 2 ([[plan-24-mod-transport#probes-batch2]]); the record is copied into
   `eval/mod_probe/fetch_rejections.json`. Still to run: a regular file, a reset, and paths of
   exactly 101 and 104 bytes. The original method: a scratch mod under `claude --plugin-dir
   <scratch>` in a scratch project (never this repo's settings) calls `$.http.fetch(url, {
   socketPath })` against: a path with no file; a regular file; a socket bound but not listening;
   a path of 101, 104 and 110 bytes; a server that accepts and never answers (stopped by the
   race); a server that resets. It records each rejection's `name`, `message` and own keys into
   `eval/mod_probe/fetch_rejections.json` (committed: it holds no prompt and no user data) with
   the Claude Code version (`$.session.version()`). The `ts.rejection` cells of R4 are copied from
   it. The probe also records the largest `socketPath` the engine accepts (the types say "near 100
   B"), which 24.5 compares with 24.2's `http_socket_bytes`. {#r5}
6. **R6 — the parity gate, extended.** `tests/test_verb_parity.py` asserts: every
   `surface == "model"` verb has a `TOOLS` entry with an equal `inputSchema`; every verb has a
   `ROUTES` entry with its `tier` / `surface` / `writes` / hash; `modgen --check` exits 0. A verb
   added to `verbs.py` without a regenerate fails the build here. {#r6}
7. **R7 — the TS gates.** `tests/test_task24_4_mod_gates.py` runs `claude plugin validate mod`
   and `claude plugin test mod` as subprocesses, output captured to
   `workflow/review-output/mod-validate.log` / `mod-test.log`, and fails on a nonzero exit or a
   missing `claude` (the message names `workflow/development_resources.md`, where the dev
   dependency is recorded). {#r7}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1, R2).** On the tree, `modgen --check` exits 0; after adding a throwaway verb to a
   copied registry (the test's, via `modgen.render(registry)`), the render differs in
   `verb-schema.json`, `verbs.ts` (a new tool for a model verb, none for an engine verb) and the
   hash header. RED at base (no generator). {#ac-1}
2. **AC-2 (R1).** `TOOLS` holds exactly the model verbs; every description ≤ 2,048; `ROUTES` has
   every verb, `rmx_focus_observe` as engine / store / writes, `rmx_where` as model / hub;
   `ROUTES.rmx_graph.modes.recall == "submit"` and `.describe == "sync"`, `rmx_save_state` is
   `submit` (null timeout), matching 24.5 R3's table. `client.ts` under `claude plugin test`, with
   `http.fetch` answered beneath: a `submit` call sends `mode: "submit"` and a generated key, gets
   202, polls `rmx_job` until `done` and returns the result; a 410 `UnknownJob` on a write leads to
   exactly one re-submit with the SAME key; a 425 is retried after `Retry-After`; each status of
   24.2 R6 maps to its `errors.ts` class (409 → `SchemaMismatch`, 425 → `InFlight`, never the
   other). {#ac-2}
3. **AC-3 (R3, R4, R5).** pytest's Python half and `claude plugin test`'s TS half both pass over
   the same case table; `eval/mod_probe/fetch_rejections.json` exists with the engine version, and
   every `ts.rejection` in the table equals a probe record. A table row whose TS class differs from
   its Python class fails both halves' shared assertion that the table is internally consistent.
   Because the `ts` cells are COPIED from the probe, equality alone proves nothing about the twin
   (r2 m3): the `expect` column is written from Python's rules BEFORE the probe values are pasted
   (its commit precedes the probe's), and a mutation run over a copy of `transport.ts` (swap the
   absent / undialable branches; classify the engine abort as absent; drop the write wording) must fail the
   TS half for each mutation. {#ac-3}
4. **AC-4 (R6).** Removing one model verb's `TOOLS` entry from the generated file (a copy) fails
   the parity gate naming the verb. {#ac-4}
5. **AC-5 (R7).** `claude plugin validate mod` exits 0 on the generated surface plus 24.5's
   module (24.4 lands a minimal `register` that imports the generated modules and registers
   nothing, so validate has a module to read). {#ac-5}

## Test strategy {#test-strategy}

`tests/test_task24_4_modgen.py` (AC-1, AC-2, AC-4, the Python half of AC-3),
`tests/test_task24_4_mod_gates.py` (AC-5, the TS half, and AC-3's mutation run over copies of `transport.ts`), `mod/tests/transport.test.ts` (the twin
over `transport_cases.ts`, using `test` / `expect` from `claude-code/testing`). The registry copy in
AC-1 / AC-4 is a fixture, listed in `workflow/test_mock_registry.md`. RED first, logged to
`workflow/review-output/task24_4-red.log`. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/modgen.py` | new: render / write / check (R1, R2) |
| `mod/.claude-plugin/plugin.json`, `mod/hooks/hooks.json`, `mod/src/index.ts` | the minimal loadable plugin (AC-5); 24.5 fills `index.ts` |
| `mod/src/generated/*` | generated, committed (R1) |
| `mod/src/transport.ts`, `mod/tests/transport.test.ts` | the twin and its test (R3) |
| `tests/fixtures/transport_errors.json`, `eval/mod_probe/` | the case table and the probe (R4, R5) |
| `scripts/check-generated.sh` | runs `modgen --check` and `install-hooks --check` (R2) |
| `tests/test_verb_parity.py`, `tests/test_task24_4_modgen.py`, `tests/test_task24_4_mod_gates.py` | R6, R7, AC-1..AC-5 |
| `workflow/development_resources.md`, `workflow/test_mock_registry.md` | the `claude` dev dependency; the registry-copy fixture |

## Revision r2 (2026-10-20, ch-bsd r2 03c2d1f) {#rev-r2}

| finding | change |
|---|---|
| m3 AC-3 passed by construction (cells copied from the probe) | AC-3: `expect` written before the probe values; a three-mutation run over `transport.ts` must fail the TS half |

## Revision r3 (2026-10-20, probe batch 2) {#rev-r3}

| finding | change |
|---|---|
| fetch failures are a `HooksError` with the errno only in the message | R3 parses the message; R4 uses the probe's exact strings |
| the engine aborts any fetch at 30 s; a race does not cancel it | d7: no race; the abort is a fifth shape, busy / not confirmed; client `deadlineS` capped at 25 |
| P-fetch answered in part | R5: answered cases recorded; regular file, reset, 101 / 104 bytes still to run |

## Revision r4 (2026-10-20, ch-bsd r3 6d3575b) {#rev-r4}

| finding | change |
|---|---|
| s3 `ROUTES` had no `modes`; `client.ts` could not submit or poll | R1: `timeouts` and computed `modes` in `ROUTES`; `client.ts` submit / 202 / poll, keyed re-submit on `UnknownJob`, 425 retry; AC-2 |
| s5 `InFlight` collided with 409 | R1 `errors.ts`: `InFlight` 425, plus `NotConfirmed`, `UnknownJob`, `HubJobUnsupported`; AC-2 maps each status to one class |

