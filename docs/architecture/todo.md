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
| G1 | Integrated | Deploy venv imports the dev tree; no deploy runtime | — | bsd #bs-2 | plan 1 |
| G2 | Planned | `learn_from_grep` (a read) upserts entities unguarded; entities index not repaired on fast-exit | — | bsd #bs-3 | plan 2 |
| G3 | Planned | Hub watchdog SIGKILLs a daemon reconnecting to an evicted model worker | — | incident 2026-09-14 | plan 2 |
| G4 | Planned | Memory bridge skips non-GMD files silently; two bridges (sync-disk vs ingest-gmd) | — | bsd #bs-1 | plan 3 |
| G5 | Integrated | Installed hooks ≠ generated hooks; PreCompact silences bridge failure | — | bsd #bs-4 | plan 4 |
| G6 | Planned | 30 MCP tools vs 10 verbs; session-start widen only in CLI | — | bsd #sk-3 | plan 5 |
| G7 | Planned | Stale deferrals: ingest_gmd/store/duckdb_view/embedder/sync docstrings | — | bsd #bs-5 | plan 6 |
| G8 | Planned | README 0.961 has no committed artifact; ARCHITECTURE.md lists 24/80 commands | — | bsd #sk-4, #meh-1 | plan 6 |
| G9 | Resolveable | orderly launchd service spawn-loops behind a manual daemon (11k runs) | — | incident 2026-09-14 | plan 2 |
| G10 | Deferred | Linux supervisor (systemd user unit) not implemented | a Linux deploy target | launchctl.py:322 | — |

rel: depends-on -> [[architecture-index]]
rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
