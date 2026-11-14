---
gmd: "0.1"
id: task-28.5-run-and-report
title: "Task 28.5: the run: the orchestrator starts the paired series when plan-28's Depends-on holds and tells the user first (L78), runs it to its frozen n (L83), reads every band as frozen, reports, and stops the goal for the user's charter decision"
tags: [task, plan-28, experiment, run, report, charter, user-gated]
metadata:
  node_type: task
  status: pending
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-14
---

# Task 28.5: run and report {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Pending: approved to build (2026-11-14, [[#approval]]; spec wave 2026-11-13, G17);
> amended by L83 ([[#rev-l83]], pending a confirm-lite).
> Depends on: [[task-28.4-preregistration-freeze]] frozen and reviewed. **The start:** the
> orchestrator starts the paired series when plan-28's Depends-on holds and tells the user first
> (L78, L80). **User-gated:** every pause (and resuming) and stopping the series early. **Goal
> stop:** the charter decision (G18).

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-28.4-preregistration-freeze]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]
rel: related-to -> [[task-10.2-plan-10-injection-dedup]]
rel: reinforces -> [[feedback_errors_fail_loudly_on_the_console]]

## Why {#why}

Under L83 (the user, 2026-11-14, Q14: "drop the live part"), the experiment is the paired
re-entry series alone: fresh agents resuming real handoffs on littlebig clones. The user's own
sessions are never assigned to an arm. L45 made the start a user step. L78 (the user,
2026-11-14: "the start of the plan-28 experiment can proceed when you feel its time")
delegated it to the orchestrator, who tells the user first. The result is an input to a user
decision (G18), not a goal step. {#why-body}

## Requirements {#requirements}

1. **R1 The start (L78, L80).** The orchestrator starts the paired series when plan-28's
   Depends-on holds: bug-216 live; 10.2 built; 21.5 phase M reported; the m1 r2-lite confirm
   CLEAN or MEH-only (G32); and 28.4's file frozen and reviewed. For each precondition it
   records the evidence (a sha, a file, a verdict). It never changes a precondition to start
   sooner. It **tells the user first**, citing:
   - the frozen pre-registration's sha;
   - the four cells and the task set (refmatrix and cliquedb handoffs);
   - the frozen minimum n per cell, and the power note's estimate of runs and agent time;
   - that the user's own sessions are not touched;
   - that deploys of the treatment modules from queue items 8-11 (`scan.py`, `recall_pack.py`,
     `hook_budget.py`, context rendering, the hooks generator, `arms.py`) need a user pause while
     the series runs (R3; L87 m3);
   - the paired archive;
   - the stop condition (the user may pause or stop at any time).

   The tell is recorded with its date. {#r1}
2. **R2 Start checks.** Before the first run, these are recorded:
   - `/Volumes/littlebig/` is mounted;
   - the paired archive's creation was announced to the user (28.2 R2);
   - the deployed `rmx` sha the series starts on.

   Nothing is committed or deployed to start the series. No period record exists, and no live
   session is touched (L83). {#r2}
3. **R3 During the series.** {#r3}
   - The runs execute in 28.2's frozen shuffled order. Each records its deployed `rmx` sha,
     cell, trigger, task id and run id. A per-cell count of runs completed, aborted,
     `leak_suspect` and `arm_error` is posted to the user daily while runs are executing.
   - **The pause (P-12, restated by L83).** It is user-gated. On the user's word, the runner
     finishes or aborts the run in flight (recorded) and starts no new run. Resuming is also on
     the user's word.
   - A deploy that touches `scan.py`, `recall_pack.py`, `hook_budget.py`, context rendering,
     the hooks generator or `arms.py` lands only while the series is paused. Readings are
     stratified by deploy sha when the series spans more than one.
   - A defect that breaks runs in any cell stops the series loudly: the user is told, nothing is
     read, and the stop is recorded.
4. **R4 End (L83).** The series ends when every reading's frozen minimum n of paired tasks per
   cell is reached (counted after exclusions), when R1's cap is reached, or when the user stops
   it. It is not time-boxed. The user is told that the series has ended, with the n reached per
   cell. No commit is needed. {#r4}
5. **R5 Score and read.** Scoring starts only after R4's end. Then 28.3's scorer runs over the
   paired archive, and `readings.py` (28.3 R9) reads every band.
   - Every outcome is computed.
   - Every band is read as frozen, and every deviation from the pre-registration is listed.
   - A reading below its minimum n is "underpowered, no verdict".
   - 10.2 R7's nested bands are read on `A+dedupe` vs `A+full` and handed to 10.2's
     implementation summary.
   {#r5}
6. **R6 Report.** `workflow/measurements/handhold-experiment-<date>.md` (GMD) holds the counts,
   the readings and the CIs, the n reached per cell, the charter-decision inputs that are not
   outcomes, and the limits. Only counts, labels and hashes are committed. A ch-bsd round over
   it must come back CLEAN or MEH-only. {#r6}
7. **R7 The goal stops.** The report goes to the user as a charter decision with the readings
   and the inputs (G18). The T3 re-plan and the plan-24 re-plan (D-Q5) follow the user's
   decision, not this task. {#r7}
8. **R8 Cleanup.** If the charter decision keeps no arm, the measurement branches of `arms.py`
   (`push_on`, `paired_override`, `parse_paired`, `as_of_admit`, the paired rows) and arm B's
   branch are deleted per the widened deferral row (28.1 R7), and the row is closed. If it keeps
   one, the decision amends the row. {#r8}

## Acceptance criteria {#acceptance}

1. **AC-1** The tell to the user (R1) and each precondition's evidence are recorded, with their
   dates, BEFORE the first paired run starts, as the run log's timestamps show (L80). {#ac-1}
2. **AC-2** The series ended per R4. Every reading whose cells are below their frozen minimum n
   says "underpowered, no verdict", and the report states the n reached per cell (L79, L83).
   {#ac-2}
3. **AC-3** Every band in the frozen file has a reading in the report, and no reading uses a
   rule absent from the frozen file. {#ac-3}
4. **AC-4** No live session was assigned to an arm (L83). Across the period of the series, the
   live stores' `query.log` and `cli.log` hold no `handhold_cell`, `arm_run` or `suppressed: "arm"`
   field, which is checked and recorded. {#ac-4}
5. **AC-5** The report passes its ch-bsd round, and the charter decision is put to the user.
   {#ac-5}

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/arms.py` | the deletion of the measurement branches (R8) |
| `workflow/measurements/handhold-experiment-<date>.md` (new) | R6 |
| `workflow/deferral_registry.md` | the `arms.py` row closed or amended (R8) |

## Definition of done {#done}

- AC-1 to AC-5 met. Implementation summary at
  `workflow/implementation_summaries/task-28.5-run-and-report.md` (the series' start and end
  times, its deploy shas, the pause log, the readings).
- The cleanup commit is made on branch `task-28.5-run-and-report`, merged `--no-ff` to
  `master`, then deployed.

## Revision r1 (2026-11-13, `bsd-spec-t3c`; lead rulings) {#rev-r1}

| finding | disposition | where |
|---|---|---|
| s7 the session-leg archive ran only at the end, after early transcripts may be pruned | a daily incremental sweep; the cleanup period is checked at the start; `no_transcript` is counted per cell | [[#r2]], [[#r3]], [[#r5]] |
| s8 the pause is undefined | a user-gated end-now commit; sessions keep their cell; resuming is a new record; readings by record | [[#r3]] |
| m9 the scope is a basename slug | the start lists the matching stores | [[#r2]] |

## Revision r2 (2026-11-13, `bsd-spec-t3c` r2; lead rulings) {#rev-r2}

| finding | disposition | where |
|---|---|---|
| r2-m3 | the record's own start, pause and end commits are exempt from the pause ban | [[#r3]] |

## Approval (2026-11-14) {#approval}

rel: derives-from -> [[bsd-spec-t3c-r3-c5d1b79]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]

**Decision row (2026-11-14):** approved by the lead on the user's pattern (d9co) after ch-bsd `bsd-spec-t3c` r3 came back MEH-only (0B/0S/2M at `c5d1b79`), with both MEHs folded (r3 m1, m2). The ch-bsd rounds were r1 DIRTY 1B/9S/11M, r2 DIRTY 0B/3S/7M and r3 MEH-only; every finding is folded, as each spec's revision tables show. This task is `pending`, which means approved to build in plan-28's order. Its user steps stay user-gated: every pause and the end (L82; the start is the orchestrator's under L78). {#approval-row}

## Revision L79 (2026-11-14, the user: "the plan 28 arms should only be 3 days"; Q11 answered (a)) {#rev-l79}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite ch-bsd round.

| change | where |
|---|---|
| 3 calendar days; a daily count; the end after 3 calendar days, never extended; AC-2 reads "underpowered, no verdict" below the minimum n | [[#why]], [[#r3]], [[#r4]], [[#ac-2]] |


**Refinement (dev master `8d88d29`; the user, the same day: "3 real days will be sufficent", Q11 a):** the period is 3 CALENDAR days from its start, with the arms concurrent. A pause does NOT extend it: the period ends 3 calendar days (72 hours) after the start, whatever was paused, and paused time is not made up. The "active days" wording is replaced. The rest of L79 is unchanged. {#rev-l79-refined}

## Revision L80 (2026-11-14, `bsd-spec-t3c` L79 confirm-lite 0B/1S/4M; lead ruling L80) {#rev-l80}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| S1 the start still required the user's go | title, Depends-on, #why, R1 and AC-1: the orchestrator starts the experiment when plan-28's Depends-on holds and tells the user first (L78); AC-1 checks that the tell and the evidence precede the start commit; pause, end and G18 stay user-gated | header, [[#why]], [[#r1]], [[#ac-1]] |
| m1 the report could score before the paired series ends | R5 waits for the session period's end AND the paired series' completion (or recorded stop) | [[#r5]] |
| m3 the #rev-l79 table did not render; "Q11 assumed" | blank line added; "Q11 answered (a)" | [[#rev-l79]] |


## Revision L82 (2026-11-14, `bsd-spec-t3c` L80 confirm-lite MEH-only 0B/0S/2M; lead ruling L82) {#rev-l82}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| m1 #approval-row still listed "the go" | "every pause and the end" | [[#approval]] |
| m2 the end waited on a user-gated commit; sessions past 72 hours could be scored | R2's start commit writes `end = start + 72 h`; R4 is the check plus the user step; the scorer drops and counts sessions whose SessionStart is at or after `end` | [[#r2]], [[#r4]], [[#ac-4]], [[#files]] |

## Approval of the L79/L80/L82 amendment (2026-11-14, d9co) {#approval-l79-2026-11-14}

| decision | basis | status |
|---|---|---|
| The 3-calendar-day session period (L79, Q11 answered a), the orchestrator-run start under L78 (L80) and the end committed with the start (L82) are approved by the lead on the user's pattern (d9co) after the L80 confirm-lite MEH-only (0B/0S/2M), folded at `49a603c` per L82 with no further round | `workflow/bullshit/2026-11-14-0200-spec-t3c-r5-l80-d42c72b.md` (with the L79 confirm-lite `2026-11-14-0150-spec-t3c-r4-l79-7758d2a.md`, over `spec-wave-t3c` `be03148..d42c72b`) | status unchanged; Q14 (where the verdicts come from) may amend this plan again |

rel: derives-from -> [[bsd-spec-t3c-r5-l80-d42c72b]]

## Revision L83 (2026-11-14, the user, Q14: "drop the live part"; lead ruling L83) {#rev-l83}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite. L79's 3-day period and L82's `end`/`after_end`
are removed; they are kept above as history.

| change | where |
|---|---|
| the run is the paired series alone; the user's own sessions are never assigned to an arm | title, [[#why]], [[#r1]], [[#ac-4]] |
| the start (L78/L80) applies to the series. Nothing is committed or deployed to start it; R2 records the mount, the archive announcement and the deploy sha | [[#r1]], [[#r2]] |
| the series ends at its frozen minimum n, at the cap, or by the user; it is not time-boxed; scoring waits for that end | [[#r4]], [[#r5]], [[#ac-2]] |
| the pause is restated for the series (user-gated; treatment-module deploys only while paused) | [[#r3]] |
| AC-4 (the end commit, `after_end`) is replaced by "no live session was assigned to an arm"; the Files row and the done list drop the period commits | [[#ac-4]], [[#files]], [[#done]] |

## Revision L86 (2026-11-14, lead ruling L86 on the crossed 10.2 / 28.1 arms shapes) {#rev-l86}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite.

| change | where |
|---|---|
| AC-4 checks the live logs for 10.2's `handhold_cell` field (not `session_arm`) | [[#ac-4]] |


## Revision L87 (2026-11-14, `bsd-spec-t3c` L83 confirm-lite; lead ruling L87) {#rev-l87}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite.

| finding | disposition | where |
|---|---|---|
| m3 the start message to the user | R1 names that treatment-module deploys from items 8-11 need a user pause while the series runs | [[#r1]] |
