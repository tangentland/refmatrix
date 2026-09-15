---
gmd: "0.1"
id: impl-task-2.3-plan-2-hooks-reproducible
title: "Task 2.3 — this repo migrated to generated hooks; drift is a test failure"
tags: [implementation-summary, plan-2, operations]
metadata:
  node_type: implementation-summary
  task: task-2.3-plan-2-hooks-reproducible
---

# Task 2.3 — migrate this repo, guard it {#root}

rel: implements -> [[task-2.3-plan-2-hooks-reproducible]]

## What was done {#done}

- Deployed 0.67.0 (`~/refmatrix` ff → relaunch, daemon pid 53244; hub kickstarted).
- `rmx install-hooks --check` before: exit 1 ("no rmx-hooks.json"). `rmx install-hooks --apply --force --no-briefing`: wrote `.claude/settings.json` (rmx block + search hooks + enforcement entries), stripped the rmx entries from `.claude/settings.local.json` (per-machine keys kept), recorded `.claude/rmx-hooks.json`. `--check` after: exit 0.
- `tests/test_repo_hooks_in_sync.py` passes against the committed files; any hand edit to the rmx block now fails the suite.
- The four formerly hand-authored hooks (composite-every 3, PreCompact promote + checkpoint, resume focus context) are now generator output; the PreCompact checkpoint no longer swallows its output and no longer runs a synchronous bridge.

## Follow-ups {#followups}

- Claude Code must be restarted for the merged `.claude/settings.json` to load.
- `install-hooks --apply --force` also refreshed `~/.claude/hooks/rmxgrep-rewrite.py` from the vendored render (it differed); the vendored copy is the source of truth per constitution X.
