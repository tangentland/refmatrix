---
gmd: "0.1"
id: impl-bug-178-bulk-write-helper
title: "bug-178: one bulk-write helper; no executemany reaches DuckDB"
tags: [implementation-summary, bug-178, duckdb, performance, writer-lock]
metadata:
  node_type: implementation-summary
  status: complete
  task: task-bug178-bulk-write-helper
  created: 2026-11-09
---

# bug-178: one bulk-write helper; no `executemany` reaches DuckDB {#root}

rel: implements -> [[task-bug178-bulk-write-helper]]
rel: derives-from -> [[bug_registry]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]

## What changed {#changed}

DuckDB runs `executemany` as one statement per row, all of it under the store's one writer lock.
On 2026-11-09 a viascope reingest spent minutes in `pagerank.store_scores` for this reason. The
fix is one helper, `refmatrix.backend.bulk_write`. Every DuckDB-reachable bulk write now goes
through it ([[task-bug178-bulk-write-helper#r1]], [[task-bug178-bulk-write-helper#r2]]). GREEN
commit: `eeda2a1` on `fix-bug178-bulk-write`. RED tests: `ffb169d`.

```python
def bulk_write(con, sql, columns, rows, *, sqlite_sql=None, types=None,
               view="_rmx_bulk") -> int
```

- **DuckDB** (a `DuckDBConnection` wrapper or a raw `DuckDBPyConnection`): the rows become one
  Arrow table, registered under a unique per-call name (`<view>_<pid>_<seq>`). Every `{view}` in
  `sql` is replaced by that name, and the statement runs once. The table is always unregistered
  (`finally`). `types` pins an Arrow type per column, as a type object or an alias string.
- **SQLite** (`sqlite3.Connection`): `sqlite_sql` runs through `executemany`. This is the
  per-row `VALUES` statement HEAD already used, so SQLite behaviour is unchanged.
- **Fail-closed**: a SQLite connection with no `sqlite_sql`, an unknown connection type, SQL
  without `{view}`, a row with the wrong width, or `types` naming an unknown column all raise.
  Statement errors propagate. Empty input is a no-op and returns 0.

## Per site {#sites}

| site | before | after |
|---|---|---|
| `pagerank.store_scores` | DuckDB `executemany` | `bulk_write` INSERT … SELECT |
| `replica_merge._merge_linkage_types` (`remap_lk_b`) | raw-connection `executemany` | `_fill_remap` → `bulk_write` |
| `replica_merge._merge_into` (`remap_a`, `remap_b`) | raw-connection `executemany` ×2 | `_fill_remap` → `bulk_write` |
| `store.bulk_upsert_entity` (DuckDB dup-key fallback) | whole batch through `executemany` | collapsed in Python (`_collapse_entity_payload`), one upsert, plus an explicit `updated_at` touch where needed |
| `store.bulk_upsert_entity` (Arrow branch + concepts) | hand-rolled `register`/`execute` | `bulk_write`; one shared column/conflict clause for both backends |
| `store._backfill_canonical_name_if_needed` | `executemany` UPDATE | `UPDATE … FROM {view}` |
| `store.bulk_link` | hand-rolled Arrow branch | `bulk_write` (same FIRST-WINS / LAST-NON-NULL-WINS policies) |
| `store.link_many` | `executemany` INSERT OR IGNORE | batch deduped in order, then `ON CONFLICT DO NOTHING` |
| `store.bulk_mark_tracked` | hand-rolled Arrow branch | `bulk_write` |
| `store._clear_gmd_content_hashes` | 900-row `executemany` chunks | one `UPDATE … FROM {view}` |
| `store.save_coref` | 900-row `executemany` chunks | one INSERT … SELECT (atomic) |
| `store.compile_pairs` | 500-row `executemany` chunks | one INSERT … SELECT |

The removed chunk sizes only set the size of each `executemany` batch. `executemany` has no
parameter limit, so no site needs chunking for a correctness reason
([[task-bug178-bulk-write-helper#r2]]).

## Duplicate keys in `bulk_upsert_entity` {#dup-keys}

DuckDB rejects two rows for the same key inside a single `ON CONFLICT DO UPDATE`. HEAD worked
around this with a per-row sequential merge. `_collapse_entity_payload` now builds the single row
that the sequence would have left, processing input in order:

- path, tldr, meta: the last non-NULL value wins;
- protected: the maximum;
- canonical_name: the first non-NULL value;
- first-occurrence order is kept.

The collapsed row cannot reproduce `updated_at` alone. The sequence bumps it whenever any step
changes a field, including a flip-flop such as X → Y where Y was already stored. A key whose batch
carries two different non-NULL values for one field always has such a step. For those keys the
helper runs a second one-statement `UPDATE … SET updated_at`. In every other case the upsert's own
CASE gives the same answer as the sequence would. I checked the flip-flop case by hand on
throwaway stores, and DuckDB and SQLite agree. The AC-2 goldens do not cover `updated_at`.

## R3 decision: the wrapper is fenced {#r3-decision}

`DuckDBConnection.executemany` behaves in two ways ([[task-bug178-bulk-write-helper#r3]]):

- Above `DUCK_EXECUTEMANY_MAX_ROWS = 32` rows it raises `DuckDBExecutemanyError`, and the
  message names `bulk_write`.
- At or below 32 rows it still runs. Each call increments a process counter
  (`duck_executemany_calls()`) and logs a warning on `refmatrix.backend`.

No src caller remains, so any call is a regression. Large calls fail loudly, and small ones are
visible. The AC-5 static scan allows `executemany` only in `backend.bulk_write` and this wrapper.

## save_coref is now all-or-nothing {#save-coref}

When a batch repeats a `pos`, save_coref still raises. The set-based insert is atomic, so none of
that batch is kept. HEAD left the rows that came before the duplicate. The user accepted this change on
2026-11-09 ([[task-bug178-bulk-write-helper#decision-save-coref-atomic]]).

## Verification {#verified}

- `tests/test_bug178_bulk_write.py`: 31/31 passed
  (`workflow/review-output/bug178-green-target.log`).
- Related suites (store, ingest, replica merge, coref, compile, duckdb parity and others): 278 +
  217 passed (`bug178-green-related.log`, `bug178-green-related2.log`).
- Full suite: 3 failed, 3,398 passed, 1 skipped (`bug178-green-full.log`). All 3 failures
  happen at `56e8d14` with the same error text, so none is new:
  - `test_brief_real_daemon` hits DuckDB `Could not set lock`. This is the known bug-127, logged
    as `bug178-master-brief-daemon.log`.
  - `test_gmd_lint_requires_version` reports dangling ADR and architecture ids in `docs/`.
  - `test_task21_1_agent_usage_report` stops with "AC-6 BLOCKED: the redacted fixture is not
    committed".

  The last two are logged as `bug178-master-3fail.log`.
- AC-3 ([[task-bug178-bulk-write-helper#ac-3]]): `store_scores` on 50,000 entities took a best of
  0.035 s on committed src, against 19.405 s at HEAD (`bug178-store-scores-green.log`). That is about 550× faster,
  and the bar was ≤ 3.88 s.

## Remedy r2 {#r2}

rel: implements -> [[task-bug178-bulk-write-helper#remedy-r2]]

This row covers the fix at `ae7c0c7`. Detail is in
[[task-bug178-bulk-write-helper#remedy-r2-green]]. Remedy r2 fixed both items that r1 flagged:

- `clear_tracked_stamps` now reports `gmd_hashes_skipped`, and `rmx reingest --force` prints
  that count when it is above zero.
- `pagerank.store_scores` no longer swallows a failed commit. It rolls back and re-raises.
- `bulk_write` rejects a bool, a fractional float or a non-numeric value bound for a column pinned
  to an integer type. The error names the column, and nothing from the batch is written.

Results:

- `tests/test_bug178_r2.py`: 33/33 passed.
- Both bug-178 files together: 64/64 passed.
- Full suite: 3,430 passed and 4 failed. Three of the failures are the baseline. The fourth is
  `test_clear_leaves_a_store_with_no_stamps_alone`, which asserts the result dict exactly and
  needs the new key from the test-engineer.
- AC-3: best 0.039 s.
