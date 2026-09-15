---
gmd: "0.1"
id: impl-task-1.3-plan-1-deploy-runtime
title: "Task 1.3 — operate: deploy venv re-pointed, fleet relaunched, memories corrected"
tags: [implementation-summary, plan-1, operations]
metadata:
  node_type: implementation-summary
  task: task-1.3-plan-1-deploy-runtime
---

# Task 1.3 — operate + memories {#root}

rel: implements -> [[task-1.3-plan-1-deploy-runtime]]

## What was done {#done}

- `git -C ~/refmatrix pull --ff-only origin master` → 8aa4cfb; `~/refmatrix/.venv/bin/python -m pip install -e ~/refmatrix --no-deps` → `.pth` = `/Users/tholley/refmatrix/src`.
- `rmx version -v`: `code: /Users/tholley/refmatrix/src/refmatrix/__init__.py`, no `[DEV TREE]`.
- `rmx daemon restart --relaunch` for refmatrix (32630→48422), then cliquedb, cliquet, thiquet, viascope, atldb, global — every one verified `version=0.66.3` + `code:` under `~/refmatrix/src` (`workflow/review-output/plan-1-fleet-relaunch.log`). Hub kickstarted (pid 48432). `rmx hub status` shows 0 DEV TREE flags. orderly left to plan 4.4 (manual unsupervised daemon).
- Memories: `feedback_deploy_tree_is_the_runtime` written (supersedes `feedback_rmx_binary_is_deploy`; amends `feedback_refmatrix_dev_deploy_split`, `reference_editable_venv_distinfo_lag`, `feedback_save_state_means_handoff` — the latter's step 4 rewritten in place). MEMORY.md indexed.

## Evidence {#evidence}

`workflow/review-output/plan-1-fleet-relaunch.log`; `rmx hub status` at 19:43.
