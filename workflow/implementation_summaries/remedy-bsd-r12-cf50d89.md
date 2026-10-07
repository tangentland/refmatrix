---
gmd: "0.1"
id: impl-remedy-bsd-r12-cf50d89
title: "Remediation of ch-bsd r12 (9a1b745..cf50d89): a retired worker never respawns; a context answer from the writer is unreranked; the warm path's mutants pinned"
tags: [implementation-summary, bsd, remediation, rerank, subproc, worker, context]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r12-cf50d89
  created: 2026-10-07
---

# Remediation of ch-bsd r12 {#root}

rel: implements -> [[bsd-r1-remedy-r12-cf50d89]]
rel: amends -> [[impl-remedy-bsd-r11-4783463]]

Round 12 was DIRTY with 4 findings (0 BULLSHIT, 3 SKETCHY, 1 MEH). r11 #b-1 was closed.
- RED (`workflow/review-output/r12-remedy-RED.log`): 8 failed. The new tests for H1, H11 and K3
  pass at HEAD; they pin existing behaviour against those mutants.
- GREEN: 45 passed.
- Families with the model socket isolated (`r12-remedy-families.log`): **1007 passed, 4 failed.**
  - 2 are the pre-existing save-state embeds.
  - 2 were `test_rerank_warning_routes::test_the_context_op_carries_a_score_time_degrade`. Its
    daemon stub returns no read store, so after #s-3 the op answered from the writer, unreranked,
    and never reached the score-time route. The test now gets a read store that is not the writer
    object (`_DRead`): 11 passed (`r12-remedy-routes.log`).
- The live-socket recorder stayed at 145 → 145. {#lead}

## #s-1: close() is not retirement {#s-1}

`WorkerClient.retire()` sets `_retired` under the worker lock, then closes the process.
- A retired client's `_ensure` raises `WorkerError("... retired ...; not respawning")`.
- `warm_async` is a no-op on a retired client.
- `_maybe_adopt_shared` retires the private client it replaces, and `_close_workers` retires at
  shutdown. Both fall back to `close` for a client without `retire`.
- An op that captured the private client before the swap can no longer spawn an untracked model
  process. The unbudgeted twin that already leaked at the base is closed by the same flag.

## #s-2: the warm path's mutants {#s-2}

- **H1:** a failing header refill is logged and the op's scores still return. The refill is now
  bounded by `REFILL_TIMEOUT_S` (10 s), not by the op's whole timeout.
- **H3:** `_store_info` clears `warm_error`. Any header, from a warm or a refill, proves the model
  loaded.
- **H11:** two cold episodes (eviction between them) warm twice; loads = 2.
- **K3:** the hub starts one `rmx-models-warm` thread per role, counted as threads, because a
  duplicate is invisible to the load count.

## #s-3: the writer branch {#s-3}

The r11 summary's "product decision" framing was a dodge. Answering unreranked is the op's normal
fallback, so `_op_context` now answers unreranked whenever its build runs on the writer store: a
partition newer than the snapshot, or boot with no snapshot. The answer says so ("the partition is
newer than the read snapshot ... unreranked"). Nothing reranks under `_store_lock` any more.

## Mutation check {#mutations}

9 mutants (J1-J9) at `4fb5000` in a detached worktree with the model socket isolated
(`workflow/review-output/r12-remedy-mutations.log`). 8 were killed at once. J2 (the `warm_async`
retired guard) survived, because `_ensure` refuses the respawn anyway. Its own effect is that no
thread runs to record "retired" as a warmup failure, and that is now pinned. **9 of 9 killed.**

## #m-1 {#m-1}

- **Warming fast-skip.** A budgeted caller on a private worker that is warming skips at once
  ("worker warming"), instead of spending its budget to say "busy".
- **Startup warmup.** `_start_embedder_warmup` calls `_reranker(load=True)`, which loads
  synchronously on that background thread, so "reranker warm in N s" is true.
- **Missing-extra label.** A worker-side `ModuleNotFoundError`/`ImportError` WorkerError from a
  rerank is labelled "dense extra missing" in `_apply_rerank_safe` (`_is_missing_extra`).
- **First-skip limitation.** The first cold skip still cannot name a ModelNotCached, because the
  warmup it starts has not failed yet. The next skip names it. This is the cost of never paying a
  load inside a budget, and it is said here rather than hidden.

{#m-1-body}
