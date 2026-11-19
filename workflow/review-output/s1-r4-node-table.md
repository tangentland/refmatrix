---
gmd: "0.1"
id: s1-r4-node-table
title: "S1 R4: the per-node fate table (RED's first commit)"
tags: [s1, sqlite, duckdb, tests, census, red]
metadata:
  node_type: report
  created: 2026-11-19
---

# S1 R4: the per-node fate table {#root}

RED (red-s1) for task S1, written BEFORE any test edit, at base `1fadfb61`. Every collected test
node that S1 deletes, de-parametrizes, re-points to DuckDB, or keeps with a SQLite leg dropped,
keyed by its node id at the base. Base collection: `pytest --collect-only -q` over the clone,
5392 nodes (one collection error, `tests/fixtures/suite_health/case_killed_mid_test.py`, is the
suite-health fixture dir and is the same at base and tip).

rel: part-of -> [[task-s1-drop-sqlite-backend#r4]]
rel: derives-from -> [[task-s1-drop-sqlite-backend#r0-tests]]

## The check this table answers {#check}

`base - tip == deleted + renamed.old` and `tip - base == renamed.new + new` (the new file
`tests/test_single_backend.py`). A de-parametrized fixture changes its DuckDB node's id
(`test_x[duckdb]` becomes `test_x`), so the rename map is listed, not folded into the
deleted list. The collected counts at base and at the RED tip are in [[#tip]].

## Counts {#counts}

| fate | nodes | test functions |
|---|---|---|
| deleted: the subject is SQLite or migrate | 22 | 22 (one whole file: `test_duckdb_migrate.py`, 6) |
| deleted: the SQLite param of a both-backend test | 26 | (the DuckDB twin of each stays, renamed) |
| renamed: de-parametrized, the DuckDB twin stays | 26 | 20 |
| re-pointed: pinned to SQLite, no twin, now DuckDB | 157 | 157 |
| kept, a SQLite leg dropped (id unchanged) | 8 | 2 |

## Deleted (48 nodes) {#deleted}

| node at base | why |
|---|---|
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_save_coref_duplicate_position_still_raises[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[pagerank.store_scores-sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store._backfill_canonical_name_if_needed-sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store._clear_gmd_content_hashes-sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.bulk_upsert_entity[dup-keys]-sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.compile_pairs-sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.link_many-sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.save_coref-sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_r2.py::test_red_clear_tracked_stamps_counts_skipped_gmd_meta[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bug178_r2.py::test_red_store_scores_propagates_a_commit_failure` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_bug212_r4_red.py::test_every_caller_of_a_library_opener_is_found` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_bug212_r5_red.py::test_migrate_to_duckdb_overwrite_refuses_a_git_tracked_catalog` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_bug212_r6_red.py::test_migrate_out_into_another_repos_tracked_catalog_is_refused` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_bug212_r6_red.py::test_migrate_out_to_an_untracked_path_from_a_tracked_store_is_allowed` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_bug212_r7_red.py::test_migrate_out_onto_a_committed_non_catalog_named_file_is_refused` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_bug212_r7_red.py::test_migrate_out_to_an_untracked_file_beside_a_tracked_catalog_is_allowed` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_bulk_link.py::test_bulk_link_empty_is_noop[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link.py::test_bulk_link_handles_multiple_linkages[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link.py::test_bulk_link_inserts_and_returns_new_count[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link.py::test_bulk_link_preserves_weights_on_duckdb_only[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link.py::test_bulk_link_skips_existing_pairs[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link_weighted.py::test_default_mode_still_first_wins[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link_weighted.py::test_duplicate_keys_in_one_batch_keep_the_last[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link_weighted.py::test_matches_per_row_link_sequence[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link_weighted.py::test_null_weight_preserves_stored_value[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_bulk_link_weighted.py::test_update_weight_overwrites_existing[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_content_rank_caches.py::test_a_document_ingested_after_the_cache_still_scores[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_content_rank_caches.py::test_batched_resolve_matches_the_singular_form[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_content_rank_caches.py::test_doclen_matches_a_live_sum[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_content_rank_caches.py::test_flush_fragments_drops_the_caches[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_content_rank_caches.py::test_namespaced_leaf_index_finds_what_the_like_scan_found[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_content_rank_caches.py::test_ranking_is_deterministic_across_equal_scores[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_content_rank_caches.py::test_scores_are_unchanged_by_caching[sqlite]` | the SQLite param of a both-backend test; the DuckDB twin stays (renamed) |
| `tests/test_duckdb_migrate.py::test_init_catalog_idempotent` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_duckdb_migrate.py::test_migrate_missing_source_raises` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_duckdb_migrate.py::test_migrate_packs_fragments_into_bitmap_blobs` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_duckdb_migrate.py::test_migrate_refuses_to_overwrite_unless_asked` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_duckdb_migrate.py::test_migrate_round_trip_row_counts` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_duckdb_migrate.py::test_sequences_dont_collide_after_migration` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_fragment_repair_audit.py::test_sqlite_repair_leaves_an_unknown_partition_dir_and_reports_it` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_fragment_repair_audit_r4.py::test_cli_repair_lists_unread_dirs` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_fragment_repair_audit_r4.py::test_sqlite_repair_that_writes_keeps_an_unread_dir` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_partitions.py::test_legacy_catalog_migrates_into_default_partition` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_plan4_remedy.py::test_rebuild_entities_refuses_sqlite` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_snapshot_policy.py::test_read_only_symlink_only_applies_to_duckdb_backend` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_snapshot_tier.py::test_snapshot_catalog_skips_sqlite_backend` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_v2_features.py::test_legacy_catalog_without_protected_noise_self_heals` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |
| `tests/test_v2_features.py::test_legacy_per_concept_bitmaps_migrate_to_fragments` | the subject is SQLite (the backend, its migration, its fragment-file layout, or `migrate-to-duckdb`) |

## Renamed: de-parametrized, the DuckDB twin stays (26 nodes) {#renamed}

| node at base | node at tip |
|---|---|
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_save_coref_duplicate_position_still_raises[duckdb]` | `tests/test_bug178_bulk_write.py::test_ac2_ac4_save_coref_duplicate_position_still_raises` |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[pagerank.store_scores-duckdb]` | `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[pagerank.store_scores]` |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store._backfill_canonical_name_if_needed-duckdb]` | `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store._backfill_canonical_name_if_needed]` |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store._clear_gmd_content_hashes-duckdb]` | `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store._clear_gmd_content_hashes]` |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.bulk_upsert_entity[dup-keys]-duckdb]` | `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.bulk_upsert_entity[dup-keys]]` |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.compile_pairs-duckdb]` | `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.compile_pairs]` |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.link_many-duckdb]` | `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.link_many]` |
| `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.save_coref-duckdb]` | `tests/test_bug178_bulk_write.py::test_ac2_ac4_store_site_rows_match_head_and_reference[store.save_coref]` |
| `tests/test_bug178_r2.py::test_red_clear_tracked_stamps_counts_skipped_gmd_meta[duckdb]` | `tests/test_bug178_r2.py::test_red_clear_tracked_stamps_counts_skipped_gmd_meta` |
| `tests/test_bulk_link.py::test_bulk_link_empty_is_noop[duckdb]` | `tests/test_bulk_link.py::test_bulk_link_empty_is_noop` |
| `tests/test_bulk_link.py::test_bulk_link_handles_multiple_linkages[duckdb]` | `tests/test_bulk_link.py::test_bulk_link_handles_multiple_linkages` |
| `tests/test_bulk_link.py::test_bulk_link_inserts_and_returns_new_count[duckdb]` | `tests/test_bulk_link.py::test_bulk_link_inserts_and_returns_new_count` |
| `tests/test_bulk_link.py::test_bulk_link_preserves_weights_on_duckdb_only[duckdb]` | `tests/test_bulk_link.py::test_bulk_link_preserves_weights_on_duckdb_only` |
| `tests/test_bulk_link.py::test_bulk_link_skips_existing_pairs[duckdb]` | `tests/test_bulk_link.py::test_bulk_link_skips_existing_pairs` |
| `tests/test_bulk_link_weighted.py::test_default_mode_still_first_wins[duckdb]` | `tests/test_bulk_link_weighted.py::test_default_mode_still_first_wins` |
| `tests/test_bulk_link_weighted.py::test_duplicate_keys_in_one_batch_keep_the_last[duckdb]` | `tests/test_bulk_link_weighted.py::test_duplicate_keys_in_one_batch_keep_the_last` |
| `tests/test_bulk_link_weighted.py::test_matches_per_row_link_sequence[duckdb]` | `tests/test_bulk_link_weighted.py::test_matches_per_row_link_sequence` |
| `tests/test_bulk_link_weighted.py::test_null_weight_preserves_stored_value[duckdb]` | `tests/test_bulk_link_weighted.py::test_null_weight_preserves_stored_value` |
| `tests/test_bulk_link_weighted.py::test_update_weight_overwrites_existing[duckdb]` | `tests/test_bulk_link_weighted.py::test_update_weight_overwrites_existing` |
| `tests/test_content_rank_caches.py::test_a_document_ingested_after_the_cache_still_scores[duckdb]` | `tests/test_content_rank_caches.py::test_a_document_ingested_after_the_cache_still_scores` |
| `tests/test_content_rank_caches.py::test_batched_resolve_matches_the_singular_form[duckdb]` | `tests/test_content_rank_caches.py::test_batched_resolve_matches_the_singular_form` |
| `tests/test_content_rank_caches.py::test_doclen_matches_a_live_sum[duckdb]` | `tests/test_content_rank_caches.py::test_doclen_matches_a_live_sum` |
| `tests/test_content_rank_caches.py::test_flush_fragments_drops_the_caches[duckdb]` | `tests/test_content_rank_caches.py::test_flush_fragments_drops_the_caches` |
| `tests/test_content_rank_caches.py::test_namespaced_leaf_index_finds_what_the_like_scan_found[duckdb]` | `tests/test_content_rank_caches.py::test_namespaced_leaf_index_finds_what_the_like_scan_found` |
| `tests/test_content_rank_caches.py::test_ranking_is_deterministic_across_equal_scores[duckdb]` | `tests/test_content_rank_caches.py::test_ranking_is_deterministic_across_equal_scores` |
| `tests/test_content_rank_caches.py::test_scores_are_unchanged_by_caching[duckdb]` | `tests/test_content_rank_caches.py::test_scores_are_unchanged_by_caching` |

## Re-pointed to DuckDB (157 nodes) {#repointed}

The pin (`RMX_BACKEND=sqlite` or `backend="sqlite"`) is dropped; every assertion not about the
SQLite file layout stays. Tests in these files that never reach a pinned helper (pure logic, or
already DuckDB) are untouched and not listed. A re-pointed node that fails on DuckDB at base is a
`workflow/bug_registry.md` row and `xfail(strict=True)`, listed in [[#xfail]].

| node at base (= at tip) |
|---|
| `tests/test_brief_bsd_r1.py::test_an_unknown_brief_class_is_reported_not_silently_empty` |
| `tests/test_brief_bsd_r1.py::test_contradicted_excludes_workflow_authored_citation_edges` |
| `tests/test_brief_bsd_r1.py::test_contradicted_finding_does_not_claim_both_sides_are_memories` |
| `tests/test_brief_bsd_r1.py::test_contradicted_fires_on_concept_anchor_endpoints` |
| `tests/test_brief_bsd_r1.py::test_contradicted_keeps_a_genuine_corpus_disagreement` |
| `tests/test_brief_bsd_r1.py::test_contradicted_reports_a_real_skip_reason_not_a_wrong_one` |
| `tests/test_brief_bsd_r1.py::test_contradicted_still_honours_supersedes_on_concept_endpoints` |
| `tests/test_brief_bsd_r1.py::test_corroborated_falls_back_to_created_at_when_unauthored` |
| `tests/test_brief_bsd_r1.py::test_corroborated_prefers_the_authored_date_over_the_ingest_date` |
| `tests/test_brief_bsd_r1.py::test_endpoint_fallthrough_still_honours_mtype_exclusion` |
| `tests/test_brief_bsd_r1.py::test_orphan_concept_drops_memory_id_shaped_names` |
| `tests/test_brief_bsd_r1.py::test_orphan_concept_drops_stopwords` |
| `tests/test_brief_bsd_r1.py::test_saved_briefs_are_excluded_from_the_next_run` |
| `tests/test_brief_detectors.py::test_a_caller_plan_counts_only_the_briefs_own_corpus` |
| `tests/test_brief_detectors.py::test_a_class_that_did_not_run_says_how_to_run_it` |
| `tests/test_brief_detectors.py::test_a_singleton_whose_id_cannot_be_resolved_is_counted_not_emitted` |
| `tests/test_brief_detectors.py::test_a_stale_caller_plan_counts_the_corpus_row_it_never_saw` |
| `tests/test_brief_detectors.py::test_compile_brief_returns_every_class_and_a_reconciled_skip_count` |
| `tests/test_brief_detectors.py::test_contradicted_does_not_fire_when_one_side_is_superseded` |
| `tests/test_brief_detectors.py::test_contradicted_fires_on_an_unresolved_pair` |
| `tests/test_brief_detectors.py::test_contradicted_ignores_operational_rows` |
| `tests/test_brief_detectors.py::test_corroborated_does_not_fire_when_every_member_lands_on_one_day` |
| `tests/test_brief_detectors.py::test_corroborated_fires_on_a_subject_spanning_several_dates` |
| `tests/test_brief_detectors.py::test_corroborated_thresholds_are_real_knobs` |
| `tests/test_brief_detectors.py::test_every_emitted_brief_has_evidence_that_resolves_to_a_real_row` |
| `tests/test_brief_detectors.py::test_operational_memories_never_appear_in_any_class` |
| `tests/test_brief_detectors.py::test_orphan_concept_does_not_fire_when_something_defines_the_term` |
| `tests/test_brief_detectors.py::test_orphan_concept_fires_on_a_term_talked_about_but_never_pinned_down` |
| `tests/test_brief_detectors.py::test_orphan_concept_threshold_is_a_real_knob` |
| `tests/test_brief_detectors.py::test_singleton_does_not_fire_on_a_clustered_memory` |
| `tests/test_brief_detectors.py::test_singleton_fires_on_a_memory_that_joined_no_cluster` |
| `tests/test_dual_write_purge.py::test_bulk_forget_dry_run_does_not_touch_lance` |
| `tests/test_dual_write_purge.py::test_bulk_forget_uses_batched_lance_drop_grouped_by_kind` |
| `tests/test_dual_write_purge.py::test_drop_lance_for_purge_actually_removes_row_when_dataset_exists` |
| `tests/test_dual_write_purge.py::test_drop_lance_for_purge_batch_skips_empty_input` |
| `tests/test_dual_write_purge.py::test_drop_lance_for_purge_skips_when_dataset_missing` |
| `tests/test_dual_write_purge.py::test_forget_memory_chains_through_purge_entity_lance_drop` |
| `tests/test_dual_write_purge.py::test_purge_entity_invokes_lance_drop_with_entity_kind` |
| `tests/test_dual_write_purge.py::test_purge_entity_lance_drop_failure_does_not_block_catalog_purge` |
| `tests/test_dual_write_purge.py::test_purge_entity_skip_lance_flag_suppresses_drop` |
| `tests/test_ingest_gmd_root_rel_mirror.py::test_context_on_doc_id_surfaces_root_graph` |
| `tests/test_ingest_gmd_root_rel_mirror.py::test_context_rows_are_deduped_per_linkage` |
| `tests/test_ingest_gmd_root_rel_mirror.py::test_memory_context_surfaces_its_own_outbound_rels` |
| `tests/test_ingest_gmd_root_rel_mirror.py::test_non_root_rel_does_not_mirror` |
| `tests/test_ingest_gmd_root_rel_mirror.py::test_prose_heading_tokens_are_stopword_filtered` |
| `tests/test_ingest_gmd_root_rel_mirror.py::test_root_node_does_not_duplicate_doc_level_memory` |
| `tests/test_ingest_gmd_root_rel_mirror.py::test_root_rel_mirrors_for_plain_doc_ingest` |
| `tests/test_ingest_gmd_root_rel_mirror.py::test_root_rel_mirrors_onto_doc_level_memory` |
| `tests/test_mcp_write.py::test_change_subject_accepts_subject_alias` |
| `tests/test_mcp_write.py::test_change_subject_missing_label_raises_clean` |
| `tests/test_mcp_write.py::test_change_subject_sets_pointer_and_node` |
| `tests/test_mcp_write.py::test_focus_note_accepts_note_alias` |
| `tests/test_mcp_write.py::test_focus_note_missing_text_raises_clean` |
| `tests/test_mcp_write.py::test_focus_note_records_reason_event` |
| `tests/test_mcp_write.py::test_memory_add_inproc` |
| `tests/test_memory.py::test_add_memory_idempotent_updates_content` |
| `tests/test_memory.py::test_add_memory_roundtrips_through_get` |
| `tests/test_memory.py::test_default_linkages_include_reinforcement_set` |
| `tests/test_memory.py::test_forget_memory_drops_entity_and_sidecar` |
| `tests/test_memory.py::test_forget_memory_returns_false_when_missing` |
| `tests/test_memory.py::test_get_memory_by_id_works` |
| `tests/test_memory.py::test_get_memory_returns_none_when_kind_mismatch` |
| `tests/test_memory.py::test_ingest_gmd_as_memory_honors_with_partition` |
| `tests/test_memory.py::test_ingest_gmd_auto_resume_runs_when_content_changed` |
| `tests/test_memory.py::test_ingest_gmd_auto_resume_skips_unchanged` |
| `tests/test_memory.py::test_iter_memories_filters_by_mtype` |
| `tests/test_memory.py::test_iter_memories_limit` |
| `tests/test_memory.py::test_link_memory_to_concept_via_reinforces` |
| `tests/test_memory.py::test_pending_embeddings_requeues_on_partition_mismatch` |
| `tests/test_memory.py::test_prestage_hashes_marks_existing_as_done` |
| `tests/test_memory.py::test_purge_entity_cascades_to_memory_content` |
| `tests/test_memory.py::test_recent_memories_orders_newest_first` |
| `tests/test_memory.py::test_recent_memories_since_filter_drops_old` |
| `tests/test_memory.py::test_search_memories_case_insensitive` |
| `tests/test_memory.py::test_search_memories_substring_name_and_content` |
| `tests/test_memory_bulk_forget.py::test_bulk_forget_by_ids_works` |
| `tests/test_memory_bulk_forget.py::test_bulk_forget_by_mtypes_deletes_matching_rows` |
| `tests/test_memory_bulk_forget.py::test_bulk_forget_by_names_works` |
| `tests/test_memory_bulk_forget.py::test_bulk_forget_dry_run_resolves_without_deleting` |
| `tests/test_memory_bulk_forget.py::test_bulk_forget_empty_filter_returns_zero` |
| `tests/test_memory_bulk_forget.py::test_bulk_forget_mtype_filter_is_partition_scoped` |
| `tests/test_memory_bulk_forget.py::test_bulk_forget_unions_ids_names_mtypes` |
| `tests/test_memory_compile.py::test_ac_c_stoplisted_and_generic_words_never_label_a_cluster` |
| `tests/test_memory_compile.py::test_apply_writes_subjects_and_part_of_edges` |
| `tests/test_memory_compile.py::test_cluster_without_a_shared_concept_is_kept_and_named_after_a_member` |
| `tests/test_memory_compile.py::test_concept_bridges_a_pair_dense_alone_would_miss` |
| `tests/test_memory_compile.py::test_concept_signal_alone_misses_the_paraphrase_pair` |
| `tests/test_memory_compile.py::test_crosscutting_excludes_hubs` |
| `tests/test_memory_compile.py::test_dense_groups_paraphrase_with_no_shared_concept` |
| `tests/test_memory_compile.py::test_empty_corpus_returns_an_empty_plan` |
| `tests/test_memory_compile.py::test_fused_edges_carry_concept_confirmation` |
| `tests/test_memory_compile.py::test_gc_dry_run_reports_missing_without_clearing_the_stamp` |
| `tests/test_memory_compile.py::test_gc_requeues_rows_claiming_a_vector_lance_does_not_have` |
| `tests/test_memory_compile.py::test_hand_declared_subjects_are_never_pruned` |
| `tests/test_memory_compile.py::test_hub_concept_alone_never_forms_an_edge` |
| `tests/test_memory_compile.py::test_label_is_the_highest_lift_shared_concept` |
| `tests/test_memory_compile.py::test_operational_mtypes_are_excluded_by_default` |
| `tests/test_memory_compile.py::test_r6_duplicate_labels_are_named_by_member_set_not_cluster_order` |
| `tests/test_memory_compile.py::test_r6_reordered_clusters_keep_their_subject_rows` |
| `tests/test_memory_compile.py::test_r_b_case_variants_are_one_label_candidate` |
| `tests/test_memory_compile.py::test_r_b_label_takes_the_most_frequent_surface_and_evidence_lists_a_term_once` |
| `tests/test_memory_compile.py::test_read_vectors_filters_to_requested_ids` |
| `tests/test_memory_compile.py::test_read_vectors_on_missing_dataset_is_empty_not_an_error` |
| `tests/test_memory_compile.py::test_read_vectors_round_trips_ids_and_matrix` |
| `tests/test_memory_compile.py::test_reapply_after_the_corpus_shifts_drops_the_stale_filing` |
| `tests/test_memory_compile.py::test_reapply_refiles_instead_of_accreting` |
| `tests/test_memory_compile.py::test_render_gmd_is_wellformed_and_anchored` |
| `tests/test_memory_compile.py::test_threshold_override_beats_the_percentile` |
| `tests/test_memory_compile.py::test_unembedded_memories_are_counted_not_silently_dropped` |
| `tests/test_memory_recall_degree.py::test_memory_get_default_omits_context` |
| `tests/test_memory_recall_degree.py::test_memory_get_with_degree_appends_context_block` |
| `tests/test_memory_recall_degree.py::test_memory_recall_recent_degree_one_attaches_context_per_row` |
| `tests/test_memory_recall_degree.py::test_memory_recall_recent_degree_one_gmd_includes_fenced_context` |
| `tests/test_memory_recall_degree.py::test_memory_recall_recent_degree_zero_no_context_field` |
| `tests/test_memory_recall_exclude_mtype.py::test_include_session_opts_back_in` |
| `tests/test_memory_recall_exclude_mtype.py::test_plain_recent_still_keeps_session_mtype` |
| `tests/test_memory_recall_exclude_mtype.py::test_recent_exclude_mtype_glob_prefix` |
| `tests/test_memory_recall_exclude_mtype.py::test_recent_exclude_mtype_repeatable_flag` |
| `tests/test_memory_recall_exclude_mtype.py::test_recent_with_exclude_mtype_drops_session_noise` |
| `tests/test_memory_recall_exclude_mtype.py::test_recent_without_exclude_keeps_everything` |
| `tests/test_memory_recall_exclude_mtype.py::test_scope_both_filters_global_rows` |
| `tests/test_memory_recall_exclude_mtype.py::test_session_start_excludes_session_mtype_by_default` |
| `tests/test_partition_merge.py::test_merge_collision_keeps_longer_dst_body` |
| `tests/test_partition_merge.py::test_merge_collision_prefers_longer_memory_content` |
| `tests/test_partition_merge.py::test_merge_collision_remaps_entity_links_to_dst_id` |
| `tests/test_partition_merge.py::test_merge_dry_run_preserves_partitions` |
| `tests/test_partition_merge.py::test_merge_reparents_non_colliding_entities` |
| `tests/test_partition_merge.py::test_merge_same_partition_is_noop` |
| `tests/test_partition_merge.py::test_merge_unknown_partition_raises` |
| `tests/test_partitions.py::test_fresh_init_creates_default_partition` |
| `tests/test_partitions.py::test_rename_partition_moves_rows_and_dirs` |
| `tests/test_partitions.py::test_rename_partition_rejects_existing_target` |
| `tests/test_partitions.py::test_two_partitions_stay_isolated` |
| `tests/test_plan7_10_remedy_r4.py::test_operational_bucket_counts_what_it_drops` |
| `tests/test_plan7_10_remedy_r4.py::test_skipped_by_accounts_for_every_skip` |
| `tests/test_plan7_10_remedy_r4.py::test_workflow_authored_bucket_counts_what_it_drops` |
| `tests/test_reinforcement.py::test_apply_to_concept_scores_boosts_reinforced` |
| `tests/test_reinforcement.py::test_apply_to_concept_scores_passthrough_when_alpha_zero` |
| `tests/test_reinforcement.py::test_batched_form_returns_zero_for_missing_concepts` |
| `tests/test_reinforcement.py::test_components_ordered_by_abs_contribution` |
| `tests/test_reinforcement.py::test_env_overrides_kick_in` |
| `tests/test_reinforcement.py::test_reinforcement_score_returns_zero_for_unlinked_concept` |
| `tests/test_reinforcement.py::test_reinforces_adds_contradicts_subtracts` |
| `tests/test_reinforcement.py::test_signal_caps_at_plus_minus_cap` |
| `tests/test_reinforcement.py::test_signal_decays_with_age` |
| `tests/test_subject.py::test_cli_change_subject_and_list` |
| `tests/test_subject.py::test_cli_promote_refuses_without_a_daemon` |
| `tests/test_subject.py::test_part_of_index_and_leaves` |
| `tests/test_subject.py::test_subject_leaves_unknown_is_empty` |
| `tests/test_subject.py::test_upsert_subject_idempotent` |
| `tests/test_untrack.py::test_cli_untrack_dry_run_then_apply` |
| `tests/test_untrack.py::test_cli_untrack_requires_a_selector` |
| `tests/test_untrack.py::test_untrack_by_explicit_paths` |
| `tests/test_untrack.py::test_untrack_dry_run_changes_nothing` |
| `tests/test_untrack.py::test_untrack_emits_replayable_event` |
| `tests/test_untrack.py::test_untrack_removes_live_paths_vacuum_cannot` |
| `tests/test_untrack.py::test_untrack_without_selector_refuses` |

## Kept, a SQLite leg dropped {#kept-changed}

| node (unchanged) | change |
|---|---|
| `tests/test_bug178_r2.py::test_m4_dup_key_upsert_updated_at_matches_the_row_by_row_sequence[agree_equal_stored]` | SQLite reference leg dropped; the hand anchor on updated_at stays |
| `tests/test_bug178_r2.py::test_m4_dup_key_upsert_updated_at_matches_the_row_by_row_sequence[agree_new_value]` | SQLite reference leg dropped; the hand anchor on updated_at stays |
| `tests/test_bug178_r2.py::test_m4_dup_key_upsert_updated_at_matches_the_row_by_row_sequence[flipflop_back_to_stored]` | SQLite reference leg dropped; the hand anchor on updated_at stays |
| `tests/test_bug178_r2.py::test_m4_dup_key_upsert_updated_at_matches_the_row_by_row_sequence[meta_flip]` | SQLite reference leg dropped; the hand anchor on updated_at stays |
| `tests/test_bug178_r2.py::test_m4_dup_key_upsert_updated_at_matches_the_row_by_row_sequence[mixed_fields]` | SQLite reference leg dropped; the hand anchor on updated_at stays |
| `tests/test_bug178_r2.py::test_m4_dup_key_upsert_updated_at_matches_the_row_by_row_sequence[new_key_two_paths]` | SQLite reference leg dropped; the hand anchor on updated_at stays |
| `tests/test_bug178_r2.py::test_m4_dup_key_upsert_updated_at_matches_the_row_by_row_sequence[triple_with_none_stored]` | SQLite reference leg dropped; the hand anchor on updated_at stays |
| `tests/test_store_vectors.py::test_vectors_updated_at_column_present` | the `kind == sqlite` PRAGMA branch dropped |

## Spec differences {#spec-diff}

- **Re-pointed: 157 functions, not 196.** The spec counted every function in the 15 files;
  153 of them reach the SQLite pin (through `_store`, the `store` fixture, `_root`, `_seed`,
  `_cli_env`, found by an AST walk of each module's helpers). The rest are pure-logic tests or
  already DuckDB, and keep their nodes untouched. `test_partitions.py` adds 4 (:14 :172 :232 :260).
- **`test_v2_features.py::test_existing_catalog_auto_heals_missing_tables` (:435) is KEPT, not
  deleted.** It carries an unused `import sqlite3` but no pin: it runs on DuckDB today and tests
  DuckDB's self-heal. Only the import goes.
- **`test_bug212_r4_red.py::test_every_caller_of_a_library_opener_is_found` is deleted** (not in
  the spec's list): it pins that the census finds `cli:migrate_to_duckdb`, the one caller of the
  one library opener `migrate:migrate_catalog`, both deleted by R2. The r4 census's
  `LIBRARY_OPENERS` entry and its must-find entry for `migrate:migrate_catalog` go too.
- `test_fragment_repair_audit_r4.py::test_cli_repair_lists_unread_dirs` (:182) is deleted: it
  lists unread `fragments/<partition>/` dirs, the SQLite-only layout R3 deletes.

## Re-pointed tests that fail on DuckDB at base {#xfail}

Filled in by the re-point commit (bug ids and E lines).

## The RED tip {#tip}

Filled in by the last RED commit.

