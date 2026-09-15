---
gmd: "0.1"
id: architecture-todo
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
| G2 | Shipped (plan 4 tasks 4.1/4.2, 2026-09-14; ch-bsd r1 open) | `learn_from_grep` (a read) upserts entities unguarded; entities index not repaired on fast-exit | — | bsd #bs-3 | plan 4 |
| G3 | Shipped (plan 4 task 4.3, 2026-09-14; ch-bsd r1 open) | Hub watchdog SIGKILLs a daemon reconnecting to an evicted model worker | — | incident 2026-09-14 | plan 4 |
| G4 | Shipped (plan 5, 2026-09-14; ch-bsd r1 open) | Memory bridge skips non-GMD files silently; two bridges (sync-disk vs ingest-gmd) | — | bsd #bs-1 | plan 5 |
| G5 | Shipped (plan 2, 2026-09-14; ch-bsd r5 open) | Installed hooks ≠ generated hooks; PreCompact silences bridge failure | — | bsd #bs-4 | plan 2 |
| G6 | Shipped (plan 3, 2026-09-14; ch-bsd r3 open) | 30 MCP tools vs 10 verbs; session-start widen only in CLI | — | bsd #sk-3 | plan 3 |
| G7 | Planned | Stale deferrals: ingest_gmd/store/duckdb_view/embedder/sync docstrings | — | bsd #bs-5 | plan 6 |
| G8 | Planned | README 0.961 has no committed artifact; ARCHITECTURE.md lists 24/80 commands | — | bsd #sk-4, #meh-1 | plan 6 |
| G9 | Resolveable | orderly launchd service spawn-loops behind a manual daemon (11k runs) | — | incident 2026-09-14 | plan 2 |
| G10 | Deferred | Linux supervisor (systemd user unit) not implemented | a Linux deploy target | launchctl.py:322 | — |
| G11 | Planned | `--like GLOB` is a selector on 5 write commands only (`protect`/`noise`/`forget`, `memory reclassify`); user 2026-09-15: make it universal — every read surface (`list entities`, `query`, `context`, `neighbors`, `top`, `co-occur`, `memory list/search/recall`, `locate`) as a PRE-filter (candidate set) and a POST-filter (rows), through the verbs so MCP gets it | after the plan-2/3/4/5 BSD loops close | user request | plan 7 (to write) |
| G12 | Open | the project's own index has no code entity or `defines` edge for `Daemon._snapshot_catalog` (`rmx query "defines:_snapshot_catalog"` → 0, `rmx context src/refmatrix/daemon.py::_snapshot_catalog` → unknown); `tldr context` finds it in one line. Also `rmx stats --stale` on the busy project daemon died with a raw `TimeoutError` traceback, not a typed busy line | — | probe 2026-09-15 01:5x | plan 3 lineage (busy≠absent) + ingest coverage |

rel: depends-on -> [[architecture-index]]
rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
