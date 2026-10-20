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

- **Deployed + pushed: 0.80.1** — `master` = `origin/main` = deploy tree = `8824ae2`. Hub + 8 stores
  on v0.80.1 (0.80.1 = plan-3 tasks 3.4-3.6 + bug-137). Contents: 0.79.0 bug-129 (hub.pid/hub.lock), 0.79.1 task 23.0 (test sandbox), 0.80.0
  task 21.1 (agent context-usage telemetry) + plan-4 closed (tasks 4.5/4.6). Release suite: 2
  expected failures (gmd repo-scope gate; 21.1 AC-6 needs the user's fixture), 0 dev-tree failures.
- Dev tree branch `wave0-spec-reviews` = master.
- Wave order of record: [[plan-review-2026-10-14#t11-folded-waves]] (plans 1-15 folded in, W2-d
  added for plan-3 task 3.7).

## In flight {#in-flight}

- **0.80.1 deployed + pushed** (master = origin/main = deploy = `8824ae2`; hub + 8 stores v0.80.1).
- **AC-6** in `/Volumes/littlebig/refmatrix-ac6`, branch `ac6-fixture` (`3deabee`, off 0.80.0):
  redacted + trimmed fixture committed (1.6 MB; d8f leaks in the user's raw cut fixed in the tool);
  grep pin corrected 1,119 → 1,121 (different cut, measured); 34 agent recalls is right — the
  report lumps cli.log recalls (244) instead of splitting per channel: product defect, RED test
  `test_ac6_cli_log_recalls_are_split_per_channel`. **Its registry row says bug-137 — that number is
  taken on master (integration fix); renumber to bug-138 when merging.** Next: implementer GREEN,
  ch-bsd, merge with master, release.
- **Task 3.7 (verb-it backlog) — user decided: do NOW, after this save-state.** Clone ready:
  `/Volumes/littlebig/refmatrix-task-3.7`, branch `task-3.7-verb-it-backlog` off release-0.80.1 (= master content).
  First step: rewrite 3.7 into a buildable per-family spec (actions, params, read source, budget,
  busy/absent, output shape, MCP tool) + RED tests; fold in the two r12 deferral rows (guard
  fixed-point plants; `global_recall_rows` errno + `cli.py` catch-all). Plan-3 closes with 3.7.

## Waiting on the user {#user}

- (AC-6 fixture cut — done 2026-10-19.)
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
