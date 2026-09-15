---
gmd: "0.1"
id: task-1.1-plan-1-deploy-runtime
title: "Task 1.1: runtime_identity + status surfaces"
tags: [task, plan-1]
metadata:
  node_type: task
  status: pending
  plan: plan-1-deploy-runtime
---

# Task 1.1: runtime_identity + status surfaces {#root}

> Plan: [[plan-1-deploy-runtime]]
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-1-deploy-runtime]]

## Requirements {#requirements}

- `runtime_identity()` on the dev venv → `dev_tree=False` (editable target == its own tree); on a fake site-packages whose `.pth` points elsewhere → `True`.
- `rmx daemon status` output contains `code:`; with `dev_tree` it contains `[DEV TREE]`.
- Hub status/alert JSON contains `dev_tree` per root.

## Files to Create / Modify {#files}

- `src/refmatrix/upgrade.py`: `def runtime_identity() -> dict` — reads `refmatrix.__file__`, the `__editable__*.pth` in the running interpreter's site-packages, `_install_root()`; `dev_tree = editable_target != install_root`.
- `src/refmatrix/cli.py`: `rmx --version --verbose` prints the dict; `daemon status` + `hub status` append `code: … [DEV TREE]` when true.
- `src/refmatrix/daemon.py` ping result gains `code_path`; `src/refmatrix/hub.py` status rows show it and the queues alert carries `dev_tree` per root.

## Test Strategy (RED first) {#test-strategy}

tests/test_upgrade.py: `test_runtime_identity_detects_foreign_editable_target(tmp_path, monkeypatch)`; tests/test_daemon_status_surface.py (CliRunner) asserts the `code:` line. No mocking of `runtime_identity` itself.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-1.1-plan-1-deploy-runtime.md`.
- Committed on branch `task-1.1-plan-1-deploy-runtime`; merged `--no-ff` to `master`.
