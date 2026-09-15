---
gmd: "0.1"
id: task-6.5-plan-6-deferrals-docs-benchmark
title: "Task 6.5: The rewriter hook stops baking the generator's tree (bug-008)"
tags: [task, plan-6]
metadata:
  node_type: task
  status: pending
  plan: plan-6-deferrals-docs-benchmark
---

# Task 6.5: The rewriter hook stops baking the generator's tree (bug-008) {#root}

> Plan: [[plan-6-deferrals-docs-benchmark]]
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-6-deferrals-docs-benchmark]]
rel: motivates -> [[bug-registry#registry]]

## Context {#context}

bug-008 (recurring, seen 2× on 2026-09-14): `~/.claude/hooks/rmxgrep-rewrite.py` is USER-GLOBAL but
`search_hooks.render_scripts` bakes `RMXGREP = "<generator tree>/bin/rmxgrep"` into it, so any
`rmx install-hooks --apply` run from the dev venv (a test without the `RMX_CLAUDE_HOOKS_DIR` redirect,
an audit probe in a throwaway project) overwrites the live hook with dev-tree paths. `--check` is the
only tripwire today.

## Requirements {#requirements}

- The rendered rewriter contains NO absolute path into any refmatrix tree: at runtime it resolves
  `rmxgrep` / `rmxrg` from the tree of the `rmx` on PATH (`shutil.which("rmx")` → its `bin/`), falling
  back to `~/bin` siblings; a unit test renders the script and asserts no `/refmatrix/bin/` literal.
- `install_search_hooks(apply=True)` REFUSES to write the user-global hooks dir when
  `upgrade.runtime_identity()["venv_tree"]` is not the tree that owns the `rmx` on PATH (prints the
  two trees and the `RMX_CLAUDE_HOOKS_DIR` escape); a test asserts the refusal from a foreign tree.
- `rmx install-hooks --check` stays clean after a deploy regen; bug-008 row → `fixed`.

## Files to Create / Modify {#files}

- `src/refmatrix/search_hooks.py`: `render_scripts` (runtime resolution), `install_search_hooks` (guard).
- `tests/test_search_hooks.py`: render assertion + foreign-tree refusal.
- `workflow/bug_registry.md` (bug-008 → fixed), `workflow/deferral_registry.md` (graduation log row).

## Test Strategy (RED first) {#test-strategy}

tests/test_search_hooks.py::test_rewriter_bakes_no_tree_path, ::test_install_refuses_user_global_dir_from_a_foreign_tree.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-6.5-plan-6-deferrals-docs-benchmark.md`.
- Committed on branch `task-6.5-plan-6-deferrals-docs-benchmark`; merged `--no-ff` to `master`.
