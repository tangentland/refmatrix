---
gmd: "0.1"
id: bsd-r1-remedy-r12-cf50d89
title: "r11 remedy: a respawned private reranker warms again and the context op never pays a cold load; a warm thread can respawn a closed client, H11/K3 survive, and the writer-branch 'product decision' is a dodge"
severity: SKETCHY
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r11
round: 12
prior: 2026-10-07-1418-r11-private-worker-cold-forever-4783463.md
tags: [bsd, audit, remediation, rerank, budget, private-worker, subproc, warmup, mutation]
---

# ch-bsd round 12: 9a1b745..cf50d89 {#root}

rel: amends -> [[bsd-r1-remedy-r11-4783463]]

**Range:** 9a1b745..cf50d89. I read the shas from `git log --oneline -6`:
- 83ab187: the r11 remedy (`subproc.py`, `reranker.py`, `daemon.py`, two test files, r10 and r11
  implementation summaries)
- cf50d89: the remedy mutation follow-up (two tests, the summary's mutation section)

**Date:** 2026-10-07T15:04:56-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 7 (src 3, tests 2, workflow 2)

## Method {#method}

- **Isolated copies.** HEAD went to `/tmp/r12c` with `git archive`, plus its own git and no
  `.refmatrix/`. The base 9a1b745 went to `/tmp/r12b` the same way, as the comparison tree. Every
  run set `PYTHONPATH=<copy>/src` and `RMX_MODEL_SOCK=<copy>/nosock.sock`, cleared `__pycache__`,
  and asserted that `refmatrix.__file__` resolves inside the copy. Probes ran with `python -I`.
- **Live-socket record.** The project recorder `workflow/review-output/live-socket-touches.log`
  read **145 lines before and 145 after** every run.
- **Targeted tests** (`r12-targeted.log`). I ran the 19 files that touch `WorkerClient`,
  `RemoteReranker`, `_reranker` or `_apply_rerank_safe`: **258 passed**, 0 failed. The one
  warning is a `BrokenPipeError` in the `_RawHub` test fixture, which was already there.
- **Probes**, on the real `WorkerClient`, `RemoteReranker` and `Daemon._reranker` /
  `_apply_rerank_safe` over the remedy's `_STUB` model process:
  - `r12-probes.log`: close/warm races, the first skip, the unbudgeted degrade, a hanging refill,
    and realistic warm timing
  - `r12-probe-adoption-orphan.log`: hub adoption with an op in flight, on both trees
- **Mutations** (`r12-mutations.log`). 10 mutants in the copy, each reverted with
  `git checkout -- src` and checked with `git diff --quiet`.
- **Untouched.** Nothing opened a live `.refmatrix/`, and no `rmx` ran against the live store. I
  wrote only under `workflow/bullshit/` and `workflow/review-output/r12-*`.

### Mutation table {#mutations}

| id | mutation | result |
|---|---|---|
| H1 | the refill in `call` loses its `try/except`, so a failing refill raises out of a successful op | **SURVIVES** |
| H3 | a successful background warm no longer clears `warm_error` | **SURVIVES** |
| H4 | `_reranker()` caches the unprobed reranker on the cold path | **SURVIVES** (near-equivalent) |
| H11 | `warm_async` never resets `_warming`, so only one warm runs per client lifetime | **SURVIVES** |
| H13 | the cold skip never reads `warm_error` | killed |
| H14 | the refill never fires (equivalent to G1) | killed |
| K1 | the no-snapshot unknown-partition guard is removed | killed (r11 residual: closed) |
| K2 | the hub `nowait` path stops calling `warm((role,))` | killed (r11 residual: closed) |
| K3 | the hub `warm()` loses its `_warming` dedupe | **SURVIVES**. The summary says it is pinned. |
| K7 | a budgeted view never closes its forked connection | killed (r11 residual: closed) |

## r11 findings: closed vs open {#r11-status}

| r11 | status | evidence |
|---|---|---|
| #b-1: a private reranker stays cold after a respawn | **CLOSED** (pin gap → [[#s-2]]) | Respawn then budgeted: scored ×3 (remedy test, green here). Timing probe at load 2.0 s / budget 1.0 s: the first op waits **1.01 s** and skips, the second **0.99 s** and scores, then 0.05 s each; spawns = 1, loads = 1. `_reranker()` on a cold private worker returns in **0.00-0.04 s**. With the idle-evict route the context op no longer pays the load before its budget. A refill that hangs does not fail the op: scores came back, wall 1.84 s at timeout 1.0 s, and the worker was killed ([[#m-1]]). G1-G7 killed. Gap: **H11** survives. With one warm per client lifetime, the SECOND cold episode (respawn or evict, then only budgeted traffic) is r11 #b-1 again, and no test notices. |
| #m-1: unpinned residuals and a miscounted claim | **PARTIAL** | K1, K2 and K7 are killed at HEAD. The tally in the r10 summary is corrected. **K3 still survives** while the summary says "K2 / K3 … pinned". The test asserts `spawns == 1 and loads == 1`, which duplicate warm threads also satisfy: they serialize on the worker lock and read the cached header. The writer-branch residual is "accepted, not changed" → [[#s-3]]. |

Closed: 1 (#b-1). Partial: 1 (#m-1). Open: 0.

## Findings {#findings}

### SKETCHY #s-1: a warm thread outlives `close()`, and an op in flight at hub adoption leaves an untracked private model process for the daemon's life {#s-1}

**File:** `src/refmatrix/subproc.py:424-451` (`warm_async`), `:285-289` (`_ensure` respawns on any
call), `src/refmatrix/reranker.py:403-410` (the cold skip calls `warm_async`),
`src/refmatrix/daemon.py:925-1013` (`_maybe_adopt_shared` swaps the client, then `w.close()`),
`:1092-1105` (`_close_workers`)

**What:** the remedy has a cold budgeted skip start a background `info()` on the client it holds.

**Why it's sketchy:**
- `close()` is not terminal. Any later call respawns, and the warm thread calls `info()`.
- An op that built its budgeted view BEFORE `_maybe_adopt_shared` swapped in the hub client can
  reach `score()` AFTER `w.close()`. There it reads `{}`, skips "cold", and calls `warm_async()` on
  the retired client. That thread spawns a private worker and loads the model.
- Nothing tracks that process. `_rerank_worker` is now the shared client, so `worker_kinds()`
  reports `shared`, idle-evict never visits it, and `_close_workers` never closes it.
- Dropping the client does not reap the child. `Popen.__del__` puts a running child on
  `subprocess._active`, which keeps its stdin pipe open. So the child lives until the daemon exits.
- That is the bug-024 "split fleet, invisible" state, at the cost of one model's RSS.

**Evidence** (`r12-probe-adoption-orphan.log`). The adoption sequence: a warm private reranker, a
budgeted view taken, the client swapped and closed, the view scored, then every reference dropped
and `gc.collect()`:

| tree | in-flight op | live pids after the op and GC | spawns |
|---|---|---|---|
| 9a1b745 (base), budgeted | skipped "cold" | `[]` | 1 |
| cf50d89 (HEAD), budgeted | skipped "cold" | **`[93720]`** | **2** |
| 9a1b745, unbudgeted (`memory_recall` shape) | scored | `[93832]` | 2 |
| cf50d89, unbudgeted | scored | `[93844]` | 2 |

- The budgeted route is NEW in this remedy.
- The unbudgeted route already existed at the base and is not registered anywhere.
- `close()` then `warm_async()` on one client: alive, spawns 2, and the pid is still live after the
  client is dropped (`r12-probes.log`, P1d).
- At `_close_workers` (shutdown) the same race spawns a child that dies once its load finishes and
  its write to the dead parent fails. That case is bounded.
- With RMX_WORKER_IDLE_S the client stays tracked, so a respawn there is the normal lazy one. That
  case is fine.
- I ran the orderings warm-then-close (20/20) and warm-queued-before-close (10/10): no leak. Only
  close-then-warm leaks.

**Fix:** give `WorkerClient` a `retire()` that sets a flag under `_lock`. Once retired, `_ensure`
raises instead of spawning and `warm_async` is a no-op. Call it from `_maybe_adopt_shared` and
`_close_workers` instead of a bare `close()`. Pin it with the adoption probe above: after the
in-flight op, the live pids must be `[]` for both the budgeted and the unbudgeted shapes. Register
the unbudgeted twin in `workflow/bug_registry.md`.

**Pattern match:** YES: imp-budget-view-shares-the-lock ("list every wait between the call and the
bytes (locks, caches, respawns)"). The respawn here is the one nobody listed.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-2: the remedy's own new code has four surviving mutants, and one of them is r11 #b-1 coming back {#s-2}

**File:** `src/refmatrix/subproc.py:389-400,432-451`, `tests/test_rerank_budget_real_clients.py`

**What:** cf50d89 says "7 of 7 killed". My mutants of the same code (`r12-mutations.log`, 125-test
baseline over 9 files):

- **H11 survives.** Without the `finally` reset, `warm_async` runs once per client lifetime. Every
  test needs exactly one warm. With traffic that is only budgeted (the case r11 #b-1 named), the
  second cold episode (a later respawn or idle-evict) makes every skip call `warm_async`, which
  returns at once, so the worker stays cold for the daemon's life. That is the blocker r11 filed,
  with no test to catch it coming back. Pin: two cold episodes on one `WorkerClient`, each healed by
  budgeted calls alone.
- **H1 survives.** The summary says "the op itself succeeded" stands even when the refill fails, but
  no test makes the refill fail. Pin: the hanging-info stub (`r12-probes.log`, P3) must return the
  scores.
- **H3 survives.** A stale `warm_error` after a later success: the next cold episode would name a
  ModelNotCached that has since been fixed, and that wording drives operator action (r6 #s-2).
- **K3 survives** while the summary says it is pinned ([[#r11-status]]). Count the warm threads, as
  the private G5 test does.
- H4 is near-equivalent and is not part of this finding.

**Pattern match:** YES: imp-mutation-tally-is-log-lines (r11). The claim's set is not the code's
set. This is the third round in a row with surviving mutants on remedy code. The finding stays
SKETCHY because each named mutant has a one-test fix.

rel: contradicts -> [[claude#before-commit]]

### SKETCHY #s-3: "a product decision, recorded here and not taken" is a dodge (escalated from r11 #m-1) {#s-3}

**File:** `workflow/implementation_summaries/remedy-bsd-r11-4783463.md#m-1-body`,
`src/refmatrix/daemon.py:4840-4877` (`_read_with_fallback`: the newer-than-snapshot and no-snapshot
branches run `fn`, the context rerank, under `_store_lock`)

**Why it's sketchy:**
1. **No new product question.** "Answering unreranked there" is the context op's existing contract.
   Every `RerankSkipped` already serves an unreranked answer with a warning. Building without the
   reranker on the writer branch, which r11 offered, is that same degrade.
2. **Recorded nowhere that drives work.** It appears only in an implementation summary. There is no
   row in `workflow/deferral_registry.md`, `docs/architecture/todo.md` or `bug_registry.md`, and no
   question to the user. By rule 9a, an accepted correctness gap with no scheduled task is
   unanchored.
3. **The window is wider than "a slow pass".**
   - A worker that dies inside a reserved private call is retried on a fresh process, which pays
     the full cold load under `_store_lock` (`call`'s respawn clause).
   - The no-snapshot branch (boot) has the same shape. Boot is exactly when `_start_embedder_warmup`
     → `_reranker()` → `warm_async` holds the worker lock for the load. So a context op in that
     window holds `_store_lock` for its whole budget in `reserve()`.
   - Timing probe: a reserve behind a warm waits **1.01 s at a 1.0 s budget**, and at 3.0 s by
     default.
   - At the base, that wait happened in `_reranker()`, outside the store lock (unbounded, but not
     holding writers).

**Fix:** on both writer branches, build with `reranker=None` and append the usual "rerank skipped
(read from the writer)" warning. Or, if the user wants it kept, file a registry row with an owner
and ask.

**Pattern match:** YES. r11 #m-1, second sighting (MEH → SKETCHY); the r9 #s-1 class (a model call
under `_store_lock`).

rel: contradicts -> [[claude#no-workarounds]]

### MEH #m-1: what the operator reads during a warm {#m-1}

- **The first skip says "busy", not "cold", and waits its whole budget.**
  - `_reranker()` starts the warm, then the same op's `reserve()` queues behind it.
  - Probe at load 2.0 s / budget 1.0 s: `wall=1.01s skipped: private worker busy past the 1.0s
    budget`.
  - With a slow ModelNotCached, the failure is named from the SECOND call onward. The base named it
    on the first call, but at the cost of an unbounded load. That trade is fine; what is wrong is
    the summary's "budgeted callers skip until it lands": during a load, each one waits its full
    budget.
- **A false log line.** `_start_embedder_warmup` logs `reranker warm in 0.0s` when the private
  worker has only started warming.
- **The refill's bound is the op's whole timeout, not what is left.** A hanging `info` adds one
  full timeout to a successful op and kills the model it just loaded (P3: wall 1.84 s at a 1.0 s
  timeout, `alive=False`, scores returned). On a real worker an `info` after a scoring op is a dict
  read, so this is theoretical.
- **A different label.** On the cold path a worker-side `ModuleNotFoundError` now reads
  `rerank failed (WorkerError: ModuleNotFoundError …)`, not "dense extra missing". It is still
  surfaced on `_apply_rerank_safe`'s warnings (probe).

## Deferral sweep (rules 9 / 9a) {#deferrals}

I ran the hard and soft patterns over every added line in `src/` and `tests/`: **0 hits**. The
"accepted, not changed" paragraph in the summary is an unanchored acceptance, filed as [[#s-3]].

## Verdict {#verdict}

**DIRTY: 4 findings (0 BULLSHIT, 3 SKETCHY, 1 MEH).** Nothing blocks.

- r11 #b-1 is **CLOSED**: a respawned or evicted private reranker warms again, and the context op
  never pays a cold load.
- r11 #m-1 is **PARTIAL**: K3 still survives, and the writer branch is escalated.
- By the project gate ("no unaddressed BULLSHIT") the branch is not blocked. It is not a CLEAN
  round.
- 10 mutations: 5 killed, 5 survive (H1, H3, H4 near-equivalent, H11, K3).
- The live-socket recorder read 145 → 145.

rel: contradicts -> [[claude#no-silent-failures]]
