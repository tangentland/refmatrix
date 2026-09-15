---
gmd: "0.1"
id: impl-task-2.2-plan-2-hooks-reproducible
title: "Task 2.2 — install-hooks writes settings.json, records flags, gains --check"
tags: [implementation-summary, plan-2]
metadata:
  node_type: implementation-summary
  task: task-2.2-plan-2-hooks-reproducible
---

# Task 2.2 — one target, recorded flags, a check {#root}

rel: implements -> [[task-2.2-plan-2-hooks-reproducible]]

## What shipped {#shipped}

- Project-scope target is the committed `.claude/settings.json` (rmx block + search hooks); `settings.local.json` keeps per-machine keys and has its legacy rmx entries stripped on apply so nothing fires twice.
- `hooks.record_flags` → `.claude/rmx-hooks.json` `{version, flags}`; `hooks.render_managed(project_root, flags)`; `hooks.check(project_root) -> (ok, diff)` compares the rmx-managed `(event, matcher, command)` sets.
- CLI: `rmx install-hooks --check` (exit 1 + diff on drift), `--[no-]memory-hooks`, `--[no-]primer`, `--[no-]scan-prompt`, `--[no-]enforce`, `--composite-every N`, `--[no-]precompact-checkpoint`, `--[no-]stop-promote`, `--resume-focus N`. `install_hooks` resolves the root via `_root()` instead of opening a store.

## TDD record {#tdd}

Same RED/GREEN logs as 2.1 (apply/check roundtrip, hand-edit detection, missing-entry detection, foreign-hook preservation, legacy strip, CLI exit codes).
