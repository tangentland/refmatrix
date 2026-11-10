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
