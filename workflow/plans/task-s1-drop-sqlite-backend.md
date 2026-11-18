---
gmd: "0.1"
id: task-s1-drop-sqlite-backend
title: "Task S1: drop the SQLite catalog backend"
tags: [task, s1, store, backend, sqlite, duckdb, deletion]
metadata:
  node_type: task
  status: approved-pending-lead
  created: 2026-11-18
---

# Task S1: drop the SQLite catalog backend {#root}

> Queue row S1 (L182, Q52 = a). After T0.4, before 29.5. Large change: RED and GREEN in separate
> hands, mutations on the `src/` change, one ch-bsd pass. One open decision: [[#d1]].

rel: part-of -> [[plan-of-plans#queue]]
rel: derives-from -> [[pop-finished#q52]]
rel: depends-on -> [[task-t0-suite-trust-sweep#t0-4-files]]
rel: related-to -> [[task-29.2-mypy-gate#r7-t0-docstrings]]

## R0: census at `a9ed8a93` {#r0}

Counted with `grep -rIic sqlite` plus `catalog\.db|RMX_BACKEND|migrate`. T0.4 lands first and
moves lines, so RED re-runs the same greps at the task base and commits the per-site list.

| kind | sites |
|---|---|
| class / selector / env | `backend.py`: `import sqlite3` :25, `select_backend` :390-424 (`RMX_BACKEND` :406, autodetect :414), `Backend` ABC :427-441, `SQLiteBackend` :457-486 (30 lines, not the 326 in Q52). `store.py`: `import sqlite3` :23, `backend=` kwarg :1284-1289, `CATALOG_DDL` :491-727 (237 lines of SQLite DDL), the connect-time self-heal arm from :1588. No setter of `RMX_BACKEND` in `scripts/`, `.claude/`, `templates/`, `tools/` (0 hits) |
| kind branches (31) | 4 spelled `== "sqlite"` (`store.py` :1518 :1523 :1588, `backend.py` :420); the other 27 are the same branch spelled `== "duckdb"` / `!= "duckdb"`: `store.py` :1316 :1332 :1815 :2673 :2707 :4306 :4330 :4589 :4607 :4660 :4716 :4770 :4796; `daemon.py` :1888 :1936 :2452 :2873 :2948 :3069 :3229 :4281 :5869 :5928 :6199; `cli.py` :4211; `verbs.py` :529; `backend.py` :422. Reporters, not branches: `daemon.py` :1879 (log), :3478 (status field) |
| `sqlite_sql=` (10 calls) | `store.py` :2682 :2749 :4441 :5318 :5377 :7330 :7896 :7926 :8005; **`pagerank.py` :513**; the parameter and its arm `backend.py` :697, :732-737 |
| migrate | `migrate.py` (182 lines); command `cli.py` :4125-4173; named at `cli.py` :235 :238, `store.py` :114 :168, `verbs.py` :3652, `tests/test_verb_parity.py` :665 |
| `catalog.db` literal | `store.py` :14 :42 :52 (`WRITER_CATALOG_FILES`) :1295 :1370 :8903; `cli.py` :10453 :10518; `verbs.py` :495 |
| comments only | `store.py` 35 of its 51 lines; `daemon.py` :2450 :2827 :2871 :2946 :4400; `cli.py` :4224 :4231; `duckdb_catalog.py` 9 (three say "see the SQLite `CATALOG_DDL`" for an incident); `replica_merge.py` :7; `eval/retrievers/rmx_retriever.py` :1102. **In derive-pass modules:** `pagerank.py` :505 :520 :521 :525, `ingest.py` :1818, `vectors.py` :21 |
| other | `scripts/check-rel-landing.py` :70-72 (a SQLite arm in its catalog opener); recorded data, not edited: `eval/memaware/REPORT.md` :327, `eval/production/results/grep_learning/replay-two-arm.json` :281 |
| hub bus, KEPT | `bus.py` 9 lines (`~/.refmatrix/bus/bus.db`); `tests/test_bus_retention.py`; `tests/sandbox_site/rmx_sandbox.py` :469 |
| docs | `ARCHITECTURE.md` :43-58 :82 :118-133 :249 :449 (generated CLI tree); `agent-doc-primer.md` :638-655; `INTEGRATION.md` :154 :181 :191 :507; `SYSTEM.md` :25 :44 :182; `PERFORMANCE.md` :44 :55. History, not edited: `adr/0001`, `system_design_review.md`, `hooks/intuition-style-hooks.md`, `architecture/explorations/` |

**Tests:** 63 files match (43 name `sqlite`). `duckdb_view.py`, `test_duckdb_parity.py` and
`test_duckdb_read_routing.py` go with T0.4. The rest, by fate: {#r0-tests}

- **Deleted, the subject is SQLite (22 test functions, 1 whole file):** `test_duckdb_migrate.py`
  (6); the migrate command in `test_bug212_r5_red.py` :170, `_r6_red.py` :97 :121, `_r7_red.py`
  :93 :116, their 3 fixtures and the census entries in `_r4_red.py` :260 :487;
  `test_fragment_repair_audit.py` :134, `_r4.py` :159 :182; `test_snapshot_tier.py` :113;
  `test_snapshot_policy.py` :73; `test_plan4_remedy.py` :179; `test_v2_features.py` :387 :435
  :464; `test_partitions.py` :49; `test_bug178_r2.py` :313.
- **Both backends, the DuckDB twin stays (6 files):** `test_bulk_link.py`,
  `test_bulk_link_weighted.py`, `test_content_rank_caches.py` (fixture params);
  `test_bug178_bulk_write.py` :587 :604 :694; `test_bug178_r2.py` :141 :275; `test_store_vectors.py` :31.
- **Feature tests pinned to SQLite with NO DuckDB twin (15 files, 196 test functions), which
  L182's "their twins stay" does not cover:** `test_memory`, `test_memory_compile`,
  `test_memory_bulk_forget`, `test_memory_recall_degree`, `test_memory_recall_exclude_mtype`,
  `test_reinforcement`, `test_partition_merge`, `test_dual_write_purge`, `test_subject`,
  `test_mcp_write`, `test_brief_detectors`, `test_brief_bsd_r1`, `test_plan7_10_remedy_r4`,
  `test_untrack`, `test_ingest_gmd_root_rel_mirror`; plus `test_partitions.py` :14 :172 :232 :260.
- **Mentions only:** 43 `delenv("RMX_BACKEND")` lines in 23 files; 79 `backend="duckdb"` in 46.

## Requirements {#requirements}

- **R1, one backend.** Delete `SQLiteBackend`, `select_backend`, the `Backend` ABC, the
  autodetect, `RMX_BACKEND`, `Store(backend=)`, `CATALOG_DDL` and the connect-time SQLite arm.
  All 31 branches collapse to the DuckDB arm; `kind` survives only in the two reporters (the
  status field keeps saying `duckdb`). The incident notes `duckdb_catalog.py` cites from
  `CATALOG_DDL` move into `duckdb_catalog.py` first. {#r1}
- **R2.** Delete `migrate.py`, its command and every mention; re-run `scripts/gen-cli-tree.py`. {#r2}
- **R3.** Delete `sqlite_sql=` at the 9 `store.py` sites and the code only a SQLite arm reached:
  the `fragments/<partition>/<linkage>.rb64` layout, its repair arm and its two `_migrate_*`
  moves. The commit body shows each deleted function has no DuckDB caller (`rmx-master context`,
  then grep); one that has stays and is reported. The pass modules: [[#d1]]. {#r3}
- **R4, tests.** Delete and de-parametrize per [[#r0-tests]]. The pinned feature tests are
  re-pointed to DuckDB: drop the pin, keep every assertion not about the file layout. One that
  then fails is a `bug_registry` row and `xfail(strict=True)`, never a deletion. RED's first
  commit is the per-node table, and the collected-node difference against the base equals its
  deleted list. A last, mechanical commit removes the `RMX_BACKEND` and `backend=` lines. {#r4}
- **R5, the refusal.** One function, called by `Store.__init__` and by the CLI before it calls or
  spawns a daemon. When `catalog.db` exists and none of `catalog.duckdb`, `catalog.A.duckdb`,
  `catalog.B.duckdb` does, it raises a typed error; the CLI prints ONE stderr line and exits
  non-zero, no traceback. The line: the file's path, "legacy SQLite catalog, this rmx reads
  DuckDB only", and the fix ("convert it with refmatrix `<V>` (`rmx migrate-to-duckdb`), or move
  it aside and run `rmx init`"; `V` is `refmatrix.__version__` read at the task base). Nothing in
  the directory is created or changed. `catalog.db` stays in `WRITER_CATALOG_FILES`: a legacy
  dir is still a store, so the generated hooks reach the refusal and their text is unchanged. {#r5}
- **R6.** `bus.py` and its tests are untouched. {#r6}
- **R7, docs.** `ARCHITECTURE.md` (backend section, module table), `agent-doc-primer.md`
  :638-655, `INTEGRATION.md`, `SYSTEM.md`, `PERFORMANCE.md` say one backend and name the refusal;
  `scripts/check-rel-landing.py` loses its SQLite arm. {#r7}

### D1 (the lead's): the pass-module lines {#d1}

`pagerank.py` :513 is CODE in the `pagerank` pass (`_DERIVE_PASS_MODULES`, `store.py:889`).
Deleting `bulk_write`'s `sqlite_sql` parameter forces that edit, and 29.2 R7's hash ignores
comments, docstrings and annotations, not a keyword argument: the edit flips `pagerank` on every
fleet store whenever it lands. **(a)** edit it in S1: a store-changing release with its own go
(L107). **(b, rec)** S1 leaves `pagerank.py`, `ingest.py` and `vectors.py` byte-identical;
`bulk_write` keeps `sqlite_sql`, accepted and unused, for that one caller; the 7 lines are
allow-listed in [[#ac-3]], owner 29.2 R7 deploy B, which edits them and deletes the parameter.

## Acceptance {#acceptance}

- **AC-1, RED at base.** Through the CLI on a `mkdtemp()` root holding only `catalog.db` (a real
  SQLite file; a zero-byte file), over a read verb, `rmx sync`, `rmx init` and an MCP tool:
  non-zero, exactly one stderr line with the path and the fix, no traceback, the directory
  listing and the file's bytes unchanged, no daemon process. Base opens it as SQLite. {#ac-1}
- **AC-2.** `catalog.db` beside `catalog.duckdb`, and beside `catalog.A.duckdb` + `active`,
  opens and answers a query. {#ac-2}
- **AC-3, census guard.** No `sqlite`, `catalog.db`, `RMX_BACKEND`, `select_backend` or
  `_backend.kind ==`/`!=` in `src/`, `scripts/`, `eval/**/*.py`, `tests/`, outside `bus.py` and
  its tests, the refusal and its test, and an allow-list whose entries each carry a reason and an
  owner. It plants a must-fail file and fails on it. {#ac-3}
- **AC-4, mutations; each FAILS a test, none hangs.** M1 re-add the autodetect arm → AC-1.
  M2 drop the refusal from `Store.__init__` → AC-1. M3 the condition ignores the rotation
  slots → AC-2. M4 drop the CLI-side check → AC-1's "no daemon process". {#ac-4}
- **AC-5, generated artifacts.** `tests/test_docs_generated.py` and verb parity green; generated
  hook text byte-equal to the base (`rmx install-hooks --check` clean); under D1 = b,
  `git diff <base> -- pagerank.py ingest.py vectors.py` is empty. {#ac-5}
- **AC-6, verify set.** The new file, every edited test file and every importer of `store.py`,
  `backend.py`, `daemon.py`, `cli.py`, `verbs.py` (most of the suite: sharded on the mini);
  E lines against the last release log; `./scripts/lint-gmd.sh` 0 errors. {#ac-6}

## Files {#files}

- Deleted: `src/refmatrix/migrate.py`, `tests/test_duckdb_migrate.py`. New:
  `tests/test_single_backend.py` (AC-1 to AC-3). Edited tests: [[#r0-tests]]. Docs: [[#r7]].
- Source, none in a pass's set: `backend.py`, `store.py`, `daemon.py`, `cli.py`, `verbs.py`,
  `duckdb_catalog.py`, `scripts/check-rel-landing.py`; a comment each in `replica_merge.py` and
  `eval/retrievers/rmx_retriever.py`. Held under D1 = b: `pagerank.py`, `ingest.py`, `vectors.py`.

## Risks {#risks}

- 196 feature tests never ran on the production backend: R4 may surface real DuckDB bugs (a row
  and a strict xfail each; more than ~10 goes back to the lead before GREEN).
- An arm deleted as SQLite-only that DuckDB reaches: R3's caller proof, then AC-6.
- A daemon launchd starts on a legacy root exits and respawns, one line each time; no fleet
  store has a `catalog.db` (Q52), so it is accepted, not built around.
