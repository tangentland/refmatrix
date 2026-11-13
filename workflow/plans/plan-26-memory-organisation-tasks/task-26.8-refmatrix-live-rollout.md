---
gmd: "0.1"
id: task-26.8-refmatrix-live-rollout
title: "Task 26.8: deploy, measure the one-time refresh, back up, organise the refmatrix memory dir, re-compile its subjects, and prove it by recall"
tags: [task, plan-26, deploy, live, migration, verification]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-13
---

# Task 26.8: refmatrix live rollout {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: 26.0-26.7 merged to `master` and released, including 26.6's R3 residual
> ([[task-26.6-compile-subject-hygiene#r3-residual]]; 26.6 is `completed` only then). 26.9 is NOT
> a dependency. Rev 6 (2026-11-13): AC-8 takes ADR-0005's amended Appendix A and A.2, and the
> expected counts are re-read at run time ([[#rev-round-6]]).

rel: part-of -> [[plan-26-memory-organisation]]
rel: reinforces -> [[feedback_deploy_tree_is_the_runtime]]
rel: reinforces -> [[feedback_restart_daemon_after_promote]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: depends-on -> [[refmatrix/adr-0005-memory-dir-layout#appendix-memory-rules]]
rel: depends-on -> [[refmatrix/adr-0005-memory-dir-layout#appendix-forget-step]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]

## Requirements {#requirements}

This task applies the result to the refmatrix dir ONLY. Every other dir is
[[plan-27-memory-fleet-rollout]]. Every live step is announced to the user first and backed up
first.

0. **AC-0: pre-deploy fleet snapshot and measurement (r2 s2). Read-only, no new code.**
   - **Snapshot.** Before the deploy, tar every `~/.claude/projects/*/memory/MEMORY.md` and every
     `.memory_hooks.json` into `~/.refmatrix/backups/memory-organise/fleet-pre-26.8-<ts>.tar.gz`.
     Follow symlinked memdirs to their targets. Record the member count.
   - **Measure the refresh (r3 s2).** With the DEV build (`.venv-eval`), for each live memdir:
     1. copy ONLY its store's read snapshot into a sandbox under a short `mkdtemp()` root;
     2. run `rmx ingest-gmd --as-memory --dry-run --store-snapshot <copy> <LIVE memdir path>`
        (26.2 AC-3). This is a read-only walk of the live path, and it writes nothing;
     3. also run the relocated-twin control, which must report 0;
     4. record `refresh_pending` per store, with its four pre-registered terms (26.2 AC-3: the
        three file terms + `moved_legacy`; r6-lite n2), in
        `workflow/review-output/26.8-refresh-pending.log`.

     The dev build never opens the live store. It never writes the live memdir.
   - **What the deploy must and must not do.** Gated behaviours are marker-gated, so the deploy
     must change no file in any un-organised dir. Ungated, it must not refresh `source_path` in
     any un-organised dir.
   - **Spot-check after AC-1 (r3 m5).** HEAD's `_ss_update_index` legitimately writes a
     save-state's pointer line, so a save-state is the wrong probe. Choose either:
     - after ONE bridge only (no save-state), cliquedb's and viascope's `MEMORY.md` and sidecar
       are byte-identical to the snapshot; or
     - on a COPY of each dir, the deployed binary's save-state output is byte-identical to the
       pre-deploy binary's output on a second copy. **Scope (r5 m2):** byte-identity holds only
       for FLAT dirs (memories top-level or in `impressions/`, 26.1 AC-9). In a nested
       un-organised dir, 26.1 AC-3's ungated `collect` legitimately widens the index. viascope's
       expected diff is stated, not waived (its figures are the 2026-11-09 r5 probe; the rule is
       what binds, and the figures are re-measured on the copy at run time): HEAD renders 3 entries (1 line / 119 chars); the
       deployed binary renders 145 (65 feedback, 68 project, 9 reference, 3 impressions) as
       139 lines / 23,857 chars, under the 24,000 budget, with 5 project entries folded behind
       "nothing was deleted". The ONLY permitted diff is those added entry/fold lines; the
       hand-written prose is dropped on BOTH sides (HEAD's compaction), so a prose line present
       on one side only fails. Any other differing line fails. Numbers from the r5 probe on a
       copy ([[bsd-plan26-27-spec-review-r5-3ded49e]]); re-measure on the copy and record.
1. **AC-1: deploy.**
   - Release on `master`.
   - Run `git -C ~/refmatrix pull --ff-only origin master`, then `rmx daemon restart --relaunch`.
   - `rmx version -v` must show the import path under `~/refmatrix`.
   - Restart the hub with `rmx hub stop`, then ONE `launchctl kickstart`.
2. **AC-2: confirm the measured refresh (ch-bsd r1 #s5; r2 s2).**
   - The refmatrix dir is not organised yet, so the deploy alone triggers no refresh here.
   - **STOP before AC-4 (r4 s3).** If AC-0's `refresh_pending` for this store is more than 50,
     stop: log a bug row and report to the user BEFORE the preview and apply.
   - The first marker-on bridge is the apply's own (26.5 AC-4 step 4 / AC-5). Its report splits
     re-ingested rows into terms (26.2 AC-3), each compared separately:

     | term | expected | tolerance |
     |---|---|---|
     | `stale_before` | AC-0's first two terms only: missing + symlink-form `source_path` (r5 m3) | ±5 |
     | `moved` | the AC-3 preview's move count, as recorded at run time ([[#counts-reread]]) | exact |
     | `forced` | save-states forced by 26.5 AC-5 that were NOT moved; 0 when every save-state moves | exact |
     | `moved_legacy` (r5 s1) | the legacy `memory_sync_disk` rows that share a moved file's `source_path`: AC-0's re-probe on a read-snapshot copy, which must equal the AC-3 preview's projected count ([[#counts-reread]]; 19 on 2026-11-09) | exact |

     The moved save-states are counted once, under `moved`. A row falls in one term only, by
     its stored path's shape (26.2 `#impl-notes-r5`). If `moved_legacy` differs from AC-0's
     re-probe or from the preview's projection, log a bug row and report before AC-5. The legacy
     duplicates are NOT merged or forgotten here (26.2 AC-1b, out of scope;
     [[feedback_decay_never_loses_knowledge]]); the implementation summary lists them by name.
   - Then run ONE `rmx memory sync-disk` and record two things from the bridge report: the number
     of rows re-ingested, and the store write counter. Record wall time only as context.
   - If that sync holds `_store_lock` for more than 60 s, log a bug row and report it to the
     user.
3. **AC-3: preview.**
   - Run `rmx memory organise <live memdir>` with the default `--store-from-memdir` (26.5 AC-1).
     The resolved store must be refmatrix's.
   - Save the plan to `workflow/review-output/26.8-organise-preview.log`.
   - The counts must match a fresh read-only survey of the dir, taken just before the preview
     and recorded in the log: every save-state to `savestates/`, and every typed file to
     `feedback/`, `project/` and `reference/`, per plan Q1, exact per folder ([[#counts-reread]]).
     `unplaceable` must be 0, or every unplaceable file is named.
   - The preview must report `index: ok` (26.5 AC-2, r2 s5).
   - The preview's `moved_legacy` must equal AC-0's re-probe (26.5 AC-2; r5 s1).
   - The preview must report `git_tracked: ~/.claude` for the two tracked files: `MEMORY.md` and
     `project_csn_production_harness.md`. It must also report the carried prose line count.
4. **AC-4: back up, then apply.**
   - Stop for the user's go-ahead, then run `--apply`.
   - The tarball must exist, and its member count must equal the full walk.
   - The two `~/.claude`-tracked moves must appear as staged `git mv`s.
   - The verb exits 3 with the exact `git -C ~/.claude commit -m '…' -- <paths>` command. Never
     `commit -a`: `~/.claude` carries unrelated unstaged deletions, counted at this step and
     named in the summary. The user commits.
   - The bridge report must show zero `duplicate_ids` and zero errors.
5. **AC-5: prove it.** Capture each check to a log.
   - `rmx recall-state` shows the newest save-state by `updated`, read from `savestates/`. The
     moved files' mtimes are unchanged (spot-check 5).
   - `rmx memory recall "<phrase unique to one moved save-state>"` returns that save-state.
   - The same recall check passes for one moved feedback memory.
   - `rmx context <a moved memory's anchor>` shows a `path` under the new folder (26.2).
   - `rmx memory organise --check` is clean, including `moved_legacy: 0` (26.5 AC-8; r5 s1).
   - For 3 of the legacy rows AC-0 counted, a daemon read by name (`rmx memory get <name>`, e.g.
     `refmatrix-daemon-architecture`) shows `source_path` under the new folder, and its content
     is unchanged from before the apply (r5 s1).
6. **AC-6: re-compile (26.6 builds 19.4).**
   - Run `memory_compile --apply` (scope `memory`) through the daemon.
   - The pre-0.34 subject rows (re-listed at this step with `rmx memory list --type subject`;
     20 on 2026-11-09: 15 `unlabeled_N`, plus `from`, `existing`, `feedback`, `fixes` and
     `memory`) must read `stale = true` with a `stale_since`. They must still be present, be returned by
     `rmx memory get`, show their mark in `rmx memory list --type subject`, and be absent from
     `MEMORY.md`. Recall absence is NOT asserted here: it lands with 25.1 AC-6 (r2 s1).
   - The run summary must report `stale_new`.
   - `rmx daemon status` must show no `memory-compile` line.
   - Grade the labels per 26.6 AC-E. Record the band and the action taken.
7. **AC-7: the index (26.7 builds 19.3).**
   - `MEMORY.md` is regenerated with live-subject blocks, under budget.
   - `rmx memory index --check-reach` passes.
   - `--check` reads in sync.
   - Curated hooks survive (spot-check 5).
   - Hand-written prose is carried.
8. **AC-8: MEMORY-RULES (plan Q8, recorded: the user authorises it here).**
   - Show the user the ADR-0005 appendix paragraph, and apply it to `~/.claude/MEMORY-RULES.md`
     with their authorisation. **Rev 6 (L11):** the paragraph is the amended
     [[refmatrix/adr-0005-memory-dir-layout#appendix-memory-rules]] text, which carries the marker
     condition (organised dir: type folder; flat dir: top level). The applied section must
     byte-equal the ADR's fenced block. Diff it and record the diff in the implementation
     summary. If the user changes the text at this step, the change is written back into the ADR in
     this task's commit, so the two never diverge.
   - **Rev 6 (L12): forget-flow step 5.** In the same window, show the user
     [[refmatrix/adr-0005-memory-dir-layout#appendix-forget-step]] (`rmx memory forget <id>` after
     the file is deleted). Before showing it, re-check at the deployed sha that the bridge still
     never forgets a deleted file, and record the evidence. If the re-check finds that the bridge
     DOES forget a deleted file by then, A.2 is withdrawn: it is not shown as a proposal, and the
     user is told why, with the evidence (rev 7, bsd-spec-t2 m5). Apply it to `MEMORY-RULES.md#forget`
     only if the user accepts it. Record the user's answer, verbatim, in the implementation
     summary, whether it is accept, change or decline.
   - **Why it matters.** Until the paragraph lands, every agent writes new memories at the memdir
     TOP level. Each one keeps `organise --check` non-zero. If an agent re-creates a top-level
     file whose id already lives in a type folder, that also trips 26.2's duplicate-id refusal:
     the row freezes until a human resolves it.
   - After the edit, the next `rmx save-state` reports zero strays.
9. **AC-9: rollback rehearsal (dry).**
   - Name the backup path in the implementation summary.
   - Do NOT run `--rollback` live unless AC-5 fails.

## Files to Create / Modify {#files}

| file | change |
|---|---|
| `workflow/implementation_summaries/task-26.8-refmatrix-live-rollout.md` | create |
| `handoff.md` | update |
| `workflow/bug_registry.md` | a row for anything found |

## Test Strategy {#test-strategy}

This task is a live verification, not new tests.
- Every command runs the deployed `rmx`.
- The live store is touched only through daemon ops.
- No `Store()` opens.
- No dev-venv `rmx` against the live store.

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| S5 (unstated one-time full re-ingest) | Measured before it happens, with a stop threshold | AC-2 |
| M2 (arithmetic) | "40 save-states plus 250 typed (68+170+12)" | AC-3 |
| S1 (`~/.claude` tracks 2 refmatrix memory files) | Staged `git mv`, user commits | AC-3, AC-4 |
| B2 | `--store-from-memdir`; resolved store checked | AC-3 |
| B1 / Q5 | `stale`/`stale_since` replaces `retired_at`; 19.3 index | AC-6, AC-7 |
| M6 | MEMORY-RULES paragraph applied with the user's go-ahead | AC-8 |
| M9 (26.9 must not gate) | Header | header |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s1 (the AC-6 recall assertion needs 25.1) | Recall leg removed; the mark, `get`, the list and the index are asserted | AC-6 |
| s2 (the deploy reaches fleet dirs before plan-27's backups; "measure before deploy" impossible) | Pre-deploy fleet snapshot; dev-build measurement on copies; post-deploy byte-identity spot-check; AC-2 confirms the measured count at the first marker-on bridge | AC-0, AC-2 |
| m5 (`~/.claude` stop and dirt) | Exit 3, exact commit command, never `commit -a` | AC-4 |
| Q8 (recorded) | The user authorises at 26.8; reason stated | AC-8 |

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| s2 (the copied memdir counts its own relocation) | Dry-run on the LIVE memdir path against a store-snapshot copy; relocated-twin control = 0; terms pre-registered | AC-0 |
| m5 (the spot-check is wrong for save-state) | Check after a bridge only, or compare the pre-deploy binary's output on copies | AC-0 |
| m8 (forced save-state re-bridge) | Counted separately in AC-2 | AC-2 |

## Revision round 4 (2026-11-09) {#rev-round-4}

Answers [[bsd-plan26-27-spec-review-r4-f89e640]].

| finding | change | anchor |
|---|---|---|
| s3 (the expected count compared a pre-move number with a post-move bridge) | Expected count = AC-0 + preview moves + forced-not-moved, per term; the >50 STOP is on AC-0's number, before AC-4 | AC-2 |

## Revision round 5 (2026-11-09) {#rev-round-5}

Answers [[bsd-plan26-27-spec-review-r5-3ded49e]].

rel: derives-from -> [[bsd-plan26-27-spec-review-r5-3ded49e]]

| finding | change | anchor |
|---|---|---|
| s1 (19 legacy rows go dead-path on apply, uncounted) | `moved_legacy` = 19, exact, in the preview and the apply bridge; `--check` includes it; 3 legacy rows read by name; merge/forget out of scope | AC-2, AC-3, AC-5 |
| m2 (spot-check option (b) fails in viascope by design) | Byte-identity scoped to flat dirs; viascope's expected diff stated (entries added, prose dropped on both sides) | AC-0 |
| m3 (`stale_before` compared with the whole `refresh_pending`) | Compared with AC-0's first two terms | AC-2 |

## Revision round 6 (2026-11-13): plan-review folds {#rev-round-6}

Answers [[plan-review-2026-11-13#lead]] L11 and L12, and spec gap G19's "counts re-read"
([[plan-review-2026-11-13#spec-gaps]]). Evidence: `workflow/review-output/pop-2026-11-13/contra-a.md`
Ca-4, Ca-9 and its clean-areas note on stale counts. Status is unchanged (`pending`).

rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]

| row | change | anchor |
|---|---|---|
| L11 / Ca-4 (Appendix A was unconditional; `/save-state` gates on the marker) | AC-8 applies the amended, marker-conditioned text; byte-equality with the ADR is checked | AC-8 |
| L12 / Ca-9 (forget flow ends at deleting the file) | Step 5 is put to the user in the AC-8 window; it is applied only on acceptance | AC-8 |
| G19 (counts) | The expected counts are re-read at run time; see [[#counts-reread]] | AC-2, AC-3, AC-4 |
| L1 | Header: 26.6's R3 residual is part of "26.0-26.7 merged" | header |
| Q8 open (brief rule) | Lines named | [[#q8-b]] |

### Expected counts, re-read (2026-11-13) {#counts-reread}

AC-3's figures (40 save-states; 250 typed as 68/170/12) and AC-2's `moved` are the 2026-11-09
survey. On 2026-11-13 a read-only count of the live refmatrix memdir gave:
- 306 top-level files: 44 save-states and 262 typed (72 `feedback`, 175 `project`, 15
  `reference`);
- `impressions/` holds 80;
- `~/.claude` still tracks 2 refmatrix files (`MEMORY.md`, `project_csn_production_harness.md`).
  It now carries 231 unstaged deletions, 93 of them under the gone `-enduris-cliquedb` dir.

The dir keeps growing until 26.8 runs, so the rule replaces the numbers:
- **AC-3.** Before the preview, re-survey the dir read-only and record the counts in
  `workflow/review-output/26.8-organise-preview.log`. The preview must equal that survey
  exactly, per folder. The 2026-11-09 and 2026-11-13 numbers are history, not expectations.
- **AC-2.** `moved` = the preview's move count, exact (the rule is unchanged).
  - `forced` = 0 while every save-state moves.
  - `moved_legacy`: 19 is the 2026-11-09 probe. AC-0 re-probes it on a read-snapshot copy. The
    preview must equal the re-probe, exact.
  - A re-probe other than 19 is logged as a bug row with its reason, and reported, before AC-4.
- **AC-4.** The "never `commit -a`" reason is the current dirt count (231 unstaged deletions
  today), re-read at the step.
- **AC-6.** The 20 pre-0.34 subject rows are re-listed at the step (`rmx memory list --type
  subject`) before the stale assertion.

### Lines that change under Q8 b {#q8-b}

Q8 is open ([[open-questions]]). This spec holds under Q8 a or c. Under Q8 b (save-states kept
out at ingest), these lines change:
- AC-0's `refresh_pending` terms and AC-2's `stale_before` / `moved` / `forced` rows lose their
  save-state share;
- the save-state half of `moved` becomes a file-only move;
- AC-5's first two bullets keep `rmx recall-state` and drop the `rmx memory recall` of a moved
  save-state. The moved-feedback recall stays.

## Revision round 7 (2026-11-13): bsd-spec-t2 {#rev-round-7}

Answers [[bsd-spec-t2-b5fe2d3]] m4 and m5. Status is unchanged (`pending`).

rel: derives-from -> [[bsd-spec-t2-b5fe2d3]]

| finding | change | anchor |
|---|---|---|
| m4 (AC bodies still asserted the 2026-11-09 numbers) | AC-2's table, AC-3, AC-4, AC-5 and AC-6 state rules that are re-read at run time; the old figures remain only as dated history | AC-2-AC-6, [[#counts-reread]] |
| m5 (no branch for a false premise in the forget-step re-check) | If the bridge forgets deleted files by then, A.2 is withdrawn and the user is told why | AC-8 |
