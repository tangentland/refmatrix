---
gmd: "0.1"
id: task-10.2-plan-10-injection-dedup
title: "Task 10.2: Injection ledger + degraded repeat rendering"
tags: [task, plan-10]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
---

# Task 10.2: Injection ledger + degraded repeat rendering {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending
> Depends on: 10.1 (only if it clears)

rel: part-of -> [[plan-10-injection-dedup]]

## Requirements {#requirements}

- **BLOCKED until 10.1 clears its threshold.** Do not start otherwise.
- A repeat renders as a one-line pointer (`path:line  name   [shown turn N]`), never as nothing. **No suppression path may exist in the code, not even behind a flag** — a dead flag is dead code and self-concealing ([[impression_bsd_dead_flag_surface]]).
- Ledger is per-session, per-entity `last_injected_turn` (plan Q2). Reuse STM session state if it fits rather than adding a sidecar with its own lifecycle to keep correct across compaction ([[feedback_prefer_existing_infra]]).
- The decay is the helix primitive applied to injection, not a second decay implementation ([[feedback_reuse_shared_stoplist]]).
- Budget interaction is explicit: bytes freed by degraded entries are RE-SPENT on additional new entries up to the same token budget, or they are not — whichever, it is a stated decision with a test, because "saves context" and "returns more" are different products.

## Files to Create / Modify {#files}

- modify `src/refmatrix/scan.py` (render path), `src/refmatrix/stm.py` (ledger, if it lands there)

## Test Strategy (RED first) {#test-strategy}

`tests/test_injection_dedup.py`:
- a first injection renders the full entry; the immediate repeat renders the pointer line and the pointer contains the path:line
- a repeat is NEVER empty — asserted directly, since that is the plan's one non-negotiable constraint
- the pointer names the turn it was first shown
- mutation check: replacing the pointer with a suppression turns the never-empty test RED
- grep the module for any branch that emits nothing for a repeat — asserted absent

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.2-plan-10-injection-dedup.md`.
- Committed on branch `task-10.2-plan-10-injection-dedup`; merged `--no-ff` to `master`.
