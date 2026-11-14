"""Proposed Store method -> module map for task-29.5 (by concern, not by banner). Static.
Lines per method include the comment/blank lines directly above it."""
import ast, sys, collections
from pathlib import Path
P = Path(sys.argv[1]) / "src/refmatrix/store.py"; src = P.read_text()
tree = ast.parse(src); store = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Store")
MAP = {
 "store_fragments": "_fragment_path _load_fragment _read_raw_blob flush_fragments _flush_current_binding _flush_fragments_duckdb _read_all_fragment_rows _write_all_fragment_rows repair_fragments _pack load_bitmap save_bitmap add_linkage_type get_linkage_id list_linkages merge_verb_alias _read_legacy_fragment_raw _drop_legacy_fragment_raw _merge_fragment_all_partitions",
 "store_links": "deferred_links link unlink derive_called_by bulk_link link_many weighted_link get_weight top_weighted add_evidence clear_rel_evidence get_evidence grep_evidence add_pending_ref _log_pending clear_pending_refs_for_file pending_refs_for delete_pending_ref _denotes_lid denotes_equivalents link_denotes iter_concept_ids_for_linkage link_part_of",
 "store_rank": "_mentions_bm25_stats _namespaced_leaf_index _mentions_doclen concept_df code_fraction mentions_tf_tail _invalidate_content_rank_caches _document_priors _null_tf _tf_transform content_rank",
 "store_entities": "upsert_entity bulk_upsert_entity add_concept get_entity get_entity_by_id resolve_entity resolve_concept_ids resolve_concept_ids_many same_as_audit iter_entities _name_of _row_to_entity _backfill_canonical_name_if_needed explain_entity find_describe_targets describe_entity add_namespaced_concept list_concepts_in_namespace find_entity_ids set_entity_flag set_flag_by_selector entity_exists save_query get_saved_query list_saved_queries stats save_coref load_coref compile_pairs link_cross_doc_coref pair_docs",
 "store_memory": "add_memory refresh_memory_source_path get_memory item_meta find_memory_any_partition _tag_filter_sql iter_memories search_memories upsert_subject list_subjects subject_leaves recent_memories forget_memory _memory_entity_id memory_facets reclassify_memories retag_memory bulk_forget_memories reinforcement_score reinforcement_scores reinforcement_components _memory_owned_anchor_ids _memory_compile_status",
 "store_vectors": "_vector_store upsert_vector ann_search read_vectors gc_vectors drop_vectors _lance_for_purge _note_vector_delete_failure _drop_lance_for_purge _drop_lance_for_purge_batch drop_vector_rows _delete_vector_groups _pending_embeddings_where pending_embeddings pending_embeddings_count",
 "store_removal": "purge_entity fold_concept_dups purge_path forget_by_selector _clear_purged_bits _bulk_purge_ids untrack_by_path _entities_for_paths _purge_paths vacuum prune_noise is_noise noise_concept_ids",
 "store_derive": "mark_tracked bulk_mark_tracked get_tracked_mtime list_tracked stamp_derive unstamp_derive derive_counts derive_history _write_derive_history derive_status clear_tracked_stamps _clear_gmd_content_hashes stale_files append_sync_log",
 "store_replay": "dump_catalog_to_log apply_log_delta _apply_one_event _replay_concept _apply_event_body rebuild_index_from_log",
 "store_partition": "rename_partition _merge_pending_refs merge_partition link_canon siblings_via_canon",
}
where = {m: mod for mod, ms in MAP.items() for m in ms.split()}
dup = [m for m, c in collections.Counter(m for ms in MAP.values() for m in ms.split()).items() if c > 1]
meths = [m for m in store.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
names = {m.name for m in meths}
print("methods:", len(meths), "| mapped names not in Store:", sorted(set(where) - names), "| mapped twice:", dup)
tot = collections.Counter(); cnt = collections.Counter(); prev = store.body[0].lineno - 1 if False else store.lineno
prev_end = store.lineno      # class statement line; docstring etc. counted to core via the first body stmt
core = []
for n in store.body:
    span = n.end_lineno - prev_end
    mod = where.get(getattr(n, "name", None), "store (core)")
    tot[mod] += span; cnt[mod] += isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    if mod == "store (core)" and isinstance(n, ast.FunctionDef): core.append(f"{n.name}:{span}")
    prev_end = n.end_lineno
pre = store.lineno - 1 + 1      # lines before the class + the class statement line
tot["store (core)"] += pre
print(f"{'module':16s} {'lines':>6s} {'methods':>8s}")
for mod, v in sorted(tot.items(), key=lambda kv: -kv[1]): print(f"{mod:16s} {v:6d} {cnt[mod]:8d}")
print("sum", sum(tot.values()), "of", src.count(chr(10)), "| lines before the class:", store.lineno - 1)
print("core keeps:", ", ".join(core))
