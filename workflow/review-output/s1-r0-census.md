---
gmd: "0.1"
id: s1-r0-census
title: "S1 R0: the SQLite-backend census re-run at the task base 1fadfb61"
tags: [s1, sqlite, duckdb, census, red]
metadata:
  node_type: report
  created: 2026-11-19
---

# S1 R0: census at `1fadfb61` {#root}

The spec's census ran at `a9ed8a93`; T0.4 and T0.5 landed since. RED (red-s1) re-ran the same
greps at the task base: `git grep -n -I -i -E 'sqlite|catalog\.db([^a-z]|$)|RMX_BACKEND|
select_backend|_backend\.kind *[!=]=|migrate[-_]to[-_]duckdb|migrate_catalog|refmatrix\.migrate'`
over `src scripts eval/**/*.py` (plus the two recorded eval files), and the same plus
`backend *= *"` over `tests`. The bare word `migrate` of the spec's grep also hits unrelated code
(`stm.migrate_legacy_errors`, `launchctl._migrate_legacy`, `edges_migrated`); those are not
S1 sites and are left out. Every line number below is at `1fadfb61`.

rel: part-of -> [[task-s1-drop-sqlite-backend#root]]
rel: derives-from -> [[task-s1-drop-sqlite-backend#r0]]

## What moved or changed fate since the spec {#moved}

| spec (at a9ed8a93) | at 1fadfb61 | fate change |
|---|---|---|
| `backend.py` `import sqlite3` :25, `select_backend` :390-424, `RMX_BACKEND` :406, autodetect :414, `Backend` ABC :427-441, `SQLiteBackend` :457-486, `bulk_write` `sqlite_sql` :697 and arm :732-737 | same | none |
| `store.py` `import sqlite3` :23, `CATALOG_DDL` :491-727, `backend=` :1284-1289 | same (`backend:` kwarg :1283, `select_backend` :1287-1289) | none |
| `store.py` connect-time SQLite arm from :1588 | :1579 (`executescript(CATALOG_DDL)` :1586) | moved -9 |
| `store.py` kind branches :1518 :1523 :1588 (`== "sqlite"`) | :1509 :1514 :1579 | moved -9 |
| `store.py` kind branches :1316 :1332 | :1316 :1332 | none |
| `store.py` :1815 :2673 :2707 :4306 :4330 :4589 :4607 :4660 :4716 :4770 :4796 | :1806 :2650 :2684 :4283 :4307 :4566 :4584 :4637 :4693 :4747 :4773 | moved -9 / -23 |
| `daemon.py` :1888 :1936 :2452 :2873 :2948 :3069 :3229 :4281 | :1887 :1935 :2451 :2872 :2947 :3068 :3228 :4280 | moved -1 |
| `daemon.py` :5869 :5928 :6199 | :5895 :5954 :6225 | moved +26 |
| `cli.py` :4211, `verbs.py` :529, `backend.py` :420 :422 | same | none |
| reporters `daemon.py` :1879 (log), :3478 (status) | :1878, :3477 | moved -1 |
| `sqlite_sql=` `store.py` :2682 :2749 :4441 :5318 :5377 :7330 :7896 :7926 :8005 | :2659 :2726 :4418 :5295 :5354 :7307 :7873 :7903 :7982 | moved -23 |
| `pagerank.py` :513 (and comments :505 :520 :521 :525), `ingest.py` :1818, `vectors.py` :21 | same | none (D1 = b: byte-identical, allow-listed) |
| `migrate.py` 182 lines; command `cli.py` :4125-4173; named `cli.py` :235 :238, `store.py` :114 :168 | same | none |
| named `verbs.py` :3652 | :3687 | moved +35 |
| named `tests/test_verb_parity.py` :665 | :671 | moved +6 |
| `catalog.db` literal `store.py` :14 :42 :52 :1295 :1370 :8903 | :14 :42 :52 :1295 :1296 :8880 (:1366 is `sqlite3.Connection` in a comment, not `catalog.db`) | moved; spec's :1370 was a different line |
| `catalog.db` literal `cli.py` :10453 :10518, `verbs.py` :495 | :10452 :10517, :495 | moved -1 |
| comments `daemon.py` :2450 :2827 :2871 :2946 :4400 | :2449 :2826 :2870 :2945 :4399 | moved -1 |
| comments `cli.py` :4224 :4231; `duckdb_catalog.py` 9; `replica_merge.py` :7; `eval/retrievers/rmx_retriever.py` :1102 | same | none |
| `scripts/check-rel-landing.py` :70-72 | same | none |
| bus: `bus.py` 9 lines, `tests/test_bus_retention.py`, `tests/sandbox_site/rmx_sandbox.py` :469 | same | none (R6) |
| recorded eval data `eval/memaware/REPORT.md` :327, `replay-two-arm.json` :281 | same | none (not `*.py`: outside AC-3's scope) |
| tests: `duckdb_view.py`, `test_duckdb_parity.py`, `test_duckdb_read_routing.py` (went with T0.4) | absent | gone, as the spec expected |
| tests touched by T0.5: `test_brief_detectors` :68, `test_brief_bsd_r1` :44 | still pinned (`setenv("RMX_BACKEND", "sqlite")`) | none: re-pointed |
| `delenv("RMX_BACKEND")` 43 lines in 23 files; `backend="duckdb"` 79 in 46 | 43 in 23; 79 in 46 | none |

Fate changes found while classifying the tests (detail in [[s1-r4-node-table#spec-diff]]):
the re-pointed set is 157 functions (153 in the 15 files + 4 in `test_partitions.py`), not 196;
`test_v2_features.py` :435 is kept (no pin, runs on DuckDB); `test_bug212_r4_red.py`
`test_every_caller_of_a_library_opener_is_found` (:679) and `test_fragment_repair_audit_r4.py`
:182 are deleted.

Test-side lines the spec did not list, cleaned by RED so AC-3 holds over `tests/`:
`test_bug112_duckdb_reopen.py` :170 :246, `test_bug113_replica_merge_recovery.py` :65,
`test_deferrals_clean.py` :472, `test_refmatrix.py` :40, `test_daemon_rotation.py` :15,
`test_fragment_repair_audit_r3.py` :6, `test_ingest_graphify.py` :252, `test_stm.py` :309,
`test_watch.py` :26, `test_snapshot_tier.py` :11, `test_snapshot_policy.py` :58,
`test_bug212_r4_red.py` :236-244 and its synthetic modules (:538 :578 :579),
`tests/fixtures/bug178_head_golden.json` (the 7 `/sqlite` golden keys).

## Per-site list: src/, scripts/, eval/ {#sites-src}

| file | lines | line numbers |
|---|---|---|
| `eval/memaware/REPORT.md` | 1 | 327 |
| `eval/production/results/grep_learning/replay-two-arm.json` | 1 | 281 |
| `eval/retrievers/rmx_retriever.py` | 1 | 1102 |
| `scripts/check-rel-landing.py` | 3 | 70 71 72 |
| `src/refmatrix/backend.py` | 50 | 3 7 11 15 16 17 25 99 390 399 402 403 406 414 415 420 421 424 434 435 444 454 457 458 459 462 463 467 469 470 478 489 516 549 556 558 564 573 621 697 702 714 716 717 732 733 735 736 737 747 |
| `src/refmatrix/bus.py` | 9 | 5 21 78 108 109 111 112 120 122 |
| `src/refmatrix/cli.py` | 16 | 235 238 4125 4136 4137 4140 4143 4146 4149 4152 4162 4211 4224 4231 10452 10517 |
| `src/refmatrix/daemon.py` | 16 | 1887 1935 2449 2451 2826 2870 2872 2945 2947 3068 3228 4280 4399 5895 5954 6225 |
| `src/refmatrix/duckdb_catalog.py` | 9 | 3 14 34 37 88 134 146 178 299 |
| `src/refmatrix/ingest.py` | 1 | 1818 |
| `src/refmatrix/migrate.py` | 20 | 1 2 21 24 25 31 39 46 50 51 62 63 64 74 80 95 108 122 127 168 |
| `src/refmatrix/pagerank.py` | 5 | 505 513 520 521 525 |
| `src/refmatrix/replica_merge.py` | 1 | 7 |
| `src/refmatrix/store.py` | 67 | 2 14 23 41 42 52 114 168 209 1287 1289 1295 1296 1316 1332 1366 1486 1508 1509 1514 1515 1552 1579 1585 1586 1644 1692 1806 1970 2510 2618 2636 2646 2650 2659 2682 2684 2726 3785 3864 4283 4284 4287 4288 4307 4418 4447 4566 4584 4629 4637 4671 4693 4747 4773 5229 5280 5295 5354 6838 7289 7307 7873 7903 7982 8880 8902 |
| `src/refmatrix/vectors.py` | 1 | 21 |
| `src/refmatrix/verbs.py` | 3 | 495 529 3687 |

## Per-site list: tests/ {#sites-tests}

Includes the mention-only `delenv("RMX_BACKEND")` and `backend="duckdb"` lines.

| file | lines | line numbers |
|---|---|---|
| `tests/fixtures/bug178_head_golden.json` | 7 | 9 25 33 41 49 57 65 |
| `tests/sandbox_site/rmx_sandbox.py` | 1 | 469 |
| `tests/test_brief_bsd_r1.py` | 1 | 44 |
| `tests/test_brief_detectors.py` | 1 | 68 |
| `tests/test_bug110_snapshot_keeps_lock.py` | 3 | 50 74 105 |
| `tests/test_bug111_repair_dead_concept_links.py` | 2 | 22 23 |
| `tests/test_bug112_duckdb_reopen.py` | 3 | 155 170 246 |
| `tests/test_bug113_replica_merge_recovery.py` | 2 | 55 65 |
| `tests/test_bug178_bulk_write.py` | 10 | 42 55 96 97 292 340 589 591 608 698 |
| `tests/test_bug178_r2.py` | 11 | 10 28 70 144 151 152 276 316 319 333 347 |
| `tests/test_bug212_r4_red.py` | 13 | 236 244 261 483 488 538 578 579 661 662 679 683 684 |
| `tests/test_bug212_r5_red.py` | 18 | 7 12 75 140 141 150 152 154 157 160 161 170 171 174 176 180 182 184 |
| `tests/test_bug212_r6_red.py` | 21 | 6 7 13 55 61 65 66 77 81 86 98 99 104 107 111 115 122 123 127 135 140 |
| `tests/test_bug212_r7_red.py` | 11 | 7 13 59 70 78 95 103 106 110 118 126 |
| `tests/test_bulk_link_weighted.py` | 2 | 18 20 |
| `tests/test_bulk_link.py` | 7 | 2 13 15 71 82 83 87 |
| `tests/test_bus_retention.py` | 4 | 172 174 175 176 |
| `tests/test_catalog_measure.py` | 1 | 46 |
| `tests/test_content_rank_caches.py` | 2 | 17 19 |
| `tests/test_context_nl_ref.py` | 1 | 96 |
| `tests/test_daemon_rotation.py` | 1 | 15 |
| `tests/test_deferrals_clean.py` | 1 | 472 |
| `tests/test_derive_history.py` | 5 | 29 30 198 200 205 |
| `tests/test_derive_surface.py` | 3 | 27 31 40 |
| `tests/test_dual_write_purge.py` | 2 | 29 30 |
| `tests/test_duckdb_fragments.py` | 14 | 14 15 42 43 49 68 70 71 86 98 99 111 112 120 |
| `tests/test_duckdb_migrate.py` | 22 | 1 7 12 18 20 21 35 58 66 68 92 94 96 102 106 108 114 118 122 124 125 139 |
| `tests/test_embed_gc.py` | 1 | 23 |
| `tests/test_fragment_partition_scope.py` | 7 | 24 25 246 250 276 278 290 |
| `tests/test_fragment_repair_audit_r2.py` | 2 | 20 21 |
| `tests/test_fragment_repair_audit_r3.py` | 4 | 6 27 28 153 |
| `tests/test_fragment_repair_audit_r4.py` | 14 | 11 32 33 63 105 157 159 161 162 183 185 267 296 339 |
| `tests/test_fragment_repair_audit.py` | 6 | 16 17 134 135 136 137 |
| `tests/test_grep_answered_by.py` | 5 | 52 56 93 251 253 |
| `tests/test_grep_argv_order_e2e.py` | 1 | 64 |
| `tests/test_grep_case_every_path.py` | 8 | 36 39 110 114 196 199 263 266 |
| `tests/test_grep_count_rows_e2e.py` | 1 | 43 |
| `tests/test_grep_empty_pipe.py` | 1 | 51 |
| `tests/test_grep_evidence_verified.py` | 2 | 46 161 |
| `tests/test_grep_fixed_and_file_lists.py` | 2 | 57 64 |
| `tests/test_grep_learned_paths_absolute.py` | 2 | 76 104 |
| `tests/test_grep_learned_reachable.py` | 3 | 50 56 196 |
| `tests/test_grep_no_flag_bundle.py` | 1 | 34 |
| `tests/test_grep_verify_before_cap.py` | 2 | 33 36 |
| `tests/test_grep.py` | 2 | 15 17 |
| `tests/test_ingest_concurrency.py` | 2 | 250 295 |
| `tests/test_ingest_gmd_root_rel_mirror.py` | 1 | 28 |
| `tests/test_ingest_graphify.py` | 1 | 252 |
| `tests/test_ingest_partition_yield_race.py` | 1 | 30 |
| `tests/test_injection_capture.py` | 2 | 125 218 |
| `tests/test_learn_toggle_sites.py` | 2 | 38 47 |
| `tests/test_mcp_write.py` | 1 | 14 |
| `tests/test_memory_bulk_forget.py` | 2 | 19 20 |
| `tests/test_memory_compile.py` | 1 | 40 |
| `tests/test_memory_recall_degree.py` | 1 | 35 |
| `tests/test_memory_recall_exclude_mtype.py` | 2 | 26 27 |
| `tests/test_memory.py` | 4 | 17 18 191 473 |
| `tests/test_partition_merge.py` | 2 | 15 16 |
| `tests/test_partitions.py` | 12 | 4 20 21 23 55 57 66 177 178 180 235 261 |
| `tests/test_plan4_remedy.py` | 2 | 179 180 |
| `tests/test_plan7_10_remedy_r4.py` | 1 | 54 |
| `tests/test_read_path_partition_and_budget.py` | 1 | 31 |
| `tests/test_refmatrix.py` | 1 | 40 |
| `tests/test_reinforcement.py` | 2 | 18 19 |
| `tests/test_scan_prompt_block_order.py` | 1 | 50 |
| `tests/test_scan_prompt_content_fusion.py` | 1 | 58 |
| `tests/test_scan_prompt_dedup.py` | 1 | 130 |
| `tests/test_scanorder_r2_l120.py` | 1 | 99 |
| `tests/test_slot_rotation_drift.py` | 9 | 30 38 40 45 52 57 64 69 89 |
| `tests/test_snapshot_policy.py` | 11 | 29 40 58 61 74 76 77 78 81 85 87 |
| `tests/test_snapshot_tier.py` | 5 | 11 47 113 114 117 |
| `tests/test_stm_composite_members.py` | 1 | 54 |
| `tests/test_stm.py` | 1 | 309 |
| `tests/test_store_health_probe.py` | 2 | 16 17 |
| `tests/test_store_vectors.py` | 1 | 32 |
| `tests/test_structural_signal.py` | 1 | 20 |
| `tests/test_subject.py` | 2 | 70 115 |
| `tests/test_sync_gmd_routing.py` | 1 | 44 |
| `tests/test_tf_norm.py` | 1 | 18 |
| `tests/test_untrack.py` | 2 | 22 127 |
| `tests/test_v2_features.py` | 6 | 388 389 439 467 469 471 |
| `tests/test_verb_parity.py` | 1 | 671 |
| `tests/test_watch.py` | 1 | 26 |
