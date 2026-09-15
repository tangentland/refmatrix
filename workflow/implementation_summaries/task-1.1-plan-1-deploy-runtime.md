---
gmd: "0.1"
id: impl-task-1.1-plan-1-deploy-runtime
title: "Task 1.1 — runtime_identity + status surfaces"
tags: [implementation-summary, plan-1]
metadata:
  node_type: implementation-summary
  task: task-1.1-plan-1-deploy-runtime
---

# Task 1.1 — runtime_identity + status surfaces {#root}

rel: implements -> [[task-1.1-plan-1-deploy-runtime]]

## What shipped {#shipped}

- `upgrade.runtime_identity(prefix=None, import_file=None)` → `{version, import_path, code_root, venv_tree, editable_target, dev_tree}`; helpers `_tree_root`, `venv_prefix`, `editable_target` (reads pip's path-style `__editable__.refmatrix*.pth`).
- `rmx version [-v]` command; `_print_code_identity` shared line `code: <path>  [DEV TREE]`.
- `daemon._op_ping` returns `code_path` + `dev_tree` (what the daemon process imported).
- `rmx daemon status` prints the daemon's `code:` line from its ping; `rmx hub status` flags `[DEV TREE]` per root via `hub._daemon_identity`; `hub._annotate_identity` stamps `dev_tree`/`code_path` on queue rows so the `global:queues` alert carries it.

## TDD record {#tdd}

- RED: `workflow/review-output/pytest-plan1-t1.1-RED.log` — 11 failed (identity, verify, version, ping, status, hub rows).
- GREEN: `workflow/review-output/pytest-plan1-t1.1-GREEN.log` — 16 passed.
- Mutation: identity is computed from injectable prefix/import paths on fake trees; no monkeypatch of `runtime_identity` in the identity tests (surface tests patch it as an external input to the CLI, registered in the mock registry).

## Files {#files}

`src/refmatrix/upgrade.py`, `src/refmatrix/cli.py`, `src/refmatrix/daemon.py`, `src/refmatrix/hub.py`, `tests/test_upgrade.py`, `tests/test_runtime_identity_surface.py`.
