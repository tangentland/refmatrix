---
gmd: "0.1"
id: impl-task-26.4-savestate-mtype-normalisation
title: "Task 26.4: a save-state's type is session/recall-state wherever it came from"
tags: [implementation-summary, plan-26, save-state, mtype, bridge, recall, bug-164]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-11
  updated: 2026-11-11
---

# Task 26.4: save-state mtype normalisation {#root}

rel: implements -> [[task-26.4-savestate-mtype-normalisation]]
rel: part-of -> [[plan-26-memory-organisation]]
rel: implements -> [[refmatrix/adr-0005-memory-dir-layout#authority]]
rel: depends-on -> [[refmatrix/adr-0005-memory-dir-layout#newest]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: depends-on -> [[task-26.2-bridge-move-safety]]
rel: related-to -> [[task-26.5-memory-organise-verb]]
rel: related-to -> [[deferral_registry]]

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

Until 26.5's organise calls it, `normalise_savestate_types` has no production caller. It is registered as `scaffold-no-caller` in `workflow/deferral_registry.md`. The row graduates when 26.5's `rmx memory organise --apply` calls it and prints its list. Owner: plan-26 26.5. The team lead approved this seam on 2026-11-11.

## Spec ambiguity left unpinned {#ambiguity}

AC-1 applies the rule to "a file whose id starts with `savestate_`". ADR-0005 #authority and
`memory_layout.is_savestate_path` limit it to a legacy top-level file. No test uses a
`savestate_*` id in any other folder.

## Mock governance {#mocks}

The only patch is `cli._root`, pointed at the throwaway store in the daemon legs. Its existing
`external` row in `workflow/test_mock_registry.md` now lists this file. No fake implementations.

## GREEN {#green}

TDD GREEN on the same branch. The `src/` commit is `1a1f189`, on top of the RED commits and
the deferral row `bf33236`. No test was authored or edited in this step.

### Lead decision applied {#green-decision}

The ADR wins over AC-1's wording (team-lead decision 2026-11-11). The bridge override applies
to the files `memory_layout.is_savestate_path` accepts and nothing else: files directly under
`savestates/`, and legacy top-level `savestate_*.md` files. A `savestate_*` file in another
folder is misfiled. 26.5's `organise --check` reports it, and the bridge does not re-type it.
No second predicate was added. The spec's AC-1 now carries a one-line clarification citing this
decision.

rel: depends-on -> [[refmatrix/adr-0005-memory-dir-layout#authority]]

### Signatures {#green-signatures}

- `ingest_gmd.IngestStats.mtype_normalised: list[tuple[str, str, str]]`, each entry
  `(id, from, to)`. `from` is the type the row would have carried: the frontmatter's value, or
  the bridge default (`curated`) when the file has none.
- `IngestStats.as_dict()["mtype_normalised"]` is `[[id, from, to]]`.
- `IngestStats.mtype_normalised_lines() -> list[str]` returns `mtype_normalised: N` plus one
  `  <id>: <from> -> <to>` line per override. It is never truncated. `report()` includes it.
- `ingest_gmd._OrganisedDirs.is_savestate(path) -> bool` is
  `memory_layout.is_savestate_path(memdir, path)`. `memdir` is the deepest bridge target that
  holds the file, which is the same bound the marker lookup uses. The walked path is judged
  before the resolved one.
- `memory_layout.SAVESTATE_MTYPE = FOLDERS["savestates"]`, which is `session/recall-state`.
- `memory_layout.normalise_savestate_types(memdir, *, apply: bool) -> list[dict]` returns one
  `{id, path, from, to, error}` per mis-typed save-state, in walk order.
- `cli._sync_memory_dir(...)["mtype_normalised"]` is copied by `_bridge_stats`. That one copy
  serves the in-process, daemon and waited-job legs.

### Where each AC lands {#green-acs}

| AC | code | test |
|---|---|---|
| AC-1 | `ingest_gmd_paths` as-memory pass 1, after the `metadata.type` read: override + count | 9 `test_ac1_*` |
| AC-1 legs | `_bridge_stats` (in-process, daemon `as_dict()`, waited-job `res["stats"]`) | `test_ac1_{in_process,daemon,waited_job}_*` |
| AC-2 | the stored mtype `session/recall-state` meets hook-mode's existing `session/*` exclusion | `test_ac2_*` |
| AC-3 | `normalise_savestate_types`: only the `type:` line changes (replace-first), atime/mtime restored | `test_ac3_*` (5) |
| AC-3b | unchanged file is skipped by the hash gate; its next touch re-ingests it and the rule lands | `test_ac3b_*` |
| AC-4 | neither the bridge nor the correction touches a non-save-state file | `test_ac4_*` |

In `normalise_savestate_types`:

- A file whose metadata block has no `type:` line gets one, added at the top of the block.
- Each of these comes back as a named `error` entry, never a skip: an unreadable file, a file
  with no frontmatter or no `metadata:` block, a symlink, a failed write, and an mtime that
  could not be restored.
- The row's metadata mirror keeps the file's own `type`, so the row records the disagreement
  until the file is corrected.

### Runs {#green-runs}

| run | result | log |
|---|---|---|
| RED file | 18 passed (17 formerly RED + the fixture proof) | `workflow/review-output/plan26/26.4-green.log` |
| 26.x families | 694 passed, 0 failed | `workflow/review-output/plan26/26.4-green-family.log` |
| RED file after the mutation restores | 18 passed | `workflow/review-output/plan26/26.4-green-postmut.log` |

The known pre-existing failures (bug-127/168, bug-196 x2, bug-170) did not occur in this family
run, so there was no E line to compare.

### Mutations {#green-mutations}

Each mutation was applied against `1a1f189` and restored with `git checkout` in its own command,
with `__pycache__` cleared. The final check found `git status --short src` empty and the fix
grep matching. Log: `workflow/review-output/plan26/26.4-mutations.log`.

| id | mutation | result |
|---|---|---|
| o | bridge override removed | 13 failed |
| s1 | count dropped on the daemon leg only | 1 failed (`test_ac1_daemon_*`) |
| s2 | count dropped on the waited-job leg only | 1 failed (`test_ac1_waited_job_*`) |
| t | rewrite lets mtime move | 3 failed (AC-3 type-line + recall-state x2) |
| u | rewrite also stamps `updated:` | 3 failed (same three) |
| f2 | override widened to every file in any folder | 5 failed |
| f3 | file correction widened to every memory file | 1 failed (`test_ac4_*`) |
| f1 | override widened to a `savestate_*` id in ANY folder | **SURVIVED** |

f1 survives because no fixture puts a `savestate_*` file outside the top level and
`savestates/`. The RED file left that case unpinned on purpose, before the lead decision. Now
that the decision pins it, a test is owed by `ch-test-engineer`: `feedback/savestate_x.md`
typed `project` keeps `project` and is not counted.

### Flags {#green-flags}

- **No production caller yet.** `normalise_savestate_types` stays registered as
  `scaffold-no-caller` (row `bf33236`) until 26.5's `organise --apply` calls it.
- **Direct callers that pass no `marker_roots`.** They bound a file by its own directory, as
  the marker lookup does. A `feedback/savestate_x.md` file passed that way would be read as a
  top-level save-state. No production as-memory caller does this: the CLI, the daemon and the
  session-card indexer all pass roots.
