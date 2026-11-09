---
gmd: "0.1"
id: task-bug178-bulk-write-helper
title: "Task bug-178: one bulk-write helper; no executemany reaches DuckDB"
tags: [task, bug-178, duckdb, performance, writer-lock]
metadata:
  node_type: task
  status: approved
  created: 2026-11-09
---

# Task bug-178: one bulk-write helper; no `executemany` reaches DuckDB {#root}

> Status: Approved (user, 2026-11-09: "find all the executemany uses and mitigate them in one pass")
> Depends on: none. Lands after 0.80.3.

rel: derives-from -> [[bug_registry]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]
rel: related-to -> [[project_batched_purge_and_footprint]]

## Why {#why}

`executemany` is per-row on DuckDB: every row is a separate statement under the store's one
writer lock. On 2026-11-09 the viascope reingest spent minutes in step 5/5 inside
`pagerank.store_scores → backend.executemany` (SIGUSR1 thread dump at 00:50:30) while a CLI
`derive_status` op and the periodic flush waited on the lock. The same writer-held shape is what
failed two Stop-hook promotes earlier the same night (bug-177). The codebase already knows the fix
— `bulk_upsert_entity`, `bulk_link` and `bulk_mark_tracked` register an Arrow table and run one
`INSERT … SELECT` on DuckDB, keeping `executemany` only for SQLite — but it is copy-pasted per site
and 8-10 other sites never got it. {#why-fact}

## Inventory at `8ddf68e` (verify each at RED time) {#inventory}

| site | DuckDB-reachable? (verified at `56e8d14`, RED) | shape | evidence |
|---|---|---|---|
| `pagerank.py:467` `store_scores` | **yes** | INSERT pagerank rows | `store._connect()` = `DuckDBConnection`; spy saw 1 call at N=5,000 |
| `replica_merge.py:232` `_merge_linkage_types` | **yes** — on a RAW `duckdb.DuckDBPyConnection` | INSERT remap temp table | `open_duckdb(target)` returns the raw connection, NOT the wrapper; a spy on `DuckDBConnection.executemany` cannot see it (the test's C-call observer does) |
| `replica_merge.py:326,328` `_merge_into` | **yes** — raw connection, as above | INSERT remap temp tables | observer saw both lines at 2 x 5,000 collisions |
| `store.py:2326` `bulk_upsert_entity` | **yes — inventory corrected** | INSERT … ON CONFLICT DO UPDATE entities | DuckDB falls back to `executemany` when the batch holds an intra-batch duplicate `(kind, name)` (`has_dups`); HEAD semantics are a sequential merge (COALESCE later-non-NULL, `protected` ratchet, first `canonical_name`). The helper path must keep that (e.g. collapse in Python first, as `bulk_link` does) |
| `store.py:2409` `bulk_upsert_entity` (concepts) | no — `else` of `kind == "duckdb"` | INSERT OR IGNORE concepts | DuckDB uses the Arrow `ON CONFLICT DO NOTHING` branch |
| `store.py:3962` `_backfill_canonical_name_if_needed` | **yes** | UPDATE entities by id | runs from `_connect()` on every DuckDB writer open (one-shot, rows with NULL `canonical_name`) |
| `store.py:4863` `bulk_link` | no — SQLite `else` (Arrow on DuckDB) | INSERT entity_links | migrate its Arrow branch onto the helper (R2) |
| `store.py:4907` `link_many` | **yes** | INSERT OR IGNORE entity_links | spy saw 1 call |
| `store.py:6483` `bulk_mark_tracked` | no — SQLite `else` (Arrow on DuckDB) | INSERT … ON CONFLICT tracked_files | migrate its Arrow branch onto the helper (R2) |
| `store.py:6950` `_clear_gmd_content_hashes` | **yes** (via `clear_tracked_stamps`) | UPDATE entities meta by id (900-row chunks) | spy saw 6 calls at 5,000 rows |
| `store.py:6969` `save_coref` | **yes** | INSERT coref_resolutions (900-row chunks) | spy saw 6 calls; a duplicate `pos` raises on both backends and HEAD leaves the rows before it (not atomic) |
| `store.py:7037` `compile_pairs` | **yes** | INSERT pair_index (500-row chunks) | spy saw 12 calls at 5,994 pairs |
| `backend.py:573` `DuckDBConnection.executemany` | the wrapper itself | — | R3: raises above a small count or logs a counted warning |

Verified count: **10 DuckDB-reachable call sites** (9 functions), 3 SQLite-only, plus the wrapper.

## Requirements {#requirements}

1. **R1 One helper.** `backend.bulk_write(con, sql_select_from, columns, rows, *, view="_rmx_bulk")`
   (exact name/signature the implementer's call) in `src/refmatrix/backend.py`: on a DuckDB
   connection it builds one Arrow table from `columns`/`rows`, registers it under a unique view
   name, runs the caller's set-based statement (`INSERT … SELECT … FROM <view>` /
   `UPDATE … FROM <view>`), and ALWAYS unregisters (`finally`); on SQLite it runs the equivalent
   `executemany`. Errors propagate (no silent failure on memory paths). Empty input is a no-op. {#r1}
2. **R2 Every DuckDB-reachable site uses it**, including the three existing hand-rolled Arrow
   branches (lifted onto the helper — one implementation). Semantics per site unchanged: conflict
   policy (`OR IGNORE`, `ON CONFLICT … DO UPDATE`, last-wins dedup in `bulk_link`), partition
   binding, chunking where a site chunks for a reason. {#r2}
3. **R3 Guard.** A test fails if any `executemany` call in `src/refmatrix/` other than the helper's
   SQLite branch is reachable with a DuckDB connection (static scan plus a runtime spy on
   `_DuckConn.executemany` across the affected ops); the backend wrapper itself either raises on
   DuckDB above a small row count or logs a counted warning — implementer decides, stated in the
   summary. {#r3}

## Acceptance criteria {#acceptance}

1. **AC-1 (RED at HEAD)** For each DuckDB-reachable site, a test drives the real store op on a
   throwaway DuckDB store (short mkdtemp root) with N≥5,000 rows and asserts `_DuckConn.executemany`
   is called zero times (spy, pass-through) — fails at HEAD. {#ac-1}
2. **AC-2 (equivalence)** The resulting rows are identical to HEAD's output for the same input
   (golden from HEAD recorded at RED time), per site, including conflict cases. {#ac-2}
3. **AC-3 (timing, measured not asserted tightly)** `store_scores` on 50,000 entities: record HEAD vs
   new wall time on the same machine; acceptance is the new path ≥5x faster (pre-registered; if the
   measurement shows less, stop and report rather than lowering the bar). {#ac-3}
4. **AC-4 (SQLite)** The same ops still work on the SQLite backend (existing SQLite tests green). {#ac-4}
5. **AC-5 (guard)** R3's test passes after GREEN and fails if any one site is reverted (mutation per
   site class). {#ac-5}
6. **AC-6** Full suite: no new failures vs `8ddf68e` by error text. {#ac-6}

## Measured at HEAD {#measured-head}

`workflow/measurements/bug178-store-scores.py` at `56e8d14` (src clean), Apple M3 Max, Python
3.14.5, DuckDB backend, 50,000 entities, 3 reps of `pagerank.store_scores` (DELETE + insert):
wall 19.405 s / 21.125 s / 19.924 s, **best 19.405 s** (`workflow/review-output/bug178-store-scores-head.log`).
AC-3's bar: the new path's best <= 3.88 s on the same machine. {#measured-head-fact}

## Decisions {#decisions}

- **`save_coref` with a duplicate `pos` (user, 2026-11-09):** accept the change. HEAD raises and
  leaves the rows `executemany` inserted before the duplicate; the set-based path raises and leaves
  nothing (all-or-nothing). The test pins only that it still raises; the partial-row state is NOT
  part of "semantics unchanged". {#decision-save-coref-atomic}

## Files to modify {#files}

`src/refmatrix/backend.py`, `src/refmatrix/store.py`, `src/refmatrix/pagerank.py`,
`src/refmatrix/replica_merge.py`; new `tests/test_bug178_bulk_write.py`; `workflow/bug_registry.md`
(bug-178 row); implementation summary `workflow/implementation_summaries/bug-178-bulk-write-helper.md`.
