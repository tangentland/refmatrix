---
gmd: "0.1"
id: task-27.1-fleet-inventory
title: "Task 27.1: inventory every memory dir — dry-run plan, store mapping, bridge coverage — before anything moves"
tags: [task, plan-27, inventory, dry-run, mapping, bridge]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
  updated: 2026-11-09
---

# Task 27.1: fleet inventory {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: plan-26 deployed

rel: part-of -> [[plan-27-memory-fleet-rollout]]

## Requirements {#requirements}

This task is read-only. Output: `workflow/plans/plan-27-memory-fleet-rollout-tasks/inventory.md`
(GMD, lint-clean).

1. **AC-1: one row per `~/.claude/projects/*/memory`, empty dirs included.** Each row gives:
   - the resolved path, and whether it is a symlink;
   - the `organise` preview counts: moves, unplaceable, non-GMD (named), type_mismatch,
     mis-typed save-states, duplicate_ids;
   - `MEMORY.md` lines and characters;
   - the links in `MEMORY.md` that point at missing files.
2. **AC-2: the mapping is computed, not guessed.** For each known repo root, compute
   `handoff.default_memory_dir(root)` to get the slug. A memdir with no matching root is marked
   `orphan`. For each root record:
   - `.refmatrix/` present?
   - supervised? (`rmx daemon launchctl status` run in that root, plus `rmx hub status`)
   - the memory partition the bridge would use
   - does a SessionStart bridge hook exist? (read the generated hook commands in
     `.claude/settings*.json`)
   - `rmx install-hooks --check` result, as read-only drift.
3. **AC-3: bridge coverage is measured.** In each store-backed project: the memory-row count of
   its memory partition (daemon op, e.g. `rmx memory list`/`memory_stats`) versus the GMD files
   on disk. Also run `rmx memory recall` for one phrase unique to the newest file. viascope and
   cliquedb are the expected gaps, because they have no SessionStart bridge.
4. **AC-4: name the anomalies.**
   - viascope2: orphan, merged repo.
   - thiquet: memdir `-bdep-thiquet` maps to the unsupervised bdep/thiquet store; the supervised
     `~/enduris/thiquet` maps to no memdir.
   - viascope: symlink, plus a stray `.memory.db`.
   - ble-sniffer-mqtt: checkout not found.
   - home dir: maps to the global store.
5. **AC-5: no live change.** The commands run are the deployed `rmx` read paths and the
   `organise` preview. Nothing is written in any memdir or store. The inventory doc names each
   command it ran.

6. **AC-6: round-1 columns.** Each row also records:
   - `git_tracked`: the owning repo top level and its tracked count, or `untracked`. Expected
     today: viascope's repo for viascope. In `~/.claude`, 2 live refmatrix files plus 93
     unstaged deletions under the gone `-Users-tholley-enduris-cliquedb` dir; all 93 names exist
     in the bdep-cliquedb memdir. Record that dirt and do not touch it (r2 m5).
   - `prose_chars` and its share of the 24,000-char budget. A share over 50% routes the dir to
     [[task-27.2a-index-prose-to-memories]] (r2 s6).
   - `refresh_pending`, taken from the pre-deploy measurement on copies (26.8 AC-0), not from a
     live run (r2 s2).
   - `organised`: whether `.memory-layout` is present. Expected: false everywhere except
     refmatrix.
   - `refresh_pending`: the 26.2 one-time refresh count for that store.
   - `prose_lines`: from the 26.5 preview, with a flag when the carried prose would exceed 75% of
     the index budget.
   - The store that 26.5 AC-1's resolver returns for the UNRESOLVED memdir path. Any disagreement
     with AC-2's computed mapping is listed as an anomaly.

## Files to Create / Modify {#files}

- Create `workflow/plans/plan-27-memory-fleet-rollout-tasks/inventory.md`.
- Create `workflow/review-output/27.1-*.log`.

## Test Strategy {#test-strategy}

There is no code. The check is that rerunning the inventory gives the same counts (idempotent,
read-only). `@ch-bsd` spot-checks three rows against the disk.

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan26-27-spec-review-r1-96feccd]].

| finding | change | anchor |
|---|---|---|
| S1 (tracked memdirs) | `git_tracked` column per dir | AC-6 |
| S5 (one-time refresh) | `refresh_pending` per store | AC-6 |
| B2 (store resolution) | The mapping uses 26.5 AC-1's resolver; disagreements are listed | AC-6 |
| B4 (prose) | `prose_lines` per dir; dirs whose prose cannot fit are flagged | AC-6 |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| m5 (`~/.claude` count) | "2 live + 93 deleted" recorded as pre-existing dirt | AC-6 |
| s6 (viascope prose) | `prose_chars` share; over 50% routes to 27.2a | AC-6 |
| s2 (refresh measured before deploy) | `refresh_pending` from 26.8 AC-0's copy measurement; `organised` column | AC-6 |
