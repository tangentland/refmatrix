---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-19 (session d6dcee49). Prior handoff archived at
`workflow/past_handoffs/016-wave0-close-plan-review_2026-10-15.md`.

rel: supersedes -> [[handoff-016-wave0-close-plan-review]]

## State {#state}

- **Deployed + pushed: 0.80.0** — `master` = `origin/main` = deploy tree = `246efb8`. Hub + 8 stores
  on v0.80.0. Contents: 0.79.0 bug-129 (hub.pid/hub.lock), 0.79.1 task 23.0 (test sandbox), 0.80.0
  task 21.1 (agent context-usage telemetry) + plan-4 closed (tasks 4.5/4.6). Release suite: 2
  expected failures (gmd repo-scope gate; 21.1 AC-6 needs the user's fixture), 0 dev-tree failures.
- Dev tree branch `wave0-spec-reviews` = master.
- Wave order of record: [[plan-review-2026-10-14#t11-folded-waves]] (plans 1-15 folded in, W2-d
  added for plan-3 task 3.7).

## In flight {#in-flight}

- **Plan-3 (W1-b)** in `/Volumes/littlebig/refmatrix-plan3-close`, branch `plan3-close-w1` (base
  d4bf001, NOT yet on 0.80.0): tasks 3.4, 3.5, 3.6 built; ch-bsd r10 (`fc80c7b`) found S1 (CLI/MCP
  bootstrap partition split, from the bug-135 fix) and S2 (transport-wording guard foolable; live
  sites cli.py:1341, :12270). RED for the fix at `a420c90`; implementer GREEN running. Then ch-bsd
  r11, then merge as 0.80.1. Plan-3 closes only with task 3.7 (verb-it backlog, W2-d) done or the
  user carrying it past closure.

## Waiting on the user {#user}

- AC-6 fixture: `! cd /Users/tholley/claude_tools/refmatrix && python3 tools/cut_agent_usage_fixture.py`
- 19.5 R1 hook-limit probe; 20.1 gold labels; 21.4 question set; 19.6 tables.

## Next (Wave 1) {#next}

23.4 ∥ (23.2 → 23.1 → 23.3); 19.5 R1 → 19.1 → 19.2; 19.0; 23.5 (+ bug-136 rider); after 23.1 the
17.x and 16.6-slice → 22.x chains; W1-e plan-15 close (clean full suite on master).

## Open bugs / notes {#open}

- bug-136 (read-only fallback onto the writer's catalog) — rider on 23.5.
- Test-isolation gap: owner lookup can walk to the runner's real Claude pid (21.1 fixed per test
  with a per-test pointer dir; root fix belongs to the 23.0 sandbox).
- bug-129 MEH m1-r4; bug-130 flake; bug-124; IMPRESSIONS.md over its line cap; GMD repo-scope gate
  (34 dangling-doc errors, ADR ids in docs/INDEX.md).
