---
gmd: "0.1"
id: task-27.6-per-store-compile-and-landing
title: "Task 27.6: re-compile subjects per store, regenerate each MEMORY.md, and report how future save-states land"
tags: [task, plan-27, compile, subjects, memory-index, hooks, drift]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
  updated: 2026-11-09
---

# Task 27.6: per-store compile, index and landing {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: [[task-27.2-viascope2-fold-and-repoint]], [[task-27.3-thiquet-store-repoint]],
> [[task-27.4-quiet-dir-migrations]], [[task-27.5-cliquedb-at-session-boundary]]

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: depends-on -> [[task-26.6-compile-subject-hygiene]]
rel: depends-on -> [[task-26.7-memory-index-by-subject]]

## Requirements {#requirements}

1. **AC-1: compile once per store, not per dir.** For each store whose memory partition was
   touched (cliquedb, cliquet, viascope, bdep/thiquet, atldb, orderly, cat-herder, atlftpd, and
   the home/global store only if plan Q4 says so), run the `memory_compile` verb with
   `--apply`, scope `memory`, through that store's daemon. This is 26.6, which builds 19.4.
   Record:
   - the subjects marked `stale` (19.4 R5), with their `stale_new`/`stale_total`;
   - that `rmx daemon status` shows no stale `memory-compile` line;
   - the label grade band, or "not graded" with a reason.
2. **AC-2: regenerate `MEMORY.md` per 19.3, as built by 26.7,** in each store-backed dir:
   - live-subject blocks;
   - `rmx memory index --check-reach` passes;
   - carried prose and id-keyed hooks are preserved (B4);
   - under budget, with `--check` in sync. viascope's index goes from 33 KB to under 24,000 chars. That is reachable only
   because 27.2a converted its 22,643 chars of prose: carried prose is at most 6,000 chars, and
   the rest is entries and 19.3 blocks. The fold count is stated (r2 s6).
3. **AC-3: landing report.** One table, one row per project:
   - `organised`: is `.memory-layout` present? (r3 m1)
   - Does `rmx save-state` write `savestates/`? Only where `organised` is true. The deployed
     binary is the same everywhere, but the MARKER decides (26.3 AC-1). Verify with
     `rmx save-state --dry-run` in one organised and one un-organised project: the target is
     `savestates/` in the first and the top level in the second.
   - Does a SessionStart bridge hook exist?
   - `rmx install-hooks --check` drift.
   - Recommended action, per plan Q3: report only; regeneration rides plan-24.
4. **AC-4: close-out.** Bring `workflow/plan-of-plans.md`'s plan-27 row up to date (by the plan
   owner), bring `handoff.md` up to date, and get `@ch-bsd` over the range to CLEAN.

## Files to Create / Modify {#files}

- Create `workflow/implementation_summaries/task-27.6-per-store-compile-and-landing.md`.
- Create `workflow/review-output/27.6-*.log`.

## Test Strategy {#test-strategy}

Live verification through each store's daemon.

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan26-27-spec-review-r1-96feccd]].

| finding | change | anchor |
|---|---|---|
| B1 (compile/index ownership) | Runs 26.6 (19.4) and 26.7 (19.3); the mark is `stale` | AC-1, AC-2 |
| B4 (prose and hooks) | Carried and preserved | AC-2 |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s6 (unreachable expected number) | The 24,000-char target is tied to 27.2a's at-most-6,000-char carried prose | AC-2 |

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| m1 (the landing table attributed `savestates/` to the binary, not the marker) | `organised` column; dry-run in one organised and one un-organised project | AC-3 |
