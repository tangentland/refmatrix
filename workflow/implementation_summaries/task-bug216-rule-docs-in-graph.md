---
gmd: "0.1"
id: impl-task-bug216-rule-docs-in-graph
title: "Task bug-216: the rule docs reach the graph (implementation summary, RED stub)"
tags: [implementation-summary, bug-216, gmd, ingest, ignore, linkages, tdd]
metadata:
  node_type: implementation-summary
  status: red
  created: 2026-11-13
---

# Task bug-216: the rule docs reach the graph {#root}

rel: implements -> [[task-bug216-rule-docs-in-graph]]
rel: derives-from -> [[bug_registry]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_red_test_must_fail_at_head]]

Stub written by the test engineer at RED. The implementer fills [[#green]]; the lead fills
[[#ac6]] after deploy and R4.

## RED {#red}

Branch `task-bug216-rule-docs-in-graph`, run with the clone's `src` on `PYTHONPATH`.

- AC-1..AC-5 at base `758bca1`: **40 failed, 18 passed**
  (`workflow/review-output/bug216/red-head-758bca1.log`).
- With rev 2 / rev 3 (AC-7, AC-8 rev 3, AC-9, AC-10, and AC-2 pinned to the rule doc's node
  entity) at `b3f2572` (the merge of dev master `12c219a`; no `src/` change since `758bca1`):
  **52 failed, 23 passed** over 75 tests (`red-head-rev3-b3f2572.log`).

Every failure is the missing mechanism, not the test's setup. The tests that pass at HEAD are
guards (existing behaviour re-asserted, or mutation killers that can only fail once the
mechanism exists); each is marked "guard" below. {#red-count}

rel: specifies -> [[task-bug216-rule-docs-in-graph#acceptance]]
rel: specifies -> [[task-bug216-rule-docs-in-graph#rev-2]]
rel: specifies -> [[task-bug216-rule-docs-in-graph#rev-3]]

### AC-1 (R1) — tests/test_bug216_ignore_reinclude.py {#red-ac1}

| test | HEAD line |
|---|---|
| `test_ac1_profile_reincluded_under_an_ignored_claude_dir` | `re-included profile is still ignored` |
| `test_ac1_claude_md_removed_from_the_spec_is_not_ignored` | guard (green: CLAUDE.md is not under a hidden dir) |
| `test_reinclude_never_beats_ingest_ignore_dirs` | guard (green: no re-include exists); kills M2 |
| `test_a_reinclude_naming_a_directory_is_reported_once_and_reincludes_nothing` | `` a `!dir` line must be reported exactly once on stderr; got: '' `` |
| `test_reinclude_beats_the_hidden_dir_rule_with_no_spec_line` | `assert True is False` (hidden-dir rule wins); kills M1 |
| `test_reinclude_beats_every_spec_pattern_shape_wherever_it_appears` | `assert True is False` |
| `test_reinclude_is_anchored_to_the_project_root` | `assert True is False` |
| `test_reinclude_accepts_a_glob` | `assert True is False` |
| `test_without_a_root_only_the_builtin_rules_apply` | guard |

{#red-ac1-table}

### R2 static — tests/test_bug216_ignore_reinclude.py {#red-r2-static}

| test | HEAD line |
|---|---|
| `test_r2_only_ingest_reads_the_ignore_spec` | `walks reading the ignore spec themselves: ['watch.py']` |
| `test_r2_only_ingest_uses_the_builtin_segment_rule` | guard |
| `test_r2_each_walker_goes_through_should_ignore[ingest.py:_ingest_tree]` | guard |
| `test_r2_each_walker_goes_through_should_ignore[sync.py:_sync_one]` | guard |
| `test_r2_each_walker_goes_through_should_ignore[watch.py:is_relevant]` | `watch.py:is_relevant does not call should_ignore` |
| `test_r2_each_walker_goes_through_should_ignore[ingest_gmd.py:collect_gmd_files]` | `ingest_gmd.py:collect_gmd_files does not call should_ignore` |
| `test_r2_the_daemon_watcher_filters_against_its_owning_root` | `daemon watcher filter called without a root: is_relevant(p)` |

{#red-r2-static-table}

### AC-2 (R1, R2) — tests/test_bug216_rule_docs_e2e.py {#red-ac2}

Routes: `sync` (`sync_files`), `watcher` (`Daemon._start_watcher`, real handler / debouncer /
`_flush`; only the watchdog `Observer` is faked), `op-ingest-gmd` (`daemon._op_ingest_gmd`
on an in-process daemon), `cli-ingest-gmd` (`rmx ingest-gmd`, no daemon up). {#red-ac2-routes}

| test | HEAD line |
|---|---|
| `…lands_the_claude_node_and_its_edge[sync]`, `[watcher]` | guard (green: removing `CLAUDE.md` from the spec is enough on these routes) |
| `…lands_the_claude_node_and_its_edge[op-ingest-gmd]`, `[cli-ingest-gmd]` | `the agent template reached the store` (ingest-gmd's walk honours no spec) |
| `…lands_the_profile_node_and_its_edge[sync]`, `[watcher]` | `` no `project-profile#constraints` node in the store `` |
| `…lands_the_profile_node_and_its_edge[op-ingest-gmd]`, `[cli-ingest-gmd]` | `the agent template reached the store` |
| `test_ac2_old_config_has_no_rule_doc_nodes[sync]`, `[watcher]` | guard |
| `test_ac2_old_config_has_no_rule_doc_nodes[op-ingest-gmd]`, `[cli-ingest-gmd]` | `` `claude#no-silent-failures` node exists under the old config `` |
| `test_ac2_old_config_counts_both_lines_unresolved[op-ingest-gmd]`, `[cli-ingest-gmd]` | report has no unresolved refs: `ingested 7 doc(s), 12 node(s), 2 rel: edge(s)…` |

{#red-ac2-table}

### R2 behavioural walker table — tests/test_bug216_rule_docs_e2e.py {#red-r2-walkers}

| test | HEAD line |
|---|---|
| `…same_files_under_the_new_config[sync]`, `[watcher]`, `[ingest-path]` | `missing ['.claude/PROJECT_PROFILE.md'], extra []` |
| `…same_files_under_the_new_config[op-ingest-gmd]`, `[cli-ingest-gmd]` | `extra ['.claude/agents/x.md', 'node_modules/n.md', 'src/refmatrix/templates/t.md']` |
| `…same_files_under_the_old_config[sync]`, `[watcher]`, `[ingest-path]` | guard |
| `…same_files_under_the_old_config[op-ingest-gmd]`, `[cli-ingest-gmd]` | `extra ['.claude/PROJECT_PROFILE.md', '.claude/agents/x.md', 'CLAUDE.md', …]` |
| `test_r2_watch_is_relevant_agrees_with_should_ignore` | `is_relevant(<profile>, root)` is `False` |
| `test_the_memory_walk_is_not_put_through_should_ignore` | guard (the memdir sits under `~/.claude`) |

{#red-r2-walkers-table}

### AC-3 (R2) — tests/test_bug216_rule_docs_e2e.py {#red-ac3}

| test | HEAD line |
|---|---|
| `test_ac3_a_path_that_becomes_reincluded_is_picked_up_by_the_next_sync` | `re-included profile not picked up by the next sync: {'added': 0, …}` |
| `test_ac3_a_path_that_becomes_ignored_is_purged_by_the_next_sync` | precondition: `` no `project-profile#constraints` node `` (cannot ingest it to purge) |
| `test_ac3_purge_of_a_path_that_becomes_ignored_is_unchanged_for_a_plain_path` | guard |

{#red-ac3-table}

### AC-4 (R3) — tests/test_bug216_scope_parity.py {#red-ac4}

| test | HEAD line |
|---|---|
| `test_ac4_fails_naming_the_file_and_the_spec_rule` | `the gate passed a lint-scope GMD doc the ingest excludes` (exit 0) |
| `test_ac4_fails_on_the_hidden_dir_rule_and_names_it` | exit 0: `gmd parity: 0 divergent doc(s), 0 parse failure(s)` |
| `test_ac4_fails_on_this_repos_head_config` | exit 0 (same line) |
| `test_ac4_this_repo_fails_with_its_head_config` | exit 0 on the mirrored real corpus |
| `test_ac4_lint_gmd_sh_fails_on_the_excluded_doc` | `lint-gmd.sh` exit 0 |
| `test_ac4_exits_zero_when_reincluded` | guard |
| `test_ac4_the_memory_dir_is_out_of_the_scope_check` | guard |
| `test_ac4_this_repo_passes_with_r4_config` | guard |

{#red-ac4-table}

`tests/test_bug179_anchor_parity.py` `_gate_root` now writes `.git` and the R4 ignore lines, so
its gate cases keep testing anchor parity only once R3 lands (43 passed at HEAD,
`bug179-head.log`). {#red-bug179-fixture}

### AC-5 (R5) — tests/test_bug216_rel_landing.py {#red-ac5}

All five fail on `scripts/check-rel-landing.py does not exist` / `can't open file`. The
fixture's own preconditions (2 docs, 3 rels landed through the real ingester) pass at HEAD.
Assumed output contract: `--json` prints one object with `authored`, `landed`,
`landed_other_line`, `file_not_ingested`, `target_unresolved`, `unresolved_by_target_doc`.
{#red-ac5-lines}

### AC-2 amended (lead, 2026-11-13) {#red-ac2-node-entity}

`_assert_edge_landed` now also requires the target to be the rule doc's NODE entity: kind
`concept` with the path of `CLAUDE.md` / `.claude/PROJECT_PROFILE.md`, not merely a row of that
name (the bsd-215m1 defect class). The HEAD lines in [[#red-ac2-table]] are unchanged.

### AC-7 (R6) — tests/test_bug216_binding.py {#red-ac7}

The same-named concept is minted the way production mints it: a plain `[[b-doc]]` mention
(`add_concept`, with `b_doc` / `b doc` variants and `same_as`). Fixture titles differ from
ids: a title equal to a hyphenated id mints that concept by itself (title terms), which hid the
producer in a first draft. {#red-ac7-fixture}

| test | HEAD line |
|---|---|
| `test_ac7_target_ingested_earlier_concept_minted_after_binds_the_doc` | `got [('concept', 'b-doc', None)]` |
| `test_ac7_citing_doc_ingested_first_then_resynced_binds_the_doc` (per-file `sync_files`) | `got [('concept', 'b-doc', None)]` |
| `test_ac7_two_citing_docs_in_one_batch_both_bind_the_doc` | `got [('concept', 'b-doc', None)]` |
| `test_ac7_memory_target_binds_the_memory` | `[('concept', 'b-mem')] == [('memory', 'b-mem')]` |
| `test_ac7_guard_fresh_one_batch_binds_the_doc[a-b-m / m-a-b / b-m-a]` | guard (pass 1 registers the doc id) |
| `test_ac7_guard_one_batch_with_an_unchanged_target_binds_the_doc` | guard (the resume skip still registers it) |
| `test_ac7_guard_anchored_target_binds_the_section_node` | guard |

{#red-ac7-table}

### AC-8 rev 3 (R7 `denotes`) — tests/test_bug216_binding.py {#red-ac8}

The misbound row is written with the store API (the fixed ingester no longer writes it). The op
is looked up as `OPS["denotes_link"]` and must return `{"added": n}`. {#red-ac8-contract}

| test | HEAD line |
|---|---|
| `test_ac8_derive_op_links_the_misbound_concept_and_its_variants_to_the_doc` | `` no `denotes_link` op in the daemon's OPS registry `` |
| `test_ac8_a_second_run_adds_nothing` | same |
| `test_ac8_ingest_links_a_preexisting_concept_and_purge_removes_it` | `set() == {(1, 4), (2, 4), (3, 4)}` (no ingest-time link) |

{#red-ac8-table}

### AC-9 (R8) — tests/test_bug216_rel_landing.py {#red-ac9}

Hand count: authored 6 = landed 5 + stale 1 (an evidence row with no live `entity_links` row);
binding `doc_or_memory` 1, `anchor_node` 1, `misbound` 1, `bound_via_denotes` 1,
`other_concept` 1. Both tests fail on the missing script. {#red-ac9-lines}

### AC-10 (R9) — tests/test_bug216_binding.py {#red-ac10}

A's only route to B: A's root node `-derives-from->` path-less `b-doc` `-denotes->` B's doc
(both written with the store API). {#red-ac10-fixture}

| test | HEAD line |
|---|---|
| `test_ac10_expansion_walk_reaches_b_at_one_hop` (`RMX_EXPAND_HOPS=1`, `content_rank`) | `assert 3 in {1, 2, 6, 7, 8, 12}` |
| `test_ac10_neighbors_of_a_lists_b` (`graphread.neighbors_payload`, depth 1) | `assert 3 in {1, 12}` |
| `test_ac10_pagerank_folds_the_in_edge_onto_b` (`pagerank.build_adjacency`) | `no A-B edge` |

{#red-ac10-table}

### Satisfiability and mutations {#red-mutations}

A scratch reference implementation (never committed; diffstat in
`scratch-ref-diffstat.txt`) turns all 58 tests green alongside `test_bug179_anchor_parity`,
`test_workflow_ignore` and `test_watch` (113 passed, `scratch-ref-green.log`). Mutations on
it, each killed (`scratch-ref-mut-M*.log`): {#red-satisfiable}

- M1 drop the hidden-dir override: 19 failures. {#red-m1}
- M2 re-include beats `INGEST_IGNORE_DIRS`: 6 failures. {#red-m2}
- M3 daemon watcher filters without a root: 3. {#red-m3}
- M4 ingest-gmd's walk ignores the spec: 13. {#red-m4}
- M5 a `!dir` line silently kept: 1. {#red-m5}
- M6 re-include matched by basename (unanchored): 1. {#red-m6}
- M7 parity scope check removed: 5. {#red-m7}

Rev 2 / rev 3, on the same scratch reference extended with R6-R9 (`scratch-ref-green-rev3.log`:
130 passed over every bug-216 file plus bug179 / workflow_ignore / watch; the 24 existing
gmd / pagerank / neighbors / ingest / sync test files give the same 1 failure and 185 passes
on the reference and at HEAD, `scratch-ref-related-files.log`): {#red-satisfiable-rev3}

- M8 concept-first restored for bare ids: 4. {#red-m8}
- M9 the batch dict caches the concept: 1. {#red-m9}
- M10 `denotes` written as `same_as`: 3. {#red-m10}
- M11 variants skipped: 2. {#red-m11}
- M12 the walk treats `denotes` as a counted hop: 1. {#red-m12}

The mock added is `_FakeObserver` (watchdog `Observer`, external), registered in
[[test_mock_registry]]. {#red-mocks}

## GREEN {#green}

(implementer)

## AC-6 (live) {#ac6}

(lead, after deploy and R4)
