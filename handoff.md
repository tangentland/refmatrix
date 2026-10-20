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

- **Release 0.80.1** in `/Volumes/littlebig/refmatrix-rel080`, branch `release-0.80.1` (HEAD
  `591a2fb`, not yet on master): plan-3 tasks 3.4-3.6 (ch-bsd r12 MEH-only, `9f12239`) merged on
  0.80.0 + bug-137 integration fix (`ae7713d`; 21.1's `_expired_reads` routed through the
  classifier). Full-suite rerun was running (`workflow/review-output/rel0801-full-2.log` in that
  clone). When clean: `git checkout -B master origin/master && git merge --no-ff release-0.80.1`
  there, `git fetch <clone> master:master` in the dev tree, deploy, push `master:main`.
- **AC-6 reconciliation** in `/Volumes/littlebig/refmatrix-ac6` (branch `ac6-fixture` off 0.80.0):
  the user cut the fixture 2026-10-19 (untracked copy also in the dev tree at
  `tests/fixtures/agent_usage/` — do not commit it from there). Report prints context 3 (match),
  grep-replica 1121 (test pins 1,119), memory recall commands=244 (pins 34). A test-engineer is
  measuring which side is wrong and checking redaction/size (22 MB cli.log).
- **Task 3.7 (verb-it backlog) — user decided: do NOW, after this save-state.** Clone ready:
  `/Volumes/littlebig/refmatrix-task-3.7`, branch `task-3.7-verb-it-backlog` off release-0.80.1.
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
