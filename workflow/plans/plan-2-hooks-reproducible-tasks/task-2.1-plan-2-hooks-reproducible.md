---
gmd: "0.1"
id: task-2.1-plan-2-hooks-reproducible
title: "Task 2.1: Hook block options for the production hooks"
tags: [task, plan-2]
metadata:
  node_type: task
  status: complete
  plan: plan-2-hooks-reproducible
---

# Task 2.1: Hook block options for the production hooks {#root}

> Plan: [[plan-2-hooks-reproducible]]
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-2-hooks-reproducible]]

## Requirements {#requirements}

- Rendering with defaults equals the union of what settings.local.json + settings.json run in this repo today (minus the swallowed redirections).
- No generated memory-path command contains `2>/dev/null` or `|| true`.
- `precompact_checkpoint=False` drops the save-state entry; `enforce=False` drops the four enforcement entries.

## Files to Create / Modify {#files}

- `src/refmatrix/hooks.py:_claude_hook_block(refmatrix_root, primer=True, scan_prompt=True, memory_hooks=True, *, composite_every=3, precompact_checkpoint=True, stop_promote=True, resume_focus=15, enforce=None)`.
- PreCompact: `rmx focus summarize --promote` + `rmx memory recall --recent --since 1h …` + `rmx save-state --no-promote --no-sync -m "auto: pre-compact checkpoint"` (no redirection, no `|| true`).
- Stop: `focus summarize --promote` joins the background group; `focus hook --event say` unchanged.
- SessionStart(resume): `rmx focus context --top {resume_focus}` (loud).
- `enforce`: PreToolUse `enforce-test-to-file.sh` + `enforce-rmx-grep.sh`, PostToolUse `adr-gate.sh`, SessionStart p20-0 compile — emitted when `<project>/.claude/hooks/<script>` exists (auto) or forced.

## Test Strategy (RED first) {#test-strategy}

tests/test_hooks.py: `test_precompact_checkpoint_is_loud_and_no_sync`, `test_enforce_entries_follow_scripts_on_disk`, `test_no_memory_path_hook_is_silenced` (extends the existing loudness test to every rmx command).

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-2.1-plan-2-hooks-reproducible.md`.
- Committed on branch `task-2.1-plan-2-hooks-reproducible`; merged `--no-ff` to `master`.
