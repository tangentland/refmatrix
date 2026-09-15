---
gmd: "0.1"
id: task-2.3-plan-2-hooks-reproducible
title: "Task 2.3: Migrate this repo and guard it in CI"
tags: [task, plan-2]
metadata:
  node_type: task
  status: complete
  plan: plan-2-hooks-reproducible
---

# Task 2.3: Migrate this repo and guard it in CI {#root}

> Plan: [[plan-2-hooks-reproducible]]
> Status: Complete
> Depends on: 2.2

rel: part-of -> [[plan-2-hooks-reproducible]]

## Requirements {#requirements}

- `rmx install-hooks --check` clean in this repo; the repo test passes; settings.local.json contains no rmx-marked hooks; Claude Code restarted picks up the merged file.

## Files to Create / Modify {#files}

- Run `rmx install-hooks --claude --apply --force` (dev venv via `.venv-eval/bin/python -m refmatrix.cli`… NO — use the deployed `rmx` after plan 1 deploy) in this repo; strip the rmx block from `.claude/settings.local.json`; commit settings.json + rmx-hooks.json.
- tests/test_repo_hooks_in_sync.py: `hooks.check(Path(__file__).parents[1])` is ok (skips if `.claude/rmx-hooks.json` absent, i.e. not this repo).
- Docs: README hooks table lists every generated event; `docs/hooks/intuition-style-hooks.md` points at install-hooks as the generator.

## Test Strategy (RED first) {#test-strategy}

tests/test_repo_hooks_in_sync.py (real files, no mocks).

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-2.3-plan-2-hooks-reproducible.md`.
- Committed on branch `task-2.3-plan-2-hooks-reproducible`; merged `--no-ff` to `master`.
