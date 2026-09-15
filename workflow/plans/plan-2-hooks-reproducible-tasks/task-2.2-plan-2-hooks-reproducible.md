---
gmd: "0.1"
id: task-2.2-plan-2-hooks-reproducible
title: "Task 2.2: install-hooks writes settings.json, records flags, gains --check"
tags: [task, plan-2]
metadata:
  node_type: task
  status: complete
  plan: plan-2-hooks-reproducible
---

# Task 2.2: install-hooks writes settings.json, records flags, gains --check {#root}

> Plan: [[plan-2-hooks-reproducible]]
> Status: Complete
> Depends on: 2.1

rel: part-of -> [[plan-2-hooks-reproducible]]

## Requirements {#requirements}

- `--apply --force` into a tmp project writes settings.json + rmx-hooks.json; a second `--check` is clean; editing one command by hand makes `--check` exit 1 and print the diff.
- Hand-authored non-rmx hooks in settings.json survive `--force`.

## Files to Create / Modify {#files}

- `src/refmatrix/hooks.py:_install_claude_hooks(..., scope="project")` target → `.claude/settings.json`; merge preserves non-rmx keys (`statusLine`, other tools' hooks).
- `hooks.record_flags(project_root, flags)` → `.claude/rmx-hooks.json`; `hooks.check(project_root) -> (ok: bool, diff: str)` re-renders from the recorded flags and compares the rmx-marked entries (order-insensitive per event).
- `src/refmatrix/cli.py:install_hooks`: new options `--check`, `--[no-]memory-hooks`, `--[no-]primer`, `--[no-]scan-prompt`, `--[no-]enforce`, `--composite-every`, `--[no-]precompact-checkpoint`; `--check` exits 1 with the diff.

## Test Strategy (RED first) {#test-strategy}

tests/test_hooks.py: `test_apply_then_check_roundtrip(tmp_path)`, `test_check_detects_hand_edit(tmp_path)`, `test_force_keeps_foreign_hooks(tmp_path)`; CliRunner for the flags.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-2.2-plan-2-hooks-reproducible.md`.
- Committed on branch `task-2.2-plan-2-hooks-reproducible`; merged `--no-ff` to `master`.
