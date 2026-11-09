---
gmd: "0.1"
id: task-23.2-lock-hold-fixture
title: "Task 23.2: one shared lock-hold and write-count recorder that every writer's tests use, on the real _FairLock"
tags: [task, tests, lock, fixture, recorder, write-count, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-11-09
---

# Task 23.2: the lock-hold and write-count fixture {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: **BUILD-READY** (revision round 4, 2026-11-09: the narrow confirm
> [[bsd-plan23-fold-additions-a9147d5]] reproduced round 3's census exactly and rates 23.2
> build-ready; no change to R6 or AC-6; one re-run caveat recorded, see [[#rev-round-4]].)
> Earlier: (revision round 3, 2026-11-09: the freshness confirm
> [[bsd-plan23-1-2-freshness-confirm-1c0b66a]]'s m1 folded: the R6 census re-run at `77c9f04`
> with a pattern that catches every assignment form (21 fake-lock lines in 17 files), AC-6
> widened to the same pattern, R3's quoted error corrected against bug-178 at `ae7c0c7`; see
> [[#rev-round-3]]. Merge gate unchanged: bug-178 merges first. Round 2: freshness fold of
> [[bsd-plan23-1-2-freshness-9bcf464]] (s3, m1, m2, m3, m6), re-cited against HEAD `9901589`; see
> [[#rev-round-2]]. Earlier: the 2026-10-14 decision log)
> Depends on: 23.0 (test sandbox). **Merge order (m6):** 3.7 → bug-178 → plan-26 → **23.2** →
> 23.1. 23.2 is written after bug-178 merges, so R3's proxy is built against its `bulk_write`.
> Blocks: 23.1 (its ACs count holds and writes with this recorder), 23.3, and the consumers' tests
> (16.6, 17.1, 19.2, 22.2)

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: implements -> [[plan-review-2026-10-14#t2-fixes]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81#b-3]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81#s-4]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81#s-5]]
rel: related-to -> [[feedback_mutation_must_fail_not_hang]]

## Why {#why}

Two kinds of wedge motivate plan-23, and they need two kinds of detector:
- a lock held while a model call runs (r8 #s-2, r9 #s-1): a free/held probe fired from INSIDE the
  call sees it;
- many small writes inside one hold (bug-085: one Lance delete per entity; bug-093: one upsert per
  concept): at fixture scale each write costs milliseconds, so a seconds bound passes the
  regression. Both RED tests counted WRITES (Lance versions, single-row upserts). The recorder
  counts them (23 #b-3).

The fakes in today's lock tests use `threading.RLock()` / `threading.Lock()`, never the production
`_FairLock` (`daemon.py::_FairLock`; strict FIFO, ownership handed on release, not reentrant;
`acquire(blocking=False)` is False when the lock is held OR waiters are queued). A nested reacquire
is invisible under an RLock (23 #s-4). 23.1's ACs need this recorder, so this task now comes
FIRST (#t2-fixes: "23.2 before 23.1"). {#why-body}

## Requirements {#requirements}

The fixture lives in `tests/lockhold.py` and is registered from `tests/conftest.py` through
`pytest_plugins`. It is test code only; nothing here enters `src/`.

1. **R1 `lock_free_during(lock) -> bool`** (one signature; 23 #m-1). A plain function a fake calls
   at the moment the code under test is inside its model call (a fake `score`, `embed_texts`, …).
   A probe thread tries `lock.acquire(blocking=False)`, releases it from the SAME thread if it got
   it (the r8 RLock lesson), and the function returns True when the lock was free. It accepts any
   lock: `_store_lock`, and the read mirror's lock AS `_MemMirror.acquire_use()` RETURNS IT
   (`daemon.py::_MemMirror.acquire_use`, r9 #b-2's shape; m2: the adopted test probes through that
   method, never through the `_use_lock` field, so R1 takes whatever object it returns). It is not a context
   manager: a context manager wraps the call and cannot fire inside it. {#r1}
2. **R2 `HoldRecorder`** wraps a REAL lock, by default a real `daemon._FairLock()`, as a
   pass-through (not a fake) with the full `_FairLock` surface (`acquire`, `release`, `locked`,
   `__enter__`, `__exit__`). Per hold it records: start, duration, thread name, and the WRITE COUNTS
   of R3. `acquire` without a timeout uses a default deadline (`RMX_TEST_LOCK_DEADLINE_S`, 10 s)
   and raises `LockDeadlock` instead of blocking forever, so a mutation that re-nests the
   non-reentrant lock FAILS the test instead of hanging the suite
   (`feedback_mutation_must_fail_not_hang`). An optional `on_release(hold)` callback lets a test
   assert a property at every release (23.3 uses it for "no open transaction"). {#r2}
3. **R3 Write counts per hold and per run** (23 #b-3). While installed on a `Store`, the recorder
   counts:
   - DuckDB statements (rewritten in round 2 against bug-178's `backend.py::bulk_write`, m3):
     - the recorder PATCHES THE EXISTING `DuckDBConnection` wrapper INSTANCE (its `execute` /
       `executemany` attributes and its `_duck` attribute), never replaces the wrapper with a
       proxy object: `bulk_write` dispatches on `isinstance(con, DuckDBConnection)` /
       `isinstance(con, duckdb.DuckDBPyConnection)`, and a stand-in object (neither of those, nor
       `sqlite3.Connection`) would make it raise `TypeError("bulk_write: unsupported connection
       type '<name>' (expected DuckDBConnection, duckdb.DuckDBPyConnection or
       sqlite3.Connection)")` (`backend.py::bulk_write`'s last branch, on `fix-bug178-bulk-write`
       at `ae7c0c7`; round 2 quoted the SQLite branch's message, which a stand-in never
       reaches; round 3, m1);
     - `_duck`'s proxy (fragment flushes call `con._duck.execute` directly,
       `store.py::Store._flush_fragments_duckdb`) passes `register` / `unregister` through
       uncounted and counts `execute`;
     - one `bulk_write` call counts as ONE statement (its register + one `execute` + unregister);
     - `executemany` counts as one statement and records its row count separately, and the
       recorder READS bug-178's counter `backend.py::duck_executemany_calls` for it instead of
       keeping a second one (`backend.py::duck_executemany_calls` on branch `fix-bug178-bulk-write`
       at `ae7c0c7`, round 3; round 2 cited `d13c4d7`; not on `master` at `77c9f04`; it exists once bug-178 merges, which precedes 23.2);
   - Lance versions: the sum of `lance.dataset(p).version` over `<root>/vectors/*/*.lance` at hold
     entry and exit (a new dataset counts its versions);
   - single-row upserts into `entities` and `concepts` (the bug-093 shape), by statement text.
   Totals per hold and per run are exposed as `rec.holds` and `rec.run_totals`. {#r3}
4. **R4 Markers that cannot pass vacuously** (23 #s-5).
   - `@pytest.mark.max_lock_hold(seconds)` fails a test whose recorded holds exceed the bound.
   - `@pytest.mark.max_writes_per_hold(statements=…, lance_versions=…)` and
     `@pytest.mark.max_writes_per_run(statements=…, lance_versions=…)` fail on R3's counts.
   - Every marker FAILS when zero holds were recorded: a marked test that never installed the
     recorder, or installed it after the code under test captured the bare lock reference
     (`ingest_path(lock=d._store_lock)`), is a failure, not a pass.
   - The fixture `recorded_daemon(root)` builds the in-process `Daemon` with the recorder installed
     as `_store_lock` BEFORE any op runs, so no callee can capture the bare lock. {#r4}
5. **R5 Seconds are an alarm, counts are the bound.** The plan's per-hold time is an alarm (23.1's
   `hold_alarm_s` logs it); consumers assert `max_writes_per_hold` / `max_writes_per_run` at
   fixture scale and use `max_lock_hold` only for model-call shapes. {#r5}
6. **R6 Adoption** (23 #m-2; extended to every fake-lock file in round 2, s3). These tests move
   onto the fixture, on a real `_FairLock` wrapped by the recorder, and their inline probe and
   counting-lock code is deleted:
   - `tests/test_context_rerank_off_the_writer_lock.py` (an `RLock` fake today);
   - `tests/test_read_path_partition_and_budget.py` (its probe through
     `d._mem_mirror.acquire_use()`, r9 #b-2, m2; a plain `threading.Lock()` `_store_lock` in its
     `_daemon` builder);
   - `tests/test_rerank_warning_routes.py` (the r9 #s-1 probes; an `RLock` fake today);
   - `tests/test_learn_queue.py` (the nested `class _CountingLock` installed as `_store_lock`, and
     its competitor thread);
   - `tests/test_bigop_nonblocking.py` (module-level `class _CountingLock`, and a
     `threading.Lock()` assigned to `_store_lock`).

   **Every other file that assigns a fake `_store_lock` (s3; re-run in round 3, m1).** AC-6 is
   suite-wide, so R6 covers every file it finds, not only the five above. Round 2's census
   matched only the spellings `threading.R?Lock()` / `class _CountingLock`, so it missed
   `__import__('threading').Lock()` and a hand-rolled context-manager recorder. The round-3
   census matches the ASSIGNMENT, whatever its value:
   `rmx grep -rnE '(_store_lock|_use_lock)\s*=' tests/ --include='*.py'`, excluding
   `tests/lockhold.py`, plus a search for `setattr(…, "_store_lock" | "_use_lock", …)` (none).
   At `77c9f04` it returns **23 lines in 18 files**. Two are not fakes:
   `tests/test_ingest_partition_yield_race.py` (`d._store_lock = _FairLock()`, already the real
   lock) and `tests/test_learn_queue.py`'s restore line (`d._store_lock = real_lock`). That
   leaves **21 fake-lock assignment lines in 17 files** (round 2 said "15 lines in 14 files";
   under its own literal pattern the figure was 14 in 13, [[bsd-plan23-1-2-freshness-confirm-1c0b66a#answers]]
   Q6). The five above plus these twelve:
   - `threading.RLock()` (an RLock hides exactly the non-reentrancy 23.1 R1.6 and this task's
     AC-5 rely on): `tests/test_context_rerank_warning.py`, `tests/test_plan12_remedy.py`
     (`:292`; and see the next bullet), `tests/test_graph_landing.py` (two assignments),
     `tests/test_lance_drop_failures_loud.py`, `tests/test_embed_phases_r10.py`;
   - `threading.Lock()`: `tests/test_ingest_concurrency.py`, `tests/test_snapshot_tier.py`,
     `tests/test_derive_unstamp.py`, `tests/test_bug110_snapshot_keeps_lock.py`;
   - **`__import__('threading').Lock()` as a class attribute (round 3, m1):**
     `tests/test_derive_coverage.py` (`:193` at `77c9f04`), `tests/test_derive_stamp.py`
     (`:179`), `tests/test_plan12_remedy.py` (`:340`, `:381`, `:430`; three more lines in a file
     already listed);
   - **a hand-rolled lock-entry recorder (round 3, m1):** `tests/test_brief_surfaces.py`
     (`_store_lock = _CtxRecorder(locks)` at `:215`; `class _CtxRecorder` at `:240` records
     `"lock"` on `__enter__`). It moves to 23.2's `HoldRecorder` (its assertion becomes "one
     hold recorded"), and `_CtxRecorder` is deleted.

   Counted per line at `77c9f04`: `test_plan12_remedy.py` 4, `test_graph_landing.py` 2, and one
   in each of the other 15 files: 21.

   Each gets a REAL `daemon._FairLock()` where the test only needs a lock to exist, or
   `recorded_daemon` where it probes or counts holds. A test that went green only BECAUSE the
   fake was reentrant is a finding, logged in the implementation summary with the nested
   acquire it hid (not "fixed" by making the fixture reentrant). The implementer re-runs the
   census at its own HEAD with the round-3 pattern; a file added since `77c9f04` joins this list.
   {#r6}

## Acceptance criteria {#acceptance}

1. **r8 #s-2 revert fails.** Moving the context rerank back under the writer lock fails the adopted
   `test_context_rerank_off_the_writer_lock.py` test through `lock_free_during`. {#ac-1}
2. **r9 #s-1 revert fails.** Moving `memory_recall`'s embedding back under the lock fails the
   adopted `test_rerank_warning_routes.py` probe. Reverting r9 #b-2 (the mirror read under the
   lock `_MemMirror.acquire_use()` returns; m2) fails `test_read_path_partition_and_budget.py`
   through `lock_free_during(d._mem_mirror.acquire_use())`. {#ac-2}
3. **The write-count detector fires on both incidents** (23 #b-3; pre-registered mutations):
   - re-introduce one Lance delete per entity in `Store.purge_path` (the bug-085 shape): a test
     marked `max_writes_per_run(lance_versions=1)` over a 12-entity purge FAILS;
   - re-introduce the per-row semantic pass in `_sync_paths` (`_ingest_python_semantics`, the
     bug-093 shape): a test marked `max_writes_per_hold(statements=K)` with K pre-registered at
     RED as the bulk path's count on the fixture + 2 FAILS, and the single-row upsert count is > 0.
   {#ac-3}
4. **No vacuous pass.** Through `pytester`: a test marked `max_lock_hold(1)` that never installs
   the recorder fails with "0 holds recorded"; a test that installs the recorder after a callee
   captured the bare lock fails the same way. {#ac-4}
5. **No hang.** A mutation that takes the recorded `_FairLock` twice on one thread raises
   `LockDeadlock` within the deadline; the test fails in under 15 s. {#ac-5}
6. **Every probe implementation is gone.** `rmx grep -rnE '(_store_lock|_use_lock)\s*='
   tests/ --include='*.py'` (round 3, m1: the census's own pattern; it matches the ASSIGNMENT,
   so `__import__('threading').Lock()`, a hand-rolled recorder, or any future spelling is
   caught) returns, outside its one exclusion (`tests/lockhold.py`), ONLY lines whose value is
   `_FairLock()` / `daemon._FairLock()`, a 23.2 `HoldRecorder`, or a restore of a lock the same
   test saved from `d._store_lock`; a search for `setattr(…, "_store_lock" | "_use_lock", …)`
   in `tests/` returns nothing; `rmx grep -rnE 'class _CountingLock|class _CtxRecorder' tests/`
   returns nothing; and no file in R6 defines a probe thread: the only definitions are in
   `tests/lockhold.py`. The patterns and the exclusion are fixed here. It can go green only
   because R6 covers all 17 files the round-3 census found; round 2's pattern
   (`class _CountingLock|threading\.R?Lock\(\)`) went green with the three `__import__` files
   and `_CtxRecorder` still in place. Mutation: leave `tests/test_derive_stamp.py:179`'s
   `__import__('threading').Lock()` in place: this AC FAILS (round 2's pattern passed it).
   {#ac-6}

## Test strategy {#test-strategy}

Every test runs inside task 23.0's sandbox (d1a/d1b): redirected `$HOME`, global root and registry,
injected store roots, the refuse guard active. Real `Store` on a short `mkdtemp` root, real
`_FairLock`, real Lance datasets for AC-3; no `rmx` subprocess. Logs go to
`workflow/review-output/pytest-lockhold.log`.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 23 #b-3 (probes cannot see per-row writes) | [[#r3]], [[#r5]], [[#ac-3]] |
| 23 #s-4 (`_FairLock` never used; 23.2 before 23.1) | [[#r2]], [[#r6]], header Depends/Blocks |
| 23 #s-5 (marker vacuous with no recorder; bound is a warning) | [[#r4]], [[#r5]], [[#ac-4]] |
| 23 #m-1 (two `lock_free_during` signatures; any lock) | [[#r1]] |
| 23 #m-2 (`test_learn_queue.py`, `test_bigop_nonblocking.py` probes) | [[#r6]], [[#ac-6]] |
| #t2-fixes (real `_FairLock`, recorder required, 23.2 before 23.1, write-count recorder) | [[#r2]], [[#r3]], [[#r4]] |
| d1a/d1b (tests in 23.0's sandbox) | [[#test-strategy]] |

## Revision round 2 (2026-11-09) {#rev-round-2}

Source: [[bsd-plan23-1-2-freshness-9bcf464]], the pre-implementation freshness review at
`9bcf464`. Code facts re-read at `9901589` (`src/` unchanged since `9bcf464`) and, read-only, in the
bug-178 clone (`fix-bug178-bulk-write` at `d13c4d7`). No user decision remained; the report's
decisions are adopted. The 2026-10-14 table above is unchanged history.

| finding | answered at | rationale |
|---|---|---|
| s3 (AC-6's suite-wide grep fails on a correct build: 9 more fake-lock files outside R6) | [[#r6]] (the nine files, by kind), [[#ac-6]] | converge the shape: one fixture, every file; an `RLock` fake hides the non-reentrancy AC-5 and 23.1 R1.6 test |
| m1 (line drift) | [[#why]] (`daemon.py::_FairLock`), [[#r6]] (symbols, not `:182` / `:104` / `:176`) | cite `file::symbol`; numbers only "at <sha>" |
| m2 (the read-path probe goes through `_MemMirror.acquire_use()`) | [[#r1]], [[#r6]], [[#ac-2]] | name what the test touches |
| m3 (R3's proxy vs bug-178's `bulk_write` `isinstance` dispatch) | [[#r3]] | patch the wrapper instance; pass `register` / `unregister` through; one `bulk_write` = one statement; reuse `duck_executemany_calls()` |
| m6 (merge order) | header `Depends on:` | 3.7 → bug-178 → plan-26 → 23.2 → 23.1 |

rel: derives-from -> [[bsd-plan23-1-2-freshness-9bcf464]]
rel: derives-from -> [[bsd-plan23-1-2-freshness-9bcf464#s3]]
rel: derives-from -> [[bsd-plan23-1-2-freshness-9bcf464#m2]]
rel: derives-from -> [[bsd-plan23-1-2-freshness-9bcf464#m3]]
rel: related-to -> [[task-bug178-bulk-write-helper]]

## Revision round 3 (2026-11-09) {#rev-round-3}

Source: [[bsd-plan23-1-2-freshness-confirm-1c0b66a]], the focused confirm of round 2 at
`1c0b66a`; its only 23.2 finding is m1. Census re-run at HEAD `77c9f04` (`tests/` read only); the
error text read, read-only, in the bug-178 clone (`fix-bug178-bulk-write` at `ae7c0c7`). No user
decision remained. With m1 folded the report rates 23.2 build-ready; its merge gate (bug-178
first) is unchanged. The round-2 table above is unchanged history.

| finding | answered at | rationale |
|---|---|---|
| m1 (the census misses `__import__('threading').Lock()` in three files and `_CtxRecorder`; the count wording; R3's quoted error) | [[#r6]] (pattern `(_store_lock\|_use_lock)\s*=`: 23 lines in 18 files, 21 fake lines in 17 files; three `__import__` files and `test_brief_surfaces.py` added), [[#ac-6]] (the same pattern; exclusions by value; `_CtxRecorder` gone; a mutation round 2's pattern passed), [[#r3]] (`bulk_write: unsupported connection type …`, at `ae7c0c7`) | match the assignment, not the spelling of its value: a spelling list misses the next spelling, and AC-6 must be able to fail on every fake the census names |

rel: derives-from -> [[bsd-plan23-1-2-freshness-confirm-1c0b66a]]
rel: derives-from -> [[bsd-plan23-1-2-freshness-confirm-1c0b66a#m1]]

## Revision round 4 (2026-11-09) {#rev-round-4}

Source: [[bsd-plan23-fold-additions-a9147d5]], the narrow confirm of round 3's additions. It has
no 23.2 finding: its check 5 reproduced the census at `77c9f04` (23 lines in 18 files; 21 fake
lines in 17 files after the two non-fakes; the quoted line numbers exact) and rates 23.2
build-ready, merge gate unchanged (bug-178 first). One caveat is recorded so a re-run does not
read a false zero. The round-3 table above is unchanged history.

| item | answered at | rationale |
|---|---|---|
| census reproduced ([[bsd-plan23-fold-additions-a9147d5#q5]]) | [[#r6]], [[#ac-6]] unchanged | the counts and AC-6's `rmx grep` pattern hold |
| re-run caveat: `git grep -E` has no `\s` and returns 0 lines for the census pattern | [[#ac-6]] unchanged; this row | re-run the census with AC-6's own `rmx grep -rnE '(_store_lock\|_use_lock)\s*=' tests/ --include='*.py'` or with `[[:space:]]` in place of `\s` |

rel: derives-from -> [[bsd-plan23-fold-additions-a9147d5#q5]]
rel: derives-from -> [[bsd-plan23-fold-additions-a9147d5#readiness]]
