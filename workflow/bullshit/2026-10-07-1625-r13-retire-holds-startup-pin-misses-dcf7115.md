---
gmd: "0.1"
id: bsd-r1-remedy-r13-dcf7115
title: "r12 remedy: retire() ends the orphan, the writer branch no longer reranks, H1/H3/H11/K3 die; the startup-warmup and refill-bound pins drive helpers, not routes"
severity: SKETCHY
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r12
round: 13
prior: 2026-10-07-1504-r12-warm-thread-outlives-close-cf50d89.md
tags: [bsd, audit, remediation, rerank, private-worker, subproc, retire, mutation]
---

# ch-bsd round 13: 8645ef6..dcf7115 {#root}

rel: amends -> [[bsd-r1-remedy-r12-cf50d89]]

**Range:** 8645ef6..dcf7115. I read the shas from `git log --oneline -6`:
- 4fb5000: the r12 remedy (`subproc.py`, `reranker.py`, `daemon.py`, three test files, the summary)
- dcf7115: the remedy mutation follow-up (J2 pinned)

**Date:** 2026-10-07T16:25:32-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 7 (src 3, tests 3, workflow 1)

## Method {#method}

- **Isolated copies.** HEAD → `/tmp/r13c`, base 8645ef6 → `/tmp/r13b`, both made with `git archive`,
  each with its own git and no `.refmatrix/`. Every run set `PYTHONPATH=<copy>/src` and
  `RMX_MODEL_SOCK=<copy>/nosock.sock` and cleared `__pycache__`. Probes ran with `python -I` and
  asserted that `refmatrix.__file__` resolves inside the copy.
- **Live-socket record.** `workflow/review-output/live-socket-touches.log` read **145 before and
  145 after** every run.
- **Targeted tests** (`r13-targeted.log`). 23 files that touch `WorkerClient`, `RemoteReranker`,
  `_reranker`, `_apply_rerank_safe`, `_op_context` or the warm path: **321 passed, 0 failed**. The
  two warnings are the starlette deprecation and the `_RawHub` BrokenPipe, both pre-existing.
- **Probes** (`r13-probes.log`) on the real `WorkerClient` and `RemoteReranker` over the test-suite
  `_STUB` model process, run on both trees.
- **Mutations** (`r13-mutations.log`). 12 mutants over a 13-file, 197-test baseline. Each one was
  reverted with `git checkout -- src`, checked with `git diff --quiet`, and followed by a cache
  clear. L12 was re-run 3× on its own file, because the `-x` loop first stopped on a different
  test.
- **Untouched.** Nothing opened a live `.refmatrix/`, and no `rmx` ran against the live store. I
  wrote only `workflow/bullshit/` and `workflow/review-output/r13-*`.

### Probe results {#probes}

| probe | 8645ef6 (base) | dcf7115 (HEAD) |
|---|---|---|
| P1: `retire`/`close` behind an in-flight 3.0 s unbudgeted call | 2.81 s | 2.81 s |
| P2: adoption, budgeted view captured before the swap | skipped "cold"; spawns 2, **live `[11185]`** | skipped "cold"; spawns 1, live `[]` |
| P2: adoption, unbudgeted (`memory_recall` shape) | scored; spawns 2, **live `[11190]`** | `WorkerError: … retired …; not respawning`; spawns 1, live `[]` |
| P3: budgeted 0.5 s ops while the warm thread queues behind a 2 s unbudgeted call on a cold worker | "busy" at 0.50 s each | "warming" at 0.00 s, then the cost-estimate skip; `warming` False at the end (not stuck) |
| P4: refill fails after a successful rerank | scores returned, 0.31 s | scores returned, 0.33 s |

### Mutation table {#mutations}

| id | mutation | result |
|---|---|---|
| L1 | the refill is bounded by `budget`, not `min(budget, REFILL_TIMEOUT_S)` | **SURVIVES** |
| L2 | `retire` sets the flag but never closes the process | killed |
| L3 | `_ensure` respawns a retired client | killed |
| L4 | the writer check becomes over-broad (`if rr is not None`) | killed (the mirror-lock test) |
| L5 | the writer branch warns but still reranks | killed |
| L6 | `_start_embedder_warmup` calls `self._reranker()` again, not `load=True` | **SURVIVES** |
| L7 | H11: `_warming` is never reset | killed |
| L8 | K3: the hub warm dedupe is removed | killed |
| L9 | H1: the refill `except` no longer catches | killed |
| L10 | H3: `_store_info` no longer clears `warm_error` | killed |
| L11 | the warming fast-skip is removed | killed |
| L12 | adoption closes the old client instead of retiring it | killed (3/3 on `test_adoption_retires_the_private_worker`). In the `-x` loop the first stop was `test_the_daemons_reranker_never_loads_a_cold_private_model`, which passed 5/5 at HEAD (`r13-flake-check.log`). That is one timing flake in about 14 suite runs; I did not file it. |

## r12 findings: closed vs open {#r12-status}

| r12 | status | evidence |
|---|---|---|
| #s-1: a warm thread outlives `close()`, and an orphan model process appears at adoption | **CLOSED** | P2: no live pid for either shape at HEAD; the base leaks one for each shape. L2, L3 and L12 killed. The unbudgeted twin now degrades for one op with a named `WorkerError`, where it used to leak. |
| #s-2: surviving mutants H1, H3, H11, K3 | **CLOSED** | L9, L10, L7 and L8 killed. Each was killed by the test written for it, except H11, which the older background-warm test also kills. |
| #s-3: the writer-branch "product decision" | **CLOSED** | `_op_context._build` drops the reranker when `rs is d.store`. L5 killed, and the over-broad L4 is killed too, so read-store builds still rerank. `_read_with_fallback` reaches the writer only as `fn(d.store)`, in both writer branches. The mirror is a `_MemMirror` Store and `_open_read_store` builds a new Store, so no read store is ever `d.store`. Every `self.store =` reassignment is init or rotation code, not the read path. So no reserve or score runs under `_store_lock` any more, and the boot `reserve()` wait is gone. |
| #m-1: what the operator reads during a warm | **CLOSED in code, partly unpinned** → [[#s-1]] | Warming fast-skip: 0.00 s (P3; L11 killed). The missing-extra label is fixed on `_apply_rerank_safe`. The startup warmup loads synchronously and the refill bound is 10 s, but L6 and L1 survive. |

Closed: 4 of 4 in behaviour. One of them (#m-1) has pin gaps.

## Answers to the brief {#brief}

- **Can `retire()` block adoption or shutdown?** Yes. It is bounded only by the in-flight call:
  the worker op timeout (`RMX_WORKER_TIMEOUT_S`, 300 s), doubled on a respawn retry, plus the 10 s
  refill. This is **not new**:
  - the base `close()` took the same `_lock` (P1: 2.81 s on both trees);
  - the same flush tick's `evict_if_idle` takes it first;
  - `retire()` re-enters the RLock that `close` takes.
  No finding.
- **`rs is d.store`.** Sound (see #s-3 above). A failed read-store open also falls through to the
  writer, and the warning text is then wrong → [[#m-1]].
- **`_ReadView` in `test_rerank_warning_routes`.** Legitimate. In production the score-time degrade
  route runs only on a read store, which is never the writer object. The writer case has its own
  test on a real `Daemon` with a real snapshot and mirror. L4 shows the proxy test still fails if
  the product stopped reranking read stores. This is not a bent test.
- **`_reranker(load=True)` with a hub-shared client.** No change. `SharedWorkerClient` has no
  `reserve`, so both `load` values take the same `model_name` probe the base took.
- **Can the "warming" skip stick?** No. `_warming` is reset in `finally`. The thread's waits are the
  worker lock (bounded by the holder's op timeout) and its own `info()` (bounded, ×2). P3 ended with
  `warming=False`.
- **CLI and MCP warning surfaces.** No regression:
  - the writer warning rides the op's `warnings`;
  - the CLI prints them to stderr (`cli.py:5162`);
  - the `context` verb merges them into the JSON (`verbs.py:562`);
  - for `memory_recall`/`ann_search` only the ImportError/worker ModuleNotFoundError label changed;
  - the route tests and the surface-parity test are green.

## Findings {#findings}

### SKETCHY #s-1: two remedy behaviours are pinned on the helper, not the route; L6 and L1 survive {#s-1}

**File:** `src/refmatrix/daemon.py:1183` (`_start_embedder_warmup` → `self._reranker(load=True)`),
`src/refmatrix/subproc.py:428-429` (`min(budget, REFILL_TIMEOUT_S)`),
`tests/test_rerank_budget_real_clients.py::test_the_startup_warmup_really_loads`

**What:** the summary says #m-1's "reranker warm in 0.0s" false log is fixed and pinned (J9).

**Why it's sketchy:**
- `test_the_startup_warmup_really_loads` calls `d._reranker(load=True)` directly. It never runs
  `_start_embedder_warmup`.
- Revert the call site to `self._reranker()` (L6): all 197 tests pass. The startup then only
  starts a background warm, and logs "reranker warm in 0.0s" again. The test's name says
  "startup"; its body tests the helper.
- `REFILL_TIMEOUT_S` (L1) has no test at all. Drop the bound and the refill is bounded by the op's
  whole timeout again (300 s default; a kill on expiry).
- This is the fourth straight round with a surviving mutant on remedy code (r10, r11, r12, r13).
  Under the escalation rule (seen 2+ times) that takes it from MEH to SKETCHY, even though both
  behaviours are low stakes.

**Fix:**
- Drive `_start_embedder_warmup` on a `Daemon` with a stub-argv private worker (rerank enabled,
  `RMX_NO_EMBED_WARMUP` unset, `_embedder` stubbed). Assert that the "reranker warm" log fires only
  once `wc.info(nowait=True)` is populated.
- Pin the refill bound with a stub whose `info` sleeps longer than a patched `REFILL_TIMEOUT_S` but
  less than the op timeout.

**Pattern match:** YES: imp-mutation-tally-is-log-lines and the r8 route-vs-helper pattern. "J9
killed" was true of the helper mutant, not of the call site the summary describes.

rel: contradicts -> [[claude#before-commit]]

### MEH #m-1: the writer-branch warning names one of its three causes {#m-1}

**File:** `src/refmatrix/daemon.py:4697-4708`, `:4848-4876`

The warning always reads "the partition is newer than the read snapshot". The same branch also
runs when:
- no snapshot exists yet (boot); the code comment names this case itself;
- `_open_read_store` fails to open the snapshot (it returns `None` and logs
  `open_read_store(...) failed`).

In those two cases the operator is told a false cause. **Fix:** word it by cause ("answered from the
writer (no usable read snapshot) …"), or pass the reason out of `_read_with_fallback`.

rel: contradicts -> [[claude#no-silent-failures]]

### MEH #m-2: registries not updated for what this remedy fixed {#m-2}

- **Bug registry.** r12 asked for a `workflow/bug_registry.md` row for the unbudgeted adoption leak,
  which existed at the base and is now fixed. There is none (rule: `.claude/rules/bug-registry.md`).
- **Mock registry graduation.** `workflow/test_mock_registry.md:85` (`_FakePrivate`) graduates
  "when an adoption test runs against a real spawned stub worker".
  `test_adoption_retires_the_private_worker` now does exactly that, and the row was not touched.
- **Mock registry, new fake.** The new `rerank_available` fake in `test_rerank_budget_real_clients.py`
  is registered only for `test_plan2_remedy_r6.py` (row 62).

rel: contradicts -> [[claude#task-completion-workflow]]

## Deferral sweep (rules 9 / 9a) {#deferrals}

I ran the hard and soft patterns over every added line in `src/` and `tests/`: **0 hits**.

## Verdict {#verdict}

**DIRTY: 3 findings (0 BULLSHIT, 1 SKETCHY, 2 MEH).** Nothing blocks.

- All four r12 findings are closed in behaviour, with probe and mutation evidence.
- By the project gate ("no unaddressed BULLSHIT") `bsd-r1-remedy` may merge to `master`. #s-1 and
  the two MEH items are follow-ups, not blockers.
- 12 mutations: 10 killed, 2 survive (L1, L6).
- Targeted tests: 321 passed.
- The live-socket recorder read 145 → 145.

rel: contradicts -> [[claude#before-commit]]
