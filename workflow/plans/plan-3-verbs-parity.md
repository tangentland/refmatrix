---
gmd: "0.1"
id: plan-3-verbs-parity
title: "Every MCP tool is a verb; CLI and MCP are adapters; parity is a test"
tags: [plan, remediation, bsd]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-09-14
  bsd_findings: "#sk-3, #meh-3"
---

# Proposed Plan: Every MCP tool is a verb; CLI and MCP are adapters; parity is a test {#root}

**Date:** 2026-09-14
**Status:** Accepted
**Location:** `workflow/plans/plan-3-verbs-parity.md` — permanent home; stage is `metadata.status`.

rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: specifies -> [[task-3.1-plan-3-verbs-parity]]
rel: specifies -> [[task-3.2-plan-3-verbs-parity]]
rel: specifies -> [[task-3.3-plan-3-verbs-parity]]

## Context {#context}

BSD #sk-3: `verbs.py` has 10 `@verb`s while `mcp.py` exposes 30 tools; `rmx_recall_state`, `rmx_memory`, `rmx_locate`,
`rmx_task`, `rmx_where`, `rmx_search`, `rmx_ingest_status`, `rmx_queues`, and nine `rmx_bus_*` tools call daemon/handoff
directly. The `--session-start` widen and the `session/*` exclusion exist only in `cli.py:memory_recall`, so the MCP recall
behaves differently. The project's own rule (`project_verbs_layer_antidrift`) says capabilities go through verbs and schemas are
generated.

## Proposed Approach {#proposed-approach}

1. `verbs.memory_recall(root, *, query=None, recent=False, session_start=False, since=None, k=5, scope="both",
   exclude_mtypes=(), include_session=False, subject=None, kinds=(), degree=0, fuse=None) -> dict` owns: session-start default
   window + widen, session/* exclusion, scope merge with the global-rows filter, subject path. `cli.py:memory_recall` becomes
   rendering over the verb's rows; `mcp._t_memory_recall` calls the verb.
2. Migrate each direct-call tool to a verb (`recall_state`, `memory` (get/add/list/dedup/promote), `locate`, `task`, `where`,
   `search`, `ingest_status`, `queues`, `bus_*` as one `bus(op=…)` verb family or nine thin verbs — decision Q2).
3. `mcp.TOOLS` generated from `verbs.REGISTRY` (name, description, JSON schema from the signature) with an explicit
   per-verb `schema_overrides` for enums; `tests/test_verb_parity.py` asserts `set(TOOLS) == set(verbs)` and that each tool's
   handler IS the verb (identity), plus a CLI↔MCP behavior test for recall.

## Open Questions {#open-questions}

### Q1: Q1 One recall verb or keep CLI logic and call it from MCP? {#q1}
**Status:** RESOLVED

**Decision:** One verb. The CLI keeps only table/GMD/JSON rendering.
**Rationale:** see Decisions Log.

### Q2: Q2 Bus: one verb with an `op` enum or nine verbs? {#q2}
**Status:** RESOLVED

**Decision:** Nine thin verbs (`bus_pub`, `bus_read`, …). Tool names are user-facing and already stable; a mega-verb would need a second schema layer.
**Rationale:** see Decisions Log.

### Q3: Q3 Schema generation vs hand-written TOOLS? {#q3}
**Status:** RESOLVED

**Decision:** Generated from signatures + `schema_overrides`; the parity test fails if a tool has no verb or a verb has no tool.
**Rationale:** see Decisions Log.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Q1 One recall verb or keep CLI logic and call it from MCP? | One verb. The CLI keeps only table/GMD/JSON rendering. | 2026-09-14 |
| Q2 | Q2 Bus: one verb with an `op` enum or nine verbs? | Nine thin verbs (`bus_pub`, `bus_read`, …). Tool names are user-facing and already stable; a mega-verb would need a second schema layer. | 2026-09-14 |
| Q3 | Q3 Schema generation vs hand-written TOOLS? | Generated from signatures + `schema_overrides`; the parity test fails if a tool has no verb or a verb has no tool. | 2026-09-14 |
| Q4 | (r1 #bs-1) What does "the CLI twin calls the verb" mean, and how is it proven? | Two wiring classes in `verbs.CLI_WIRING`: `calls` (the click command invokes `verbs.<fn>` and renders — 23 twins) and `payload` (bespoke-routed surfaces: `context`/`query` replica-first reads, blocking `ingest` — build their daemon payload through `payload_context`/`payload_query`/`payload_ingest`). The gate records the call while the click command runs (`test_cli_twin_calls_its_verb`, `test_cli_routed_twin_builds_its_payload_through_the_verb_helper`); an existence check is no longer possible. | 2026-09-14 |
| Q5 | (r1 #bs-2) Which `k`, and how do exclusions stay honest? | The verb takes the CLI default: `k=10`, `query=None`. `PAIRING` covers every twin; a `no_twin` param that has a same-named click option must be a declared `SHAPE_DIFFERENCES` entry (multiple=True `()` vs None, nargs=-1, required argument) or the gate fails (`test_no_twin_exclusions_are_honest`). | 2026-09-14 |
| Q6 | (r1 #sk-5) CLI `--recent` shows session cards, the tool hides them — keep? | Keep, as a NAMED parameter: the CLI's non-hook modes pass `include_session=True`; hook modes (`--session-start`, `--stdin-json`) pass `False`; `--exclude-mtype` always wins. Covered by `test_cli_recent_passes_include_session_explicitly`. | 2026-09-14 |
| Q7 | (r1 #sk-4) The daemon-down fallback and the dense path in cli.py | One rule: `verbs.recent_rows(fetch, …)` (over-fetch, filter, widen) is called by the verb with the daemon op and by the CLI fallback with the reader; the dense path builds its payload via `payload_memory_recall` and annotates rows via `annotate_hit` (score/distance/fused — MCP rows carry them too). `test_cli_session_start_widens_with_the_daemon_down` covers the fallback. | 2026-09-14 |
| Q8 | (r1 #sk-7) Silent swallows in the verb layer | `memory_recall` returns `warnings: [str]`; a global store that does not answer is a warning on `scope=both`, fatal on `scope=global`; a failed context bundle is `context_error` on the row + a warning; the CLI prints warnings on stderr; `memory_partition` logs. | 2026-09-14 |
| Q10 | (r2 #b-1) The hub boundary | `_hub_rpc` is the ONE boundary: hub down, `ok:false`, or a socket timeout are a typed `VerbError` carrying the hub's words; `queues` and all ten bus verbs go through it; `_bus_verb`/`hub queues` render the ClickException. | 2026-09-14 |
| Q11 | (r2 #b-2) Busy is not absent, and no twin string-matches | `verbs.require_daemon` classifies with `discovery.daemon_status`: up / `VerbBusyError` / `VerbAbsentError`; `_call` and every verb that used a bare ping use it; a socket timeout on an op is `VerbBusyError`. CLI twins and the MCP `memory add` bootstrap fallback dispatch on the TYPE — only `VerbAbsentError` may open the store in-process. `federated_where`/`locate` report busy or absent stores in `skipped` instead of dropping them. | 2026-09-14 |
| Q13 | (r3 #b-1/#s-3/#m-5) Busy on the write and read paths | Writes: `handoff._promote_digest` (save-state's promote) classifies through `verbs.require_daemon` — busy is an error dict, only ABSENT opens the store in-process. `memory_partition` raises busy and keeps the project default on absent; `attach_context` names busy/absent. Reads: `memory get` and interactive `memory recall` fall through to the lock-free replica reader on busy OR absent with a stderr note; the hook modes degrade to an empty answer instead (plan-2 r5). `_call` treats any transport exception from `daemon.call` as busy. | 2026-09-14 |
| Q14 | (r3 #b-2) Skipped stores | Every fan-out (`federated_where` / `locate` / `query` / `concept`) returns `skipped: [{project, root, reason}]` from one `_live_roots()`; `rmx locate` prints each on stderr and says "no matches (N stores skipped)"; the hub's queue rows carry `daemon_busy` and render `busy`, never `down`. | 2026-09-14 |
| Q12 | (r2 #s-3) What the wiring gate proves | Three properties per twin: the verb is called with the root; the argv's options arrive as the verb's own parameters (bound against the real signature, compared to `CLI_INVOKE`'s expected kwargs); the CLI renders the verb's result (a canary string). `rmx_focus` now carries `dialogue`, `milestones`, `last_line`, `events_total` so `focus context` renders the verb's result, not the ring. | 2026-09-14 |
| Q9 | (r1 #sk-6/#bs-3) Test strategy for the 18 migrated verbs | Real: a spawned daemon on a tmp store (`task`, `memory`, `recall_state`, `ingest_status`, `where`, `search`, `locate`), the bus verbs on a real `Bus` + real `hub.rpc` socket with only the hub process replaced by `_MiniHub` (registered). This found bug-007 (stale cached replica). | 2026-09-14 |
| Q10 | (r4 #b-1) recall-state's daemon line | `compose_recall_state` classifies through `discovery.daemon_status`: `daemon = {running, busy, pid}`; the anomaly says busy when the pid is alive and not answering, stale only when the process is gone; the render's `busy pid` branch finally has a producer. | 2026-09-15 |
| Q11 | (r4 #b-2/#s-3/#s-4) Which calls are bounded, and what does op-level busy mean | Read actions of the `memory` verb (get/list/search) run under `MEMORY_READ_BUDGET_S` (10 s) with one attempt, then the CLI twins read the replica; `memory_recall` defaults to `timeout=30.0` (the MCP tool inherits it; the CLI passes its own budget; `None` is a deliberate no-bound); `_promote_digest` and the dense per-hit `memory_get` go through `_call(retries=0)`; `memory_partition` makes ONE `partition_list` attempt and raises busy when it does not answer — it guesses the project partition only for an ANSWERED error; `global_recall_rows` / `hub.global_call` carry `retries`. Amends Q13. | 2026-09-15 |
| Q12 | (r4 #m-6) A read on a busy store without a replica | `_read_store` raises a read-worded error ("no read replica yet … retry after the daemon's first snapshot"); the twins print "reading the replica" only after the replica opened. | 2026-09-15 |
| Q15 | (r5 #b-1) The twins call the verb | `rmx memory list` and `rmx memory search` route through `verbs.memory(action=…, partition=_resolve_partition(), timeout=remaining)` under `MEMORY_READ_BUDGET_S`, with the `get` twin's busy/absent → replica fallthrough; ONE op attempt (the held-writer simulation records exactly one `memory_iter` / `memory_search`). The bare `ping` gate is gone: a held writer answers ping, and the twins waited 190 s on it while the replica held the rows. | 2026-09-15 |
| Q16 | (r5 #s-2, amends Q12) A read never goes to the write proxy | `_read_store` on an UP daemon with no replica raises the one read-worded error ("no read replica yet … retry after the daemon's first snapshot") instead of returning `_store()` — the daemon WRITE proxy, whose first read raised "no lock-free reader … snapshot not built" after the twin had printed "reading the replica". Every twin prints "reading the replica" only after `_read_store()` returned. Proven on the held-writer simulation without a replica for get / list / search / recall. | 2026-09-15 |
| Q17 | (r5 #s-3, amends Q14) A fan-out names every store it did not hear from | `federated_query`: one attempt per store at `QUERY_OP_TIMEOUT_S` (20 s); a transport failure or an answered error → `skipped: {project, root, reason}`. The pooled fan-outs (`federated_where` 6 s, `federated_locate` 8 s) name every future still running at the deadline ("did not answer within Ns") and every per-leg failure `_where_one_project` reports (its 3 s `memory_search` on a held writer; the replica bundle); the global memory leg is bounded (3 s, `retries=0`) and said. `_locate_one_project` reads the replica only, so a held writer WITH a replica is served, not skipped — the test says so; the pool contract is proven with a helper that sleeps past a 1 s deadline. | 2026-09-15 |
| Q18 | (r5 #m-4) One partition probe per command | `verbs.memory_recall(partition=…)`: the CLI recall twin passes the partition it resolved under its budget and the verb probes `partition_list` only when none is given. The MCP tool gains `partition`; the parity gate lists it as carried by the `rmx` group (`-p`). The held-writer simulation counts the probes: one for `get`, one for `recall`. | 2026-09-15 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 3.1 | memory_recall verb owns recall semantics | — |
| 3.2 | Migrate the 20 direct-call tools to verbs | 3.1 |
| 3.3 | Generated TOOLS + parity test | 3.2 |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation check on every new test;
implementation summary per task under `workflow/implementation_summaries/`; then `@ch-bsd` over the plan's commit range —
remedy and re-review until the verdict is CLEAN; then the plan's `metadata.status` → `completed`.
