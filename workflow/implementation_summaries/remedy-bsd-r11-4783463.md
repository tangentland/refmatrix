---
gmd: "0.1"
id: impl-remedy-bsd-r11-4783463
title: "Remediation of ch-bsd r11 (436b6d7..4783463): a private reranker refills its header after a respawn and warms in the background; the daemon never loads a cold private model on the context path"
tags: [implementation-summary, bsd, remediation, rerank, budget, subproc, worker]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r11-4783463
  created: 2026-10-07
---

# Remediation of ch-bsd r11 {#root}

rel: implements -> [[bsd-r1-remedy-r11-4783463]]
rel: amends -> [[impl-remedy-bsd-r10-06711cd]]

Round 11 was DIRTY with 2 findings (1 BULLSHIT, 1 MEH). The blocker was introduced by the r10
remedy itself. `WorkerClient.close()`/`_spawn()` clear the cached header, and nothing filled it
again. So after one private-worker respawn, every budgeted context rerank skipped as "cold" for the
life of the daemon, while the unbudgeted recall reranks kept the model loaded. {#lead}

## #b-1: the private worker does not stay cold {#b-1}

- **Refill after a respawn.** `WorkerClient.call` refills the header after any successful scoring op
  on a process with no header. The op proves the model is loaded, so `info` answers at once.
  `_store_info` is now the one place a header is cached and checked (version, prefix).
- **Background warm.** `WorkerClient.warm_async()` runs one background `info()` at a time and keeps
  its failure on `warm_error`. A budgeted cold skip starts it. The skip message names the last
  failed warmup, so a ModelNotCached still reaches the answer (r6 #s-2's rule).
- **`_reranker()` on a cold private worker** starts the warmup and returns an unprobed reranker,
  uncached. Before, `model_name` paid the cold load before the context op's budget started: the
  second route r11 found, after an idle eviction.
- **Model name from the header.** The budgeted path takes the model name from the header it
  already read, so `model_name` never asks `info()` after scoring.

RED (`workflow/review-output/r11-remedy-RED.log`), 4 failed:
- after a respawn, 3 of 3 budgeted reranks skipped "cold";
- a cold private worker "never warmed";
- `warm_error` was missing;
- `_reranker()` took 2.05 s on a cold private worker.

GREEN: 32 passed.

## Mutation check {#mutations}

7 mutants over the fixes (G1-G7), in a detached worktree at `83ab187` with the model socket isolated
(`workflow/review-output/r11-remedy-mutations.log`). 5 were killed at once. G5 (the warm-thread
dedupe) and G7 (the model name from the header) survived. Two tests were added: one thread per
concurrent cold skip, and an unprobed view sends exactly `info(nowait)` then `rerank`. Both mutants
are now killed (the same log, appended). **7 of 7 killed.**

## #m-1: residuals {#m-1}

- **K1:** a test pins that the no-snapshot branch neither answers an unknown partition nor creates
  it.
- **K2 / K3:** a cold hub role starts exactly one warmup however many budgeted reads ask, and then
  scores (spawns = 1, loads = 1).
- **K7:** a budgeted view closes its forked connection.
- **Mutation tally:** the r10 summary now reads 15 mutants, 14 killed, F16 argued equivalent, and
  F16's argument names `reserve()` on the private path.
- **Accepted, not changed:** a context op on a partition newer than the snapshot runs its rerank on
  the writer under `_store_lock`. With a private worker that pass is "let finish", so it is unbounded
  in that narrow window (seconds after a partition is created). r10 prescribed this branch. Bounding
  it means either refusing to rerank under the writer lock or answering unreranked there. That is a
  product decision, so it is recorded here and not taken.

{#m-1-body}
