---
gmd: "0.1"
id: impl-task-26.1-layout-module-and-index-walk
title: "Task 26.1: memory_layout.py is the one memdir walk; the index walks every folder, keys hooks by id and carries prose"
tags: [implementation-summary, plan-26, memory-dir, memory-index, layout, hooks, bridge]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-09
---

# Task 26.1: memory_layout.py, one walk, a lossless index {#root}

rel: implements -> [[task-26.1-layout-module-and-index-walk]]
rel: part-of -> [[plan-26-memory-organisation]]
rel: realizes -> [[refmatrix/adr-0005-memory-dir-layout]]

TDD GREEN over the RED commit `65af1f6` (45 failed / 54 passed,
`workflow/review-output/plan26/task-26.1-red-61b3bde.log`). No test was written or edited in
this step.

## What shipped {#shipped}

| file | change |
|---|---|
| `src/refmatrix/memory_layout.py` | NEW. `FOLDERS`, `folder_for_type`, `savestate_dir`, `iter_memory_files`, `sort_savestates`, `iter_savestates`, `is_organised`, `MemoryLayoutError` |
| `src/refmatrix/ingest_gmd.py` | `collect_gmd_files(targets, *, as_memory=False)`: memory dirs expand through `iter_memory_files` |
| `src/refmatrix/daemon.py` | sync op, detached op, `prestage_hashes` op pass `as_memory` from their args |
| `src/refmatrix/cli.py` | `--prestage` daemon branch sends `as_memory`; no-daemon prestage and `_ingest_gmd_sync` pass it |
| `src/refmatrix/memory_index.py` | ungated `collect`; `Entry.id`; folder-first `Entry.kind`; dual hook reader; marker-gated id-keyed sidecar; carried prose; 25% budget refusal; content-line guard |

Signatures (final):

- `memory_layout.folder_for_type(mtype: str) -> str` (an unknown type raises `MemoryLayoutError`)
- `memory_layout.savestate_dir(memdir) -> Path`
- `memory_layout.iter_memory_files(memdir, *, skipped: list | None = None) -> Iterator[Path]`
- `memory_layout.sort_savestates(paths) -> list`; `memory_layout.iter_savestates(memdir) -> list`
- `memory_layout.is_organised(memdir) -> bool`
- `ingest_gmd.collect_gmd_files(targets, *, as_memory: bool = False) -> list[Path]`
- `memory_index.save_hooks(memdir, entries, *, dead: dict | None = None) -> None`
- `memory_index.render` / `write` / `check` / `load_hooks` / `parse_hooks`: signatures unchanged

## How each AC is met {#ac}

| AC | where | note |
|---|---|---|
| AC-1 | `memory_layout.py` | Dot-ness is judged on the path RELATIVE to the memdir (every real memdir is under `~/.claude/`). Order = top-level by name, then each sub-folder, which equals the old glob order on a flat-plus-`impressions/` dir. `#newest`: date, then datetime only when both carry a time (and the same tz-awareness), else mtime, then name. `is_organised` rejects JSON `true` (`True == 1`) |
| AC-2 | `collect_gmd_files` + five sites | The memdir's top-level `MEMORY.md` is still passed through so `skipped_index` keeps counting it (plan-5 #b-2 contract, `test_bridge_ingests_gmd_and_plain_files`). Other excluded `.md` files are counted and named on stderr |
| AC-3 | `memory_index.collect` | `iter_memory_files`, ungated |
| AC-4 | `parse_hooks`, `load_hooks`, `Entry.__init__`, `save_hooks`, `_dead_hooks` | Readers alias every path key to the linked file's `id` (or its stem when the file moved). The organised writer keys by id and keeps dead hooks under the key they were found under, reported on `out`. Un-organised writer unchanged |
| AC-5 | `_prose_lines`, `_carried_block`, `_render_organised`, `_write_organised` | Block = header + non-blank prose + a blank line; empty when there is no prose. Its chars and lines come off both budgets |
| AC-6 | `_write_organised`, `_named_count` | New content = inline entry links + the counts the pointer and fold lines stand for + carried prose |
| AC-7 | `Entry.kind` | folder in `FOLDERS` first, then HEAD's stem/frontmatter rules |
| AC-8/9 | `write`, `render` | Without the marker, HEAD's render, compaction and path-keyed sidecar, byte-identical to the goldens |

## Verification {#verification}

Run with `PYTHONPATH=$PWD/src` and the dev interpreter, `-B`:

- `workflow/review-output/plan26/26.1-green-index-layout.log`: `test_memory_layout.py`,
  `test_memory_index_layout.py`, `test_memory_index.py`, `test_memory_index_char_budget.py`
  passed 82 of 82.
- `workflow/review-output/plan26/26.1-green-bridge.log`: `test_memory_bridge.py` passed 17 of 17.
- `workflow/review-output/plan26/26.1-green-memory-family.log`: the memory family (see
  [[#family]]).

### Memory family {#family}

`tests/test_memory*.py`, `tests/test_ingest_gmd*.py`, `tests/test_save_state*.py` and
`tests/test_verb_parity.py` passed 423 of 423. There are no `test_handoff*` or `test_recall_state*`
files. The full suite was not run (the orchestrator scoped it out).

## Mutation table {#mutations}

The fix was committed first (`ebe749d`). For each mutation, the driver applied it, cleared
`__pycache__`, and ran the tests under `timeout 900` with `-x`. It then restored the file with
`git checkout` as a separate command and cleared `__pycache__` again. `git status --short src` was
empty after every restore. Logs are `workflow/review-output/plan26/26.1-mut-<name>.log`.

| mutation | killed by | failure |
|---|---|---|
| `collect` back to the old glob (spec) | `test_ac3_collect_sees_type_folders_in_an_unorganised_dir` | sees 2 of 8 |
| bridge walks with `rglob` (spec) | `test_ac2_in_process_bridge_skips_dot_dirs` | `x` ingested |
| organised sidecar keyed by path (spec) | `test_ac4_a_moved_file_keeps_its_curated_hook_in_an_organised_dir` | `KeyError: 'project_x'` |
| `Entry` hook lookup by path only | same AC-4 moved-file test | derived prose rendered |
| drop the carried block (spec) | `test_ac5_every_prose_line_is_carried_verbatim_in_order_before_the_entries` | header count 0 |
| count links only (spec) | `test_ac6_a_fold_is_not_a_loss_content_counting_lets_it_through` | refused, 9 of 30 |
| no 25% prose-budget refusal | `test_ac5_prose_that_leaves_under_a_quarter_of_the_budget_refuses_the_write` | index rewritten |
| no 50% content guard | `test_ac6_the_guard_refuses_when_under_half_the_content_would_remain` | 11 -> 6 lines written |
| **no lose-any-prose guard** | **SURVIVED** (82 passed) | known spec gap, [[#flags]] |
| dead hooks not kept | `test_ac4_a_dead_link_hook_is_kept_under_its_path_and_reported` | hook missing |
| marker gate always on | `test_ac6_no_guard_in_an_unorganised_dir` | returned 0, not 3 |
| `Entry.kind` ignores the folder | `test_ac7_kind_reads_the_folder_first[feedback/...]` | `project` |
| walk takes dot-dirs | `test_iter_memory_files_walks_type_folders_and_skips_dot_paths_and_non_memories` | `.hidden/y.md` yielded |
| unparseable marker read as False | `test_an_unreadable_or_foreign_marker_is_a_hard_error_naming_the_file[{not json]` | did not raise |
| date-only read as midnight | `test_same_date_one_side_date_only_mtime_decides_never_midnight` | order flipped |
| `created` used as the key | `test_created_is_never_part_of_the_key` | order flipped |
| no-daemon prestage without `as_memory` | `test_ac2_prestage_without_a_daemon_walks_the_same_set` | considered=4 |
| `--prestage` daemon call omits `as_memory` | `test_ac2_prestage_through_the_daemon_walks_the_same_set` | considered=4 |

## Flags {#flags}

- **No pseudocode node.** ADR-0005 #implementation says `@ch-alignment` derives the
  `memory_layout` pseudocode before 26.1 goes RED. There is no `pseudocode/` dir in the repo, so
  this was built from the ADR and the spec.
- **The lose-any-prose branch survives its mutation** (a known spec gap from RED). The render
  carries every prose line by construction, so no input reaches the branch. It stays as a check
  on the written text, not on the extraction.
- **`folder_for_type` raises on an unknown type.** 26.5 must catch it and report the file.
- **`.gmd` files in a memdir** are no longer walked on the memory path, because
  `iter_memory_files` yields `.md` only (ADR-0005). The r4 probe found no such files.
- **No version bump.** The release is 26.8's.

## Remedy r2: ch-bsd 26.1 b-1, s-1, s-2, s-3, m-1 {#remedy-r2}

rel: derives-from -> [[bsd-task26.1-layout-index-walk-8337368]]

TDD GREEN over the remedy RED commits `8fa7b63` (11 tests) and `26d620e` (the legacy cut-line
test), built from the amended spec (AC-2, AC-5, AC-6, `#rev-bsd-26-1`; `ce140aa`, `4fff5cc`) and
ADR-0005 `#newest`. Fix commit `238f060`. No test was written or edited in this step.

### What changed {#remedy-r2-changes}

| finding | where | change |
|---|---|---|
| b-1 (bug-192) | `memory_index.Entry.line` | never cut inside `](rel)`. The hook is shortened first, which gives HEAD's exact bytes whenever HEAD's cut fell inside the hook, so short-title goldens are unchanged. When the link alone is over `MAX_LINE_CHARS`, the hook is dropped and the title is shortened, keeping at least `TITLE_MIN_CHARS` (40). This changes marker-off bytes for long-title dirs only |
| b-1 | `memory_index._prose_lines` (organised path only) | any line starting `- [` is an entry, link or no link. HEAD's link-less cut lines are dropped and the memory is rendered again with its link |
| s-1 | `memory_index._write_organised` | the unreachable lose-any-prose branch is removed |
| m-1 | `memory_index._write_organised` | a render still over `max_chars` after the renderer's full fold refuses. The index and sidecar are untouched, the reason on `out` names the prose line count, and it returns 0 |
| s-2 | `memory_layout._SaveKey`, `sort_savestates` | one key, `(date, mtime, name)`, descending. The date is `updated`'s calendar date, or the mtime's local date when `updated` is missing or unreadable. `_cmp_newer` and `functools` are gone |
| s-3 | `memory_layout.iter_memory_files` | `skipped` also receives a symlinked sub-folder (the folder itself, never followed), a dangling `.md` symlink, any `.gmd`, and `.gmd` files under dot-dirs |
| s-3 | `ingest_gmd.collect_gmd_files(..., skipped=)`, `render_memory_skip_line` | with `skipped=`, the caller owns the report; without it, the shared line goes to stderr. The line gives the count of every skip and up to 20 names |
| s-3 | `daemon._skip_fields`, `_run_ingest_gmd_body(..., skipped=)` | the `ingest_gmd` op result, the empty-target result and the `ingest_gmd_start` reply carry `skipped` and `skipped_paths`. The `prestage_hashes` result carries `walk_skipped`, because its own `skipped` key was already taken |
| s-3 | `cli._ingest_gmd_sync`, `ingest-gmd --detach`, `--prestage` | each branch prints the shared skip line, daemon and in-process alike. `with_stats` gains `skipped`/`skipped_paths`. `--detach` no longer raises `KeyError` when the op returns without starting a job |

New or changed signatures:

- `memory_index.TITLE_MIN_CHARS = 40`
- `ingest_gmd.collect_gmd_files(targets, *, as_memory: bool = False, skipped: list | None = None) -> list[Path]`
- `ingest_gmd.render_memory_skip_line(skipped) -> str`
- `daemon._skip_fields(skipped: list | None) -> dict`
- `daemon._run_ingest_gmd_body(d, job_id, files, args, *, skipped: list | None = None) -> dict`

### Verification {#remedy-r2-verification}

Every run used `PYTHONPATH=$PWD/src` with the dev interpreter and `-B`.

- `workflow/review-output/plan26/26.1-r2-green.log`: the 12 RED tests plus 4 guards, 16 of 16.
- `workflow/review-output/plan26/26.1-r2-five-files.log`: `test_memory_layout.py`,
  `test_memory_index_layout.py`, `test_memory_index.py`, `test_memory_index_char_budget.py` and
  `test_memory_bridge.py`, 112 of 112.
- `workflow/review-output/plan26/26.1-r2-family.log`: `tests/test_memory*.py`,
  `tests/test_ingest_gmd*.py`, `tests/test_save_state*.py` and `tests/test_verb_parity.py`, 436 of
  436. The full suite was not run (out of scope).

### Mutation table (r2) {#remedy-r2-mutations}

All mutations ran against fix commit `238f060`, one at a time. The driver cleared `__pycache__`,
applied the mutation, cleared it again and ran with `-x`. Each restore was a `git checkout` in its
own command, followed by a `__pycache__` clear and a grep confirming the fix text was back.
`git status --short src` was empty after every restore. Logs are
`workflow/review-output/plan26/26.1-r2-mut-<name>.log`.

| mutation | killed by |
|---|---|
| link cut back to HEAD's whole-line cut | `test_b1_long_title_organised_render_is_stable_over_three_renders` |
| `- [` rule removed (back to `_is_entry_line`) | `test_b1_a_legacy_link_less_cut_line_is_dropped_and_re_rendered_with_its_link` |
| sort key back to the datetime rule (timed `updated` decides within the day) | `test_same_date_both_with_time_of_day_mtime_still_decides` |
| a `.gmd` skip left uncounted | `test_iter_memory_files_puts_every_dropped_shape_on_skipped` |
| op result without `skipped` | `test_s3_daemon_sync_op_returns_the_skip_count_to_the_caller` |
| over-budget organised write allowed | `test_m1_organised_write_refuses_when_a_full_fold_cannot_fit` |

All 6 were killed, with no survivors.

### Flags (r2) {#remedy-r2-flags}

- **A dropped hook is not kept in the sidecar.** When the link alone is over the cap, the line
  carries no hook. The next render then reads an empty hook from the index, and the index wins
  over the sidecar (`load_hooks`), so the entry's sidecar value becomes its derived prose. At HEAD
  a cut line had no `](`, so its sidecar hook was never overridden. The index shows no hook either
  way. The loss only shows if the title is later shortened. This is not fixed, because it would
  change the precedence for every dir.
- **An organised dir with zero prose also refuses over budget.** AC-6 says the write "refuses
  when even a full fold cannot fit", without exception. The reason then names "0 prose lines".
  Such a dir's index stops updating until feedback entries shrink. Marker-off dirs still write
  the over-budget index with `STILL OVER`.
- **bug-192's registry row** lives on `master`. It is left for the orchestrator to flip at merge.
