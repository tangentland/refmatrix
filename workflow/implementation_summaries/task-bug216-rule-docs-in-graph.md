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

Base `758bca1`, branch `task-bug216-rule-docs-in-graph`, run with the clone's `src` on
`PYTHONPATH`. Log: `workflow/review-output/bug216/red-head-758bca1.log`.
**40 failed, 18 passed.** Every failure is the missing mechanism, not the test's setup. The
18 that pass at HEAD are guards (existing behaviour re-asserted, or mutation killers that can
only fail once R1 exists); each is marked "guard" below. {#red-count}

rel: specifies -> [[task-bug216-rule-docs-in-graph#acceptance]]

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

The mock added is `_FakeObserver` (watchdog `Observer`, external), registered in
[[test_mock_registry]]. {#red-mocks}

## GREEN {#green}

(implementer)

## AC-6 (live) {#ac6}

(lead, after deploy and R4)
