---
gmd: "0.1"
id: impl-task-26.4-savestate-mtype-normalisation
title: "Task 26.4: a save-state's type is session/recall-state wherever it came from (RED stub)"
tags: [implementation-summary, plan-26, save-state, mtype, bridge, recall, bug-164]
metadata:
  node_type: implementation-summary
  status: red
  created: 2026-11-11
---

# Task 26.4: save-state mtype normalisation {#root}

rel: implements -> [[task-26.4-savestate-mtype-normalisation]]
rel: part-of -> [[plan-26-memory-organisation]]
rel: implements -> [[refmatrix/adr-0005-memory-dir-layout#authority]]
rel: depends-on -> [[refmatrix/adr-0005-memory-dir-layout#newest]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: depends-on -> [[task-26.2-bridge-move-safety]]
rel: related-to -> [[task-26.5-memory-organise-verb]]

TDD RED only, on branch `task-26.4-savestate-mtype-normalisation` in the clone
`/Volumes/littlebig/refmatrix-plan26-4`, base `f7c0d39`. No `src/` change. One new file,
`tests/test_savestate_mtype.py`: 17 tests fail at the base, and 1 fixture-proof test passes on
purpose. RED log: `workflow/review-output/plan26/26.4-red.log`.

## Contracts the RED file chooses {#contracts}

- `IngestStats.mtype_normalised: list[(id, from, to)]`. `as_dict()` gives it as
  `[[id, from, to]]`. `cli._sync_memory_dir` returns it as `out["mtype_normalised"]` from the
  in-process leg, the daemon leg and the waited-job branch.
- The bridge report prints `mtype_normalised: N` and names each id.
- The AC-3 file correction is a 26.4-owned primitive that 26.5's organise calls:
  `memory_layout.normalise_savestate_types(memdir, *, apply: bool) -> list[dict]`. Each entry
  is `{id, path, from, to}`. With `apply=False` it writes nothing. With `apply=True` it changes
  only the `type:` line and restores the prior mtime.

## RED tests {#red}

| test | AC | RED at `f7c0d39` |
|---|---|---|
| `test_ac1_top_level_hand_typed_savestate_is_stored_as_recall_state` | AC-1 | stored as `project` |
| `test_ac1_savestates_folder_file_ignores_its_frontmatter_type[project/feedback/None]` | AC-1 | stored as `project` / `feedback` / `curated` |
| `test_ac1_ingest_stats_count_every_override_and_only_overrides` | AC-1 | no `IngestStats.mtype_normalised` |
| `test_ac1_bridge_report_prints_the_count_and_names_each_id` | AC-1 | no `mtype_normalised: 4` line |
| `test_ac1_in_process_bridge_result_carries_mtype_normalised` | AC-1 (`_bridge_stats`) | `KeyError` |
| `test_ac1_daemon_bridge_result_carries_mtype_normalised` | AC-1 (daemon leg) | field is `None` |
| `test_ac1_waited_job_result_carries_mtype_normalised` | AC-1 (`_bridge_wait_for_active_job`, r1 #m5) | field is `None` |
| `test_ac2_hook_mode_recall_hides_the_hand_typed_savestate_and_include_session_keeps_it` | AC-2 | the hook-mode answer contains the save-state |
| `test_ac3_apply_rewrites_only_the_type_line_and_restores_mtime` | AC-3 | no `normalise_savestate_types` |
| `test_ac3_preview_lists_the_corrections_and_writes_nothing` | AC-3 | no `normalise_savestate_types` |
| `test_ac3_recall_state_still_resumes_from_august_after_the_rewrite[False/True]` | AC-3 | no `normalise_savestate_types` (August is newest before the call) |
| `test_ac3_after_the_rewrite_disk_and_store_agree_and_the_next_bridge_counts_zero` | AC-3 | `KeyError` |
| `test_ac3b_unorganised_unchanged_file_keeps_its_row_until_its_next_touch` | AC-3b (un-organised) | after the touch, still `project` |
| `test_ac4_a_project_file_in_feedback_is_not_retyped_by_bridge_or_correction` | AC-4 | `KeyError` |
| `test_ac3_fixture_discriminates_both_mutations` | AC-3 fixture proof | passes by design |

The AC-2 test runs the hook's own argv. It takes the UserPromptSubmit command from
`hooks._claude_hook_block` and replaces only the `--timeout` value. It runs that argv with
`RMX_INVOCATION_SOURCE=hook` against a real daemon and the real embed model. A feedback note
that answers the same prompt is the control. Task 25.1 depends on this test.

## Not in this task {#handed-to-265}

- The organised half of AC-3b, where `organise --apply` forces a one-time re-bridge of every
  save-state. That is 26.5 AC-5.
- AC-4's `organise --check` line `folder/type mismatch`. That is 26.5 AC-2.

Both need the organise verb, and 26.5 depends on 26.4.

## Spec ambiguity left unpinned {#ambiguity}

AC-1 applies the rule to "a file whose id starts with `savestate_`". ADR-0005 #authority and
`memory_layout.is_savestate_path` limit it to a legacy top-level file. No test uses a
`savestate_*` id in any other folder.

## Mock governance {#mocks}

The only patch is `cli._root`, pointed at the throwaway store in the daemon legs. Its existing
`external` row in `workflow/test_mock_registry.md` now lists this file. No fake implementations.
