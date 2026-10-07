---
gmd: "0.1"
id: bsd-r1-remedy-r11-4783463
title: "r10 remedy: the shared budget, the lock-free cost header and the partition fix hold; after one respawn, a private worker reads as cold for good, so context reranking on it stops for the life of the daemon"
severity: BULLSHIT
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r10
round: 11
prior: 2026-10-07-1314-r10-budget-bound-excludes-client-lock-06711cd.md
tags: [bsd, audit, remediation, rerank, budget, private-worker, modelsrv, partition, embed, mutation]
---

# ch-bsd round 11: 436b6d7..4783463 {#root}

rel: amends -> [[bsd-r1-remedy-r10-06711cd]]

**Range:** 436b6d7..4783463. I read the shas from `git log --oneline 436b6d7..HEAD`:
- 6e86af0: the r10 remedy (src 8 files, tests 4, bug-094 row, r9 and r10 implementation summaries)
- 4783463: the remedy mutation follow-up (one test and a summary section)

**Date:** 2026-10-07T14:18:10-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 15 (src 8, tests 4, workflow 3)

## Method {#method}

- **Isolated copy.** I made a `git archive` copy of HEAD at `/tmp/r11c`, with its own git and no
  `.refmatrix/`. Every run set `PYTHONPATH=/tmp/r11c/src` and
  `RMX_MODEL_SOCK=/tmp/r11c/nosock.sock`, cleared `__pycache__`, and asserted that
  `refmatrix.__file__` resolves inside the copy.
- **Live-socket record.** The project recorder `workflow/review-output/live-socket-touches.log` read
  **145 lines before and 145 after** every run. The copy's recorder never created its log, so the
  copy made zero touches.
- **Targeted tests.** I ran the five touched families (`r11-targeted.log`): **72 passed**. That
  includes `test_plan2_remedy_r7.py`, so bug-094 is green at HEAD.
- **Probes.** Two probes ran on the real `subproc.WorkerClient`, `modelsrv.ModelServer` and
  `SharedWorkerClient`, over the remedy's own stub model process (`_STUB` in
  `tests/test_rerank_budget_real_clients.py`):
  - `r11-probe-private-respawn.log`
  - `r11-probe-hub-respawn.log`
- **Mutations.** I ran 7 mutants of my own (`r11-mutations.log`) over 6 test files, 97 tests in the
  baseline. Each mutant was reverted with `git checkout` and then checked with `git diff --quiet`.
- **Untouched.** Nothing opened a live `.refmatrix/`. No `rmx` command ran against the live store.
  I edited nothing in the dev tree outside `workflow/bullshit/` and `workflow/review-output/r11-*`.

### Mutation table {#mutations}

| id | mutation | result |
|---|---|---|
| K1 | the writer-only branch of `_read_with_fallback` (no snapshot) drops its unknown-partition guard and falls back to `with_partition` | **SURVIVES** |
| K2 | the hub `nowait` path no longer calls `self.warm((role,))` on a cold header | **SURVIVES** |
| K3 | `warm()` drops the `_warming` dedupe | **SURVIVES** |
| K4 | the version handshake goes back under `ModelServer._lock` | killed |
| K5 | the private path no longer records `overrun_s` | killed |
| K6 | `drain_memory_vectors` loses the `remaining == 0` early return | killed |
| K7 | a budgeted view never `close()`s its forked connection | **SURVIVES** |

### The remedy's own mutation claim {#remedy-mutations}

- The summary and the 4783463 subject say **"16 mutants … 15 killed, 1 equivalent"**.
- `r10-remedy-mutations.log` records **15** mutants: F1-F4 and F6-F16. That is 14 killed and F16
  surviving. **F5 is not in the log.**
- The F16 equivalence argument says the header probe is bounded by the remaining budget, so a
  header that would exhaust it reads as cold. That holds on the hub path.
  - On the private path the budget is spent by `reserve(remaining)`, not by the header, and the
    header is an instant cache read.
  - A reservation granted just before the deadline, with the cost still unknown (no rerank scored
    yet), starts a full forward pass with about 0 s left.
  - The guard does not stop that case either, because `remaining` is still slightly positive. So
    the conclusion ("jitter only") survives, but for a different reason than the one written.
  - See [[#m-1]].

## r10 findings: closed vs open {#r10-status}

| r10 | status | evidence |
|---|---|---|
| #b-1 the budget does not bound the caller | **PARTIAL** → [[#b-1]] | **Shared: CLOSED with power.** `with_budget` forks its own `SharedWorkerClient`. The S2 test (a 2.5 s unbudgeted rerank on the daemon's client, 0.8 s budget) asserts a skip in under 1.2 s; F1 is killed. **Private busy/kill: CLOSED.** `reserve()` skips a busy worker (F2 killed), the pass finishes without a kill (spawns = 1, loads = 1), and K5 is killed. **Private cold: NEW DEFECT.** After any respawn the header never refills, and every budgeted rerank skips as "cold" for the daemon's life (probe: 5/5 skipped while the model was loaded). See [[#b-1]]. The opt-in idle-evict route still pays an unbounded cold load in `d._reranker()`, before the budget exists. |
| #s-1 an unknown partition answers from id 1 | **CLOSED** (MEH residuals) | The tests assert the bound id and the row count, not the name. F6/F7 are killed. "Newer than the snapshot" answers from its own id, and "absent everywhere" gives id -1 with 0 rows and no partition created. Every other `_read_with_fallback` caller (memory get/iter/search/recent/facets, subject list/leaves, derive) passes a caller-named partition, where empty is the correct answer. Residuals in [[#m-1]]: K1 (the no-snapshot branch is unpinned) and the rerank under `_store_lock` on the newer-than-snapshot branch. |
| #s-2 the fresh header waits behind the worker | **CLOSED with power** (residual K2/K3) | The hub answers `info(nowait=True)` from the worker's cached header without touching `_worker()` or the worker lock. The real-ModelServer test, with a 3.0 s rerank in flight, skips a 20-doc pool "queued" in under 0.6 s. F3/F14 are killed, and K4 is killed (handshake off `_lock`). `ahead` stays correct: it is sampled at enqueue, and an in-flight rerank counts as 1. Concurrent `nowait` frames also count, but each lives for microseconds, so this is not filed. |
| #m-1 three-phase embed side effects | **CLOSED** | Double encode: `_embed_serial` is its own lock; `_op_embed` has no caller under `_store_lock` (the drain at `daemon.py:3497` runs after the ingest's lock); F8 is killed. Early stop: `_embed_batch_verdict` stamps only when `remaining == 0`. The one remaining `embedded == 0, remaining > 0, changed == 0` route is the shutdown cancel, and not stamping it is correct. The extract-empty route still returns `remaining: 0` and stamps, as before. F9/F10/K6 are killed, and R2/V16 are pinned. |
| #m-2 r9 summary missing | **CLOSED** | `remedy-bsd-r9-a3a324e.md` exists and reads the logs on disk. |

Closed: 4 (#s-1, #s-2, #m-1, #m-2). Partial: 1 (#b-1). Open: 0.

## Findings {#findings}

### BULLSHIT #b-1: after one respawn a private reranker reads as cold forever, so the context op stops reranking for the daemon's life and says the warm model "is not loaded" {#b-1}

**File:** `src/refmatrix/subproc.py:246-298,365-395` (`_spawn` and `close` clear `_info`; `call`
respawns and refills nothing), `src/refmatrix/reranker.py:399-404` (the cold skip),
`src/refmatrix/daemon.py:1047-1065` (`_reranker` reads `model_name` once)

**What:** 6e86af0 says a private worker "skips when cold" and that a cold role "starts ONE warmup so
a LATER budget can use it".

**Why it's bullshit:** the warmup exists only on the hub. For a private worker:

1. `_info` is filled only by `WorkerClient.info()`.
   - In the daemon, only `_reranker()` → `model_name` calls it, once, when the proxy is built.
2. `WorkerClient.call` respawns on `EOFError`/`BrokenPipeError`/`OSError`, which its own docstring
   calls "the expected case under jetsam".
   - `close()` and `_spawn()` now clear `_info`.
   - The retry's reply folds cost only `if self._info`, so nothing refills it.
3. From then on, `info(nowait=True)` returns `{}`, and every budgeted rerank raises
   `RerankSkipped("worker cold (model not loaded)")`.
   - The unbudgeted `memory_recall`/`ann_search` reranks keep the model loaded and serving the
     whole time.
   - Nothing ever calls `info()` again: `_reranker_inst` is cached, and the private path has no
     `warm()`.
4. The state ends only on a daemon restart, or when `_maybe_adopt_shared` swaps in the hub. That
   happens only once the hub is reachable, and the hub being unreachable is why the worker is
   private in the first place.

**Evidence:**
- **Private** (`r11-probe-private-respawn.log`; real `WorkerClient`, the remedy's stub):

  | step | result |
  |---|---|
  | budgeted #1 | scored |
  | SIGKILL the worker (jetsam); unbudgeted rerank | scored, spawns=2, loads=2 |
  | `info(nowait=True)` | `{}` |
  | budgeted ×5, each after a warm unbudgeted rerank | **5/5 `skipped: worker cold (model not loaded)`** |

- **Hub, the same sequence** (`r11-probe-hub-respawn.log`): one cold skip, then the hub's `warm()`
  refills the header, then scored ×3. So the hub heals and the private worker does not.
- Nothing pins the hub's heal either: **K2** (no `warm()` on a cold header) and K3 survive.
- **Second route, opt-in.** With `RMX_WORKER_IDLE_S > 0`, `_evict_idle_workers` drops
  `_reranker_inst`. The next `_op_context` calls `d._reranker()` (`daemon.py:4657`) before
  `with_budget` is applied, and `RemoteReranker.model_name` calls `client.info()` with no timeout,
  which pays the full cold load (6-33 s live) inside a "budgeted" context op. r10 #b-1 said "never
  call an unbounded `info()` inside a budget"; this one sits one line before the budget.

**Fix:**
- Refill a private header when the worker is respawned, or when `_info` is empty after a
  successful scoring reply. The model is already loaded, so an `info` frame inside the held lock
  costs milliseconds.
- Or give the private budgeted path the hub's shape: a cold header starts ONE background
  `info()`, deduplicated.
- Resolve the reranker for a budgeted op without an unbounded `model_name` probe: pass a timeout
  and skip on expiry.
- Pin the respawn → budgeted-scored sequence on a real `WorkerClient`, and pin the hub's heal
  (kill K2).

**Pattern match:** YES. This is "a reader without a producer" (imp-reader-without-producer
family): the cold gate reads a field that only one rarely-run path writes. It is also the 7th
"bound on one leg" round. The fix made the private worker safe to bound by never loading it inside
the budget, and the respawn path means it stops loading it at all.

rel: contradicts -> [[claude#no-workarounds]]

### MEH #m-1: unpinned residuals and a miscounted mutation claim {#m-1}

- **K1.** The no-snapshot branch of `_read_with_fallback` (boot window, `rs is None`) guards an
  unknown partition by binding the WRITER to id -1. Removing the guard survives, and the removal
  would let a read CREATE the partition through `with_partition`. Pin it with a test that has no
  snapshot.
- **Newer-than-snapshot branch.** It runs `fn` on the writer under `_store_lock`. For `context`,
  `fn` includes the rerank.
  - On the hub that is bounded by the budget (3.0 s default) while every writer waits.
  - On a private worker the pass is "let finish" with no bound, which puts a model call back under
    the store lock (the r9 #s-1 class).
  - The trigger is narrow (a partition created inside the snapshot debounce). I prescribed this
    branch in r10. The tighter fix is to build without the reranker on that branch, or to release
    the lock before scoring.
- **K3.** The `_warming` dedupe is unpinned.
- **K7.** The forked connection's `close()` is unpinned. A leak would be one hub socket and one hub
  thread per context op until GC.
- **Mutation claim.** The summary and the commit say 16 mutants, 15 killed. The log holds 15
  (F5 missing): 14 killed and F16 surviving. The F16 argument names the header probe as what
  spends the budget, but on the private path it is `reserve()`.
  - A reservation granted near the deadline, with cost still unknown, starts a full forward pass
    with about 0 s left, which then shows up as an "overrun".
  - That is marginal (cost is unknown only before the first scored rerank), but the written reason
    is wrong.

## Deferral sweep (rules 9 / 9a) {#deferrals}

I ran the hard and soft patterns over the lines added in `src/` and `tests/`. The one hit is "so a
LATER budget can use it" (`modelsrv.py`), which describes runtime ordering, not deferred work.
There is no stale deferral to a completed plan.

## Verdict {#verdict}

**DIRTY: 2 findings (1 BULLSHIT, 0 SKETCHY, 1 MEH).**

**Blocker:** [[#b-1]]. After any private-worker respawn the context op's rerank is skipped as
"cold" on every call while the model is loaded and serving, for the life of the daemon, unless the
hub comes back.

r10: 4 closed (#s-1, #s-2 with power, #m-1, #m-2), 1 partial (#b-1: shared and private-busy are
closed; private-cold is the new #b-1), 0 open. 7 mutations: 3 killed, 4 survive (K1, K2, K3, K7).
The live-socket recorder read 145 → 145.

rel: contradicts -> [[claude#no-workarounds]]
