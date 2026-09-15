---
gmd: "0.1"
id: task-1.2-plan-1-deploy-runtime
title: "Task 1.2: upgrade --from-dev reinstalls from the install root and re-verifies"
tags: [task, plan-1]
metadata:
  node_type: task
  status: pending
  plan: plan-1-deploy-runtime
---

# Task 1.2: upgrade --from-dev reinstalls from the install root and re-verifies {#root}

> Plan: [[plan-1-deploy-runtime]]
> Status: Pending
> Depends on: 1.1

rel: part-of -> [[plan-1-deploy-runtime]]

## Requirements {#requirements}

- A fake `pip` (monkeypatched subprocess) that writes a `.pth` to the dev path makes `upgrade.run()` fail loudly; one that writes the install root passes.
- Templates no longer contain `pip install -e /Users/tholley/claude_tools/refmatrix`.

## Files to Create / Modify {#files}

- `src/refmatrix/upgrade.py:run()`: after `pip install -e {root}` call `runtime_identity()`; if `dev_tree` → raise `UpgradeError("editable target is <x>, expected <root>")` and print the fix.
- `src/refmatrix/templates/commands/save-state.md` + `.claude/commands/save-state.md` step 4: deploy = ff `~/refmatrix` + `rmx daemon restart --relaunch`; NEVER `pip install -e <dev tree>` into the deploy venv.

## Test Strategy (RED first) {#test-strategy}

tests/test_upgrade.py: `test_from_dev_refuses_foreign_editable(tmp_path, monkeypatch)`; template grep test in tests/test_hooks.py.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-1.2-plan-1-deploy-runtime.md`.
- Committed on branch `task-1.2-plan-1-deploy-runtime`; merged `--no-ff` to `master`.
