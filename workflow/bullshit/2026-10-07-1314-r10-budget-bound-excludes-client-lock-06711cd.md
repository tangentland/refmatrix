---
gmd: "0.1"
id: bsd-r1-remedy-r10-06711cd
title: "r9 remedy: the partition race is closed with power, but the rerank budget still does not bound the caller when the daemon's own client is busy or the worker is private, and an unknown partition answers from partition 1"
severity: BULLSHIT
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r9
round: 10
prior: 2026-10-07-1210-r9-context-read-path-wrong-partition-a3a324e.md
tags: [bsd, audit, remediation, rerank, budget, context, mirror, partition, embed, mutation]
---

# ch-bsd round 10: a3a324e..06711cd {#root}

rel: amends -> [[bsd-r1-remedy-r9-a3a324e]]

**Range:** a3a324e..06711cd. I read the shas from `git log --oneline a3a324e..06711cd`:
- 09db9a6: r9 #b-1 and #b-2 (partition bound under the mirror lock; private snapshot store for
  `context`; `with_budget` socket timeout and fresh `info`)
- 8986637: r9 #s-1 (query embed before `_store_lock`; three-phase `_op_embed`)
- ef061c8: r9 #s-2 (`vector_delete_failed` on `memory forget` and `untrack`, render pins, bug-093 row)
- 06711cd: r9 #m-1 (verb merge dedupe test, snapshot-lag docstring)
- 846cdf6 (the r9 report), f21ef21, 48fb7bf, 023e55d, 210f9b4, 1b6210e, a26b3a2, 1fdd5e5,
  10d6c23, de95e8e: docs only. I gave these a MEH-level read.

HEAD moved to 235fcae during the audit (a peer session; out of range). The working tree also
shows uncommitted renames of plan-16 tasks 16.7-16.10 into a new plan-21. I did not touch them.

**Date:** 2026-10-07T13:14:47-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed (code commits):** 13 (src 5, tests 7, workflow 1)

## Method {#method}

- **Isolated copies.** I made three `git archive` copies, each with its own `Store.init()`ed
  `.refmatrix/`:
  - `/tmp/r10m` (06711cd): mutations.
  - `/tmp/r10p` (06711cd): probes.
  - `/tmp/r10o` (a3a324e): the pre-remedy comparison.

  Every run prepended `PYTHONPATH`, asserted that `refmatrix.__file__` resolves inside the copy,
  and cleared `__pycache__`.
- **Mutation harness** (`workflow/review-output/r10-mut-harness.py`):
  - It restores the file from saved bytes, checks the sha256, and runs `git diff --quiet` in the
    copy.
  - It takes an exclusive lock and refuses a dirty copy.
  - Every run collected **227** tests, the baseline count.
  - A mutant counts as KILLED only if it fails tests BEYOND the baseline's failure set.
- **Live-socket discipline. One violation, disclosed.**
  - My FIRST baseline run in `/tmp/r10m` did not isolate the model socket. The copy's conftest
    recorder logged **18 connects to the LIVE `~/.refmatrix/models.sock`**, from
    `test_daemon_dense_ops.py` (7 tests) and `test_daemon_subproc_embed.py`
    (`r10-copy-live-socket-touches.log`). These were embed/ann calls on the shared worker. No store
    was written: those tests use tmp stores.
  - Every later run set `RMX_MODEL_SOCK` to a nonexistent path inside the copy. The project
    recorder stayed at **145 → 145** lines across every probe and all 28 mutants, and the copy
    recorder stayed at 18 → 18.
  - This is bug-088 evidence: those two files reach the live hub whenever a run does not
    override the socket.
- **Isolated baseline:** 225 passed, 2 failed. The 2 are
  `test_save_state_embeds_memories.py::{test_no_memory_row_is_left_without_a_vector,
  test_a_bare_ingest_gmd_as_memory_embeds_too}`. They fail identically at a3a324e: the in-process
  daemon holds the DuckDB lock (`r10-save-state-embeds-isolated.log`). They pass only when the live
  hub serves them. They are pre-existing, not caused by this range, and I excluded them from kill
  credit.
- **Probes ran on the real classes; only the model process is a stub.**
  - The budget probe (`r10-probe-budget.py`) runs a REAL `modelsrv.ModelServer`, whose `_handle`
    queues `info` behind a rerank on the role's `WorkerClient`. The daemon side is a REAL
    `SharedWorkerClient(timeout=45)`, probed once as `_model_client` does. The private side is a
    REAL `subproc.WorkerClient`.
  - The model process is a stub worker over the real frame protocol (`r10-probe-stub-worker.py`).
    It applies `embed_worker`'s dequeue-deadline drop, a cold "model load" on its first non-ping
    op, and a per-request rerank time read from a file. No model was loaded.
  - The mirror probe (`r10-probe-mirror.py`) is r9's P3 on a real two-partition store, with a
    real snapshot and a real `_MemMirror`, plus P3b, P4 and P5 below.
- Nothing opened a live `.refmatrix/`. No `rmx` write ran, and no launchctl verb ran. I edited
  nothing under the live `src/`.

### Mutation table {#mutations}

28 mutations: **21 killed, 7 survive** (`r10-mutations.log`).

| id | mutation | result |
|---|---|---|
| P1 | mirror partition not restored after `fn` | survives: **equivalent** (every `_read_with_fallback` caller passes a non-None partition and rebinds inside the lock) |
| P2 | an unknown partition still answers from the mirror | killed |
| P3 | no rebind inside the use-lock | killed (2) |
| P4 / P5 | `_op_context` back on the shared mirror (`private` dropped / ignored) | killed |
| B1 | `score` drops `timeout=` | killed (2) |
| B2 | `score` asks for the cached `info` | killed |
| **B3** | `SharedWorkerClient.info` ignores `fresh` | **SURVIVES**: the fresh path is pinned only on a fake client |
| B4 | socket `TimeoutError` not mapped to `RerankSkipped` | killed |
| **B5** | `remaining <= 0` early skip removed | **SURVIVES** |
| B6 | the `TypeError` (private-client) branch returns `{}` | killed (4, `test_rerank_cost_budget.py`) |
| **B7** | socket timeout = the whole budget instead of what is left after the `info` probe | **SURVIVES** |
| E1 / E2 | `_op_embed` phase-3 `updated_at` guard removed / weakened | killed |
| **E3** | `changed_while_encoding` dropped from the result | **SURVIVES**: nothing reads it |
| R1 | recall gets the live embedder under the lock | killed |
| **R2** | `_PrecomputedQuery` returns the vector for ANY text | **SURVIVES**: the "refused loudly" guard is unpinned |
| V10-V14, V19-V22 | each render site / op return / flush line | killed (10) |
| **V16** | the watch flush does not ACCUMULATE `vector_delete_failed` | **SURVIVES**: the line function is pinned, the sum feeding it is not |
| M2 | verb merge no longer de-duplicates | killed |

## r9 findings: closed vs open {#r9-status}

| r9 | status | evidence |
|---|---|---|
| #b-1 context answers from another partition | **CLOSED with power** → residual [[#s-1]] | P3: `context(code)` ×40 racing `memory_get(notes)` ×40 gave **40/40 right**, against 1/40 at a3a324e. P3b: 200 slow mirror reads on two partitions crossed **0** times, against 67. P5: the binding is restored after a raising `fn`, and `partition=None` binds the default. P2/P3/P4/P5 are killed. The unknown-partition half is not closed ([[#s-1]]). |
| #b-2 `with_budget` bounds nothing; mirror lock held | **PARTIAL** → [[#b-1]], [[#s-2]] | **Closed:** the mirror lock is free during the score (P4/P5 killed). An idle-client socket bound is real: S1 budget 1.0 → **1.01 s**, budget 3.0 → **3.00 s**, both `RerankSkipped`, against 3.80 s `WorkerError` at a3a324e. **Open:** the bound does not cover the client's own lock or the private worker ([[#b-1]]), and the fresh estimate is blind on a busy hub ([[#s-2]]). |
| #s-1 model calls under `_store_lock` | **CLOSED** → residual [[#m-1]] | R1 and E1/E2 are killed. A sweep of `embed_texts(` / `.score(` / `_embedder()` / `_reranker()` / `.dim` in `src/` finds no model call under `_store_lock`. The one remaining branch is `_read_with_fallback`'s writer fallback when no snapshot exists (boot only). That branch is documented and runs under the budget, and [[#b-1]] shows the budget is not airtight. |
| #s-2 vector-delete count | **CLOSED** (one MEH residual) | V10-V14 and V19-V22 are killed, so every render site, `memory forget` (daemon and op), `untrack` and the flush line are pinned. V16 (the accumulation) survives. The legacy-doc purge in `ingest_path` (`ingest.py`, `s.purge_path`) still returns no count. That is a rare migration path; I note it under [[#m-1]] and do not re-file it. |
| #m-1 dedupe unpinned; snapshot lag undocumented | **CLOSED** | M2 is killed. The `_op_context` comment now names the debounce lag. |
| #m-2 16.10 has no spec | **CLOSED** | 1b6210e wrote `task-16.10-surfaces-and-nl-ranking.md`. Its R2 measures hit@1/@5 on both the daemon (reranked) and replica routes. An uncommitted peer change is moving it to plan-21 task 21.4; the anchor survives the rename. |

Closed: 5 (#b-1 with power and a residual, #s-1 with power, #s-2, #m-1, #m-2). Partial: 1 (#b-2). Open: 0.

## Findings {#findings}

### BULLSHIT #b-1: the rerank budget still does not bound the caller. The daemon's own unbudgeted rerank holds the client lock (3.80 s on a 1.0 s budget), and on a private worker the timeout kills the model process and the next op pays the cold load (6.01 s on 3.0 s) {#b-1}

**File:** `src/refmatrix/reranker.py:340-385` (`RemoteReranker.score`),
`src/refmatrix/modelsrv.py:143-178,200-213` (`SharedWorkerClient.call` / `info` hold `self._lock`
for the whole round trip), `src/refmatrix/subproc.py:342-380` (`WorkerClient._call_once` /
`call`), `src/refmatrix/daemon.py:1047-1065` (`_reranker`: ONE client per daemon),
`daemon.py:5646-5700` (`_apply_rerank_safe`: unbudgeted)

**What:** 09db9a6 says "with_budget bounded nothing … a busy worker costs at most the budget".

**Why it's bullshit:** the budget now limits the SOCKET read. It does not limit the two other
waits on the same path.

1. **The client lock.** `with_budget` returns a view over the daemon's ONE cached client.
   - `SharedWorkerClient.info` and `.call` both hold `self._lock` for the whole round trip.
   - `memory_recall` and `ann_search` rerank through `_apply_rerank_safe`, on the same client,
     with no budget. Each of those has a 45 s socket timeout.
   - A context op that arrives while one of them is in flight blocks on the lock, unbounded. The
     budget only starts to matter after the lock is free. By then it is spent, and the estimate
     reports "`2.6s > -2.8s left`".
2. **The private worker** (the documented fallback whenever the hub is down at first use;
   `project_shared_worker_private_split`).
   - `score` now passes `timeout=remaining` to `WorkerClient.call`.
   - On expiry, `_call_once` raises `TimeoutError` after `close()`, which kills the model
     process. `TimeoutError` is an `OSError`, so `call`'s respawn clause catches it, spawns a NEW
     worker, and retries with the already-expired deadline.
   - The result is a `WorkerError("deadline expired")`, not a `RerankSkipped`, and the model is
     gone.
   - The next context op goes through the `TypeError` branch to `self._client.info()`. `_spawn`
     reset `_info`, and that `info()` has no timeout (300 s default), so it pays the full cold
     model load inside the "budgeted" call.
   - Before the remedy, the same slow rerank waited, scored, and left the worker warm.

**Evidence** (`r10-budget-probe-shared.log`, `r10-budget-probe-private.log`; real ModelServer,
real `SharedWorkerClient`, real `WorkerClient`, stub model process):

| case | budget | 06711cd | a3a324e |
|---|---|---|---|
| S1 another daemon's 4 s rerank on the shared worker | 1.0 s | **1.01 s** RerankSkipped | 3.80 s WorkerError |
| S1 same | 3.0 s | **3.00 s** RerankSkipped | 3.80 s WorkerError |
| **S2 this daemon's own unbudgeted rerank (memory_recall shape) on the same client** | 1.0 s | **3.80 s** | 3.80 s |
| **Q2 private worker, one 4 s rerank** | 3.0 s | **3.54 s, WorkerError, worker killed + respawned (spawns 1→2)** | 4.00 s scored, no respawn |
| **Q3 the next context op, rerank 0.1 s** | 3.0 s | **6.01 s** (cold load via unbounded `info()`), WorkerError | 0.11 s scored |
| Q4-Q7 after that | 3.0 s | 0.10-0.11 s | 0.10-0.11 s |

The stub's cold load is 6 s. The hub's own comment measures real cold loads at 6-33 s
(`modelsrv.py` `_handle`). Every new budget test drives a fake `_Client` whose `call` implements
the timeout itself and holds no lock. No test uses a real `SharedWorkerClient` under contention
or a real `WorkerClient`, which is why B3, B5 and B7 survive.

**Fix:**
- Give a budgeted view its OWN connection: a per-request `SharedWorkerClient` with
  `timeout=remaining`, exactly the shape `shared_reranker` uses for the hook. It shares no lock,
  has no stale cache, and closes after use. Alternatively, acquire the client lock with
  `acquire(timeout=remaining)` and skip on failure.
- For a private `WorkerClient`, do not hand it a socket timeout that kills the model. Either skip
  when its lock is busy, or let a started forward pass finish and record the overrun. And never
  call an unbounded `info()` inside a budget: use the cached header or skip.
- Map a worker-side `deadline expired` `WorkerError` to `RerankSkipped`.
- Pin all of this with tests on the REAL client classes: contention on one `SharedWorkerClient`,
  and a `WorkerClient` over a stub argv. Kill B3, B5 and B7.

**Pattern match:** YES. This is the 6th appearance of "a bound on one leg is not a bound on the
caller" (imp-partial-bound-4, imp-bound-holds-answer-dead, imp-probe-timeout-leak,
imp-deadline-is-not-a-timeout, r9 #b-2), so it stays BULLSHIT. It is also "a fix that changes a
shared resource's lifecycle": a timeout on a private pipe kills the process.

rel: contradicts -> [[claude#no-workarounds]]

### SKETCHY #s-1: a partition the mirror lacks falls to the snapshot Store, which binds partition id 1 under the REQUESTED name, and the test asserts the name {#s-1}

**File:** `src/refmatrix/daemon.py:4786-4805` (`_read_with_fallback` miss branch),
`src/refmatrix/store.py:1204-1214` (read-only fast path: `row[0] if row else 1`),
`tests/test_read_path_partition_and_budget.py::test_an_unknown_partition_never_answers_from_the_mirrors_current_one`

**What:** 09db9a6 says "a mirror lacking the partition falls through to the snapshot file instead
of answering from its current one".

**Why it's sketchy:**
- The snapshot file is the mirror's own source. A partition missing from the mirror is almost
  always missing from the snapshot too: it was created within the debounce, or it does not exist
  (a typo'd `-p`).
- The read-only `Store` fast path resolves a missing partition row to id 1, the default
  partition, and keeps `_partition_name` = the requested name.
- The op therefore answers from the DEFAULT partition, labelled as the requested one.
- The test checks `rs._partition_name != "pb"`. The snapshot Store sets the name to the request,
  so the test cannot see the id. Its assertion passes on the wrong data. That is rule-10 shape:
  the test reads the field the fallback fakes.

**Evidence** (`r10-mirror-probe.log`, P4): partitions are `{pw: 1, code: 3, notes: 4}`. The
jetsam docs are in `pw` (default) and `code`. I created a `fresh` partition on the writer (id 5)
after the snapshot.

| probe | 06711cd | a3a324e |
|---|---|---|
| `context("jetsam", partition="fresh")` | **6 hits; `build_context` ran on `('fresh', 1)`** | 0 hits; ran on `('notes', 4)` |
| `_read_with_fallback(d, "fresh", …)` binds | **`('fresh', 1)`** (expected 5; 1 = `pw`) | `('notes', 4)` |

Both trees answer from the wrong partition. The remedy changed WHICH wrong partition, and the
test cannot tell.

**Fix:**
- On a mirror miss, read from the writer: `with d._store_lock, d._st().with_partition(p)`. The
  writer knows every partition, and this is rare and cheap. Alternatively, make the read-only fast
  path report "partition absent" (no `else 1`), and have the op return an empty or explicit
  "unknown partition" answer.
- Assert on `_partition_id` / the data, not the name.

**Pattern match:** YES. This is the residual of r9 #b-1 (wrong partition answers) and the
"fake/test reads the field the fallback sets" shape (imp-reader-without-producer family).

rel: contradicts -> [[claude#no-workarounds]]

### SKETCHY #s-2: the "fresh queue depth" cannot be read while the worker is busy, which is the only time it matters; it spends up to 1 s of the budget, and the test models a hub that cannot exist {#s-2}

**File:** `src/refmatrix/reranker.py:349-368`, `src/refmatrix/modelsrv.py:469-520` (`_handle`
routes `info` through `w.call`), `tests/test_read_path_partition_and_budget.py::_Client`,
`::test_the_estimate_uses_a_fresh_queue_depth`

**What:** the remedy estimates cost from "a FRESH header … the queue depth NOW".

**Why it's sketchy:**
- The real `ModelServer` answers `info` through the role's `WorkerClient`, under that client's
  lock. A fresh `info` therefore waits behind the very rerank it is supposed to predict.
- On a busy worker, the `min(remaining, 1.0)` probe times out, `info` becomes `{}`, the estimate
  is `None`, and the op waits out the rest of the budget.
- With a 1.0 s budget the probe consumes all of it: S1 reports "no answer within the **0.0**s
  budget".
- The test's `_Client.info` returns `queue_depth=500` instantly. The real hub cannot produce that
  shape while busy.
- B3 (the real client ignoring `fresh`) survives.

**Evidence** (`r10-budget-probe-shared.log`):

| case | outcome |
|---|---|
| S3a idle worker, 20 docs, budget 3.0 | estimate fires: **0.00 s** RerankSkipped (13.6 s > 3.0 s) |
| S3b another daemon's 4 s rerank ahead, 20 docs, budget 3.0 | estimate blind: **3.00 s**, skip by socket timeout |

**Fix:** have the hub answer `info` without the worker lock: the cached worker header plus the
live `_pending[role]`. Or add a lock-free `queue` op. Then test the estimate against the real
`ModelServer` with a busy stub worker.

**Pattern match:** YES. This is "the fake that omits the new field is the blindfold"
(imp-renderer-destroys-payload / r7-10 r3) and the counter-sampled-at-the-wrong-instant lineage
(plan-12 `queue_depth`).

rel: contradicts -> [[claude#no-workarounds]]

### MEH #m-1: side effects of splitting `_op_embed` into three phases {#m-1}

- **Double encoding.** Rows are selected under the lock and encoded outside it, so two concurrent
  embed ops now select the SAME pending rows and both encode them. Examples: a save-state
  `drain_memory_vectors` overlapping an `embed_start` job or `rmx embed`. Before the split, the
  second op waited and found nothing pending. The Lance `merge_insert` makes the double write
  harmless, but the shared worker pays twice.
- **Early stop on a fully changed batch.** If every row changed mid-encode, the op returns
  `embedded=0` with `remaining>0`.
  - `drain_memory_vectors` stops.
  - The CLI `embed` loop treats `embedded == 0` as done and stamps a COMPLETE embed derive pass
    (`_stamp_derive_pass`) over a partition with rows pending.
  - That loop already accepted `embedded == 0` from the extract-empty path; this split adds a new
    route into it.
- **Unread results.** `changed_while_encoding` has no reader (E3 survives); it reaches only
  `rmxd.log`. The `_PrecomputedQuery` refusal is unpinned (R2 survives).
- **Small leftovers.** V16 (the flush accumulation) survives. The legacy-doc purge in
  `ingest_path` returns no vector-delete count.

### MEH #m-2: the r9 remedy has no implementation summary {#m-2}

`workflow/implementation_summaries/` has `remedy-bsd-r8-64117e1.md` and nothing for the r9 remedy.
The CLAUDE.md quality gate makes the summary mandatory. The summary should also record the result
of the commit message's "239 passed / 282 passed" runs. On this host, two of the files in those
families reach the live `models.sock` unless the socket is overridden (bug-088; see Method).

## Docs-only commits (MEH read) {#docs-commits}

f21ef21, 48fb7bf, 023e55d, 210f9b4, 1b6210e, a26b3a2, 1fdd5e5, 10d6c23 and de95e8e contain no
`src/` or `tests/` lines. The plan-17/19/20 specs are `drafting` or have task specs written. The
16.10 spec anchors r9 #m-2. Nothing to file.

## Deferral sweep (rules 9 / 9a) {#deferrals}

I ran the hard and soft deferral patterns over the added lines in `src/` and `tests/` in range.
They return 4 hits, all `Phase 2/3` labels for `_op_embed`'s own phases, plus "a later change
cannot quietly move a model call". None is a deferral. There is no stale deferral to a completed
plan.

## Verdict {#verdict}

**DIRTY: 5 findings (1 BULLSHIT, 2 SKETCHY, 2 MEH).**

**Blocker:**
- [[#b-1]]: the context rerank budget is not a bound on the caller.
  - The daemon's own unbudgeted `memory_recall`/`ann_search` rerank holds the shared client's
    lock: 3.80 s on a 1.0 s budget.
  - On a private worker the timeout kills the model process (WorkerError, spawns 1→2), and the
    next op pays the cold load through an unbounded `info()`: 6.01 s on 3.0 s.

r9: 5 closed (#b-1 and #s-1 with power; #b-1 has a residual), 1 partial (#b-2), 0 open.
28 mutations: 21 killed, 7 survive (P1 equivalent; B3, B5, B7, E3, R2, V16).

rel: contradicts -> [[claude#no-workarounds]]
