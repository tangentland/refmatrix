---
gmd: "0.1"
id: impl-remedy-bsd-r10-06711cd
title: "Remediation of ch-bsd r10 (a3a324e..06711cd): the rerank budget bounds the caller on both clients, the hub answers cost without the worker lock, an unknown partition never answers from id 1"
tags: [implementation-summary, bsd, remediation, rerank, budget, modelsrv, partition, embed]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r10-06711cd
  created: 2026-10-07
---

# Remediation of ch-bsd r10 {#root}

rel: implements -> [[bsd-r1-remedy-r10-06711cd]]
rel: amends -> [[impl-remedy-bsd-r9-a3a324e]]

Round 10 was DIRTY with 5 findings (1 BULLSHIT, 2 SKETCHY, 2 MEH). Every new test that pins a fix
was shown RED first (`workflow/review-output/r10-remedy-RED.log`: 27 failed, 8 passed). The 8 that
passed at HEAD pin guards that already existed, and their job is to kill mutants B5, B7 and R2. The
full suite was NOT run (bug-088). The touched families ran with `RMX_MODEL_SOCK` isolated: **987
passed, 3 failed** (`r10-remedy-families.log`), and the live-socket recorder stayed at 145 → 145.
- 2 of the 3 failures are the pre-existing `test_save_state_embeds_memories` pair. r10 showed they
  pass only when the live hub serves them.
- The third failure was red at HEAD too (bug-094, below) and is fixed. {#lead}

## #b-1: the budget is a bound on the caller {#b-1}

The budget tests now run on the REAL classes (`tests/test_rerank_budget_real_clients.py`): a real
`ModelServer`, real `SharedWorkerClient`s, and a real `WorkerClient`. Only the model process is a
stub, and it uses the real frame protocol.

- **Shared worker.** `RemoteReranker.with_budget` gives the view its OWN connection
  (`SharedWorkerClient.fork`), closed after `score`. The view no longer queues on the daemon
  client's lock behind `memory_recall`'s unbudgeted rerank.
  - RED: 2.20 s on a 0.8 s budget. Now: a skip inside the budget.
- **Private worker.**
  - The view `reserve()`s the worker within the remaining budget and skips when it is busy.
  - It reads the cost from the client's cached header, never from a probe.
  - It skips a cold worker instead of paying the model load.
  - It never hands the worker a socket timeout, because that timeout kills the process. A started
    forward pass finishes, and `overrun_s` is reported on the answer's warnings
    (`context._rerank_bodied`).
  - `WorkerClient.close()` clears the header, so an evicted worker reads as cold.
  - RED: `WorkerError: deadline expired`, the worker killed and respawned, and the next op paying
    the cold load. Now: scored, spawns = 1, loads = 1.
- A worker-side `deadline expired` refusal is a `RerankSkipped`, not an error.
- B5 (a spent budget sends no frame) and B7 (the socket gets what is left after the header) are now
  pinned on a real client.

## #s-2: the cost header without the worker lock {#s-2}

- **Hub `info(nowait=True)`.** The hub answers from the worker's cached header plus the queue depth
  it sampled at enqueue. It never sends a frame to the worker and never calls `_worker()`.
  - A cold role answers `{}` and starts ONE warmup (`ModelServer._warming`).
- **Rerank replies carry the cost.** Every rerank reply from the worker carries `cost_s_per_doc` and
  `scored_docs`, and both clients fold them into their cached header.
- **Version handshake moved off `_lock`.** `ModelServer._worker` runs the handshake, which loads the
  model, outside `_lock`. Before, every frame's queue count stalled behind a cold start. That is
  what made the cold-hub test take 1.0 s.
- RED: "no answer within the 1.5 s budget" behind a busy worker. Now: an estimate-driven skip in
  under 0.6 s, with the queue named.
- `fresh` is gone. `nowait` is the one keyword on both clients.

## #s-1: a partition the read stores lack {#s-1}

`_read_with_fallback` checks that the partition exists in the read store it got. On a miss it checks
the WRITER.
- **Newer than the snapshot:** `fn` runs on the writer under `_store_lock`.
- **Absent everywhere, default `missing="empty"`:** `fn` runs bound to `_NO_PARTITION_ID` (-1) and
  sees zero rows. The read creates nothing; a memory partition a fresh project never wrote is
  normal.
- **Absent everywhere, `missing="raise"` (the context op):** `ValueError("unknown partition ...")`.
  A typo'd `-p` no longer reads as "no matches".
- **Tests:** they assert the bound id and the row count, not the name. RED: bound id 1, where the
  `fresh` partition's id was 4.

## #m-1: the three-phase embed's side effects {#m-1}

- **Double encoding.** `_op_embed` runs under a per-daemon embed lock (`_embed_serial`). It is not
  the store lock, so writers stay free. RED: 6 encodes for 3 rows.
- **A fully changed batch is not "done".**
  - `drain_memory_vectors` continues when `changed_while_encoding > 0`, within its batch budget.
  - `rmx embed` decides each batch with `_embed_batch_verdict`, and only `complete` (no rows left)
    stamps the derive pass. No progress with rows pending is now `partial`, said in yellow and not
    stamped.
  - `EMBED_CHANGED_RETRIES` (3) bounds the retries.
  - E3 now has two readers.
- **R2.** The `_PrecomputedQuery` refusal is pinned.
- **V16.** The watch flush sums its per-root reports in `_sum_sync_reports`, and the accumulation is
  pinned.

## #m-2 {#m-2}

[[impl-remedy-bsd-r9-a3a324e]] was written. Its test-run section reads the logs on disk. The r9 #s-1
commit claimed "282 passed", but the only sibling log on disk says 185.

## bug-094 (found here) {#bug-094}

`test_plan2_remedy_r7::test_shared_reranker_scores_after_a_short_probe` was red at 06711cd
(`r10-remedy-r7-at-head.log`, run in a HEAD worktree). r9's `fresh=True` header put a second
worker-bound `info` frame on the hook path. The test now pins probe → `nowait` header → rerank.

**Open, not code:** the full suite stays unrun until bug-088 isolates it. {#open}
