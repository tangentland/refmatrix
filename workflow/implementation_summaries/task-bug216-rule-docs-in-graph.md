---
gmd: "0.1"
id: impl-task-bug216-rule-docs-in-graph
title: "Task bug-216: the rule docs reach the graph (implementation summary)"
tags: [implementation-summary, bug-216, gmd, ingest, ignore, linkages, tdd]
metadata:
  node_type: implementation-summary
  status: green
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

- With rev 4 (AC-11, AC-12, AC-13, the `ingest-gmd <subdir>` root, and the fixture updates
  R11/R12 require) at `4206137` (merge of dev master `3ddba55`; still no `src/` change since
  `758bca1`): **bug-216 files 71 failed, 28 passed** over 99 tests; `test_workflow_ignore` 1
  failed (its R12-updated default set), `test_bug179_anchor_parity` 43 passed
  (`red-head-rev4-4206137.log`).

Every failure is the missing mechanism, not the test's setup. The tests that pass at HEAD are
guards (existing behaviour re-asserted, or mutation killers that can only fail once the
mechanism exists); each is marked "guard" below. {#red-count}

rel: specifies -> [[task-bug216-rule-docs-in-graph#acceptance]]
rel: specifies -> [[task-bug216-rule-docs-in-graph#rev-2]]
rel: specifies -> [[task-bug216-rule-docs-in-graph#rev-3]]
rel: specifies -> [[task-bug216-rule-docs-in-graph#rev-4]]

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

### AC-11 (R10 pending refs) — tests/test_bug216_rev4.py {#red-ac11}

Observed by behaviour, not by a table name: the edge appears, evidence is never duplicated, a
purged citer leaves nothing. {#red-ac11-shape}

| test | HEAD line |
|---|---|
| `test_ac11_a_pending_ref_resolves_when_its_target_is_ingested` | `the pending bare ref did not resolve (to B's doc) when B was ingested` |
| `test_ac11_a_resolved_pending_row_is_cleared` | `assert 0 == 1` (no edge at all yet) |
| `test_ac11_resolution_is_counted_in_the_ingest_report` | report has no `pending` line |
| `test_ac11_the_rule_doc_lines_land_when_claude_md_is_unignored_without_touching_citers` | `` no `claude#no-silent-failures` node `` after syncing only CLAUDE.md |
| `test_ac11_purging_the_citer_drops_its_pending_rows` | guard (nothing resolves at HEAD) |

{#red-ac11-table}

### AC-12 (R11 built-in include) — tests/test_bug216_rev4.py, tests/test_bug216_scope_parity.py {#red-ac12}

| test | HEAD line |
|---|---|
| `test_ac12_no_ignore_file_includes_the_gmd_profile` | `assert True is False` |
| `test_ac12_reinclude_beats_an_explicit_ignore` | `assert True is False` |
| `test_ac12_every_walker_ingests_the_rule_docs_with_no_ignore_file[sync / watcher / ingest-path]` | `missing ['.claude/PROJECT_PROFILE.md']` |
| `…[op-ingest-gmd / cli-ingest-gmd]` | extra `.claude/agents/x.md`, `node_modules/n.md` |
| `test_ac12_guard_a_profile_without_frontmatter_is_not_included` | guard |
| `test_ac12_guard_explicit_ignore_lines_beat_the_builtin_include` | guard |
| `test_ac12_the_gate_passes_a_checkout_with_no_ignore_file` | guard (no scope check yet; fails if R3 lands without R11) |

`test_ac4_fails_on_the_hidden_dir_rule_and_names_it` now scans a `.claude/NOTES.md` (the GMD
profile is a built-in include under R11) and asserts the profile is never a finding. The bug-179
gate fixture no longer writes a `.refmatrix_ignore` (it keeps `.git`): like a clone, it passes
only through R11. {#red-ac12-updates}

### AC-13 (R12 one ignore list) — tests/test_bug216_rev4.py, tests/test_workflow_ignore.py {#red-ac13}

| test | HEAD line |
|---|---|
| `test_ac13_ingest_ignore_dirs_holds_the_watchers_dirs` | `('node_modules', 'venv')` |
| `test_ac13_watch_py_defines_no_ignore_list` | `watch.py still defines its own ignore list: ['IGNORE_DIRS']` |
| `test_ac13_tool_dirs_are_ignored_by_every_walker[sync / op-ingest-gmd / cli-ingest-gmd / ingest-path]` | `ingested ['__pycache__/x.md', 'build/x.md', 'dist/x.md', …]` |
| `…[watcher]` | guard (the watcher's private list already drops them) |
| `test_workflow_ignore.py::test_builtin_defaults_minimal_no_workflow` (updated) | `{'node_modules', 'venv'} == {… '__pycache__', 'dist', 'build'}` |

{#red-ac13-table}

### ingest-gmd on a subdir (#rev-4-accepted) — tests/test_bug216_rev4.py {#red-subdir}

`test_ingest_gmd_on_a_subdir_reads_the_spec_from_the_project_root[op / cli]`: HEAD ingests
`docs/private/p.md` (`{'docs/finding.md', 'docs/other.md', 'docs/private/p.md'}`). {#red-subdir-line}

### AC-14 (R13 replay fidelity, rev 5) — tests/test_bug216_replay_fidelity.py {#red-ac14}

RED at `4cacc5c` (`red-r13-4cacc5c.log`): 4 failed, 2 passed (the two guards).

| test | line at `4cacc5c` |
|---|---|
| `test_ac14_a_replay_after_a_changed_doc_matches_the_catalog[rebuild / delta]` | replay has an extra v1 `rel: derives-from -> b-doc` evidence row (line 16), and is missing both pending rows (`c-doc`, `d-doc`) |
| `test_ac14_a_pending_ref_binds_identically_after_replay[rebuild / delta]` | the same extra v1 evidence row; missing the `d-doc` pending row |
| `test_ac14_guard_a_log_without_the_new_events_replays_as_before[rebuild / delta]` | guard |

A scratch R13 reference (logged clear / pending events; `_apply_event_body` applies them; the
rebuild applies them in log order with `evidence`) passes the file plus test_bug117 / test_log /
test_factslog_compaction (29), and every bug-216 file + bridge-move + log tests (185). Mutations,
each failing: drop the clear event (4), drop the pending events (4), the rebuild ignores them (2),
the delta path ignores them (2) (`scratch-r13-*.log`). {#red-ac14-proof}

### Rev 6: AC-14 purge, AC-15 (R14), AC-16 (R6b) {#red-rev6}

RED at `f79dab1`, run in a clean clone of the committed tip (green-216's uncommitted R13 work in
the shared tree excluded): `red-rev6-f79dab1.log` (replay + surfaces + verb parity: 20 failed,
165 passed) and `red-rev6-surfaces-f79dab1.log` (surfaces alone: 9 failed, 1 guard passed).

| test | line at `f79dab1` |
|---|---|
| `test_ac14_a_purged_citer_leaves_no_pending_rows_after_replay[rebuild / delta]` | replay differs: the survivor's pending row is missing (nothing logged) |
| `test_ac15_the_derive_is_a_verb_with_cli_and_mcp_twins` | `` no `rmx_derive_denotes` verb `` |
| `test_ac15_the_verb_returns_the_ops_counts` / `…mcp_tool_returns_the_ops_counts` | `KeyError: 'rmx_derive_denotes'` |
| `test_ac15_the_cli_prints_the_ops_counts` | `Usage: main derive [OPTIONS] COMMAND` (no `denotes`) |
| `test_ac15_daemon_down_the_cli_fails_loudly_and_writes_nothing` | `the command does not exist` |
| `test_ac15_daemon_down_the_mcp_tool_returns_an_error` | `` no `rmx_derive_denotes` tool `` |
| `test_ac16_the_prestage_op_names_its_ignored_path_in_the_result` | result has no `ignored` / `ignored_paths` |
| `test_ac16_the_prestage_cli_names_its_ignored_path_daemon_down / _daemon_up` | stdout is only `prestaged: considered=1 …` |
| `test_ac16_guard_the_memory_prestage_still_names_its_skips` | guard |
| `test_verb_parity`: pairing / exclusions / click defaults / wiring / `cli_twin_calls_its_verb[rmx_derive_denotes]` | the new PAIRING and CLI_INVOKE rows name a verb that does not exist |

A scratch reference (R13 events incl. the purge, the verb + `rmx derive denotes`, prestage
`ignored`) passes these three files (185) and 31 cli / tree / mcp / verb / bug-216 files (565).
Mutations, each failing (`scratch-rev6-mut-*.log`): tombstone replay leaves pending rows (1, the
delta case — the rebuild never materializes a row for a dead source); the CLI swallows the
daemon-down error (1); the CLI bypasses the verb (2); the verb drops counts (3); the prestage op
leaves exclusions on stderr (2); the prestage CLI does not print them (2). {#red-rev6-proof}

### R13 on the rebuild only (d9bu) + AC-17 (watcher / sync `base=`) {#red-rev6b}

Lead correction: d9bu RETIRED the incremental replay (`apply_log_delta` / `_apply_event_body`;
no caller in `src/`, 16.6 deletes it), so `tests/test_bug216_replay_fidelity.py` now replays
through `rebuild_index_from_log` ONLY — the `[delta]` cases were removed, not xfailed, and the
mutations "the delta path ignores them" and "the tombstone replay leaves pending rows" (which
killed only the delta case) are gone. The rebuild never materializes a citer that did not
survive its tombstone, so the purge case pins the outcome. {#red-rev6b-d9bu}

RED at `fa71087`, clean clone (`red-rev6b-fa71087.log`): 11 failed, 3 passed.

| test | line at `fa71087` |
|---|---|
| `test_ac14_a_replay_after_a_changed_doc_matches_the_catalog` | the rebuild differs: an extra v1 evidence row, both pending rows missing |
| `test_ac14_a_pending_ref_binds_identically_after_replay` | the rebuild differs |
| `test_ac14_a_purged_citer_leaves_no_pending_rows_after_replay` | the rebuild differs: the survivor's pending row missing |
| `test_ac14_guard_a_log_without_the_new_events_replays_as_before` | guard |
| `test_ac17_a_project_below_an_ignored_ancestor_still_syncs[.hidden / build × watcher / sync / ingest-path]` | `assert 'docs/d.md' in set()` — nothing synced |
| `…[.hidden-op-ingest-gmd / build-op-ingest-gmd]` | guard (`ingest-gmd` already passes `base=`) |
| `test_ac17_watch_is_relevant_judges_paths_below_the_root[.hidden / build]` | `is_relevant(docs/d.md)` is False |

Scratch reference (`ignore_reason` defaults `base` to `root`; R13 on the rebuild): 210 passed over
every bug-216 file + workflow_ignore / watch / bug179 (`scratch-rev6b-ref-green.log`). Mutations,
each failing (`scratch-rev6b-mut-*.log`): drop `base=` (8), no segment rules under a root (10),
drop the clear event (2), drop the pending events (3), the rebuild ignores them (3).
{#red-rev6b-proof}

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

Rev 4, on the reference extended with R10-R12 and the subdir root
(`scratch-ref-green-rev4.log`: 154 passed over every bug-216 file plus bug179 / workflow_ignore
/ watch; 28 related existing files: the same 1 pre-existing failure and 206 passes,
`scratch-ref-related-files-rev4.log`): {#red-satisfiable-rev4}

- M13 resolved pending rows never cleared: 1. {#red-m13}
- M14 no built-in include: 10 (incl. both bug-179 gate cases). {#red-m14}
- M15 purge leaves pending rows AND resolution skips the source-liveness check: 1 (either
  safeguard alone satisfies the AC). {#red-m15}
- M16 ingest-gmd takes the target dir as the spec root: 2. {#red-m16}

The mock added is `_FakeObserver` (watchdog `Observer`, external), registered in
[[test_mock_registry]]. {#red-mocks}

## GREEN {#green}

Implementer `green-216`, 2026-11-13. Commits on `task-bug216-rule-docs-in-graph`: `2fc5554`
(src + scripts), `4994a37` (docs/INTEGRATION.md). Interpreter: the clone's `.venv-eval` with
`PYTHONPATH=<clone>/src`. No test was authored or edited. {#green-commits}

rel: implements -> [[task-bug216-rule-docs-in-graph#requirements]]
rel: implements -> [[task-bug216-rule-docs-in-graph#rev-2]]
rel: implements -> [[task-bug216-rule-docs-in-graph#rev-3]]
rel: implements -> [[task-bug216-rule-docs-in-graph#rev-4]]

### Where each requirement lives {#green-map}

| R | code |
|---|---|
| R1 | `ingest.IgnoreSpec` (`reincludes`, `dir_reincludes`, `reincluded`, `matching_pattern`); `load_ignore_spec` reports a `!dir` line once per load on stderr |
| R2 | `ingest.ignore_reason(p, root, *, base=None)` is THE rule; `should_ignore` wraps it. Callers: `_ingest_tree`, `sync._sync_one`, `watch.is_relevant` (no private list), the daemon handler `_start_watcher._maybe` (now `is_relevant(p, _owning_root(...))`), `ingest_gmd.collect_gmd_files` (project root = `ingest.find_project_root`, segment rules below the target via `base`, exclusions returned as `ignored` and named by `render_ignored_line` in the daemon/CLI reports) |
| R3 | `scripts/check-gmd-parity.py`: `scan(..., exclusions)`, `[ingest-scope]` error line naming the file and the rule; spec read from the nearest `.refmatrix/`, else `.git`, else the script's checkout |
| R5/R8 | `scripts/check-rel-landing.py` (new): copies the catalog (+WAL) to a temp dir and opens the copy read-only; live-edge join in SQL; categories, `stale`, `binding`, `unresolved_by_target_doc`, `files_not_ingested`, `parse_failures` |
| R6 | `ingest_gmd._resolve_target_eid`: bare `doc, memory, concept`; anchored `concept, doc, memory`; a bare concept hit is never cached. `_resolve_ref` (ADR slash bridge) serves `rel:` lines, plain wikilinks and pending resolution alike |
| R7 | `store.DENOTES`; `Store.link_denotes(names=None)` (variants = the concept's `same_as` group, two hops, AND the `_concept_variants` spellings, because a sync batch buffers `same_as` until commit); `daemon._op_denotes_link` = `OPS["denotes_link"]` -> `{added, concepts, targets, multi_target, partition}`; GMD ingest calls `link_denotes` for the ids it wrote, the wikilink-mention concepts, title tokens and tags it minted; `purge_entity` already deletes both sides of `entity_links` |
| R9 | `Store.denotes_equivalents`; `content_rank` expansion (`_close`: zero-cost, never in the hop query, never decayed); `QueryEngine.neighbors` (equivalents join the same frontier; `denotes` dropped from the counted linkages); `pagerank.build_adjacency` (typed non-`mentions` in-edges of a denoting concept folded onto its targets, split evenly; `_ADJ_SHAPE` in both adjacency cache keys); `context.build_context` one-hop walk reads the denoting concepts' rows for a doc/memory anchor (the PPR degree walk inherits the fold through `cached_adjacency`) |
| R10 | `pending_refs` table; `Store.add_pending_ref` / `clear_pending_refs_for_file` / `pending_refs_for` / `delete_pending_ref` / `entity_exists`; `ingest_gmd.resolve_pending_refs` after pass 2 over every name the batch registered (skipped docs included); `purge_entity` deletes the purged source's rows; resolution re-checks the source exists (dropped rows counted); a re-processed doc first clears its own pending rows and its `rel:` evidence (`Store.clear_rel_evidence`), so no line ever carries two evidence rows; report lines `pending refs resolved/dropped`, `unresolved refs: N (M recorded as pending …)`, `denotes links added` |
| R11 | `ingest.BUILTIN_INCLUDES` + `is_gmd_file` (the one sniff; `sync._is_gmd_file` is now an alias), step 4 of `ignore_reason` |
| R12 | `INGEST_IGNORE_DIRS = (node_modules, venv, __pycache__, dist, build)`; `watch.py` defines no ignore list |

### Migration {#green-migration}

One new table, `pending_refs`, in BOTH catalog DDLs (`store.CATALOG_DDL` for SQLite,
`duckdb_catalog.CATALOG_DDL` for DuckDB) as `CREATE TABLE IF NOT EXISTS`, no key or index (it
holds the unresolved residue; `add_pending_ref` keeps it duplicate-free). An existing store gains
it the first time a writer opens it: the DuckDB backend runs `init_catalog` on every writer open,
the SQLite backend runs `executescript(CATALOG_DDL)` on every connect. Read-only snapshot
connections never touch it. The `denotes` linkage type is registered on first use by
`link_denotes` (`add_linkage_type`, which logs a `linkage_type` event), so no store carries it
until something is linked. SUPERSEDED for `pending_refs` (this paragraph first said it was
neither merged nor replayed): R13 makes its writes facts.log events that `rebuild_index_from_log`
applies and the compaction dump re-emits ([[#green-rev6]]), and remedy S2 puts it in
`replica_merge` and `merge_partition` ([[#green-remedy-r1]]). {#green-migration-story}

### Results {#green-results}

- **bug-216 files + `test_workflow_ignore` + `test_bug179_anchor_parity`:** 149 passed
  (`green-iter1.log`). With `test_watch`, `test_derive_coverage`, `test_memory_bridge`,
  `test_session_ingest` added after the `base` fix: 212 passed, 1 failed — [[#green-flag-bridge]]
  (`green-iter2.log`).
- **Family** (112 files over ingest, ingest_gmd, sync, watch, daemon ops, pagerank / PPR,
  neighbors / graph, context, store, replica, duckdb, rank, bridge, plus the scope and bug-179
  files): 4 failed, 1511 passed, 1 skipped (`green-family.log`, BEFORE the `base` fix). Two were
  mine and are fixed or flagged (`test_derive_coverage` -> [[#green-flag-base]];
  `test_memory_bridge` AC-2 -> [[#green-flag-bridge]]); two are pre-existing (below).
- **Full suite** at `4994a37`: **5 failed, 4377 passed, 1 skipped** in 46 min (`green-full.log`)
  against `release-0.82.0-full.log`'s 14 failed, compared by E line:
  `test_brief_real_daemon::test_an_unknown_class…` (DuckDB "Conflicting lock", same E line) and
  `test_task21_1_agent_usage_report` ×2 (same E lines) are pre-existing;
  `test_gmd_lint_requires_version::test_the_repo_scope_is_clean…` fails in the clone only
  because lint namespaces ids by the checkout's directory name (`refmatrix-bug216`) — 9 passed on
  a copy named `refmatrix` (`gmd-lint-requires-version-copy.log`);
  `test_memory_bridge::test_ac2_doc_ingest_keeps_its_own_walk` was the R2 conflict, since
  re-specified by the lead and passing ([[#green-flag-bridge]]). No other failure.
- **`./scripts/lint-gmd.sh`:** exit 0 (`lint-gmd.log`) on a copy of the tree named `refmatrix`
  with a COPY of the memdir under a scratch HOME. In place, the clone fails on the two
  environmental causes alone: the memdir is keyed by the checkout path (1,067 memory-id
  dangling-docs) and namespaced ids resolve by directory name (32). The scope check itself: 0
  docs outside the ingest scope (the clone has no `.refmatrix/`, so R11 applies).

### Mutations {#green-mutations}

Each applied alone after the GREEN commit, run, restored with `git checkout -- <file>` in its own
command, the fix grepped back; `__pycache__` cleared after the batch (src clean at `4994a37`).

| id | mutation | killed by | log |
|---|---|---|---|
| R6 | bare ids concept-first again | 4: `test_ac7_target_ingested_earlier…`, `…citing_doc_ingested_first_then_resynced…`, `…two_citing_docs_in_one_batch…`, `…memory_target_binds_the_memory` | `mut-R6.log` |
| R7 | `denotes` written as `same_as` | 3: all of AC-8 rev 3 | `mut-R7.log` |
| R9 | `denotes` an ordinary counted, decayed hop (`_den = None`) | 1: `test_ac10_expansion_walk_reaches_b_at_one_hop` | `mut-R9.log` |
| R10 | a resolved pending row never cleared | 1: `test_ac11_a_resolved_pending_row_is_cleared` | `mut-R10.log` |
| R11 | no built-in include | 10: AC-12 (7, incl. the no-ignore-file gate), `test_ac4_fails_on_the_hidden_dir_rule…`, both bug-179 gate cases | `mut-R11.log` |

{#green-mutation-table}

### Flags {#green-flags}

1. **Test conflict — RESOLVED by the lead's ruling.** `tests/test_memory_bridge.py::test_ac2_doc_ingest_keeps_its_own_walk`
   (task 26.1 AC-2) expected the DOC walk of a memdir to take `.organise-rollback-1/x.md` and
   `.hidden/y.md`, which R2 forbids. Ruling 2026-11-13 (`64d70bc`, spec #r2-supersedes-261): R2
   wins; the test now expects `{keep_top.md, keep_nested.md}` with the two paths named. The
   user's condition is pinned by `tests/test_bug216_hidden_no_pollution.py` (`f75cbc3`). Both
   pass on this src unchanged: 54 passed (`green-after-ruling.log`). {#green-flag-bridge}
2. **The gate goes red in the dev tree at merge, by design.** Its live `.refmatrix_ignore` lists
   `CLAUDE.md` and `.claude`; `check-gmd-parity.py` there reports both rule docs
   (`parity-dev-tree-live-ignore.log`). R4 clears it, and R4 is safe before the deploy: old code
   reads `!.claude/PROJECT_PROFILE.md` as an anchored pattern matching nothing, and removing the
   `CLAUDE.md` line lets the running daemon ingest CLAUDE.md. {#green-flag-gate}
3. **Daemon watcher behaviour.** Its first filter now reads the spec, so a spec-ignored file's
   fs event no longer reaches `sync_files` (which used to purge it). This is what `rmx watch`
   already did; a path that BECOMES ignored is still purged by any sync that names it (AC-3).
   {#green-flag-watcher}
4. **`base` on the predicate.** `should_ignore(p, root, *, base=…)`: the doc walk applies the
   segment rules below the target it was handed. Found by `test_derive_coverage`: `rmx session
   ingest` walks `<project>/.refmatrix/sessions/` with the doc walk and indexed nothing once the
   hidden-dir rule saw `.refmatrix` in the absolute path. {#green-flag-base}
5. **No CLI for the derive op.** A new command needs a verb + MCP tool or an `INTERNAL_CLI`
   entry (a frozen, user-decided set), so the op is run through the daemon:
   `daemon.call(root, "denotes_link", {}, timeout=600)`, per partition (`{"partition": …}`).
   {#green-flag-cli}
6. **Prestage.** `prestage_hashes` (op and CLI) uses the same walk but does not take `ignored`;
   its exclusions print on the process's stderr (the daemon's log for the op). {#green-flag-prestage}
7. **Evidence re-derivation cost.** `clear_rel_evidence` scans `linkage_evidence` by `file` (no
   index on it) once per re-processed GMD doc. {#green-flag-cost}
8. **AC-6 run.** `check-rel-landing.py <catalog-copy> CLAUDE.md docs workflow eval
   .claude/PROJECT_PROFILE.md --json` (it copies the catalog it is given again before opening).
   `bound_via_denotes` needs the derive op first. {#green-flag-ac6}

### GREEN rev 5-6: R13, R14, R6b, R2 base {#green-rev6}

Commits: `c44233b` (R13), `87b2ec3` (R13 on the rebuild only — d9bu retired
`apply_log_delta` / `_apply_event_body`; the four branches `c44233b` added there are removed),
`e26f0c9` (R14 + R6b + R2 base), `b556bf3` (regenerated CLI tree in docs/ARCHITECTURE.md). RED
built against: `f79dab1`, `fa71087`, `4b4b96e`. {#green-rev6-commits}

rel: implements -> [[task-bug216-rule-docs-in-graph#r13]]
rel: implements -> [[task-bug216-rule-docs-in-graph#r14]]
rel: implements -> [[task-bug216-rule-docs-in-graph#r6b]]
rel: implements -> [[task-bug216-rule-docs-in-graph#r2-base]]

- **R13.** `Store.clear_rel_evidence` logs `rel_evidence_clear{partition, file}`;
  `add_pending_ref` / `delete_pending_ref` log `pending_ref` / `pending_ref_delete{partition,
  s_kind, s, linkage, target_name, file, line[, ref, weight, detail]}` (source by kind + name,
  never id, via `_log_pending`); `clear_pending_refs_for_file` logs `pending_refs_clear{partition,
  file}`. `rebuild_index_from_log` applies the clear in log order against the `evidence` events
  (same predicate: partition, file, `rel: ` detail) and folds pending ops with source
  `tombstone`s in log order (purge_entity's pending delete), writing the survivors whose source
  survives (`pending_refs`, `pending_refs_skipped_dead` in its counts). `dump_catalog_to_log`
  re-emits live pending rows, so a facts.log compaction keeps them. The `pending_refs` schema
  comment (both DDLs) now says the rows are rebuilt from facts.log. {#green-r13}
- **R14.** `verbs.derive_denotes(root, *, partition=None, timeout=None)` = verb
  `rmx_derive_denotes` over the `denotes_link` op (one attempt, `write=True`,
  `DERIVE_DENOTES_TIMEOUT_S = 600`); CLI twin `rmx derive denotes` (partition from `rmx -p` or
  `RMX_PARTITION`, else the daemon's) prints `added=… concepts=… targets=… multi_target=…`;
  daemon down → `ClickException` naming the daemon, exit 1, nothing written; the MCP tool is
  generated from the verb and returns `{"error": …}`. `CLI_MAP` entry, wiring `calls`. {#green-r14}
- **R6b.** `_op_prestage_hashes` passes `ignored=` and returns `ignored` / `ignored_paths`; both
  CLI prestage branches pass `ignored=` and print `render_ignored_line` on stdout. {#green-r6b}
- **R2 base (AC-17).** `ignore_reason`'s segment rules read the parts below `base`, which now
  DEFAULTS to `root`: every walker (watcher, sync, `ingest_path`, the tldr / semantic passes)
  judges a project under `<x>/.hidden/` or `<x>/build/` by its own paths; `ingest-gmd <dir>` still
  passes the target as `base`. {#green-r2-base}

Results (logs in `workflow/review-output/bug216/`): R13 file at `4b4b96e` 4 passed
(`r13-green-4b4b96e.log`); R14 / R6b / AC-17 + verb parity + docs-generated + replay: 198 passed
(`r14-iter1.log`); full suite at `b556bf3`: **4 failed, 4435 passed, 1 skipped**
(`rev6-full.log`) — `test_brief_real_daemon` and `test_task21_1_agent_usage_report` ×2 with the
release-0.82.0 E lines, and `test_gmd_lint_requires_version` (clone directory name; 9 passed on a
copy named `refmatrix`, `gmd-lint-requires-version-copy-rev6.log`). `lint-gmd.sh` exit 0 on that
copy (`lint-gmd-rev6.log`). The earlier `#green-results` runs predate these commits. {#green-rev6-results}

| mutation | killed by | log |
|---|---|---|
| R13: drop the `rel_evidence_clear` event | 2 (AC-14 changed doc, binds identically) | `mut-R13-clear.log` |
| R13: drop the pending events | 3 (+ purged citer) | `mut-R13-pending.log` |
| R13: the rebuild ignores the new ops | 3 | `mut-R13-rebuild.log` |
| R2 base: no default `base` (absolute parts) | 8 (AC-17) | `mut-R2base.log` |
| R14: the CLI swallows the daemon-down error | 1 | `mut-R14-cli-swallow.log` |
| R14: the verb drops the counts | 3 (verb, CLI, MCP) | `mut-R14-verb-counts.log` |
| R6b: the op does not collect `ignored` | 2 (op result, CLI daemon-up) | `mut-R6b-prestage-op.log` |

{#green-rev6-mutations}

Flags 5 and 6 of [[#green-flags]] are closed by R14 and R6b; flag 9 by R13. The R13 mutation run
that hit red-216's in-flight test edits was discarded and re-run at `4b4b96e`. {#green-rev6-flags}

### GREEN remedy r1: bsd-216 r1 (rulings L81 + L86) {#green-remedy-r1}

Commits: `b8c680a` (src), `dea70a0` (SQLite fix), `af89663` (docs: INTEGRATION.md `#ignore-rules`, spec R4 / AC-6 /
`revision: 6`). RED built against: `aac951c`, `1d2e200` (L86 pins), `eeaaefa` (red-216's fixture
fixes after this implementer's report: the M2 context fixture shared B's title / tag, and the S1
`rmx ingest .` pin drops the ingest-gmd build per L86). Audit: dev master's
`workflow/bullshit/2026-11-13-1619-bug216-r1-df092ac.md` (not on this branch, so cited by path).
{#green-remedy-commits}

- **B1.** `ingest.ingest_ignore_root(s, target)` is the root every `ingest_path` walk is judged
  against: the store's own project when the target lies inside it, else the nearest `.refmatrix/`
  above, else the target. The tree walk, the python-semantic `rglob`, the tldr metadata and
  call-graph passes take it (`ignore_root=`). `rmx ingest <memdir>`, MCP `rmx_ingest` on a memdir
  and `rmx ingest <proj>/.claude` store nothing but a built-in-included GMD profile (L86).
  `ingest-gmd <dir>` keeps `base=<dir>` (session ingest). {#green-remedy-b1}
- **S1.** No code: `reingest --force` already runs `clear_tracked_stamps`, which clears the GMD
  content hashes (`_clear_gmd_content_hashes`); the L86 pin passes on that. The procedure is written
  into spec `#r4` / `#ac-6`, INTEGRATION `#ignore-rules`, and the `resolve_pending_refs`
  docstring. {#green-remedy-s1}
- **S2.** `pending_refs` is in `replica_merge`'s three table lists (`OPTIONAL_TABLES`: a slot that
  predates it counts 0); `_merge_into` copies it with the `linkage_evidence`-style source remap,
  collapsing a row both slots hold. The fixture surfaced a pre-existing merge loss: two DIFFERENT
  entities sharing an id across diverged slots were read as one, B's newer row overwrote A's, and
  A's entity was gone; B's row now moves to a fresh id in the sequence headroom (`remap_fresh_b`,
  carried through `remap_b`; `MergeRefused` past `REMAP_HEADROOM`). `audit_via_writer` takes its
  arguments positionally as well. `Store._merge_pending_refs` (called by `merge_partition`)
  repoints, dedupes, deletes dead-source rows; the result carries `pending_refs_merged` and
  `pending_refs_dropped`. {#green-remedy-s2}
- **M2.** `store.DENOTES_TERM_LINKAGES` = {mentions, titles, aliases, lead, coref}: the zero-cost
  `denotes` hop never carries these, in PageRank's fold, `build_context`'s companion rows and
  `QueryEngine.neighbors` alike (adjacency cache shape `denotes-fold-2`). `neighbors` lists the raw
  `denotes` link and a seed's equivalents. {#green-remedy-m2}
- **M3.** A missing file at a `BUILTIN_INCLUDES` path stays in scope, so the watcher's delete
  event reaches `_sync_one`, which purges it. (Frontmatter REMOVED from an existing profile still
  drops the event: the file is then out by the hidden-dir rule, and nothing purges the stale doc
  until a sync names it.) {#green-remedy-m3}
- **M4.** The migration note above, the spec's `revision`, INTEGRATION `#ignore-rules` (which
  root a path is judged against; the live-store procedure; the delete case), the
  `_op_denotes_link` docstring. {#green-remedy-m4}

Results (logs in `workflow/review-output/bug216/`): the bug-216 family + workflow_ignore + watch
+ bug179 + session_ingest + derive_coverage + verb_parity + docs_generated + memory_bridge + the
three bridge files + replica_merge + bug113 + graph / context / PPR / adjacency + factslog /
bug117 / log: **659 passed** (`remedy-family.log`). Full suite at `af89663`: **11 failed, 4449 passed, 1 skipped** in 54 min
(`remedy-full.log`), compared by E line against `release-0.82.0-full.log`:
- MINE, fixed in `dea70a0`: `test_partition_merge` ×4, `sqlite3.OperationalError: no such
  function: any_value` (the merge_partition pending dedupe ran on the SQLite backend); the file
  plus the remedy and bug-178 files re-run: 63 passed, 3 failed (below) (`remedy-fix1.log`).
- EXPECTED by S2, golden owed by the test owner: `test_bug178_bulk_write::
  test_ac2_replica_merge_matches_head_and_reference` ×2 — the golden digests `merged_counts`
  item by item and S2 adds `pending_refs`; with that one entry removed both digests equal the
  golden (sent to red-216).
- ENVIRONMENTAL: `test_task21_1_recall_skip::test_ac2b_live_daemon_recall_writes_one_ok_recall_row`
  (`'skipped_budget' == 'ok'`, a 5 s live recall budget at load average 13) fails identically at
  `df092ac` and at the branch base `758bca1` (`recall-skip-at-*.log`);
  `test_gmd_lint_requires_version` (clone directory name, as before).
- PRE-EXISTING, same E lines as 0.82.0: `test_brief_real_daemon` (DuckDB lock conflict),
  `test_task21_1_agent_usage_report` ×2.
`lint-gmd.sh` exit 0, 0 errors, scope check 0 on a copy named `refmatrix` (`lint-gmd-remedy.log`).
{#green-remedy-results}

Mutation spot-checks, each alone in a throwaway clone of `af89663` (not this tree), restored with
`git checkout -- src` after each, `__pycache__` cleared; suite = `test_bug216_remedy_r1.py` +
`test_bug216_remedy_l86.py`:

| mutation | result | log |
|---|---|---|
| B1: the ignore root is the target | 4 failed | `mut-remedy-B1.log` |
| S2: the slot merge copies no pending rows | 1 failed | `mut-remedy-S2-slot.log` |
| S2: no fresh id for a shared id | 1 failed | `mut-remedy-S2-fresh.log` |
| S2: merge_partition keeps dead-source rows | 1 failed | `mut-remedy-S2-part.log` |
| M2: companion rows walk term linkages | 1 failed | `mut-remedy-M2-ctx.log` |
| M2: `neighbors` drops `denotes` from its linkages | **survived** (21 passed): equivalent — the seed's equivalents list the same target | `mut-remedy-M2-nbr.log` |
| M2: `neighbors` hides a seed's equivalents (df092ac shape) | 1 failed (+ binding) | `mut-remedy-M2-nbr-hide.log` |
| M3: the include needs the file to exist | 1 failed | `mut-remedy-M3.log` |

{#green-remedy-mutations}

## AC-6 (live) {#ac6}

(lead, after deploy and R4)
