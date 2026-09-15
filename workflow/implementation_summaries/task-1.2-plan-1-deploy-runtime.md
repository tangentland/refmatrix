---
gmd: "0.1"
id: impl-task-1.2-plan-1-deploy-runtime
title: "Task 1.2 — upgrade --from-dev verifies the editable target; templates stop teaching the mistake"
tags: [implementation-summary, plan-1]
metadata:
  node_type: implementation-summary
  task: task-1.2-plan-1-deploy-runtime
---

# Task 1.2 — verify after install; fix the templates {#root}

rel: implements -> [[task-1.2-plan-1-deploy-runtime]]

## What shipped {#shipped}

- `upgrade.verify_editable(root)` — after `install_fn`, the venv's editable marker must point under `root`; otherwise `UpgradeError("editable target is … expected …")` with the exact fix command. The install step stays injectable; the verify step is not.
- `templates/commands/save-state.md` (+ this repo's copy) step 4: deploy = ff + `rmx daemon restart --relaunch`, verify `rmx version -v`; explicit NEVER-pip-the-dev-tree line.
- Memories: `feedback_deploy_tree_is_the_runtime` (supersedes `feedback_rmx_binary_is_deploy`, amends two others); `feedback_save_state_means_handoff` step 4 rewritten in place.

## TDD record {#tdd}

- RED in `pytest-plan1-t1.1-RED.log` (`test_verify_editable_*`, `test_upgrade_from_dev_verifies_editable_after_install`); GREEN in `pytest-plan1-t1.1-GREEN.log` + `pytest-plan1-t1.2.log` (template guard test).
- Test-sequencing fix: the refused upgrade already fast-forwards (git before pip); the test bumps dev again before the good install.
