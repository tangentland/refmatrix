---
gmd: "0.1"
id: task-12.1-shared-worker-readoption-summary
title: "Implementation summary: a private daemon re-probes and adopts the shared worker"
tags: [summary, plan-12, daemon, model-workers]
metadata:
  node_type: summary
  task: task-12.1-shared-worker-readoption
  created: 2026-09-16
---

# Implementation summary: task 12.1 (bug-024, G14) {#root}

rel: implements -> [[task-12.1-shared-worker-readoption]]
rel: part-of -> [[plan-12-open-bug-remediation]]

## What shipped {#shipped}

- `Daemon._maybe_adopt_shared(now=None)` — per-role re-probe + swap, with backoff.
- `Daemon.worker_kinds()` -> `{role: shared|private|none}`.
- Tick call site beside `_evict_idle_workers` in `_start_periodic_flush`.
- `_store_health["workers"]`; hub row `private_workers`; `cli.render_worker_split`; a flag in
  `rmx hub queues`.
- `_reprobe_next` / `_reprobe_backoff` state on the daemon.

## Design points {#design}

- **The swap takes `_worker_lock` and never runs on a request path.** A call already in flight
  finishes against the client it started with; only the next call sees the new one.
- **A failed probe keeps the private worker serving.** The failure mode being fixed is a daemon
  that lost sharing; it must not become a daemon that lost its worker.
- **Backoff doubles from `RMX_SHARED_REPROBE_S` (300) to `RMX_SHARED_REPROBE_MAX_S` (1800)**, so a
  host that will never run a hub stops probing at full rate.
- **`derive_stale` and `private_workers` are carried by the hub row but do NOT make it hot.** The
  day this ships every store in the fleet is unstamped; making that hot would alert eight rows at
  once and train the signal away.

## RED / GREEN / mutation {#evidence}

- RED: `workflow/review-output/red-task-12.1.log` — 10 failed.
- GREEN: `workflow/review-output/green-task-12.1.log` — 11 passed.
- Mutation (tick no longer calls `_maybe_adopt_shared`):
  `test_the_background_tick_calls_the_reprobe` RED.
- Regression: `test_hub`, `test_derive_stamp`, `test_shared_worker_readoption` — 35 passed.

## What is NOT proven {#limits}

The tests drive a REAL unix socket speaking the REAL frame protocol, with a stub worker behind it —
no torch, no model load. The live 16-private-process fleet replay of 2026-09-15 is not reproduced
in the suite, and the adoption has not yet been observed on the deployed fleet: that check belongs
to the deploy step (`rmx hub queues` must show no `private_workers` flag once a daemon that booted
private has ticked).
