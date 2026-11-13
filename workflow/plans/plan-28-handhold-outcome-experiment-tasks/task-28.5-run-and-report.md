---
gmd: "0.1"
id: task-28.5-run-and-report
title: "Task 28.5: the user-gated run: start the period on the user's go, run both legs, read every band as frozen, report, and stop the goal for the user's charter decision"
tags: [task, plan-28, experiment, run, report, charter, user-gated]
metadata:
  node_type: task
  status: drafting
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 28.5: run and report {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Drafting (spec wave 2026-11-13, G17).
> Depends on: [[task-28.4-preregistration-freeze]] frozen and reviewed. **User-gated:** the
> start (L45). **Goal stop:** the charter decision (G18).

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-28.4-preregistration-freeze]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]
rel: related-to -> [[task-10.2-plan-10-injection-dedup]]
rel: reinforces -> [[feedback_errors_fail_loudly_on_the_console]]

## Why {#why}

The experiment randomises the user's own work sessions in two projects for at least 14 days.
That is a user step by the plan review's rule (L45), and its result is an input to a user
decision (G18), not a goal step. {#why-body}

## Requirements {#requirements}

1. **R1 The go.** The lead asks the user to start, citing the frozen pre-registration's sha,
   the cells, the stores, the minimum period, and what cell `B` feels like (no per-prompt push).
   The user's answer is recorded verbatim with its date. Without it, nothing below runs. {#r1}
2. **R2 Start.** One commit on `master` sets the plan-28 period's salt (from the frozen file)
   and its start, then a deploy per the project's deploy rules. `rmx install-hooks --check`
   stays clean (28.1 AC-6). The first SessionStart rows in each store show `arm_period`, and
   they are checked within one day. {#r2}
3. **R3 During the period.** {#r3}
   - A weekly count of sessions per cell per store and of suppressed rows, posted to the user.
   - Every deploy sha and date in the period is recorded. A deploy that touches a module the
     pause rule names pauses the period; the period extends by the paused days.
   - The paired runs (28.2) execute in the frozen shuffled order.
   - A defect that blocks work in any cell stops the period loudly: the user is told, the period
     record's `end` is set, nothing is read, and the stop is recorded.
4. **R4 End.** At the end rule, a commit sets `end` (if it was not already set) and deploys.
   After that, `arms.draw` returns the default for every session (checked on a new session in
   each store). {#r4}
5. **R5 Score and read.** 28.3's scorer runs over local copies (stores read-only, transcripts in
   place). Every outcome is computed, every band is read as frozen, and every deviation from the
   pre-registration is listed. 10.2 R7's nested bands are read and handed to 10.2's
   implementation summary. {#r5}
6. **R6 Report.** `workflow/measurements/handhold-experiment-<date>.md` (GMD) holds the counts,
   the readings and the CIs, the charter-decision inputs that are not outcomes, and the
   limits. Only counts, labels and hashes are committed. A ch-bsd round over it must come back
   CLEAN or MEH-only. {#r6}
7. **R7 The goal stops.** The report goes to the user as a charter decision with the readings
   and the inputs (G18). The T3 re-plan and the plan-24 re-plan (D-Q5) follow the user's
   decision, not this task. {#r7}
8. **R8 Cleanup.** If the charter decision keeps no arm, `arms.py` (10.2's), arm B's branch,
   `push_on` and the period records are deleted per the widened deferral row (28.1 R5), and the
   row is closed. If it keeps one, the decision amends the row. {#r8}

## Acceptance criteria {#acceptance}

1. **AC-1** The user's go is recorded verbatim with its date before the start commit, as the
   git order shows. {#ac-1}
2. **AC-2** The period's minimums are met, or the session leg's readings say report-only, as
   frozen. {#ac-2}
3. **AC-3** Every band in the frozen file has a reading in the report, and no reading uses a
   rule absent from the frozen file. {#ac-3}
4. **AC-4** After the end, a new session in each store draws the default, checked and recorded.
   {#ac-4}
5. **AC-5** The report passes its ch-bsd round, and the charter decision is put to the user.
   {#ac-5}

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/arms.py` | the period's salt, start and end (R2, R4); the deletion (R8) |
| `workflow/measurements/handhold-experiment-<date>.md` (new) | R6 |
| `workflow/deferral_registry.md` | the `arms.py` row closed or amended (R8) |

## Definition of done {#done}

- AC-1 to AC-5 met. Implementation summary at
  `workflow/implementation_summaries/task-28.5-run-and-report.md` (the start and end shas, the
  pause log, the readings).
- The start, end and cleanup commits are each made on branch `task-28.5-run-and-report` and
  merged `--no-ff` to `master`, then deployed.
