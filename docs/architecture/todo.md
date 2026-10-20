---
gmd: "0.1"
id: refmatrix/architecture-todo
title: "Architecture Gap Tracking — refmatrix"
tags: [architecture, todo, gaps, refmatrix]
---

# Architecture Gap Tracking {#root}

Authoritative gap surface, curated by @ch-gap-master. Seeded 2026-09-14 from the ch-bsd
end-to-end audit ([[bsd-0661-e2e-memory-bridge]]).

## Status Vocabulary {#status}

| Status | Meaning |
|--------|---------|
| Deferred | Blocked by a named, concrete dependency |
| Resolveable | Can be addressed now with existing infrastructure |
| Planned | Task defined, scheduled in a plan |
| Integrated | Shipped and verified in source |

## Open Gaps {#open-gaps}

| ID | Status | Description | Dependencies | Source Ref | Decision Ref |
|----|--------|-------------|--------------|------------|--------------|
| G1 | Shipped (plan 1 completed 2026-09-14, ch-bsd r5 CLEAN-on-bookkeeping) | Deploy venv imports the dev tree; no deploy runtime | — | bsd #bs-2 | plan 1 |
| G2 | Shipped (plan 4 tasks 4.1/4.2, 2026-09-14). Plan-4's latest audit, ch-bsd r4 at ffed3df ([[bsd-plan4-daemon-resilience-r4-ffed3df]]), names no open finding against 4.1/4.2; plan-4 stays `in-progress` on the supervision findings listed under G3, owned by W1-a ([[plan-review-2026-10-14#t11-folded-waves]]) | `learn_from_grep` (a read) upserts entities unguarded; entities index not repaired on fast-exit | — | bsd #bs-3 | plan 4 |
| G3 | Shipped (plan 4 task 4.3, 2026-09-14). Open from ch-bsd r4 at ffed3df ([[bsd-plan4-daemon-resilience-r4-ffed3df]]; r4 #b-1 closed by bug-028): #s-2 `binary_identity` lets an unknown binary pass the dev-tree refusal; #s-3 the stop grace reaches 3 of 7 stop paths; #m-5 `install(allow_dev=)` has no CLI caller; #m-6 the session-indexer plist lacks `ExitTimeOut`; #s-4 (tests write the live `hub.log`) expected closed by 23.0, to be confirmed with a ledger line. All owned by W1-a, together with G9 ([[plan-review-2026-10-14#t11-folded-waves]]) | Hub watchdog SIGKILLs a daemon reconnecting to an evicted model worker | — | incident 2026-09-14 | plan 4 |
| G4 | Shipped (plan 5 r3, 2026-09-15; ch-bsd r3: 0 BULLSHIT / 0 SKETCHY) | Memory bridge counts every skip (non-GMD, unparseable, index files); ONE bridge (`ingest-gmd --as-memory`; `memory sync-disk` is a thin alias kept for the fleet's p20-0 compiler, deferral row); busy ≠ absent at the write control point incl. the boot window | — | bsd #bs-1 → r3 | plan 5 |
| G5 | Shipped (plan 2, 2026-09-14). Plan-2's latest audit, ch-bsd r9 at ffed3df ([[bsd-plan2-hooks-reproducible-r9-ffed3df]]), leaves three findings open, none on the installed-vs-generated hook check itself: #s-3 memory WRITES resolve their partition from a lagging replica (rides 23.5); #s-2 the rerank spends the global leg's budget and the hook blames the daemon, and #m-4 the degrade line reports the 1.5 s slice as the budget (both ride 19.1). r9 #b-1 closed by bug-025; #m-5 registered. Owned by W1-c ([[plan-review-2026-10-14#t11-folded-waves]]) | Installed hooks ≠ generated hooks; PreCompact silences bridge failure | — | bsd #bs-4 | plan 2 |
| G6 | Shipped (plan 3 tasks 3.1-3.3: 82bbc2b, merged 8ba4799). Plan-3's latest audit, ch-bsd r7 at e0b7df6 ([[bsd-plan3-verbs-parity-r7-e0b7df6]]), was DIRTY with #b-1 (both `skipped` producer legs sit above a `_replica_bundle` that never raises), #b-2 (`memory promote` still 180.2 s on the global write), #s-3 (`ui/server.py` drops `skipped`; renderer duplicated), #s-4 (`tests/test_plan3_remedy_r6.py` unregistered), #m-5 (promote does not subtract the partition probe), #m-6 (no round-7 decisions row; Q17 unamended). The round-8 remedy (0e3002f, merged 273cc16) answers them and is NOT yet audited. The r8 audit and task 3.4 (internal-CLI allowlist) are W1-b ([[plan-review-2026-10-14#t11-folded-waves]]) | 30 MCP tools vs 10 verbs; session-start widen only in CLI | — | bsd #sk-3 | plan 3 |
| G7 | Planned | Stale deferrals: ingest_gmd/store/duckdb_view/embedder/sync docstrings | — | bsd #bs-5 | plan 6 |
| G8 | Planned | README 0.961 has no committed artifact; ARCHITECTURE.md lists 24/80 commands | — | bsd #sk-4, #meh-1 | plan 6 |
| G9 | Done 2026-10-19 (closed as bookkeeping by task 4.5 R6) | orderly launchd service spawn-loops behind a manual daemon (11k runs) **DONE (task 4.4):** a supervised start adopts an unsupervised live daemon instead of exiting 1 into the KeepAlive loop (`Daemon._adopt_unsupervised`, `tests/test_daemon_adopt.py`, two tests); plan-4 r1 verified orderly adopted with launchd `runs` static for 30 min; r2's residual (the `RMX_SUPERVISED` gate missing from 2/8 plists) closed in r3, and every plist is drift-checked by `launchctl.check`. Not a real open defect — the row had never been flipped. | — | incident 2026-09-14 | plan 4 task 4.4; [[task-4.5-r4-remedy]] R6 |
| G10 | Deferred | Linux supervisor (systemd user unit) not implemented | a Linux deploy target | launchctl.py:322 | — |
| G11 | Planned | `--like GLOB` is a selector on 5 write commands only (`protect`/`noise`/`forget`, `memory reclassify`); user 2026-09-15: make it universal — every read surface (`list entities`, `query`, `context`, `neighbors`, `top`, `co-occur`, `memory list/search/recall`, `locate`) as a PRE-filter (candidate set) and a POST-filter (rows), through the verbs so MCP gets it | after the plan-2/3/4/5 BSD loops close | user request | plan 7 (to write) |
| G12 | Open | the project's own index has no code entity or `defines` edge for `Daemon._snapshot_catalog` (`rmx query "defines:_snapshot_catalog"` → 0, `rmx context src/refmatrix/daemon.py::_snapshot_catalog` → unknown); `tldr context` finds it in one line. Also `rmx stats --stale` on the busy project daemon died with a raw `TimeoutError` traceback, not a typed busy line | — | probe 2026-09-15 01:5x | plan 3 lineage (busy≠absent) + ingest coverage |
| G13 | Done 2026-09-16 (acceptance pending deploy) | the shared rerank worker does not report its cost, so a budgeted caller (the per-prompt hook, `scan-prompt`) cannot know whether a pool fits and times out instead — and the worker keeps scoring after the client left, so the next caller's probe reads "unavailable" (bug-019). Also: the two UserPromptSubmit hooks (`scan-prompt`, `memory recall --stdin-json`) race ONE serialized worker. Proposed: `info` returns an EMA of seconds-per-doc; the caller skips (and says) when `docs × cost > remaining`; a cancelled request is dropped by the worker (a deadline in the frame) **DONE (task 12.2):** `_RerankRole` keeps a seconds-per-doc EMA (alpha 0.3, seeded only by real scoring calls) and `info` returns `cost_s_per_doc` + `scored_docs`; `ModelServer._augment_info` adds `queue_depth`; `reranker.estimate_rerank_s` is the one place the arithmetic lives; `RemoteReranker` carries a DEADLINE and raises `RerankSkipped` with the numbers when the pool cannot fit; the `rerank` frame carries that deadline and the worker drops it at dequeue. Live proof + the pending acceptance run: `workflow/measurements/rerank-cost-budget-0916.md`. | plan-2 round 9 (2026-09-15), `live9-rerank-diag9.log` |
| G14 | Done 2026-09-16 | a daemon that fails the shared-worker probe at boot (the hub down or cold) goes private for its whole life: after the hub returns the fleet runs N private model processes beside the shared pair and CPU oversubscription makes the shared rerank 5–20× slower (bug-024, 2026-09-15 05:37: 16 workers, 10 docs in 16–25 s). Proposed: `_model_client` re-probes the shared socket every RMX_SHARED_REPROBE_S (300) while private and switches when it answers, closing the private worker; the hub's `queues`/`status` names daemons running private workers **DONE (task 12.1):** `Daemon._maybe_adopt_shared` runs on the existing periodic tick, re-probes the shared socket for any role still private (`RMX_SHARED_REPROBE_S`, default 300, doubling to `RMX_SHARED_REPROBE_MAX_S`), swaps under `_worker_lock`, closes the private worker and drops the cached proxy. `Daemon.worker_kinds()` -> `_store_health['workers']` -> the hub row's `private_workers` -> `rmx hub queues` flags. | plan-4 round 4 (2026-09-15), `deploy-r6-r4.log` |

rel: depends-on -> [[architecture-index]]
rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
