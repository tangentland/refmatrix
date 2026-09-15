---
gmd: "0.1"
id: task-8.2-plan-8-derived-coverage-notes
title: "Task 8.2: Verb, daemon op, CLI + MCP adapters, parity"
tags: [task, plan-8]
metadata:
  node_type: task
  status: complete
  plan: plan-8-derived-coverage-notes
---

# Task 8.2: Verb, daemon op, CLI + MCP adapters, parity {#root}

> Plan: [[plan-8-derived-coverage-notes]]
> Status: Complete
> Depends on: 8.1

rel: part-of -> [[plan-8-derived-coverage-notes]]

## Requirements {#requirements}

- Capability is a VERB first ([[project_verbs_layer_antidrift]]): the `rmx_memory` verb gains a `brief` action; the CLI `rmx memory brief` and the MCP tool are thin adapters that render only.
- The derivation writes rows, so the write half goes through a daemon `_op_` and the `_store(write)` control point ([[feedback_store_calls_via_daemon]], [[project_write_control_point]]). No CLI path opens `Store()` on the active slot.
- Rendering: default table, `--gmd`, `--json`. Filters: `--class`, `--limit`. Read paths use the lock-free replica ([[project_replica_read_audit]]).
- The existing verb-parity test must cover the new action with its FULL parameter set — an existence check that the action name appears on both surfaces is not a parity gate ([[impression_bsd_existence_check_tests]]: plan-3's parity test excluded every `memory_recall` param and hid a `k` default mismatch).

## Files to Create / Modify {#files}

- modify `src/refmatrix/brief.py` (read/write entry points)
- modify `src/refmatrix/verbs.py`, `src/refmatrix/daemon.py`, `src/refmatrix/cli.py`

## Test Strategy (RED first) {#test-strategy}

`tests/test_brief_surfaces.py`:
- the verb returns the same payload the CLI renders and the same the MCP tool returns, compared field-by-field over the full parameter set (assert the compared-key count equals the parameter count — a parity test that compares a subset is not one)
- the write path is dispatched through the daemon op; a test that the CLI never constructs `Store()` directly
- `--json` output validates against the declared schema
- mutation check: deleting the daemon-op dispatch line turns the wiring test RED ([[impression_bsd_tests_bypass_wiring]])

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-8.2-plan-8-derived-coverage-notes.md`.
- Committed on branch `task-8.2-plan-8-derived-coverage-notes`; merged `--no-ff` to `master`.
