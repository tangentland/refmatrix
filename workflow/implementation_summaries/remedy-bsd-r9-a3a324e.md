---
gmd: "0.1"
id: impl-remedy-bsd-r9-a3a324e
title: "Remediation of ch-bsd r9 (64117e1..a3a324e): reads bind their partition under the mirror lock, the rerank budget reaches the socket, no model call under the writer lock"
tags: [implementation-summary, bsd, remediation, rerank, context, mirror, partition, embed]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r9-a3a324e
  created: 2026-10-07
---

# Remediation of ch-bsd r9 {#root}

rel: implements -> [[bsd-r1-remedy-r9-a3a324e]]
rel: amends -> [[impl-remedy-bsd-r8-64117e1]]

Written after the fact: ch-bsd r10 #m-2 found no summary for this remedy. Round 9 was DIRTY with 6
findings (2 BULLSHIT, 2 SKETCHY, 2 MEH). The full suite was NOT run (bug-088); the touched families
were. Round 10 ([[bsd-r1-remedy-r10-06711cd]]) judged the result: 5 closed, 1 partial (#b-2). {#lead}

| finding | commit | change | r10 verdict |
|---|---|---|---|
| #b-1 | `09db9a6` | `_read_with_fallback` binds the partition INSIDE the mirror's use-lock and restores it after. A mirror lacking the partition falls through to the snapshot file. | Closed with power (40/40 right, 0 of 200 crossed). Residual: the snapshot file bound a missing partition to id 1 (r10 #s-1). |
| #b-2 | `09db9a6` | `score` passes the remaining budget to the socket and asks a `fresh` header. The context op reads through a PRIVATE snapshot Store, so its rerank holds no mirror lock. | Partial: the socket bound is real on an idle client. It did not cover the daemon client's own lock or a private worker, and `fresh` went through the worker's lock (r10 #b-1, #s-2). |
| #s-1 | `8986637` | `memory_recall` embeds the query before `_store_lock` (`_PrecomputedQuery`). `_op_embed` runs select → encode outside the lock → write-back of rows unchanged meanwhile. | Closed. Side effects are r10 #m-1. |
| #s-2 | `ef061c8` | `vector_delete_failed` comes back from `memory forget` (op and daemon) and `untrack`. Every render site and the flush line are pinned. | Closed; V16 (the accumulation) survived (r10 #m-1). |
| #m-1 | `06711cd` | The verb's warning-merge dedupe has a test, and the context op documents its snapshot lag. | Closed. |
| #m-2 | `1b6210e` | The 16.10 spec was written (since moved to plan-21 task 21.4). | Closed. |

## Test runs, as logged {#runs}

- #b-1/#b-2: `workflow/review-output/r9-families.log`, **239 passed**, matching the commit message.
- #s-1: the commit message says "282 passed". The only sibling log on disk,
  `r9-s1-siblings.log`, says **185 passed**; no 282 run is on disk. The RED log is
  `r9-s1-red.log` (2 failed).
- #s-2: `r9-s2-red.log` (5 failed RED) and `r9-s2.log` (16 passed).
- None of these runs overrode `RMX_MODEL_SOCK`. r10 found that `test_daemon_dense_ops.py` and
  `test_daemon_subproc_embed.py` reach the live hub's `models.sock` whenever a run does not
  (bug-088).

{#runs-body}
