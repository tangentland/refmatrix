---
gmd: "0.1"
id: bsd-r1-remedy-r9-a3a324e
title: "r8 remedy: the warning routes are pinned and the Lance pins fail loudly, but moving the context op onto the read path makes it answer from the wrong partition, and its rerank budget does not limit the wait"
severity: BULLSHIT
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r8
round: 9
prior: 2026-10-07-1128-r8-legs-wired-but-unpinned-and-a-lock-held-rerank-64117e1.md
tags: [bsd, audit, remediation, rerank, context, mirror, partition, lance, mutation]
---

# ch-bsd round 9: 64117e1..a3a324e {#root}

rel: amends -> [[bsd-r1-remedy-r8-64117e1]]
rel: evidence-for -> [[impl-remedy-bsd-r8-64117e1]]

**Range:** 64117e1..a3a324e. I read the shas from `git log`:
- 9b61988: the r8 report
- 797def8: r8 #s-2
- 868845d: r8 #s-1 and #s-4
- db2750f: r8 #s-3
- a3a324e: r8 #m-1..#m-3 and the summary
- 643fb70, e830897, cadc80f: docs-only (explorations, ADR-0004 and plan-11). I gave these a MEH-level read.

Two commits after a3a324e (de95e8e, 10d6c23) are out of range.
**Date:** 2026-10-07T12:10:32-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed (code commits):** 22 (src 6, tests 13, workflow 3)

## Method {#method}

- **Targeted tests only** (bug-085/088).
  - I ran 16 files in an isolated copy: **202 passed** (`workflow/review-output/r9-baseline-copy.log`).
  - Adding `test_rerank_cost_budget.py` makes 17 files: 224 passed.
- **Mutations** ran in a `git archive a3a324e` copy at `/tmp/r9m`, which had its own `Store.init()`ed
  `.refmatrix/`. The harness is `mut.py` in my scratchpad. For every run it:
  - PREPENDED `PYTHONPATH` with the copy's `src`;
  - asserted `refmatrix.__file__` resolves inside the copy;
  - cleared `__pycache__`;
  - restored each mutated file from saved bytes and checked the sha256;
  - ran `git diff --quiet` in the copy.

  Every surviving mutant collected the baseline count (202 or 224). The 12 launchctl dev-tree-guard
  failures are not in this file set. Log: `workflow/review-output/r9-mutations.log`.
- **Probes** ran in a second copy (`/tmp/r9p`, a3a324e) and a third (`/tmp/r9o`, 9b61988, the code
  before the remedy). Each used a real Store, a real snapshot and a real `_MemMirror` on a bare `Daemon`
  (the shape of `tests/test_ingest_concurrency.py::_bare_daemon_with_store`). The budget probe used a
  REAL `SharedWorkerClient` over the real frame protocol, talking to a fake worker socket inside the
  copy (`RMX_MODEL_SOCK`). That fake applies the worker's own dequeue-deadline check
  (`embed_worker.py:160-170`). No model was loaded. The only network was a unix socket in the copy.
- **bug-092's premise had changed.** `env -u PYTHONPATH .venv-eval/bin/python -c 'import lance'` now
  works: `typing_inspection` was installed into `.venv-eval` at 11:45, and de95e8e (out of range)
  records it. To test the loud-skip change I therefore simulated the broken import: a `PYTHONPATH`
  dir whose `typing_inspection/__init__.py` raises `ModuleNotFoundError`.
- Nothing opened a live `.refmatrix/`. No `rmx` write ran, and no launchctl verb ran.

### Mutation table {#mutations}

27 mutations: **18 killed, 9 survive.**

| id | mutation | result |
|---|---|---|
| R2 | `_op_ann_search` drops `warnings` | killed |
| R3 / R3b | `_op_memory_recall` drops / does not collect `warnings` | killed (2 each) |
| R5 | CLI `memory recall` daemon branch does not print | killed |
| R8 | replica recall ignores `why` | killed |
| R9 | scan-prompt drops `rr_why` | killed |
| R10b | `_op_context` drops the construction-failure warning | killed |
| R13 | `RerankSkipped` not appended | killed |
| R16 | anchored path drops `warnings=bundle.warnings` | killed |
| **B1** | `with_budget` returns an UNBOUNDED view (`budget_s=None`) | **SURVIVES** (with `test_rerank_cost_budget.py` too) |
| **B2** | `with_budget` returns `self` | **SURVIVES** (same) |
| B3 | `_op_context` does not call `with_budget` | killed |
| B4 | `_op_context` back on the writer under `_store_lock` | killed |
| B5 | `RMX_CONTEXT_RERANK_S` ignored | killed |
| B6 | the estimate check in `RemoteReranker.score` never fires | killed by `test_rerank_cost_budget.py` (4) |
| M1 | verb overwrites body warnings with the op's | killed |
| **M2** | verb merge no longer de-duplicates | **SURVIVES** |
| **V10-V14** | the `vacuum` / `prune-noise` / `sync` / `memory dedup` / `memory bulk-forget` render site does not call `_say_vector_delete_failures` | **SURVIVE (5)** |
| V15 | `forget` render site | killed |
| **V16** | the watch flush does not total `vector_delete_failed` | **SURVIVES** |
| V17 | `forget_by_selector` reports 0 | killed (2) |
| V18 | `_say_vector_delete_failures` never prints | killed |
| L3 | `launchd_path` drops its `is_dir()` filter | killed |

## r8 findings: closed vs open {#r8-status}

| r8 | status | evidence |
|---|---|---|
| #s-1 count reaches no renderer | **PARTIAL** → [[#s-2]] | `bulk_forget_memories`, `forget_by_selector` and `vacuum` now return the count. Every op I traced passes it through, and `rmx forget` prints it (V15, V17, V18 killed). Still open: 5 of the 6 render sites and the watch-flush tail can be deleted with the suite green, and single `memory forget` and `untrack` still drop the count. |
| #s-2 phrase rerank under `_store_lock` | **PARTIAL** → [[#b-1]], [[#b-2]] | The writer lock is free during the rerank: probe P2 waited 0.00 s, against 1.61 s at 9b61988, and B4 is killed. The move created [[#b-1]] and only moved the lock wait to the read lock. The budget does not limit the wait ([[#b-2]]). |
| #s-3 9 route mutations survive | **CLOSED with power** | R2, R3, R3b, R5, R8, R9, R13 and R16 are all killed in my run. R10's behaviour was deliberately removed (#m-2), and its replacement R10b is killed. |
| #s-4 `importorskip` on a broken Lance | **CLOSED with power** | With a simulated broken `typing_inspection`, the 7 files ERROR at collection (`7 errors`), and 0 of the 8 other Lance/dense files skip (24 failed, 12 errors, 0 skipped). The other Lance users already used `find_spec` (`r9-lance-broken-import.log`). Clean env, real venv: 106 passed (`r9-lance-clean-env.log`). |
| #m-1 launchd residue | **CLOSED** | The docstring matches the symlink install, the hub passthrough is named, and L3 is killed. r8's `which rmx` duplicate and `~/bin`-leads-PATH suggestions were not taken. I do not re-file them. |
| #m-2 duplicate / unreachable messages | **CLOSED** | The R10 test asserts the score-time degrade appears once in text mode, and M1 is killed. The `embed --gc` hint names its `import lance` prerequisite. M2 (dedupe) survives → [[#m-1]]. |
| #m-3 doc notes | **CLOSED** (text) | The r6 summary now says the second `npm install` row is ASSUMED kept and awaits the user. |

Closed: 5. Partial: 2. Open: 0.

## Findings {#findings}

### BULLSHIT #b-1: on the daemon's default read path, the context op now answers from another partition when a read on a different partition runs at the same time (39 of 40 under contention, 0 of 40 before) {#b-1}

**File:** `src/refmatrix/daemon.py:4682` (`_read_with_fallback(d, _ctx_part, _build)`),
`src/refmatrix/daemon.py:2420-2436` (`_open_read_store`, mirror branch),
`tests/test_graph_landing.py:97-99`
**What:** 797def8 moved `build_context` from the writer to `_read_with_fallback`. That path is
"bound to the requested partition" by `_open_read_store`.
**Why it's bullshit:**
- The default read path is the in-memory mirror (`RMX_MEM_MIRROR=1`). The mirror is ONE shared
  `Store`, and `_open_read_store` re-points it by assigning `mirror_store._partition_name` /
  `_partition_id` after it releases `_use_lock`.
- `fn` then takes `_use_lock` in a separate acquisition. Any other mirror reader on another partition
  (`memory_get`, `memory_iter`, `describe`, `top_concepts` …) can re-point the shared store in
  between. `build_context` then resolves the ref in THAT partition.
- The old code bound the partition with `d._st().with_partition(_ctx_part)` under `_store_lock`.
  That is the exact defect its own comment names, the "graph not coming up" `anchor=None` (bug-034
  lineage).
- The remedy did not test this path; it bent the guard around it:
  - `test_context_op_honors_partition_under_ambient_drift` gained `_open_read_store → None`, so the
    partition-drift guard now exercises only the writer fallback (no snapshot yet).
  - Every new context test stubs `_open_read_store`, with `None` or a private second `Store`.
  - No test runs `_op_context` over a `_MemMirror`.

  That is rule-10 shape: the test was adapted so it no longer reaches the path production takes.

**Evidence** (probe P3, `workflow/review-output/r9-mirror-probe-a3a324e.log` vs
`r9-mirror-probe-9b61988.log`): this is a real two-partition store (`code` has the jetsam docs,
`notes` has unrelated docs plus memory `note-1`). Real snapshot, real mirror. 40 `context("jetsam",
partition="code")` ops ran concurrently with 40 `memory_get(note-1, partition="notes")`. I
instrumented `build_context` to record `store._partition_name` at call time.

| tree | right | empty (wrong partition) | `build_context` ran on |
|---|---|---|---|
| a3a324e | 1 | **39** | `{'code': 1, 'notes': 39}` |
| 9b61988 (before the remedy) | 40 | 0 | `{'code': 40}` |
| a3a324e, contexts only (control) | 40 | 0 | `{'code': 40}` |
| a3a324e, serial | 6,6,6,6,6 | — | — |

**Fix:**
- Bind the partition INSIDE the same `_use_lock` acquisition that runs `fn`: re-point (or pass the
  partition id) and run under one `with`, and restore after. Better still, stop mutating a shared
  Store's partition; give `fn` a per-call partition-bound view.
- Also handle the silent case: the `SELECT id FROM partitions` that finds no row (a partition newer
  than the snapshot) leaves the mirror on whatever partition it last held. Fall through to the
  snapshot file in that case.
- Pin the fix with a test that drives `_op_context` over a real `_MemMirror` against a concurrent
  read on another partition. My probe is that test, minus the assertions.

**Pattern match:** YES. This is "a read-path fix applied to a shared resolver reaches …"
(imp-read-fix-reaches-write-path) and the test-bent shape (rule 10). It is the first wrong-ANSWER
regression in this remedy lineage.

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-2: `with_budget` does not limit the wait, and on the read path the rerank now holds the mirror's one-reader lock instead of the writer's {#b-2}

**File:** `src/refmatrix/reranker.py:329-338` (`with_budget`), `src/refmatrix/reranker.py:340-363`
(`score`), `src/refmatrix/modelsrv.py:200-210` (`info` caches), `src/refmatrix/daemon.py:4647-4682`,
`src/refmatrix/daemon.py:300-340` (`_MemMirror`)
**What:** The summary says an over-budget pool "degrades to a warning", and the code comment says
"recorded on bundle.warnings, never a wait".
**Why it's bullshit:**
- **The budget limits nothing on the client.**
  - `with_budget` builds a view over the daemon's cached client, whose socket timeout is
    `SHARED_OP_TIMEOUT_S` (45 s). `score` never passes `timeout=`.
  - The `deadline` only lets the WORKER drop the frame when it reaches the front of the queue. The
    daemon still blocks until then.
  - The pre-check reads `self._client.info()`, which `SharedWorkerClient.info` caches forever from
    the adoption-time probe. On a fresh hub that probe has no `cost_s_per_doc`, so the estimate is
    `None` and the check never fires. It also never sees a later `queue_depth`.
- **The hold moved; it was not removed.** On the default (mirror) path, `fn` — and so the model call
  — runs under `_MemMirror._use_lock`, "one reader at a time". The class docstring says a borrower
  "must NOT hold the returned Store across blocking ops". On the snapshot-file path the rerank holds
  a `_read_inflight` reservation for the same time.
- **Neither property is tested.** The new lock test stubs `with_budget` (it records the number and
  returns `self`), so B1 and B2 survive. The summary's "86 related tests pass" says nothing about the
  bound.

**Evidence:**
- **Probe P1** (`r9-budget-probe.log`): a real `SharedWorkerClient(timeout=45)`, probed once as
  `_model_client` does, against a worker that takes 4 s to reach our frame.

  | case | budget | wall | outcome |
  |---|---|---|---|
  | daemon's client | 1.0 s | **4.01 s** | `WorkerError(deadline expired 3.01s ago)`, not a skip |
  | daemon's client | 3.0 s | **4.01 s** | same |
  | daemon's client after the hub reports `queue_depth=10, cost_s_per_doc=0.5` | 3.0 s | **4.01 s** | cached info is `{'model': 'fake/ce'}` |
  | a FRESH client (the hook's `shared_reranker` shape), same report | 3.0 s | **0.00 s** | `RerankSkipped(… = 16.5s > 3.0s left)` |

  A worker that is busy for longer holds the op up to 45 s, the r8 number.
- **Probe P2:** a 2 s score inside a context op, with three callers starting 0.4 s later.

  | tree | writer lock waits | `memory_get` waits | mirror `refresh()` waits |
  |---|---|---|---|
  | a3a324e | 0.00 s | **1.61 s** | **1.61 s** |
  | 9b61988 | **1.61 s** | 0.00 s | 0.01 s |

  The mirror refresh runs under `_snapshot_lock`, so the snapshot tick stalls too.

**Fix:** Do what r8's first option and `memory_recall` already do. Collect the docs under the read
lock, RELEASE it, and score outside. And make the bound real:
- `score(..., timeout=remaining)` on the call, or a per-request `SharedWorkerClient` view with the
  budget as its socket timeout, like `shared_reranker`;
- `info` re-read (uncached) for the estimate.

Add a test that runs `with_budget` against a slow worker and asserts on the wall, which kills B1
and B2.
**Pattern match:** YES. This is the 5th appearance of "a bound on one leg is not a bound on the
caller" (imp-partial-bound-4, imp-bound-holds-answer-dead, imp-probe-timeout-leak), so SKETCHY
escalates to BULLSHIT. The cached-`info` blind spot is the daemon-side twin of the hook's bug-025
fix, which only works because the hook builds a fresh client each process.

rel: contradicts -> [[claude#no-workarounds]]

### SKETCHY #s-1: two more model calls run under `_store_lock`: the recall query embed and the batch embed {#s-1}

**File:** `src/refmatrix/daemon.py:5764-5771` → `src/refmatrix/recall.py:57`;
`src/refmatrix/daemon.py:5473-5511`, reached from `daemon.py:3514` (`drain_memory_vectors`)
**What:** I swept every `with d._store_lock` block for a path into `embed_texts` or `score`. The
context op is no longer one of them. Two remain, both pre-existing and outside the range:
1. **`_op_memory_recall`.** `hybrid_memory_recall` / `dense_recall` call `embedder.embed_texts([query])`
   INSIDE `with d._store_lock, d._st().with_partition(partition)`. This is the same op whose rerank
   was carefully moved outside ("Model call OUTSIDE _store_lock").
2. **`_op_embed`.** It encodes up to 256 texts (`emb.embed_texts(...)`) under the lock. Its
   unattended callers are the `as_memory` ingest completion (`drain_memory_vectors`), which is
   `rmx save-state` and the SessionStart `--detach` catch-up, and it loops batch after batch.

**Why it's sketchy:**
- Both go to the shared embed worker with the client's 45 s socket timeout and no deadline.
- One embed worker serves the whole fleet. Any other daemon's batch therefore queues ahead of this
  daemon's one-line query embed, and this daemon's writer waits behind it.
- That is the lock-holding wedge class of bug-085, on the hottest memory read (`memory_recall` from
  hooks and MCP).

**Evidence:** I read the code at the lines above. `rmx grep -nE "embed_texts\(|\.score\(" src/`
finds 4 call sites. These 2 are under the lock. `_op_ann_search` embeds before its lock (`:5682`
vs `:5684`).
**Fix:**
- Embed the query BEFORE taking the lock, and pass the vector into `hybrid_memory_recall` (the
  `ann_search` shape).
- For `_op_embed`, extract the texts under the lock, encode outside it, and upsert under it again,
  checking that the rows still exist.

**Pattern match:** YES, related to bug-085 and to r8 #s-2.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-2: `vector_delete_failed`: the remaining routes are unpinned, and single `memory forget` and `untrack` still drop it {#s-2}

**File:** `src/refmatrix/cli.py:7730`, `7760`, `8362`, `12568`, `12945`;
`src/refmatrix/daemon.py:3031`; `src/refmatrix/daemon.py:4866-4874` (`_op_memory_forget`);
`src/refmatrix/store.py:2751-2761` (`forget_memory`), `store.py:6855-6881` (`untrack_by_path`)
**What:** The summary says "Every render site prints it … memory forget".
**Why it's sketchy:**
- **5 of the 6 render calls are unpinned.** V10 (vacuum), V11 (prune-noise), V12 (sync), V13
  (memory dedup) and V14 (memory bulk-forget) each delete one call with all 202 tests green. Only
  `rmx forget` has an end-to-end test (V15). The watch-flush `vector_delete_FAILED=N` tail is
  unpinned too (V16).
- **"memory forget" in the summary is the BULK command.** `rmx memory forget <name>` and the MCP
  memory verb's `forget` action reach `_op_memory_forget`. That calls `forget_memory`, then
  `purge_entity`, then the single-id `_drop_lance_for_purge` (the V8 site). It counts the failure
  on the Store and returns `{"forgotten": ok}`. The count never leaves the daemon. The project rule
  covers memory paths specifically, and this is the most common one.
- `untrack_by_path` (`rmx untrack`, op `untrack`) and the re-ingest purge (`ingest.py:1180`) return
  no count either.

**Evidence:** Mutations V10-V14 and V16 survive (`r9-mutations.log`). I read the code at the lines
above. `_op_memory_forget` returns exactly `{"forgotten": ok}`.
**Fix:**
- Return the delta from `forget_memory` (as a dict, or through the op) and from `untrack_by_path`.
- Print it in `memory forget`, and put it on the verb's result.
- Add one CLI test per render site. They can share a parametrized fixture: the forget test's
  broken-dataset store already works for all of them.

**Pattern match:** YES, the fourth consecutive round (r6 #s-2, r7 #s-1, r8 #s-1, now this) where the
remedy covered the legs it listed and the claim covered more. It stays SKETCHY, as in r8: every
failure is printed somewhere, and the uncovered legs are named. A fifth round escalates.

rel: contradicts -> [[claude#no-silent-failures]]

### MEH #m-1: small unpinned or undocumented changes in the context op {#m-1}

- M2 survives: the verb's merge de-duplication (`if w not in …`) can be deleted with the suite green.
- The context op now reads the snapshot or mirror, which trails the writer by
  `RMX_SNAPSHOT_DEBOUNCE_MS` plus the copy. It used to read the writer, so a `memory add` / `sync`
  followed at once by `context` was read-your-writes. Now it can miss the write. The op's docstring
  still says only "routes through the daemon". Say so there, or bind the read store to the latest
  snapshot when a write is pending.

### MEH #m-2: the r8 "MCP ordering never measured" point is anchored to task 16.10, which has no spec {#m-2}

The summary's `{#open}` block hands it to "task 16.10's NL replay". 16.10 exists as one bullet in
`docs/architecture/explorations/agent-context-usage.md:167` and a "tasks 16.7-16.10" note on
plan-16's `plan-of-plans.md` row. plan-16 is `drafting`, and `workflow/plans/plan-16-invisible-grep-shim-tasks/`
holds task-16.1 … 16.6 only. Following r8's treatment of plan-17 row 17.1, this is an active plan
with its spec pending, so MEH-active. It becomes unanchored (rule 9a) if 16.10's spec is written
without an NL-ordering acceptance criterion on the MCP/daemon route.

## Docs-only commits (MEH read) {#docs-commits}

643fb70, e830897 and cadc80f contain no `src/` or `tests/` lines. The explorations record measured
numbers with their environment ("run on deployed 0.76.2, which skips the NL reranker"). ADR-0004's
supersession of plan-11 is a user decision, recorded as such. Nothing to file.

## Deferral sweep (rules 9 / 9a) {#deferrals}

The hard and soft deferral patterns over the added lines in `src/` and `tests/` return 0 hits. The
only open item in the summary is [[#m-2]]. bug-092's "env NOT fixed, awaits the user" was false from
11:45 (the venv had `typing_inspection`). It was corrected out of range by de95e8e. No stale
deferral to a completed plan.

## Verdict {#verdict}

**DIRTY: 6 findings (2 BULLSHIT, 2 SKETCHY, 2 MEH).**

**Blockers:**
- [[#b-1]]: the context op answers from the wrong partition on the default mirror path (39/40 under
  contention; 0/40 before 797def8), and the partition guard test was redirected to the writer
  fallback.
- [[#b-2]]: `with_budget` does not limit the wait (1 s budget, 4.01 s wall; the cached `info` blinds
  the estimate), and the rerank now holds the mirror's one-reader lock (`memory_get` 1.61 s behind
  a 2 s score).

r8: 5 closed (#s-3 and #s-4 with power), 2 partial (#s-1, #s-2). 27 mutations: 18 killed, 9 survive
(B1, B2, M2, V10-V14, V16).

rel: contradicts -> [[claude#no-workarounds]]
