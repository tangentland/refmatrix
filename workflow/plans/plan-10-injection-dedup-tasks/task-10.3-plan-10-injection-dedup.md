---
gmd: "0.1"
id: task-10.3-plan-10-injection-dedup
title: "Task 10.3: PreCompact clear, turn TTL, and a live re-measurement"
tags: [task, plan-10]
metadata:
  node_type: task
  status: cancelled (10.1 did not clear)
  plan: plan-10-injection-dedup
---

# Task 10.3: PreCompact clear, turn TTL, and a live re-measurement {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: cancelled (10.1 did not clear)
> Depends on: 10.2

rel: part-of -> [[plan-10-injection-dedup]]

## Requirements {#requirements}

- **PreCompact clears the ledger.** rmx already owns that hook; wire the clear there rather than inventing a signal.
- **A turn TTL re-promotes to full after N turns regardless of the ledger.** Claude Code has auto-compaction and context-editing paths that may never surface as a PreCompact this hook sees; a ledger trusting one signal is a guard that cannot fire when it matters ([[impression_bsd_guard_cannot_fire]]).
- Both resets are proven by driving the real caller, not by calling the helper: a test that exercises the clear function directly does not show the hook is wired ([[impression_bsd_tests_bypass_wiring]]).
- **The saving is re-measured live** with `rmx telemetry --context` before and after, same corpus, AFTER the fleet has been busy — never in the quiet minute following a restart ([[impression_bsd_cost_measured_idle]]).

## Files to Create / Modify {#files}

- modify `src/refmatrix/hooks.py` (PreCompact clear), `src/refmatrix/scan.py` / `stm.py` (TTL)
- modify `workflow/measurements/injection-overlap.md` (the before/after figures)

## Test Strategy (RED first) {#test-strategy}

`tests/test_injection_dedup.py` (extended):
- a PreCompact firing clears the ledger and the NEXT call renders full entries again
- an entry older than the TTL renders full even with the ledger intact and no PreCompact
- mutation check: deleting the PreCompact clear CALL SITE (not the function) turns the wiring test RED
- mutation check: an infinite TTL turns the TTL test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.3-plan-10-injection-dedup.md`.
- Committed on branch `task-10.3-plan-10-injection-dedup`; merged `--no-ff` to `master`.
