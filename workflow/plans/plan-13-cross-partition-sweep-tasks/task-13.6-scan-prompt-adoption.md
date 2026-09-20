---
gmd: "0.1"
id: task-13.6-scan-prompt-adoption
title: "Task 13.6: adopt the sweep into the always-on hook, or decline with a number"
tags: [task, plan-13, scan-prompt, hooks, cost]
metadata:
  node_type: task
  status: pending
  plan: plan-13-cross-partition-sweep
  gate: after PASS
---

# Task 13.6: scan-prompt adoption {#root}

> Plan: [[plan-13-cross-partition-sweep]]
> Status: Pending — blocked on [[task-13.5-gate-1-measurement]] reading PASS
> Depends on: [[task-13.5-gate-1-measurement]]

rel: part-of -> [[plan-13-cross-partition-sweep]]
rel: depends-on -> [[task-13.5-gate-1-measurement]]
rel: reinforces -> [[project_grep_learn_wall_and_queue]]
rel: reinforces -> [[feedback_daemon_call_retries_multiply_timeouts]]

## Requirements {#requirements}

- `scan-prompt` fires on EVERY prompt. Adoption is a product-latency decision, and this project has
  a live scar: `rmx grep` walled at 30 s on 17% of calls because four call sites inherited
  `daemon.call`'s `retries=2` (bug-049). The sweep's legs serialize on `_store_lock`, so its cost
  is the SUM of three legs.
- **The p95 is measured on the installed hook path, not modelled.** Run the installed hook command
  verbatim (`CLAUDE_PROJECT_DIR=… bash -c '<hook string>'`) and read the elapsed from
  `.refmatrix/query.log` / `cli.log` over a real prompt sample — the telemetry is now honest about
  outcomes (bug-052), so `empty` and `consumer-closed` rows will not be mistaken for failures.
- A hook that misses its deadline DROPS legs and still answers. The hook never holds the turn for
  the store ([[impression_bsd_partial_bound_enumerate_surfaces]]).
- **Declining is a valid outcome with a number attached**: if the measured p95 exceeds the budget,
  `scan-prompt` keeps its current path and the sweep stays an explicit surface (`rmx sweep`,
  `rmx context --sweep`). Record the number either way.
- Hook config is GENERATED (`hooks.py` / `search_hooks.py`); any change goes through the generator
  and `rmx install-hooks --check` must stay clean ([[claude#permissions]] and the repo's hook rule).

## Acceptance criteria {#acceptance}

- A measured p95 on the installed hook path, before and after, on the same prompt sample.
- Budget: the sweep's added p95 is ≤ 250 ms over the current `scan-prompt` p95, or adoption is
  declined. The threshold is stated HERE, before the measurement, not chosen after it.
- If adopted: `rmx install-hooks --check` clean, and the generated hook carries the deadline and
  `retries=0` explicitly.
- If declined: `docs/PERFORMANCE.md` records the measured cost and the decision, and the sweep
  remains reachable by hand.

## Files {#files}

- modify `src/refmatrix/hooks.py` and/or `search_hooks.py` (only if adopted)
- modify `src/refmatrix/scan.py` (the scan-prompt composition path — confirm the module at write
  time)
- modify `docs/PERFORMANCE.md`
- create `tests/test_scan_prompt_sweep_budget.py`

## Test strategy (RED first) {#test-strategy}

1. `test_the_hook_path_carries_a_deadline_and_no_retries` — asserted on the GENERATED hook string,
   not on a hand-written one.
2. `test_a_sweep_that_exceeds_the_budget_drops_legs_and_still_answers` — the hook returns context,
   with `dropped` legs named, under an artificially small deadline.
3. `test_installed_hooks_match_generated_after_the_change` — the existing repo gate, which skips
   correctly in a relocated checkout since bug-054 (merged `8e6bcaa`, released 0.72.4).
4. `test_declining_adoption_leaves_the_hook_byte_identical` — the negative path is tested too, so
   "we declined" cannot silently change the hook.

**Mutations:** drop the deadline from the generated hook (kills 1); await a slow leg instead of
dropping it (kills 2).
