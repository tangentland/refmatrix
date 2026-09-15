---
gmd: "0.1"
id: impl-task-2.1-plan-2-hooks-reproducible
title: "Task 2.1 — the production hooks are generator options"
tags: [implementation-summary, plan-2]
metadata:
  node_type: implementation-summary
  task: task-2.1-plan-2-hooks-reproducible
---

# Task 2.1 — production hooks as generator options {#root}

rel: implements -> [[task-2.1-plan-2-hooks-reproducible]]

## What shipped {#shipped}

`hooks._claude_hook_block(..., composite_every=3, precompact_checkpoint=True, stop_promote=True, resume_focus=15, enforce=None, project_root=None)`:
- scan-prompt `--composite-every N`; PreCompact `rmx focus summarize --promote` (was missing `--promote` in the template — the 2026-07-06 leak) + `rmx save-state --no-promote --no-sync -m "auto: pre-compact checkpoint"`, loud; Stop `rmx focus summarize --promote`, loud; SessionStart(resume) `rmx focus context --top N`, loud.
- Memory bridge catch-up is now its own SessionStart entry `rmx ingest-gmd --as-memory --detach '<memdir>'` (loud) instead of a swallowed member of the sync/primer background group; `ingest-gmd --detach` without a daemon fails with a message instead of a 25 s foreground ingest.
- `_add_enforce_entries`: cat-herder `enforce-test-to-file.sh`, `enforce-rmx-grep.sh`, `adr-gate.sh`, p20-0 compile — emitted when the script exists under the project (or forced), byte-identical to the template's commands so an onboarded project's file matches.
- `_RMX_HOOK_SIGNATURES` extended so `--force` and `--check` manage the new entries.

## TDD record {#tdd}

RED `workflow/review-output/pytest-plan2-RED.log` (16 failed); GREEN `pytest-plan2-GREEN.log`.
