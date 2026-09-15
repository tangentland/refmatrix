---
gmd: "0.1"
id: impl-task-6.2-plan-6-deferrals-docs-benchmark
title: "Task 6.2 — CLI tree + hooks table are rendered from the code"
tags: [implementation-summary, plan-6]
metadata:
  node_type: implementation-summary
  task: task-6.2-plan-6-deferrals-docs-benchmark
---

# Task 6.2 — the docs stop hand-drawing the CLI {#root}

rel: implements -> [[task-6.2-plan-6-deferrals-docs-benchmark]]

## What shipped {#shipped}

- `scripts/gen-cli-tree.py`: walks `refmatrix.cli.main` (click) into a box tree with each command's first help line, and renders the default `hooks._claude_hook_block` as an Event / Matcher / Command table (hook env prefix stripped, store path → `<project>/`, curated memory dir → `~/.claude/projects/<slug>/memory`, enforcement entries omitted because they depend on which scripts a project has on disk). Both land between `<!-- cli-tree:start/end -->` in `docs/ARCHITECTURE.md` and `<!-- hooks-table:start/end -->` in `README.md`. `--check` prints a unified diff and exits 1; missing markers raise `MarkerError` (never a silent skip).
- `docs/ARCHITECTURE.md` `{#cli-hook-surface}`: the hand-drawn tree (30 lines, no `hub` / `focus` / `bus` / `task` / `schedule` / `refine` / `curator` / `pairs` / `taxonomy`) is replaced by the render (199 visible commands, 6 hidden aliases named). `README.md`: the hooks prose row keeps its summary; the per-event command table follows it.
- `tests/test_docs_generated.py` (7 tests): each section equals its render; every visible click command appears and no hidden alias does; a tiny synthetic click tree renders with nesting + one-line help; every generator event is a table row with no home path; `--check` sees a hand edit and `apply` repairs it; missing markers fail loud.

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-6.2-6.3-red.log` (11 failed: no script, no markers, no artifact). GREEN `pytest-task-6.2-green.log` (8 passed incl. the existing `test_docs_hooks_target.py`). Mutations `pytest-task-6.2-mutation.log`: (A) one hand-edited tree line (`daemon` → `deamon`) fails `test_cli_tree_section_equals_its_render` + the check-mode test; (B) the generator dropping group children (`if isinstance(cmd, click.Group)` → `if False`) fails 4 of 7.

## Regeneration rule {#rule}

Add a command or a hook → `.venv-eval/bin/python scripts/gen-cli-tree.py` → commit the two docs. The dev interpreter, not `rmx`, so the tree is the tree being committed.

## Not in scope {#not}

The hooks table shows the generator DEFAULTS; a project's installed file (which may carry `enforce` entries and `--composite-every` variants) is proven by `rmx install-hooks --check`, not by the README.
