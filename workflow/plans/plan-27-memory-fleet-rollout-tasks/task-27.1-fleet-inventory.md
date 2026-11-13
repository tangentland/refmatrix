---
gmd: "0.1"
id: task-27.1-fleet-inventory
title: "Task 27.1: inventory every memory dir — dry-run plan, store mapping, bridge coverage — before anything moves"
tags: [task, plan-27, inventory, dry-run, mapping, bridge]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
  updated: 2026-11-13
---

# Task 27.1: fleet inventory {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: plan-26 deployed

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]

## Requirements {#requirements}

This task is read-only. Output: `workflow/plans/plan-27-memory-fleet-rollout-tasks/inventory.md`
(GMD, lint-clean).

0. **AC-0: refresh plan-27's `#survey` and `#facts` first (rev 6, L13).** {#ac-0}
   - Before AC-1, re-measure every [[plan-27-memory-fleet-rollout#survey]] column read-only:
     memories, top-level, save-states, store and daemon, and the SessionStart bridge.
   - Rewrite the table in the plan with a dated note, and mark each changed cell. Rewrite
     [[plan-27-memory-fleet-rollout#facts-hooks-0820]] from the measurement.
   - **The hook column is measured two ways:**
     - read each repo's `.claude/settings*.json` for the SessionStart `ingest-gmd --as-memory`
       command;
     - find fleet repos by the installed hook marker (the `refmatrix: refresh` line in
       `<repo>/.git/hooks/post-commit`), over `~/github`, `~/claude_tools` and `~/enduris`,
       skipping `_frameworks_and_libraries` and never searching from `/`. `rmx hub status`
       alone is not enough ([[project_fleet_hooks_found_by_marker_not_hub]]).
   - A repo found by its marker that is missing from `#survey` gets a row.
   - Known on 2026-11-13: viascope's, cliquedb's and cliquet's settings carry the bridge. bdep/thiquet
     and atlftpd were missed by the 0.82.0 re-install.
   - Every command and its output goes to `workflow/review-output/27.1-survey-refresh.log`.
   - Read-only, like the rest of this task: no hook is regenerated here
     ([[plan-27-memory-fleet-rollout#q3-rehost]]).

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
   - ble-sniffer-mqtt: the checkout is `~/github/atollogy/bdep/ble_sniffer_mqtt` (user,
     2026-11-09; the slug turns `_` into `-`). It has no `.refmatrix/`, so the row is
     `no store` (file-only organise). Record the path; the anomaly is the naming, not a
     missing checkout.
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
   - `refresh_pending`, from 26.8 AC-0's pre-deploy measurement: a dry-run of the LIVE memdir
     path against a store-snapshot copy (r3 s2). It is never measured on a memdir copy, which
     counts the copy's own relocation.
   - **Headroom (r3 m4):** the `MEMORY.md` line count and char count against the 200-line and
     24,000-char budgets. Un-organised dirs keep HEAD's compaction until organised, so dirs near
     the cap (viascope 157 lines / 33 KB, cliquedb 77 lines / 17.5 KB) are ordered earlier in
     27.4.
   - **viascope notice (r3 m4).** Post one bus message to viascope's sessions: "no
     `rmx save-state` in viascope until 27.2". A save-state there runs HEAD's compaction, which
     drops viascope's hand-written prose. That is prose loss, not a wipe: the ungated `collect`
     still lists the entries (r4 s1). 26.8 AC-0's fleet snapshot is the recovery path.
   - `organised`: whether `.memory-layout` is present. Expected: false everywhere except
     refmatrix.
   - `prose_lines`: from the 26.5 preview. The ONE prose threshold is the 50% route above
     (r3 m1). The r1 75% flag is withdrawn.
   - The store that 26.5 AC-1's resolver returns for the UNRESOLVED memdir path. Any disagreement
     with AC-2's computed mapping is listed as an anomaly.
   - **`moved_legacy` (r5 s1), per store.** From the organise preview (26.5 AC-2): the rows,
     other than a file's id row, whose `source_path` equals a planned move's from-path. Also
     record the total of rows that share a `source_path` with another row in the memory
     partition (daemon read), and how many are `source: memory_sync_disk`. Expected non-zero in
     stores that predate the `sync-disk` alias; refmatrix's is 0 after 26.8 (it was 19 before).
     The count is recorded, not acted on: merging or forgetting the duplicates is out of scope
     ([[feedback_decay_never_loses_knowledge]]). Each later apply must report the same
     `moved_legacy`, exact.

## Files to Create / Modify {#files}

- Create `workflow/plans/plan-27-memory-fleet-rollout-tasks/inventory.md`.
- Create `workflow/review-output/27.1-*.log`.
- Modify `workflow/plans/plan-27-memory-fleet-rollout.md` `#survey` and `#facts` (AC-0, rev 6).

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

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| m1 (duplicate `refresh_pending` line; two prose thresholds) | One `refresh_pending` line; one threshold (50% route) | AC-6 |
| s2 (measured on copies) | Live-path dry-run against a store-snapshot copy | AC-6 |
| m4 (no compaction in un-organised dirs) | Line and char headroom per dir; viascope "no save-state" notice | AC-6 |

## Revision round 5 (2026-11-09) {#rev-round-5}

Answers [[bsd-plan26-27-spec-review-r5-3ded49e]].

rel: derives-from -> [[bsd-plan26-27-spec-review-r5-3ded49e]]

| finding | change | anchor |
|---|---|---|
| s1 (legacy rows uncounted in every pre-alias store) | `moved_legacy` and the legacy-duplicate count recorded per store; later applies must match | AC-6 |
| m6 (Q6 answer not carried; "latent wipe") | ble-sniffer-mqtt row names `~/github/atollogy/bdep/ble_sniffer_mqtt`, `no store`; the notice says prose loss | AC-4, AC-6 |

## Revision round 6 (2026-11-13) {#rev-round-6}

Answers [[plan-review-2026-11-13#lead]] L13 (`workflow/review-output/pop-2026-11-13/contra-a.md`
Ca-8; spec gap G19). Status is unchanged (`pending`).

| finding | change | anchor |
|---|---|---|
| L13 / Ca-8 (the survey's hook column is stale after the 0.82.0 re-install; fleet found by hub, not by marker) | AC-0 refreshes `#survey` and `#facts` before AC-1, and finds repos by their hook marker | [[#ac-0]] |
| Q8 open (brief rule) | Under Q8 b, AC-1's mis-typed save-state count and AC-6's `refresh_pending` lose their store side; the file counts stay | [[plan-27-memory-fleet-rollout#q8-b]] |

## Approval (2026-11-14, d9co) {#approval-2026-11-14}

| decision | basis | status |
|---|---|---|
| The spec-wave revisions in this file are approved by the lead on the user's pattern (d9co) after ch-bsd bsd-spec-t2 r8 MEH-only (0B/0S/2M), folded at `8ea3230` per L66 with no further round | `workflow/bullshit/2026-11-14-0105-spec-t2-r8-e3cd4c7.md` (over `spec-wave-t2` up to `e3cd4c7`; r1-r7 in the same ledger) | `metadata.status` stays `pending`, which means approved to build within the records above |

rel: derives-from -> [[bsd-spec-t2-r8-e3cd4c7]]
