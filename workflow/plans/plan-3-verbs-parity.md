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
| Q9 | (r1 #sk-6/#bs-3) Test strategy for the 18 migrated verbs | Real: a spawned daemon on a tmp store (`task`, `memory`, `recall_state`, `ingest_status`, `where`, `search`, `locate`), the bus verbs on a real `Bus` + real `hub.rpc` socket with only the hub process replaced by `_MiniHub` (registered). This found bug-007 (stale cached replica). | 2026-09-14 |

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
