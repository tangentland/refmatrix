---
gmd: "0.1"
id: impl-bug-015-daemon-wedge
title: "bug-015 — the wedged daemon: bounded shared-worker ops, a stack dump, a self-healing hub worker"
tags: [implementation-summary, bug, plan-2, plan-4]
metadata:
  node_type: implementation-summary
  task: bug-015
---

# bug-015 — stop the bleeding, make the next wedge diagnosable {#root}

rel: evidence-for -> [[plan-2-hooks-reproducible]]
rel: evidence-for -> [[plan-4-daemon-resilience]]

## Incident {#incident}

2026-09-15 01:47 / 01:53 / 02:26: the project daemon wedged minutes after boot — ping answered, the heartbeat went stale (88 s), `rmx partition list` sat 25 s+, `hub queues` said busy, rmxd.log showed no job. The hub's watchdog restarted it each time (`graceful stop … not answering ping (SIGTERM sent now)`). Every hook probe in those windows returned `[]`. The hub's shared rerank worker was broken the whole time (`models role=rerank op=rerank failed: BrokenPipeError` on every call; the worker process at 1.25 GB in state R) and `scan-prompt` — the other per-prompt hook — hung 20 s+ on it (killed by the probe's timeout). Working hypothesis: a daemon-side rerank inside an op waited on that worker at the client's 300 s default while holding the store lock. Not proven: the daemon had no way to show its stacks.

## What shipped {#shipped}

- `SIGUSR1` → `faulthandler` dumps every thread's stack to the daemon's stderr log (`daemon.stderr.log` under launchd, `rmxd.stderr` detached); the daemon keeps serving. Test: a spawned daemon, the signal, `serve_forever` in the dump, ping still answers.
- `daemon.SHARED_OP_TIMEOUT_S` (30 s, `RMX_SHARED_OP_TIMEOUT_S`): the daemon's `SharedWorkerClient` is constructed bounded; a broken worker costs an op seconds and the rerank stage's existing "rerank failed, keeping retrieval order" handles it.
- `scan.scan_prompt(rerank_timeout=)` → `shared_reranker(timeout=, probe_timeout=min(t, 1))`; `rmx scan-prompt --timeout` (default 5) and the generated UserPromptSubmit hook passes `--timeout 5`. README hooks table regenerated.
- `ModelServer._drop_worker`: a worker whose call raised `BrokenPipeError` / `EOFError` / `ConnectionError` is closed and dropped so the next call recreates it, said in the hub log.

## TDD record {#tdd}

RED `workflow/review-output/pytest-bug015-red.log` (5 failed). GREEN `pytest-bug015-green.log` (36 passed with hooks_reproducible, plan2_remedy_r6, docs_generated; then 5 passed after the SIGUSR1 test learned the spawned daemon's stderr file). Mutations `pytest-bug015-mutation.log`: (A) the hub keeps the broken worker → `test_model_server_drops_a_worker_whose_pipe_broke` fails; (B) the daemon's client unbounded again → `test_daemon_shared_worker_client_is_bounded` fails.

## Open {#open}

The root cause is a hypothesis until a wedge is caught with `kill -USR1`. The hub-side worker that goes bad (bug-014: cold-start probe, warm 2195 s under load, BrokenPipe) is ch-performance-tuner's; the daemon-side bounds above hold regardless.
