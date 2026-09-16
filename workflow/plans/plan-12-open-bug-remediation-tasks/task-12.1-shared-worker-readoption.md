---
gmd: "0.1"
id: task-12.1-shared-worker-readoption
title: "Task 12.1: a private daemon re-probes and adopts the shared worker"
tags: [task, plan-12, daemon, model-workers]
metadata:
  node_type: task
  status: complete
  plan: plan-12-open-bug-remediation
---

# Task 12.1: a private daemon re-probes and adopts the shared worker {#root}

> Plan: [[plan-12-open-bug-remediation]]
> Status: Complete
> Bug: bug-024 (todo G14)
> Depends on: [[task-12.5-pyc-invalidation]]

rel: part-of -> [[plan-12-open-bug-remediation]]

## Requirements {#requirements}

- bug-024: after the fleet relaunched while the hub was down, every daemon booted with PRIVATE
  embed + rerank workers (16 model processes) and kept them after the hub returned. N torch
  processes on one CPU oversubscribe its threads — the shared reranker then scored 10 x 700-char
  docs in 16-25 s against 0.7 s for one, and every per-prompt hook rerank timed out.
- `Daemon._model_client` decides shared-vs-private ONCE per role, at first use, and never revisits
  it. The hub's outage is currently permanent for the daemon that lived through it.
- Add `Daemon._maybe_adopt_shared()`: for each role holding a PRIVATE worker, and no more often
  than `RMX_SHARED_REPROBE_S` (default 300), check `modelsrv.shared_available()` and then a
  bounded `info` probe. On success: install the shared client, close the private worker, drop the
  cached proxy (`_embedder_inst` / `_reranker_inst`), and log the swap with the role and the
  private worker's pid.
- Called from the daemon's existing background tick (beside `_evict_idle_workers`). No new thread,
  no new socket, and nothing on the request path — an adoption must never happen underneath an
  in-flight call, so the swap takes `_worker_lock` and a worker mid-call keeps serving until it is
  replaced between calls.
- A failed re-probe is CHEAP and SILENT-BUT-COUNTED: it logs at most once per backoff window, and
  the backoff doubles up to `RMX_SHARED_REPROBE_MAX_S` (default 1800) so a machine that will never
  have a hub does not probe forever at full rate.
- `RMX_SHARED_MODELS=0` still means never — the existing escape hatch outranks re-adoption.
- The hub names it: `rmx hub status` marks a daemon whose `health` reports a private worker, so
  "the fleet is split" is visible without reading eight logs. The daemon's `health` op gains
  `workers: {embed: "shared"|"private"|"none", rerank: ...}`.

## Files to Create / Modify {#files}

- modify `src/refmatrix/daemon.py` (`_maybe_adopt_shared`, tick call, `health` -> `workers`)
- modify `src/refmatrix/hub.py` (surface private workers in `status`)
- modify `src/refmatrix/cli.py` (`hub status` renders it)
- modify `docs/architecture/todo.md` (G14 -> done)
- create `tests/test_shared_worker_readoption.py`
- modify `workflow/bug_registry.md` (bug-024 -> fixed)

## Test Strategy (RED first) {#test-strategy}

`tests/test_shared_worker_readoption.py`, with a stub socket server standing in for the hub (no
torch, no real model — the existing stub-worker `argv` hook exists for exactly this):
- a daemon that went private while nothing listened ADOPTS the shared client once the stub socket
  starts answering `info`, and the private worker is CLOSED (its pid is gone)
- the cached proxies are dropped on adoption, so the next `_embedder()` builds against the shared
  client — asserted by the proxy identity, not by a log line
- a daemon already on the shared worker is a NO-OP (no probe, no swap)
- re-probe respects `RMX_SHARED_REPROBE_S`: two ticks inside the window issue ONE probe
- backoff doubles on repeated failure and is capped
- `RMX_SHARED_MODELS=0` never probes
- a probe that TIMES OUT leaves the private worker in place and serving (the failure must not cost
  the daemon its working worker)
- `health` reports `workers.embed == "private"` before adoption and `"shared"` after; `hub status`
  renders the split fleet (the renderer is asserted, not just the field —
  [[impression_bsd_unread_diagnostic_field]])
- mutation check: removing the tick call site turns the adoption test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation noted.
- `workflow/implementation_summaries/task-12.1-shared-worker-readoption.md`.
- Branch `task-12.1-shared-worker-readoption`, merged `--no-ff` to `master`.
