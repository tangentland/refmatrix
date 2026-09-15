---
gmd: "0.1"
id: development_resources
title: "Development Resources"
tags: [reference]
metadata:
  node_type: doc
---

# Development Resources {#root}

Inventory of available infrastructure and services. Consult this before implementing
features — use what exists rather than creating workarounds.

## Runtime (host, no Docker) {#docker-services}

| Component | Where | Purpose |
|-----------|-------|---------|
| dev venv | `.venv-eval/` (Python 3.14) | tests, evals, dev verification |
| deploy venv | `~/refmatrix/.venv/` behind `~/bin/rmx` | the `rmx` users and daemons run |
| project daemon | `.refmatrix/rmxd.sock`, launchd `com.refmatrix.daemon.refmatrix-*` | single writer for this store |
| hub | `~/.refmatrix/hub.sock`, :7777, launchd `com.refmatrix.hub` | watchdog, shared model workers, global memory, bus, UI |
| fleet | cliquedb, cliquet, atldb, viascope, orderly, thiquet, global | other stores the hub supervises (do not write to them) |

## Storage {#database}

DuckDB catalog per store (`catalog.A/B.duckdb` writer slots + `catalog.read.duckdb` snapshot),
Lance vector datasets, roaring-bitmap fragments, JSONL logs (`facts.log`, `cli.log`, `query.log`).

## Environment Variables {#environment-variables}

| Variable | Required | Purpose |
|----------|----------|---------|
| `RMX_INVOCATION_SOURCE` | hooks set `hook` | telemetry source tag |
| `RMX_PARTITION` | optional | override the memory/code partition |
| `RMXGREP_MODE=rich` | agent shells | force the index path even when piped (the only value; `plain` was removed 2026-09-15 as a bypass) |
| `RMX_HUB_WATCH_*` | optional | watchdog ping timeout / grace misses |

## Test Infrastructure {#test-infrastructure}

| Tool | Location | Notes |
|------|----------|-------|
| pytest | `.venv-eval/` | primary runner; ~1380 tests, ~13 min |
| GMD lint | `tools/gmd/lint.py` | doc/memory validation |
| eval harnesses | `eval/production/`, `eval/memaware/` | production-path benchmarks |

## Planning & Documentation Infrastructure {#planning-documentation-infrastructure}

| Directory | Purpose |
|-----------|---------|
| `workflow/plan-of-plans.md` | Plan index + sequenced execution order (Status column) |
| `workflow/plans/` | All plans, permanently + `<plan>-tasks/` spec dirs; stage = `metadata.status` (`drafting` → `approved` → `in-progress` → `completed`) |
| `docs/architecture/` + `docs/adr/` | Architecture index/todo + ADRs |
| `workflow/implementation_summaries/` | Per-task implementation summaries |
| `workflow/review-output/` | Agent review output files |
| `workflow/past_handoffs/` | Archived session handoffs |

---

*Update this file when new services, tables, or infrastructure are added.*
