---
gmd: "0.1"
id: task-1.3-plan-1-deploy-runtime
title: "Task 1.3: Operate + memories"
tags: [task, plan-1]
metadata:
  node_type: task
  status: complete
  plan: plan-1-deploy-runtime
---

# Task 1.3: Operate + memories {#root}

> Plan: [[plan-1-deploy-runtime]]
> Status: Complete
> Depends on: 1.1, 1.2

rel: part-of -> [[plan-1-deploy-runtime]]

## Requirements {#requirements}

- `~/refmatrix/.venv/bin/python -c "import refmatrix; print(refmatrix.__file__)"` is under `~/refmatrix/src`.
- `rmx hub status` shows no `[DEV TREE]`; memories linted; MEMORY.md index updated.

## Files to Create / Modify {#files}

- `~/refmatrix/.venv/bin/python -m pip install -e ~/refmatrix --no-deps`; `rmx --version --verbose` shows `dev_tree=False`; `rmx daemon restart --relaunch`; hub restarts on handshake; verify every fleet daemon reports the deploy path.
- Memory: new `feedback_deploy_tree_is_the_runtime` (supersedes `feedback_rmx_binary_is_deploy`, amends `feedback_refmatrix_dev_deploy_split` + `reference_editable_venv_distinfo_lag`); fix `feedback_save_state_means_handoff` step 4 in place.

## Test Strategy (RED first) {#test-strategy}

Operational verification logged to workflow/review-output/plan-1-deploy.log; no unit test (environment task).

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-1.3-plan-1-deploy-runtime.md`.
- Committed on branch `task-1.3-plan-1-deploy-runtime`; merged `--no-ff` to `master`.
