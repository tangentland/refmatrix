# Pyright error sweep — 2026-09-06

Mechanical type-fix sweep over the assigned files. Behavior-preserving:
narrowing locals + asserts, annotation corrections, duck-typed param
loosening. pyright 1.1.410, default env (no pyrightconfig added — adding
one would shift counts for main-thread-owned files).

## Commits

| Cluster | SHA | Files |
|---|---|---|
| (a) daemon | d9e73f0 | daemon.py + store.py `_conn: Any` (dependency) |
| (b) store | 0fd611a | store.py |
| (c) ingest/merge/embed | 1d317b2 | replica_merge.py, ingest.py, embedder.py, ingest_gmd.py |
| (d) misc + test | 3631848 | assoc, mcp, migrate, watch, composite, query, reranker, stm, tests/test_bigop_nonblocking.py |

## Error counts before → after

| File | Before | After |
|---|---|---|
| src/refmatrix/daemon.py | 156 | 0 |
| src/refmatrix/store.py | 21 (15 after the cluster-a `_conn` change) | 0 |
| src/refmatrix/replica_merge.py | 21 | 0 |
| src/refmatrix/ingest.py | 18 | 0 |
| src/refmatrix/embedder.py | 7 | 0 |
| src/refmatrix/ingest_gmd.py | 4 | 0 |
| src/refmatrix/assoc.py | 3 | 0 |
| src/refmatrix/mcp.py | 3 | 0 |
| src/refmatrix/migrate.py | 3 | 0 |
| src/refmatrix/watch.py | 2 | 0 |
| src/refmatrix/composite.py | 1 | 0 |
| src/refmatrix/query.py | 1 | 0 |
| src/refmatrix/reranker.py | 1 | 0 |
| src/refmatrix/stm.py | 1 | 0 |
| tests/test_bigop_nonblocking.py | 8 | 0 |

Final: `pyright src/refmatrix/` = **0 errors** across the whole package
(main-thread-owned cli.py/context.py/hooks.py/telemetry.py/backend.py
were already/independently clean; cli.py verified 0 before AND after my
query.py change — an initial broadening of `run_pql`'s return type
introduced 3 cli.py errors and was reverted in favor of a cast).

## Key transformations

- **Daemon._st()**: new private helper narrowing the Optional `store`
  (`assert st is not None` — serve_forever opens it before dispatch).
  All ~129 unguarded `d.store.` / `self.store.` handler accesses route
  through it. Test fakes that SimpleNamespace a Daemon must now provide
  `_st` (fixed in test_bigop_nonblocking.py; repo-wide grep found no
  other daemon fakes).
- getattr-guarded shutdown events/threads bound to locals so pyright
  narrows; tick-runner closures bind + assert their stop events.
- COUNT(*)/aggregate `fetchone()[0]` sites: row bound + asserted
  non-None (store.py, migrate.py); replica_merge.py gets a `_scalar()`
  helper (21 sites).
- Duck-typed loosenings: `Store._conn: Any`, `_row_to_entity(row: Any)`,
  ingest `_emit_*` helpers (`s: Any`, `doc_eid: int | str` — Store or
  RecordingStore), composite `_render_gmd(s: Any)`.
- ingest.py: TYPE_CHECKING import fixes 5 unresolvable quoted
  `"IngestRecord | None"` annotations.

## Ignore comments

- `# type: ignore`: **0 uses**.
- `# pyright: ignore[reportMissingImports]`: **4 uses** — the watchdog
  imports in daemon.py (2) and watch.py (2). watchdog IS installed in
  .venv; pyright's default env doesn't resolve it, and adding a
  pyrightconfig would change counts on files outside this sweep.

## Test results per cluster

- (a) `tests/test_daemon_*.py`: 39 passed, 11 failed — identical
  failure set at HEAD (verified by swapping HEAD files in); all in
  test_daemon_subproc_embed.py, environment-dependent (dense workers).
- (b) 15 store-related files: 103 passed, 5 failed — identical at HEAD;
  `ModuleNotFoundError: typing_extensions` in the Lance/pydantic chain.
- (c) 14 ingest/merge/embed files: 88 passed, 4 failed — same
  pre-existing typing_extensions failure (transformers chain).
- (d) 14 misc files: 148 passed, 2 failed (test_reranker real-model
  tests, same typing_extensions cause). tests/test_bigop_nonblocking.py:
  **11/11 passed** (2 had broken against the `_st()` rewrite before the
  fake-daemon fix; caught and fixed in this sweep).

## Follow-up bugs found (NOT fixed beyond type-safe minimum)

1. **query.py `run_pql`** is annotated `-> BitMap | list` but PQL
   `Count(...)` returns `int` at runtime. cli.py calls `len(result)`
   (cli.py:3838, cli.py:3918) and `list(result)` (cli.py:5575) on it —
   a Count query through those paths would TypeError. Kept the declared
   contract via `cast` + NOTE comment; cli.py is main-thread-owned.
2. **store.py `ph_df`/`postings_by_cid`** were genuinely possibly
   unbound: the term-boost/reinforcement loops run whenever
   `scores and _idf_by_cid` even if the mentions-BM25 block that bound
   them was skipped → latent NameError. Fixed by hoisting the init next
   to `_idf_by_cid` (whose own comment already states that rationale).
3. **assoc.py `scored`** annotation said 2-tuples while 3-tuples were
   appended — annotation corrected (runtime was fine).
4. **Test environment**: `typing_extensions` is missing from
   `~/python_libraries/.../site-packages`, breaking every
   transformers/Lance-importing test (18 pre-existing failures across
   5 files). Installing it would likely clear most of them.

## Final git status

Working tree clean for all sweep-owned files; 4 cluster commits +
this report on master.
