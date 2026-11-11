---
gmd: "0.1"
id: impl-task-bug199-200-repair-index-and-brief-old-scope
title: "bug-199/200 GREEN: the cut-hook repair rewrites the affected index lines; brief refuses recall's scope"
tags: [implementation-summary, bug-199, bug-200, memory, hooks, repair, index, brief, verbs, plan-26]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-10
---

# bug-199/200 GREEN: repair rewrites the index, brief refuses `scope` {#root}

RED `771117c` had 13 failing tests. GREEN `e473610` passes all 13. Branch
`task-bug199-200-repair-index-and-brief-old-scope`.

rel: implements -> [[bug_registry]]
rel: implements -> [[bug_registry]]
rel: amends -> [[impl-task-26.6-compile-subject-hygiene]]
rel: depends-on -> [[impl-task-bug197-198-compile-status-and-brief-scope]]

## What changed {#changes}

| File | Change |
|------|--------|
| `src/refmatrix/memory_index.py` | `_repaired_index` rewrites the hook part of each affected MEMORY.md line. `repair_cut_hooks` backs MEMORY.md up into the sidecar's backup dir and writes it atomically after the sidecar. It prints each rewritten (or would-rewrite) line. `_with_hook` is now the one hook placement, shared by `Entry.line` and the rewrite. `_split_entry_line` is now the one index-line split, read by `_index_hook_records` and the rewrite. `_atomic_write_text` is the atomic write that `_store_sidecar` now calls; it keeps the file's mode. |
| `src/refmatrix/verbs.py` | `memory`: a non-None `scope` with `action="brief"` raises `VerbArgsError` naming `scope` and `compile_scope`, before any daemon call. `Verb.run`, the MCP path, reaches the same check. The `scope` schema description now says brief refuses it. |
| `workflow/implementation_summaries/task-26.6-compile-subject-hygiene.md` | Amended at `#rm-one-corpus` and in the "No `--scope` flag" note. They no longer say `scope` is forwarded for brief. |

## Signatures {#signatures}

- `memory_index._with_hook(link_part: str, hook: str) -> str | None`
- `memory_index._split_entry_line(line: str) -> tuple[str, str, str] | None`
- `memory_index._atomic_write_text(memdir: Path, name: str, text: str) -> None`
- `memory_index._repaired_index(memdir: Path, new: dict, changed: set) -> tuple[bytes, str, list] | None`
- `memory_index.repair_cut_hooks(memdir, *, apply=False, restores=None, out=None) -> int` (unchanged)

## Design {#design}

- **Only the affected lines change.** A line is affected when its link, or the memory id its
  link points at, is a key the repair dropped or restored. Its new hook is what `Entry` would
  read from the new sidecar alone: the path key, then the id, then `_first_prose`. `_with_hook`
  places it with the renderer's own cut. The link part, every other line, and every line ending
  stay byte-identical. Hand edits elsewhere survive, and no whole-index re-render meets
  `write`'s guards.
- **Order on apply.** The backup dir is created. The sidecar and (when any line changes)
  MEMORY.md are copied into it and read back. Then the sidecar is written, then the index. If
  the backup fails, nothing is written. If the index write fails after the sidecar write, the
  repair refuses by name and points at the sidecar backup. The stale lines would win the next
  `write` back.
- **Dry-run** prints `would rewrite MEMORY.md line <rel>` and the count. It writes nothing.
- An index that is not valid UTF-8 is refused (`RepairError`). It is never rewritten with
  replacement characters.

## Verification {#verification}

| Run | Log | Result |
|-----|-----|--------|
| RED files + `test_memory_hook_repair.py` | `bug199-200-green.log` | 55 passed |
| Wide (RED files, `test_memory*`, `test_save_state*`, `test_brief*`, `test_bug19*`, `test_bug200*`, `test_verb_parity`) | `bug199-200-green-wide.log` | 666 passed, 1 failed |
| bug-127 rerun ×2 | `bug199-200-green-bug127-{1,2}.log` | 3 passed, 1 failed each |
| bug-127 at RED `771117c` (src stashed) | `bug199-200-green-bug127-at-red.log` | same test, same `E` line |
| after the mutations were restored | `bug199-200-green-post-mut.log` | 55 passed |

The one failure is `tests/test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon`:
`_duckdb.IOException: Could not set lock on file ".../catalog.A.duckdb": Conflicting lock`.
It is pre-existing bug-127 (open). Its normalised `E` line is identical at the RED baseline.

## Mutations {#mutations}

Each mutation ran from the committed GREEN. Each was restored with `git checkout` in its own
command and checked by grepping for the fix, with `__pycache__` cleared.

| # | Mutation | Result | Log |
|---|----------|--------|-----|
| M1 | index not rewritten on apply | killed (8 failed) | `bug199-200-green-mut-M1.log` |
| M2 | whole-index `render()` instead of the line rewrite | killed (8 failed) | `bug199-200-green-mut-M2.log` |
| M3 | MEMORY.md not backed up | **survived** (35 passed) | `bug199-200-green-mut-M3.log` |
| M4 | brief accepts `scope` again | killed (5 failed) | `bug199-200-green-mut-M4.log` |

M2 is killed because `render()` still reads the stale index through `load_hooks`, so the cut
wins, not by the hand-edit guard.

## Open items for review {#open}

- **M3 survives: a test gap** for `@ch-test-engineer`. No test asserts that the MEMORY.md
  backup exists or equals the pre-apply index. The code writes and reads it back
  (`repair_cut_hooks`, `backups`).
- bug-200 m-2 (the faked `--compile` test / mock registry) belongs to the test side and the
  RED commit. This GREEN does not touch it.
- `workflow/bug_registry.md` statuses for bug-199/200 are left for after ch-bsd.

## Test pass: M3 closed, bug-200 m-2 confirmed {#tests-m3}

rel: evidence-for -> [[#mutations]]

- **M3 killed.** `tests/test_bug199_repair_rewrites_index.py::test_apply_backs_the_pre_apply_index_up_beside_the_sidecar`
  (flat + organised) runs the real `--repair-cut-hooks --apply` with `RMX_HOME` at tmp.
  It asserts that the one dir under `backups/memory-hooks/` (named `<project>-<ts>` by
  `_repair_backup_dir`) holds a `MEMORY.md` byte-equal to the pre-apply index, next to a
  byte-equal sidecar, and that the path is printed. Under M3 (the `backups.append` of
  `INDEX_NAME` dropped) 2 failed and 35 passed: only the new test fails
  (`bug199-200-m3-red.log`). The source was restored by `git checkout`, `__pycache__`
  cleared, the fix grepped back at `memory_index.py:1150`, and `git status --short src` was
  empty. Green: 57 passed across the four bug-198/199/200 files plus
  `test_memory_hook_repair.py` (`bug199-200-m3-green.log`).
- **bug-200 m-2 was already closed at the RED commit (771117c), using the real-store option.**
  The scope-blind fakes (`compile_memories` and `_read_store` -> `object()`) were deleted.
  `tests/test_bug200_brief_compile_real_daemon.py` drives the real CLI, plan, verb and a
  spawned daemon under a short mkdtemp root. A plan/brief scope disagreement makes it exit 1
  (`bug199-200-red-mut1.log`, `-mut2.log`). The routing recorders left in
  `test_bug198_brief_compile_scope.py` had no mock-registry row, so one was added.

## Remedy r1 RED: ch-bsd r1 #s-1, #s-2, #m-1 {#remedy-r1-red}

rel: derives-from -> [[bsd-bug199-200-r1-30c35a9#s-1]]
rel: derives-from -> [[bsd-bug199-200-r1-30c35a9#s-2]]
rel: derives-from -> [[bsd-bug199-200-r1-30c35a9#m-1]]

The tests are in `tests/test_bug199_r2_remedy.py`. They rebuild the setups of the auditor's
probe B on the shared fixtures; they do not import the probe. `stale` runs every case in both
layouts (flat and organised). No `src/` change is in this commit.
`bug199-r2-red.log` shows 11 failed at HEAD `40be640`, each for the reason the finding names.

- **#s-1:** a line is rewritten only when its current hook is what the OLD sidecar value
  renders to. Otherwise it is kept, and the output names it with `kept` and `hand`.
  - `test_s1_a_drop_keeps_a_hand_edit_on_the_affected_line_and_says_so`: the drop keeps the
    hand edit and does not report the line as rewritten. The hand edit also survives the
    next `write`.
  - `test_s1_a_restore_keeps_a_hand_edit_on_the_affected_line_and_says_so`: the same
    contract for a `--restore`, as the team-lead brief sets it. The auditor's alternative
    (replace and say so) would fail this test.
  - `test_s1_a_rendered_line_is_still_rewritten_beside_a_kept_hand_edit`: in one apply the
    hand-edited line is kept and the rendered line is rewritten to the restore. Both survive
    the next `write`. A fix that stops rewriting fails here.
- **#s-2:** on an index-write failure the sidecar goes back to its original bytes. Exit is
  non-zero. Sidecar and index both equal their pre-apply bytes. The sidecar keeps its mode, and
  no stray file is left in the memdir. The message says nothing was changed and names the one
  backup dir.
  - `test_s2_a_real_index_write_failure_puts_the_sidecar_back`: a real fault. The tmp
    `MEMORY.md` gets `UF_IMMUTABLE`, so the rename fails with EPERM. The test runs the real
    entry point in a child process.
  - `test_s2_an_injected_index_write_failure_puts_the_sidecar_back`: in-process. The
    `_atomic_write_text` wrapper raises ENOSPC for `INDEX_NAME` only. It is registered in
    `workflow/test_mock_registry.md` as a permanent fault injection.
- **#m-1:** a `--restore` keyed by a moved file's OLD path rewrites the line that links the
  new path. The restore survives the next `write`, and no sidecar value is left holding the
  cut.
  - `test_m1_a_restore_keyed_by_a_moved_files_old_path_rewrites_its_line`. The id-keyed form
    is already covered by the organised cases in `test_bug199_repair_rewrites_index.py`.

**Can be passed.** A scratch copy of `src/` with the auditor's three fixes passed all 48 tests
across `test_bug199_r2_remedy.py`, `test_bug199_repair_rewrites_index.py` and
`test_memory_hook_repair.py` (`bug199-r2-fixsim.log`). The three fixes are:

- the old-render check in `_repaired_index`;
- `changed |= {_id_of_link(...)}`;
- writing `raw` back on an index-write failure.

That copy was a scratchpad check only, never committed. The not-covered item: a rollback that
itself fails, which the auditor asked to have named, has no test.
